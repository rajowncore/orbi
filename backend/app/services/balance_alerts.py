"""
Orbi — Balance Alert Service

Handles prepaid balance alerts in two ways:

1. CGRateS webhook (push) — CGRateS fires an HTTP call to Orbi when an
   ActionTrigger fires (e.g. ActionTrigger_0MB_Remaining). Orbi receives
   this at POST /api/v1/webhooks/cgrates and immediately notifies the customer.

2. Scheduled poll (pull) — a background job runs every N minutes, calls
   CGRateS GetAccount for all active prepaid subscribers, and sends alerts
   when balance drops below configured thresholds.

Notifications currently: in-app alert record + log.
Extend by adding email/SMS in _notify_customer().

CGRateS ActionTriggers set up during provisioning:
  ActionTrigger_BalanceExpired   — balance ExpiryTime reached
  ActionTrigger_500MB_Remaining  — data bundle below 500MB
  ActionTrigger_0MB_Remaining    — data bundle exhausted
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Customer, CreditType
from app.provisioning.models import ProvisioningWorkflow
from app.provisioning import WorkflowStatus

log = logging.getLogger(__name__)


# ── Alert thresholds (pence) ───────────────────────────────────────────────
LOW_BALANCE_THRESHOLD_PENCE  = 500   # £5.00
ZERO_BALANCE_THRESHOLD_PENCE = 0


# ── Alert types ────────────────────────────────────────────────────────────
class AlertType:
    LOW_BALANCE       = "low_balance"       # monetary balance below threshold
    ZERO_BALANCE      = "zero_balance"      # monetary balance at zero
    BUNDLE_LOW        = "bundle_low"        # data/voice/SMS bundle below 10%
    BUNDLE_EXHAUSTED  = "bundle_exhausted"  # data/voice/SMS bundle at zero
    BALANCE_EXPIRED   = "balance_expired"   # CGRateS ExpiryTime reached
    TOPUP_RECEIVED    = "topup_received"    # customer topped up


# ── In-memory alert dedup (prevents spam) ─────────────────────────────────
# In production replace with Redis SET with TTL
_sent_alerts: dict[str, datetime] = {}

def _already_sent(key: str, cooldown_hours: int = 4) -> bool:
    last = _sent_alerts.get(key)
    if not last:
        return False
    return (datetime.utcnow() - last).total_seconds() < cooldown_hours * 3600

def _mark_sent(key: str) -> None:
    _sent_alerts[key] = datetime.utcnow()


# ══════════════════════════════════════════════════════════════════════════
# MAIN ALERT FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

async def check_balance_and_alert(
    db: AsyncSession,
    customer_id: str,
    service_uuid: str,
) -> list[dict]:
    """
    Check a single prepaid customer's CGRateS balance and fire alerts
    if any threshold is breached.

    Returns list of alerts that were fired.
    """
    from app.engine import get_active_engine
    from app.engine.cgrates import CGRatesChargingEngine

    engine = get_active_engine()
    if not isinstance(engine, CGRatesChargingEngine):
        return []  # Not in CGRateS mode

    try:
        balance = await engine.get_account_balance(service_uuid)
    except Exception as e:
        log.error(f"Failed to fetch CGRateS balance for {service_uuid}: {e}")
        return []

    # Fetch customer for notification details
    r = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = r.scalar_one_or_none()
    if not customer or customer.credit_type != CreditType.PREPAID:
        return []

    fired = []

    # ── Monetary balance alerts ────────────────────────────────────────
    pence = balance.monetary_pence

    if pence <= ZERO_BALANCE_THRESHOLD_PENCE:
        key = f"zero_balance:{customer_id}"
        if not _already_sent(key):
            alert = await _fire_alert(db, customer, AlertType.ZERO_BALANCE, {
                "balance_pence":  pence,
                "balance_pounds": f"£{pence/100:.2f}",
                "service_uuid":   service_uuid,
                "message": "Your balance has run out. Top up to continue using services.",
            })
            fired.append(alert)
            _mark_sent(key)

    elif pence <= LOW_BALANCE_THRESHOLD_PENCE:
        key = f"low_balance:{customer_id}"
        if not _already_sent(key, cooldown_hours=12):
            alert = await _fire_alert(db, customer, AlertType.LOW_BALANCE, {
                "balance_pence":   pence,
                "balance_pounds":  f"£{pence/100:.2f}",
                "threshold_pounds": f"£{LOW_BALANCE_THRESHOLD_PENCE/100:.2f}",
                "service_uuid":    service_uuid,
                "message": f"Your balance is low (£{pence/100:.2f}). Top up to avoid service interruption.",
            })
            fired.append(alert)
            _mark_sent(key)

    # ── Bundle alerts ─────────────────────────────────────────────────
    bundles = [
        ("data",  balance.data_mb,    "data_mb",    "MB"),
        ("voice", balance.voice_mins, "voice_mins", "mins"),
        ("sms",   balance.sms_count,  "sms",        "SMS"),
    ]

    for name, remaining, field, unit in bundles:
        if remaining <= 0:
            key = f"bundle_exhausted:{customer_id}:{name}"
            if not _already_sent(key):
                alert = await _fire_alert(db, customer, AlertType.BUNDLE_EXHAUSTED, {
                    "bundle_type":  name,
                    "service_uuid": service_uuid,
                    "message": f"Your {name} bundle has run out. Further usage will be charged at out-of-bundle rates.",
                })
                fired.append(alert)
                _mark_sent(key)

    return fired


async def handle_cgrates_webhook(
    db: AsyncSession,
    payload: dict,
) -> dict:
    """
    Handle incoming CGRateS ActionTrigger webhook.

    CGRateS posts to /api/v1/webhooks/cgrates when a trigger fires.
    Expected payload:
      {
        "Account": "Mobile_SIM_abc123",
        "Tenant":  "cgrates.org",
        "Event":   "ActionTrigger_0MB_Remaining"  or  "ActionTrigger_BalanceExpired"
        "ThresholdValue": "0",
        "BalanceValue": "0.0"
      }
    """
    account    = payload.get("Account", "")
    event_type = payload.get("Event", "")
    tenant     = payload.get("Tenant", "")

    log.info(f"CGRateS webhook: account={account} event={event_type}")

    if not account:
        return {"status": "ignored", "reason": "no account in payload"}

    # Resolve customer from service_uuid
    customer_id, customer = await _resolve_customer_from_service_uuid(db, account)
    if not customer:
        log.warning(f"CGRateS webhook: no customer found for account {account}")
        return {"status": "ignored", "reason": f"no customer for account {account}"}

    # Map CGRateS trigger name → AlertType
    alert_map = {
        "ActionTrigger_BalanceExpired":  AlertType.BALANCE_EXPIRED,
        "ActionTrigger_0MB_Remaining":   AlertType.BUNDLE_EXHAUSTED,
        "ActionTrigger_500MB_Remaining": AlertType.BUNDLE_LOW,
    }
    alert_type = alert_map.get(event_type)
    if not alert_type:
        log.info(f"CGRateS webhook: unhandled event type {event_type}")
        return {"status": "ignored", "reason": f"unhandled event: {event_type}"}

    balance_val = payload.get("BalanceValue", "0")
    extra = {
        "service_uuid":   account,
        "cgrates_event":  event_type,
        "balance_value":  balance_val,
        "message": _alert_message(alert_type, balance_val),
    }

    key = f"webhook:{alert_type}:{customer_id}"
    if _already_sent(key, cooldown_hours=2):
        return {"status": "deduplicated", "customer_id": customer_id}

    alert = await _fire_alert(db, customer, alert_type, extra)
    _mark_sent(key)

    return {
        "status":      "ok",
        "alert_type":  alert_type,
        "customer_id": customer_id,
        "alert_id":    alert.get("id"),
    }


async def poll_all_prepaid_balances(db: AsyncSession) -> dict:
    """
    Scheduled job — check all active prepaid customers' CGRateS balances.
    Called by APScheduler or a background task on startup.
    Returns summary of alerts fired.
    """
    # Find all active provisioning workflows (gives us service_uuid → customer_id mapping)
    r = await db.execute(
        select(ProvisioningWorkflow).where(
            ProvisioningWorkflow.status == WorkflowStatus.COMPLETED,
        )
    )
    workflows = r.scalars().all()

    total_checked = 0
    total_alerts  = 0

    for wf in workflows:
        service_uuid = wf.context.get("service_uuid")
        customer_id  = wf.context.get("customer_id")
        if not service_uuid or not customer_id:
            continue

        alerts = await check_balance_and_alert(db, customer_id, service_uuid)
        total_checked += 1
        total_alerts  += len(alerts)

    return {
        "checked": total_checked,
        "alerts_fired": total_alerts,
        "polled_at": datetime.utcnow().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════

async def _fire_alert(
    db: AsyncSession,
    customer: Customer,
    alert_type: str,
    extra: dict,
) -> dict:
    """
    Create an alert record and send notifications.
    Currently: logs + stores in customer.extra.
    Extend here to add email/SMS.
    """
    alert = {
        "id":          str(uuid.uuid4()),
        "type":        alert_type,
        "customer_id": customer.id,
        "created_at":  datetime.utcnow().isoformat(),
        **extra,
    }

    log.warning(
        f"BALANCE ALERT [{alert_type}] customer={customer.name} "
        f"({customer.id}) — {extra.get('message','')}"
    )

    # Persist alert in customer.extra.alerts (append-only log)
    extra_data = customer.extra or {}
    alerts = extra_data.get("balance_alerts", [])
    alerts.append(alert)
    # Keep last 50 alerts per customer
    extra_data["balance_alerts"] = alerts[-50:]
    customer.extra = extra_data
    await db.flush()

    # ── Extend here: send email / SMS ─────────────────────────────────
    await _notify_customer(customer, alert)

    return alert


async def _notify_customer(customer: Customer, alert: dict) -> None:
    """
    Send the alert to the customer.
    Currently logs only — add email/SMS here.
    """
    log.info(
        f"[NOTIFY] {customer.email or customer.phone or customer.id}: "
        f"{alert.get('message','')}"
    )
    # TODO Phase 2: send email via SMTP
    # await send_email(
    #     to=customer.email,
    #     subject=f"Balance alert — {alert['type']}",
    #     template="balance_alert.html",
    #     context=alert,
    # )

    # TODO Phase 2: send SMS via Twilio/SMS gateway
    # await send_sms(
    #     to=customer.phone,
    #     message=alert.get("message", ""),
    # )


def _alert_message(alert_type: str, balance_val: str = "0") -> str:
    msgs = {
        AlertType.BALANCE_EXPIRED:   "Your balance has expired. Please top up to continue using services.",
        AlertType.BUNDLE_EXHAUSTED:  "Your data bundle has run out. Further usage will be charged at standard rates.",
        AlertType.BUNDLE_LOW:        f"Your data bundle is running low ({balance_val}MB remaining).",
        AlertType.ZERO_BALANCE:      "Your balance has reached zero. Please top up immediately.",
        AlertType.LOW_BALANCE:       f"Your balance is low (£{float(balance_val or 0)/100:.2f}). Top up to avoid interruption.",
    }
    return msgs.get(alert_type, "Account notification from your MVNO.")


async def _resolve_customer_from_service_uuid(
    db: AsyncSession,
    service_uuid: str,
) -> tuple[str | None, Customer | None]:
    """Find customer_id from service_uuid via provisioning workflow context."""
    r = await db.execute(
        select(ProvisioningWorkflow).where(
            ProvisioningWorkflow.status == WorkflowStatus.COMPLETED,
        )
    )
    for wf in r.scalars().all():
        if wf.context.get("service_uuid") == service_uuid:
            customer_id = wf.context.get("customer_id")
            if customer_id:
                cr = await db.execute(
                    select(Customer).where(Customer.id == customer_id)
                )
                customer = cr.scalar_one_or_none()
                return customer_id, customer
    return None, None
