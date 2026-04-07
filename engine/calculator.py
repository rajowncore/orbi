"""
Orbi Billing Engine — Calculation logic.

All functions are pure: given inputs → deterministic outputs.
No side effects, no I/O, no database.
"""
from __future__ import annotations
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence
from uuid import uuid4

from .models import (
    Aggregation, BillingModel, Invoice, InvoiceStatus, LineItem,
    MeteredConfig, OneTimeConfig, PriceConfig, Product, RecurringConfig,
    Subscription, Tier, TieredConfig, TierMode, UsageRecord,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _days_in_month(d: date) -> int:
    return monthrange(d.year, d.month)[1]


def _pro_rate(amount: int, period_start: date, period_end: date,
              sub_start: date) -> int:
    """
    Pro-rate `amount` when a subscription starts mid-period.
    Uses simple day-fraction: active_days / total_days_in_period.
    """
    total_days = (period_end - period_start).days + 1
    effective_start = max(sub_start, period_start)
    active_days = (period_end - effective_start).days + 1
    if active_days <= 0:
        return 0
    if active_days >= total_days:
        return amount
    ratio = Decimal(active_days) / Decimal(total_days)
    return int((Decimal(amount) * ratio).to_integral_value(ROUND_HALF_UP))


# ── Aggregation ───────────────────────────────────────────────────────────

def aggregate_usage(records: Sequence[UsageRecord],
                    method: Aggregation) -> Decimal:
    """Collapse usage records into a single quantity."""
    if not records:
        return Decimal("0")
    quantities = [r.quantity for r in records]
    if method == Aggregation.SUM:
        return sum(quantities, Decimal("0"))
    if method == Aggregation.MAX:
        return max(quantities)
    if method == Aggregation.LAST:
        latest = max(records, key=lambda r: r.recorded_at)
        return latest.quantity
    raise ValueError(f"Unknown aggregation method: {method}")


# ── Tier calculations ─────────────────────────────────────────────────────

def _calc_volume(quantity: Decimal, tiers: tuple[Tier, ...]) -> int:
    """All units priced at the single tier the total quantity falls into."""
    for tier in tiers:
        if tier.up_to is None or quantity <= tier.up_to:
            return int(
                (quantity * Decimal(tier.unit_price)).to_integral_value(ROUND_HALF_UP)
            )
    raise ValueError("Quantity exceeds all defined tiers — missing an open-ended tier.")


def _calc_graduated(quantity: Decimal, tiers: tuple[Tier, ...]) -> int:
    """Each tier's slice is priced at its own rate; totals are summed."""
    total = Decimal("0")
    remaining = quantity
    previous_limit = Decimal("0")

    for tier in tiers:
        if remaining <= 0:
            break
        if tier.up_to is None:
            units_in_tier = remaining
        else:
            tier_cap = Decimal(tier.up_to)
            units_in_tier = min(remaining, tier_cap - previous_limit)
            previous_limit = tier_cap
        total += units_in_tier * Decimal(tier.unit_price)
        remaining -= units_in_tier

    return int(total.to_integral_value(ROUND_HALF_UP))


# ── Per-model line item builders ──────────────────────────────────────────

def _line_item_recurring(sub: Subscription, cfg: RecurringConfig,
                         period_start: date, period_end: date) -> LineItem:
    base = cfg.amount * int(sub.quantity)
    amount = _pro_rate(base, period_start, period_end, sub.start_date)
    return LineItem(
        description=f"{sub.product.name} — {cfg.interval}ly subscription",
        quantity=sub.quantity,
        unit_price=cfg.amount,
        amount=amount,
        product_id=sub.product.id,
        subscription_id=sub.id,
    )


def _line_item_metered(sub: Subscription, cfg: MeteredConfig,
                       usage_records: Sequence[UsageRecord]) -> LineItem:
    qty = aggregate_usage(usage_records, cfg.aggregation)
    amount = int(
        (qty * Decimal(cfg.unit_price)).to_integral_value(ROUND_HALF_UP)
    )
    return LineItem(
        description=f"{sub.product.name} — {qty} {sub.product.unit_label}(s) used",
        quantity=qty,
        unit_price=cfg.unit_price,
        amount=amount,
        product_id=sub.product.id,
        subscription_id=sub.id,
    )


def _line_item_one_time(sub: Subscription, cfg: OneTimeConfig) -> LineItem:
    return LineItem(
        description=f"{sub.product.name} — one-time charge",
        quantity=Decimal("1"),
        unit_price=cfg.amount,
        amount=cfg.amount,
        product_id=sub.product.id,
        subscription_id=sub.id,
    )


def _line_item_tiered(sub: Subscription, cfg: TieredConfig,
                      usage_records: Sequence[UsageRecord]) -> LineItem:
    qty = aggregate_usage(usage_records, Aggregation.SUM)
    if cfg.tier_mode == TierMode.VOLUME:
        amount = _calc_volume(qty, cfg.tiers)
    else:
        amount = _calc_graduated(qty, cfg.tiers)
    return LineItem(
        description=f"{sub.product.name} — {qty} {sub.product.unit_label}(s) ({cfg.tier_mode.value} pricing)",
        quantity=qty,
        unit_price=0,   # n/a for tiered; amount is composite
        amount=amount,
        product_id=sub.product.id,
        subscription_id=sub.id,
    )


# ── Public API ────────────────────────────────────────────────────────────

def calculate_line_item(
    subscription: Subscription,
    period_start: date,
    period_end: date,
    usage_records: Sequence[UsageRecord] | None = None,
    is_first_invoice: bool = False,
) -> LineItem | None:
    """
    Produce a single LineItem for a subscription in a billing period.
    Returns None if this model produces no charge in this period
    (e.g. one-time charges after the first invoice).
    """
    cfg = subscription.product.price_config
    model = subscription.product.billing_model
    records = usage_records or []

    if model == BillingModel.RECURRING:
        assert isinstance(cfg, RecurringConfig)
        return _line_item_recurring(subscription, cfg, period_start, period_end)

    if model == BillingModel.METERED:
        assert isinstance(cfg, MeteredConfig)
        return _line_item_metered(subscription, cfg, records)

    if model == BillingModel.ONE_TIME:
        assert isinstance(cfg, OneTimeConfig)
        if not is_first_invoice:
            return None       # one-time: only on first invoice
        return _line_item_one_time(subscription, cfg)

    if model == BillingModel.TIERED:
        assert isinstance(cfg, TieredConfig)
        return _line_item_tiered(subscription, cfg, records)

    raise ValueError(f"Unsupported billing model: {model}")


def build_invoice(
    invoice_number: str,
    customer_id,
    period_start: date,
    period_end: date,
    currency: str,
    subscriptions: Sequence[Subscription],
    usage_by_subscription: dict | None = None,
    first_invoice_subs: set | None = None,
) -> Invoice:
    """
    Build a complete draft Invoice for a customer covering a billing period.

    Args:
        invoice_number:        Human-readable invoice ID (e.g. INV-2026-00042)
        customer_id:           Customer UUID
        period_start/end:      Inclusive billing window
        currency:              ISO 4217
        subscriptions:         Active subscriptions for this customer
        usage_by_subscription: {subscription_id: [UsageRecord, ...]}
        first_invoice_subs:    Set of subscription IDs on their first invoice
    """
    usage_map = usage_by_subscription or {}
    first_subs = first_invoice_subs or set()

    invoice = Invoice(
        id=uuid4(),
        invoice_number=invoice_number,
        customer_id=customer_id,
        period_start=period_start,
        period_end=period_end,
        currency=currency,
    )

    for sub in subscriptions:
        records = usage_map.get(sub.id, [])
        is_first = sub.id in first_subs
        line = calculate_line_item(
            subscription=sub,
            period_start=period_start,
            period_end=period_end,
            usage_records=records,
            is_first_invoice=is_first,
        )
        if line is not None:
            invoice.line_items.append(line)

    return invoice
