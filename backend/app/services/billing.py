"""
Orbi — Billing Run Service

Generates invoices for all active subscriptions in a given period.

Flow:
  1. Find active subscriptions due for billing
  2. Rate any pending usage events first
  3. Generate recurring charge records for each subscription
  4. Aggregate all unbilled charge records → Invoice + LineItems
  5. Generate PDF
  6. Return run summary
"""
from __future__ import annotations
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from calendar import monthrange
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models import (
    Customer, CreditType,
    Product, BillingModel,
    Subscription, SubscriptionStatus,
    ChargeRecord, ChargeType,
    Invoice, InvoiceStatus, InvoiceLineItem,
    BalanceLedger, LedgerEntryType,
    BundleBalance, ServiceType,
)
from app.services.rating import rate_pending_events
from app.services.pdf import generate_invoice_pdf
from app.engine import get_active_engine

import logging

# This grabs the existing logger Uvicorn is already using
logger = logging.getLogger("uvicorn.error")

# ── helpers ───────────────────────────────────────────────────────────────

def _next_inv_number(seq: int) -> str:
    return f"INV-{datetime.utcnow().year}-{str(seq).zfill(5)}"


def _pro_rate(amount: int, period_start: date, period_end: date, sub_start: date) -> int:
    """Pro-rate a charge if subscription started mid-period."""
    total_days   = (period_end - period_start).days + 1
    effective    = max(sub_start, period_start)
    active_days  = (period_end - effective).days + 1
    if active_days <= 0:
        return 0
    if active_days >= total_days:
        return amount
    return int(
        (Decimal(amount) * Decimal(active_days) / Decimal(total_days))
        .to_integral_value(ROUND_HALF_UP)
    )


async def _next_invoice_number(db: AsyncSession) -> str:
    r = await db.execute(select(func.count()).select_from(Invoice))
    n = (r.scalar() or 0) + 1
    return _next_inv_number(n)


# ══════════════════════════════════════════════════════════════════════════
# MAIN BILLING RUN
# ══════════════════════════════════════════════════════════════════════════

async def run_billing(
    db: AsyncSession,
    period_start: date,
    period_end: date,
    customer_id: Optional[str] = None,
) -> dict:
    """
    Execute a billing run for the given period.
    Returns a summary of what was generated.
    """
    run_start = datetime.utcnow()

    # Step 1: Rate any pending usage events first
    rating_summary = await rate_pending_events(db)

    # Step 2a: If using CGRateS, pull rated CDRs and create charge records
    from app.config import settings
    if settings.OCS_MODE == "cgrates":
        cgrates_charges = await _import_cgrates_cdrs(
            db, period_start, period_end, customer_id
        )
        logger.info(f"Imported {cgrates_charges} CGRateS CDR charge records")

    # Step 2b: Find subscriptions due for billing
    q = select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE)
    if customer_id:
        q = q.where(Subscription.customer_id == customer_id)
    subs_r = await db.execute(q)
    subscriptions = subs_r.scalars().all()

    # Step 3: Generate recurring charge records
    recurring_generated = 0
    for sub in subscriptions:
        prod_r = await db.execute(select(Product).where(Product.id == sub.product_id))
        product = prod_r.scalar_one_or_none()
        if not product:
            continue

        # Skip non-recurring products in billing run (usage already rated above)
        if product.billing_model not in (BillingModel.RECURRING,):
            continue

        # Check if already charged this period
        existing_r = await db.execute(
            select(ChargeRecord).where(
                ChargeRecord.subscription_id == sub.id,
                ChargeRecord.charge_type     == ChargeType.RECURRING,
                ChargeRecord.period_start    == period_start,
            )
        )
        if existing_r.scalar_one_or_none():
            continue  # Already billed for this period

        amount = product.price_config.get("amount", 0)
        if amount <= 0:
            continue

        # Pro-rate if subscription started mid-period
        billed_amount = _pro_rate(amount, period_start, period_end, sub.start_date)
        if billed_amount <= 0:
            continue

        desc = f"{product.name}"
        if billed_amount < amount:
            desc += f" (pro-rated)"

        charge = ChargeRecord(
            id=str(uuid.uuid4()),
            customer_id=sub.customer_id,
            subscription_id=sub.id,
            amount=billed_amount,
            currency=product.currency,
            charge_type=ChargeType.RECURRING,
            description=desc,
            period_start=period_start,
            period_end=period_end,
            billed=False,
            rated_at=datetime.utcnow(),
        )
        db.add(charge)
        recurring_generated += 1

    await db.flush()

    # Step 4: Aggregate unbilled charges into invoices per customer
    invoices_created = []
    customers_billed = set()

    # Get all customers with unbilled charges in this period
    unbilled_r = await db.execute(
        select(ChargeRecord.customer_id)
        .where(
            ChargeRecord.billed == False,
            ChargeRecord.period_start >= period_start,
            ChargeRecord.period_end   <= period_end,
        )
        .distinct()
    )
    customer_ids = [row[0] for row in unbilled_r.fetchall()]
    if customer_id:
        customer_ids = [c for c in customer_ids if c == customer_id]

    for cid in customer_ids:
        inv = await _build_invoice(db, cid, period_start, period_end)
        if inv:
            invoices_created.append(inv)
            customers_billed.add(cid)

    await db.flush()

    # Step 5: Generate PDFs
    pdf_count = 0
    for inv in invoices_created:
        try:
            pdf_path = await generate_invoice_pdf(inv, db)
            if pdf_path:
                inv.pdf_url = pdf_path
                pdf_count += 1
        except Exception:
            pass  # PDF failure should not block billing

    await db.flush()

    run_duration = (datetime.utcnow() - run_start).total_seconds()

    return {
        "status": "completed",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "subscriptions_processed": len(subscriptions),
        "recurring_charges_generated": recurring_generated,
        "usage_events_rated": rating_summary["events_processed"],
        "invoices_created": len(invoices_created),
        "customers_billed": len(customers_billed),
        "pdfs_generated": pdf_count,
        "duration_seconds": round(run_duration, 2),
    }

