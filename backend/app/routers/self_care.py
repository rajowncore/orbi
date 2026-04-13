"""
Orbi — Self-Care API

Public-facing endpoints for prepaid customers to:
  - Check real-time balance (from CGRateS)
  - View usage summary for the current period
  - Record a topup
  - View their alert history
  - Receive CGRateS webhook notifications

These endpoints are designed to be consumed by a customer self-care portal
or a mobile app. They return JSON only — no auth in this version (add
a customer JWT or API key for production use).

Also includes the CGRateS webhook receiver endpoint.
"""
from __future__ import annotations
from datetime import datetime, date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import (
    Customer, CreditType, BalanceLedger,
    UsageEvent, Subscription, SubscriptionStatus,
)
from app.config import settings

router = APIRouter(prefix="/self-care", tags=["Self-care"])


# ══════════════════════════════════════════════════════════════════════════
# BALANCE — real-time from CGRateS + Orbi ledger
# ══════════════════════════════════════════════════════════════════════════

@router.get("/customers/{customer_id}/balance")
async def get_balance(customer_id: str, db: AsyncSession = Depends(get_db)):
    """
    Real-time balance for a prepaid customer.

    Returns:
      - monetary_pence  — CGRateS account balance (authoritative for prepaid)
      - ledger_pence    — Orbi's ledger balance (may lag CGRateS slightly)
      - data_mb         — remaining data bundle
      - voice_mins      — remaining voice bundle
      - sms_count       — remaining SMS bundle
      - alerts          — any unread balance alerts
    """
    customer = await _get_prepaid_customer(db, customer_id)

    # CGRateS real-time balance
    cgrates_balance = None
    service_uuid    = await _get_service_uuid(db, customer_id)

    if service_uuid and settings.OCS_MODE == "cgrates":
        from app.engine import get_active_engine
        from app.engine.cgrates import CGRatesChargingEngine
        engine = get_active_engine()
        if isinstance(engine, CGRatesChargingEngine):
            try:
                cgrates_balance = await engine.get_account_balance(service_uuid)
            except Exception:
                pass  # fall back to ledger only

    # Orbi ledger balance (fallback / cross-check)
    ledger_r = await db.execute(
        select(func.sum(BalanceLedger.amount))
        .where(BalanceLedger.customer_id == customer_id)
    )
    ledger_pence = int(ledger_r.scalar() or 0)

    # Recent alerts from customer.extra
    extra  = customer.extra or {}
    alerts = extra.get("balance_alerts", [])
    # Return only alerts from last 7 days
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
    recent_alerts = [
        a for a in alerts
        if a.get("created_at", "") >= cutoff
    ]

    result = {
        "customer_id":   customer_id,
        "customer_name": customer.name,
        "credit_type":   customer.credit_type.value,
        "currency":      customer.currency,
        "service_uuid":  service_uuid,

        # Balances
        "ledger_pence":  ledger_pence,
        "ledger_pounds": f"£{ledger_pence/100:.2f}",

        # CGRateS real-time (None if not in cgrates mode or unreachable)
        "cgrates_balance": {
            "monetary_pence":  cgrates_balance.monetary_pence,
            "monetary_pounds": f"£{cgrates_balance.monetary_pence/100:.2f}",
            "data_mb":         cgrates_balance.data_mb,
            "voice_mins":      cgrates_balance.voice_mins,
            "sms_count":       cgrates_balance.sms_count,
            "disabled":        cgrates_balance.disabled,
        } if cgrates_balance else None,

        # Alerts
        "recent_alerts":   recent_alerts,
        "unread_alerts":   len(recent_alerts),

        # Status
        "ocs_mode": settings.OCS_MODE,
        "retrieved_at": datetime.utcnow().isoformat(),
    }

    # Trigger background balance check (non-blocking)
    if service_uuid:
        from app.services.balance_alerts import check_balance_and_alert
        from app.database import AsyncSessionLocal
        import asyncio

        async def _bg_check():
            async with AsyncSessionLocal() as bg_db:
                await check_balance_and_alert(bg_db, customer_id, service_uuid)
                await bg_db.commit()

        asyncio.create_task(_bg_check())

    return result


# ══════════════════════════════════════════════════════════════════════════
# USAGE SUMMARY — current period breakdown
# ══════════════════════════════════════════════════════════════════════════

