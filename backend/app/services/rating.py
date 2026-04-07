"""
Orbi — Rating Service

Rates pending UsageEvents against their subscription's bundle balances.
Produces ChargeRecords for any out-of-bundle usage.
Updates BundleBalance.allowance_used / allowance_remaining.

For prepaid customers: debits the BalanceLedger immediately.
For postpaid customers: accumulates ChargeRecords for billing run.
"""
from __future__ import annotations
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import (
    UsageEvent, UsageEventStatus,
    Subscription, SubscriptionStatus,
    Product, Customer, CreditType,
    BundleBalance, ServiceType,
    ChargeRecord, ChargeType,
    BalanceLedger, LedgerEntryType,
    InventoryItem,
)
from app.engine import get_active_engine, IChargingEngine


# ── Service type mapping ───────────────────────────────────────────────────

EVENT_TO_SERVICE = {
    "data":  ServiceType.DATA,
    "voice": ServiceType.VOICE,
    "sms":   ServiceType.SMS,
}

ALLOWANCE_FIELD = {
    ServiceType.DATA:  "data_mb",
    ServiceType.VOICE: "voice_mins",
    ServiceType.SMS:   "sms",
}


# ── Main rating function ───────────────────────────────────────────────────

async def rate_event(
    db: AsyncSession,
    event: UsageEvent,
    engine: IChargingEngine | None = None,
) -> ChargeRecord | None:
    """
    Rate a single usage event.
    Returns a ChargeRecord if a charge was generated (OOB usage),
    or None if fully covered by bundle.
    Updates the event status to RATED or FAILED.
    """
    if engine is None:
        engine = get_active_engine()

    try:
        # Resolve subscription from MSISDN if not already linked
        if not event.subscription_id:
            sub = await _resolve_subscription(db, event.msisdn)
            if not sub:
                event.status = UsageEventStatus.FAILED
                return None
            event.subscription_id = sub.id
            event.customer_id = sub.customer_id
        else:
            sub_r = await db.execute(select(Subscription).where(Subscription.id == event.subscription_id))
            sub = sub_r.scalar_one_or_none()
            if not sub:
                event.status = UsageEventStatus.FAILED
                return None

        # Load product and customer
        prod_r = await db.execute(select(Product).where(Product.id == sub.product_id))
        product = prod_r.scalar_one_or_none()
        cust_r  = await db.execute(select(Customer).where(Customer.id == sub.customer_id))
        customer = cust_r.scalar_one_or_none()

        if not product or not customer:
            event.status = UsageEventStatus.FAILED
            return None

        # Get bundle balance for this service type and current period
        service_type = EVENT_TO_SERVICE.get(event.event_type)
        bundle_remaining = 0
        bundle_balance = None

        if service_type and product.allowances:
            today = date.today()
            bb_r = await db.execute(
                select(BundleBalance).where(
                    BundleBalance.subscription_id == sub.id,
                    BundleBalance.service_type    == service_type,
                    BundleBalance.period_start    <= today,
                    BundleBalance.period_end      >= today,
                )
            )
            bundle_balance = bb_r.scalar_one_or_none()
            if bundle_balance:
                bundle_remaining = bundle_balance.allowance_remaining

        # Get OOB rate
        unit_price_oob = 0
        if product.out_of_bundle_rates and service_type:
            field = ALLOWANCE_FIELD.get(service_type, "")
            unit_price_oob = product.out_of_bundle_rates.get(field, 0) or 0

        # Rate the event — use async CGRateS path if available
        quantity = Decimal(str(event.quantity))
        from app.engine.cgrates import CGRatesChargingEngine
        if isinstance(engine, CGRatesChargingEngine):
            # CGRateS needs account identifier (service_uuid from provisioning context)
            # Fall back to MSISDN if service_uuid not available
            account = event.extra.get("service_uuid", event.msisdn) if event.extra else event.msisdn
            result = await engine.rate_usage_async(
                event_type=event.event_type,
                quantity=quantity,
                unit=event.unit,
                bundle_remaining=bundle_remaining,
                unit_price_oob=unit_price_oob,
                customer_credit_type=customer.credit_type.value,
                account=account,
                origin_id=event.event_id,
            )
        else:
            result = engine.rate_usage(
                event_type=event.event_type,
                quantity=quantity,
                unit=event.unit,
                bundle_remaining=bundle_remaining,
                unit_price_oob=unit_price_oob,
                customer_credit_type=customer.credit_type.value,
            )

        # Update bundle balance
        if bundle_balance and result.bundle_deducted > 0:
            bundle_balance.allowance_used      += result.bundle_deducted
            bundle_balance.allowance_remaining  = result.bundle_remaining
            bundle_balance.updated_at           = datetime.utcnow()

        # Mark event rated
        event.status = UsageEventStatus.RATED

        # Only create charge record if there's an actual charge
        if result.charged_amount <= 0:
            return None

        today = date.today()
        charge = ChargeRecord(
            id=str(uuid.uuid4()),
            customer_id=sub.customer_id,
            subscription_id=sub.id,
            usage_event_id=event.id,
            amount=result.charged_amount,
            currency=product.currency,
            charge_type=ChargeType.USAGE,
            description=result.description,
            period_start=today,
            period_end=today,
            billed=False,
            rated_at=datetime.utcnow(),
        )
        db.add(charge)

        # Prepaid: debit immediately
        if customer.credit_type == CreditType.PREPAID and result.charged_amount > 0:
            ledger = BalanceLedger(
                id=str(uuid.uuid4()),
                customer_id=customer.id,
                entry_type=LedgerEntryType.CHARGE,
                amount=-result.charged_amount,
                reference_id=event.id,
                description=f"Usage charge: {result.description}",
            )
            db.add(ledger)

        return charge

    except Exception as e:
        event.status = UsageEventStatus.FAILED
        raise


async def rate_pending_events(db: AsyncSession, limit: int = 500) -> dict:
    """Rate all pending usage events. Called by billing run or background task."""
    engine = get_active_engine()
    r = await db.execute(
        select(UsageEvent)
        .where(UsageEvent.status == UsageEventStatus.PENDING)
        .limit(limit)
    )
    events = r.scalars().all()

    rated = 0
    charged = 0
    failed = 0
    total_amount = 0

    for event in events:
        try:
            charge = await rate_event(db, event, engine)
            rated += 1
            if charge:
                charged += 1
                total_amount += charge.amount
        except Exception:
            failed += 1

    await db.flush()
    return {
        "events_processed": rated,
        "charges_generated": charged,
        "events_failed": failed,
        "total_charged_pence": total_amount,
    }


async def _resolve_subscription(db: AsyncSession, msisdn: str) -> Subscription | None:
    """Find active subscription for a given MSISDN via inventory lookup."""
    # Find inventory item by value
    inv_r = await db.execute(
        select(InventoryItem).where(InventoryItem.value == msisdn)
    )
    inv = inv_r.scalar_one_or_none()
    if not inv or not inv.assigned_to_order_id:
        return None

    # Find active subscription via order
    sub_r = await db.execute(
        select(Subscription).where(
            Subscription.order_id == inv.assigned_to_order_id,
            Subscription.status   == SubscriptionStatus.ACTIVE,
        )
    )
    return sub_r.scalar_one_or_none()