async def _import_cgrates_cdrs(
    db: AsyncSession,
    period_start: date,
    period_end: date,
    customer_id: str | None = None,
) -> int:
    """
    Pull rated CDRs from CGRateS and create ChargeRecord rows in Orbi.
    Only runs when OCS_MODE=cgrates.

    CGRateS owns the CDR rating — we just import the results.
    Skips CDRs already imported (idempotent via CGRID dedup).
    """
    from datetime import datetime as dt
    from app.engine.cgrates import CGRatesChargingEngine
    from app.models import ChargeType, InventoryItem

    engine = get_active_engine()
    if not isinstance(engine, CGRatesChargingEngine):
        return 0

    period_start_dt = dt.combine(period_start, dt.min.time())
    period_end_dt   = dt.combine(period_end,   dt.max.time())

    # Get service_uuids for this customer if filtering
    accounts = None
    if customer_id:
        # Look up service_uuids from provisioning context
        from app.provisioning.models import ProvisioningWorkflow
        from app.provisioning import WorkflowStatus
        wf_r = await db.execute(
            select(ProvisioningWorkflow).where(
                ProvisioningWorkflow.status == WorkflowStatus.COMPLETED,
            )
        )
        wfs = wf_r.scalars().all()
        accounts = [
            wf.context.get("service_uuid")
            for wf in wfs
            if wf.context.get("customer_id") == customer_id
               and wf.context.get("service_uuid")
        ]
        if not accounts:
            return 0

    cdrs = await engine.get_cdrs_for_billing(period_start_dt, period_end_dt, accounts)

    imported = 0
    for cdr in cdrs:
        if cdr.cost <= 0:
            continue  # skip zero-cost CDRs (bundle usage, no charge)

        # Idempotency: skip if already imported
        existing_r = await db.execute(
            select(ChargeRecord).where(
                ChargeRecord.description.contains(cdr.cgrid[:16])
            )
        )
        if existing_r.scalar_one_or_none():
            continue

        # Resolve customer_id from service_uuid via provisioning context
        from app.provisioning.models import ProvisioningWorkflow
        from app.provisioning import WorkflowStatus
        wf_r = await db.execute(
            select(ProvisioningWorkflow).where(
                ProvisioningWorkflow.status == WorkflowStatus.COMPLETED,
                ProvisioningWorkflow.context["service_uuid"].as_string() == cdr.account,
            )
        )
        wf = wf_r.scalar_one_or_none()
        if not wf:
            log.warning(f"No provisioning workflow found for CGRateS account {cdr.account}")
            continue

        cust_id = wf.context.get("customer_id")
        sub_id  = wf.context.get("subscription_id")

        charge = ChargeRecord(
            id=str(uuid.uuid4()),
            customer_id=cust_id,
            subscription_id=sub_id,
            amount=cdr.cost_pence,
            currency="GBP",
            charge_type=ChargeType.USAGE,
            description=(
                f"{cdr.event_type.upper()} usage — "
                f"CGRateS CGRID:{cdr.cgrid[:16]}"
            ),
            period_start=period_start,
            period_end=period_end,
            billed=False,
            rated_at=datetime.utcnow(),
        )
        db.add(charge)
        imported += 1

    if imported:
        await db.flush()
    return imported