@router.get("/customers/{customer_id}/usage-summary")
async def get_usage_summary(
    customer_id: str,
    period_start: str | None = None,  # ISO date, defaults to start of current month
    period_end:   str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Usage summary for the current billing period.

    In CGRateS mode, pulls rated CDRs from CGRateS.
    In orbi-native mode, aggregates UsageEvent records.

    Returns per-service totals with cost breakdown.
    """
    await _get_prepaid_customer(db, customer_id)  # validates customer exists

    today = date.today()
    start = date.fromisoformat(period_start) if period_start else date(today.year, today.month, 1)
    end   = date.fromisoformat(period_end)   if period_end   else today

    service_uuid = await _get_service_uuid(db, customer_id)

    # ── CGRateS mode: pull rated CDRs ────────────────────────────────
    if settings.OCS_MODE == "cgrates" and service_uuid:
        from app.engine import get_active_engine
        from app.engine.cgrates import CGRatesChargingEngine
        engine = get_active_engine()
        if isinstance(engine, CGRatesChargingEngine):
            try:
                cdrs = await engine.get_cdrs_for_billing(
                    datetime.combine(start, datetime.min.time()),
                    datetime.combine(end,   datetime.max.time()),
                    accounts=[service_uuid],
                )
                return _summarise_cdrs(cdrs, customer_id, service_uuid, start, end)
            except Exception as e:
                # Fall through to Orbi-native if CGRateS unreachable
                pass

    # ── Orbi-native mode: aggregate UsageEvent records ───────────────
    sub_r = await db.execute(
        select(Subscription).where(
            Subscription.customer_id == customer_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
    )
    sub = sub_r.scalar_one_or_none()

    if not sub:
        return _empty_summary(customer_id, service_uuid, start, end)

    events_r = await db.execute(
        select(UsageEvent).where(
            UsageEvent.customer_id == customer_id,
            UsageEvent.event_timestamp >= datetime.combine(start, datetime.min.time()),
            UsageEvent.event_timestamp <= datetime.combine(end,   datetime.max.time()),
        )
    )
    events = events_r.scalars().all()

    # Aggregate by event type
    totals = {"data": 0.0, "voice": 0.0, "sms": 0.0}
    costs  = {"data": 0,   "voice": 0,   "sms": 0}

    for ev in events:
        t = ev.event_type
        if t in totals:
            totals[t] += float(ev.quantity)

    return {
        "customer_id":   customer_id,
        "service_uuid":  service_uuid,
        "period_start":  start.isoformat(),
        "period_end":    end.isoformat(),
        "source":        "orbi-native",
        "summary": {
            "data":  {"quantity": totals["data"],  "unit": "MB",  "cost_pence": costs["data"]},
            "voice": {"quantity": totals["voice"], "unit": "min", "cost_pence": costs["voice"]},
            "sms":   {"quantity": totals["sms"],   "unit": "msg", "cost_pence": costs["sms"]},
        },
        "event_count": len(events),
        "total_cost_pence": sum(costs.values()),
        "total_cost_pounds": f"£{sum(costs.values())/100:.2f}",
    }


# ══════════════════════════════════════════════════════════════════════════
# TOPUP — record payment + credit CGRateS
# ══════════════════════════════════════════════════════════════════════════

@router.post("/customers/{customer_id}/topup", status_code=201)
async def record_topup(
    customer_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a prepaid topup.

    Body:
      amount_pence  — amount to add (integer, pence)
      reference     — payment reference / voucher code
      method        — payment method (card, voucher, bank_transfer)

    Automatically credits CGRateS balance if OCS_MODE=cgrates.
    Fires a TOPUP_RECEIVED alert.
    """
    customer = await _get_prepaid_customer(db, customer_id)

    amount_pence = int(body.get("amount_pence", 0))
    if amount_pence <= 0:
        raise HTTPException(400, "amount_pence must be a positive integer")

    reference = body.get("reference", "")
    method    = body.get("method", "self_care")

    # Record in Orbi payment service
    from app.services.payment import create_payment
    from app.schemas import PaymentCreate

    payment_data = PaymentCreate(
        customer_id  = customer_id,
        amount       = amount_pence,
        currency     = customer.currency,
        method       = method,
        payment_date = date.today().isoformat(),
        reference    = reference,
        description  = f"Self-care topup — {reference}",
    )
    payment = await create_payment(db, payment_data)

    # Credit CGRateS if in cgrates mode
    cgrates_result = None
    service_uuid   = await _get_service_uuid(db, customer_id)

    if service_uuid and settings.OCS_MODE == "cgrates":
        from app.engine import get_active_engine
        from app.engine.cgrates import CGRatesChargingEngine
        engine = get_active_engine()
        if isinstance(engine, CGRatesChargingEngine):
            cgrates_result = await engine.topup_balance(
                account      = service_uuid,
                amount_pence = amount_pence,
                package_name = f"Topup {reference}",
            )

    # Fire topup alert (clears low-balance dedup so customer gets fresh alerts next time)
    from app.services.balance_alerts import AlertType, _fire_alert, _sent_alerts
    # Clear dedup keys so next check can alert fresh if balance drops again
    for key in [f"low_balance:{customer_id}", f"zero_balance:{customer_id}"]:
        _sent_alerts.pop(key, None)

    await _fire_alert(db, customer, AlertType.TOPUP_RECEIVED, {
        "amount_pence":  amount_pence,
        "amount_pounds": f"£{amount_pence/100:.2f}",
        "reference":     reference,
        "service_uuid":  service_uuid,
        "message": f"Topup of £{amount_pence/100:.2f} received successfully.",
    })

    return {
        "status":        "ok",
        "payment_id":    payment.id,
        "amount_pence":  amount_pence,
        "amount_pounds": f"£{amount_pence/100:.2f}",
        "reference":     reference,
        "cgrates_credited": cgrates_result.ok if cgrates_result else None,
        "service_uuid":  service_uuid,
    }


# ══════════════════════════════════════════════════════════════════════════
# ALERTS HISTORY
# ══════════════════════════════════════════════════════════════════════════

@router.get("/customers/{customer_id}/alerts")
async def get_alerts(
    customer_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Return balance alert history for a customer."""
    customer = await _get_prepaid_customer(db, customer_id)
    extra    = customer.extra or {}
    alerts   = extra.get("balance_alerts", [])
    return {
        "customer_id": customer_id,
        "alerts":      list(reversed(alerts))[:limit],
        "total":       len(alerts),
    }


# ══════════════════════════════════════════════════════════════════════════
# CGRATES WEBHOOK RECEIVER
# ══════════════════════════════════════════════════════════════════════════

@router.post("/webhooks/cgrates")
async def cgrates_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive ActionTrigger notifications from CGRateS.

    Configure in CGRateS action: type=*http_post url=http://orbi:8000/api/v1/self-care/webhooks/cgrates

    CGRateS posts form-encoded or JSON depending on version.
    We handle both.
    """
    content_type = request.headers.get("content-type", "")

    if "json" in content_type:
        payload = await request.json()
    else:
        # CGRateS older versions post form-encoded
        form = await request.form()
        payload = dict(form)

    from app.services.balance_alerts import handle_cgrates_webhook
    result = await handle_cgrates_webhook(db, payload)
    return result


# ══════════════════════════════════════════════════════════════════════════
# BALANCE POLL — manual trigger for testing / admin
# ══════════════════════════════════════════════════════════════════════════

@router.post("/admin/poll-balances")
async def poll_balances(db: AsyncSession = Depends(get_db)):
    """
    Manually trigger a balance poll across all active prepaid customers.
    In production this runs on a schedule (APScheduler).
    """
    from app.services.balance_alerts import poll_all_prepaid_balances
    result = await poll_all_prepaid_balances(db)
    return result


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

async def _get_prepaid_customer(db: AsyncSession, customer_id: str) -> Customer:
    r = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = r.scalar_one_or_none()
    if not customer:
        raise HTTPException(404, f"Customer {customer_id} not found")
    if customer.credit_type != CreditType.PREPAID:
        raise HTTPException(400, "This endpoint is for prepaid customers only")
    return customer


async def _get_service_uuid(db: AsyncSession, customer_id: str) -> str | None:
    """Get service_uuid from provisioning workflow context."""
    from app.provisioning.models import ProvisioningWorkflow
    from app.provisioning import WorkflowStatus
    r = await db.execute(
        select(ProvisioningWorkflow).where(
            ProvisioningWorkflow.status == WorkflowStatus.COMPLETED,
        ).order_by(ProvisioningWorkflow.created_at.desc())
    )
    for wf in r.scalars().all():
        if wf.context.get("customer_id") == customer_id:
            return wf.context.get("service_uuid")
    return None


def _summarise_cdrs(cdrs, customer_id, service_uuid, start, end) -> dict:
    """Summarise CGRateS CDRs into per-service totals."""
    totals = {"data": 0.0, "voice": 0.0, "sms": 0.0, "other": 0.0}
    costs  = {"data": 0,   "voice": 0,   "sms": 0,   "other": 0}

    for cdr in cdrs:
        t = cdr.event_type
        if t not in totals:
            t = "other"
        totals[t] += float(cdr.usage or 0)
        costs[t]  += cdr.cost_pence

    total_cost = sum(costs.values())

    return {
        "customer_id":   customer_id,
        "service_uuid":  service_uuid,
        "period_start":  start.isoformat(),
        "period_end":    end.isoformat(),
        "source":        "cgrates",
        "summary": {
            "data":  {"quantity": round(totals["data"] / 1048576, 2),  "unit": "MB",  "cost_pence": costs["data"]},
            "voice": {"quantity": round(totals["voice"] / 60e9, 2),    "unit": "min", "cost_pence": costs["voice"]},
            "sms":   {"quantity": round(totals["sms"], 0),             "unit": "msg", "cost_pence": costs["sms"]},
        },
        "cdr_count": len(cdrs),
        "total_cost_pence":  total_cost,
        "total_cost_pounds": f"£{total_cost/100:.2f}",
    }


def _empty_summary(customer_id, service_uuid, start, end) -> dict:
    return {
        "customer_id":   customer_id,
        "service_uuid":  service_uuid,
        "period_start":  start.isoformat(),
        "period_end":    end.isoformat(),
        "source":        "orbi-native",
        "summary": {
            "data":  {"quantity": 0, "unit": "MB",  "cost_pence": 0},
            "voice": {"quantity": 0, "unit": "min", "cost_pence": 0},
            "sms":   {"quantity": 0, "unit": "msg", "cost_pence": 0},
        },
        "cdr_count": 0,
        "total_cost_pence": 0,
        "total_cost_pounds": "£0.00",
    }