async def _build_invoice(
    db: AsyncSession,
    customer_id: str,
    period_start: date,
    period_end: date,
) -> Optional[Invoice]:
    """Build a single invoice for a customer from their unbilled charge records."""

    # Get all unbilled charges for this customer in this period
    charges_r = await db.execute(
        select(ChargeRecord).where(
            ChargeRecord.customer_id == customer_id,
            ChargeRecord.billed      == False,
            ChargeRecord.period_start >= period_start,
            ChargeRecord.period_end   <= period_end,
        ).order_by(ChargeRecord.rated_at)
    )
    charges = charges_r.scalars().all()

    if not charges:
        return None

    total = sum(c.amount for c in charges)
    if total <= 0:
        return None

    # Get customer currency
    cust_r = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = cust_r.scalar_one_or_none()
    currency = customer.currency if customer else "GBP"

    # Create invoice
    inv_number = await _next_invoice_number(db)
    invoice = Invoice(
        id=str(uuid.uuid4()),
        invoice_number=inv_number,
        customer_id=customer_id,
        period_start=period_start,
        period_end=period_end,
        status=InvoiceStatus.DRAFT,
        subtotal=total,
        total=total,
        currency=currency,
        due_date=period_end + timedelta(days=14),
        created_at=datetime.utcnow(),
    )
    db.add(invoice)
    await db.flush()

    # Create line items and mark charges as billed
    for charge in charges:
        li = InvoiceLineItem(
            id=str(uuid.uuid4()),
            invoice_id=invoice.id,
            charge_record_id=charge.id,
            description=charge.description,
            quantity="1",
            unit_price=charge.amount,
            amount=charge.amount,
        )
        db.add(li)
        charge.billed   = True
        charge.invoice_id = invoice.id

    # For postpaid: add ledger debit entry
    if customer and customer.credit_type == CreditType.POSTPAID:
        ledger = BalanceLedger(
            id=str(uuid.uuid4()),
            customer_id=customer_id,
            entry_type=LedgerEntryType.CHARGE,
            amount=-total,
            reference_id=invoice.id,
            description=f"Invoice {inv_number} — {period_start.strftime('%b %Y')}",
        )
        db.add(ledger)

    return invoice


# ── Bundle renewal ─────────────────────────────────────────────────────────

async def renew_bundles(db: AsyncSession, period_start: date) -> int:
    """
    Create new BundleBalance rows for the new period.
    Called at start of each billing cycle.
    """
    from calendar import monthrange
    year, month = period_start.year, period_start.month
    last_day = monthrange(year, month)[1]
    period_end = date(year, month, last_day)

    subs_r = await db.execute(
        select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE)
    )
    subscriptions = subs_r.scalars().all()

    renewed = 0
    for sub in subscriptions:
        prod_r = await db.execute(select(Product).where(Product.id == sub.product_id))
        product = prod_r.scalar_one_or_none()
        if not product or not product.allowances:
            continue

        svc_map = {
            "data_mb":    ServiceType.DATA,
            "voice_mins": ServiceType.VOICE,
            "sms":        ServiceType.SMS,
        }
        for field, svc in svc_map.items():
            total = product.allowances.get(field)
            if not total:
                continue

            existing_r = await db.execute(
                select(BundleBalance).where(
                    BundleBalance.subscription_id == sub.id,
                    BundleBalance.period_start    == period_start,
                    BundleBalance.service_type    == svc,
                )
            )
            if existing_r.scalar_one_or_none():
                continue

            bb = BundleBalance(
                id=str(uuid.uuid4()),
                subscription_id=sub.id,
                period_start=period_start,
                period_end=period_end,
                service_type=svc,
                allowance_total=total,
                allowance_used=0,
                allowance_remaining=total,
            )
            db.add(bb)
            renewed += 1

    await db.flush()
    return renewed
