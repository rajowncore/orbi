"""
Orbi Billing Engine — Test Suite

Covers all four billing models, edge cases, and the full invoice builder.
Run with:  cd orbi && python -m pytest tests/ -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from engine import (
    build_invoice, calculate_line_item, aggregate_usage,
    BillingModel, TierMode, Aggregation,
    RecurringConfig, MeteredConfig, OneTimeConfig, TieredConfig, Tier,
    Product, Subscription, UsageRecord,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

def make_sub(product: Product, quantity=Decimal("1"),
             start_date=date(2026, 1, 1)) -> Subscription:
    return Subscription(
        id=uuid4(), customer_id=uuid4(), product=product,
        quantity=quantity, start_date=start_date,
    )

def make_usage(sub: Subscription, qty: Decimal,
               when: datetime | None = None) -> UsageRecord:
    return UsageRecord(
        id=uuid4(), subscription_id=sub.id, quantity=qty,
        recorded_at=when or datetime(2026, 1, 15, tzinfo=timezone.utc),
        idempotency_key=str(uuid4()),
    )

JAN_START = date(2026, 1, 1)
JAN_END   = date(2026, 1, 31)


# ══════════════════════════════════════════════════════════════════════════
# 1. RECURRING BILLING
# ══════════════════════════════════════════════════════════════════════════

class TestRecurring:

    def test_full_month_single_seat(self):
        product = Product(uuid4(), "Pro Plan", BillingModel.RECURRING,
                          RecurringConfig(amount=9900))
        sub = make_sub(product)
        line = calculate_line_item(sub, JAN_START, JAN_END)
        assert line.amount == 9900
        assert line.quantity == Decimal("1")

    def test_full_month_multi_seat(self):
        product = Product(uuid4(), "Team Plan", BillingModel.RECURRING,
                          RecurringConfig(amount=5000))
        sub = make_sub(product, quantity=Decimal("5"))
        line = calculate_line_item(sub, JAN_START, JAN_END)
        assert line.amount == 25000     # 5 × $50.00

    def test_pro_rate_mid_month_start(self):
        # Subscription starts Jan 16 → 16 active days out of 31
        product = Product(uuid4(), "Starter", BillingModel.RECURRING,
                          RecurringConfig(amount=3100))
        sub = make_sub(product, start_date=date(2026, 1, 16))
        line = calculate_line_item(sub, JAN_START, JAN_END)
        # active_days=16, total=31 → 3100 * 16/31 = 1600
        assert line.amount == 1600

    def test_pro_rate_first_day(self):
        """Start on period start → full charge."""
        product = Product(uuid4(), "Plan", BillingModel.RECURRING,
                          RecurringConfig(amount=1000))
        sub = make_sub(product, start_date=JAN_START)
        line = calculate_line_item(sub, JAN_START, JAN_END)
        assert line.amount == 1000

    def test_pro_rate_last_day_only(self):
        """Subscription starts on last day of period → 1/31 of charge."""
        product = Product(uuid4(), "Plan", BillingModel.RECURRING,
                          RecurringConfig(amount=3100))
        sub = make_sub(product, start_date=JAN_END)
        line = calculate_line_item(sub, JAN_START, JAN_END)
        assert line.amount == 100   # 3100 * 1/31 = 100

    def test_description_includes_product_name(self):
        product = Product(uuid4(), "Enterprise Plan", BillingModel.RECURRING,
                          RecurringConfig(amount=49900))
        sub = make_sub(product)
        line = calculate_line_item(sub, JAN_START, JAN_END)
        assert "Enterprise Plan" in line.description


# ══════════════════════════════════════════════════════════════════════════
# 2. METERED (USAGE-BASED) BILLING
# ══════════════════════════════════════════════════════════════════════════

class TestMetered:

    def test_basic_sum_aggregation(self):
        product = Product(uuid4(), "API Calls", BillingModel.METERED,
                          MeteredConfig(unit_price=2))   # $0.02 per call
        sub = make_sub(product)
        records = [make_usage(sub, Decimal("100")), make_usage(sub, Decimal("200"))]
        line = calculate_line_item(sub, JAN_START, JAN_END, usage_records=records)
        assert line.quantity == Decimal("300")
        assert line.amount == 600               # 300 × $0.02

    def test_max_aggregation(self):
        product = Product(uuid4(), "Peak Bandwidth", BillingModel.METERED,
                          MeteredConfig(unit_price=100, aggregation=Aggregation.MAX))
        sub = make_sub(product)
        records = [
            make_usage(sub, Decimal("50")),
            make_usage(sub, Decimal("150")),
            make_usage(sub, Decimal("80")),
        ]
        line = calculate_line_item(sub, JAN_START, JAN_END, usage_records=records)
        assert line.quantity == Decimal("150")
        assert line.amount == 15000

    def test_last_aggregation(self):
        product = Product(uuid4(), "Storage GB", BillingModel.METERED,
                          MeteredConfig(unit_price=25, aggregation=Aggregation.LAST))
        sub = make_sub(product)
        t1 = datetime(2026, 1, 10, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 20, tzinfo=timezone.utc)
        t3 = datetime(2026, 1, 5,  tzinfo=timezone.utc)
        records = [
            make_usage(sub, Decimal("80"), t1),
            make_usage(sub, Decimal("120"), t2),   # latest
            make_usage(sub, Decimal("60"), t3),
        ]
        line = calculate_line_item(sub, JAN_START, JAN_END, usage_records=records)
        assert line.quantity == Decimal("120")     # last (by time) reading
        assert line.amount == 3000

    def test_zero_usage(self):
        product = Product(uuid4(), "API Calls", BillingModel.METERED,
                          MeteredConfig(unit_price=2))
        sub = make_sub(product)
        line = calculate_line_item(sub, JAN_START, JAN_END, usage_records=[])
        assert line.amount == 0
        assert line.quantity == Decimal("0")

    def test_fractional_units(self):
        """Usage quantities can be fractional (e.g. GB with decimals)."""
        product = Product(uuid4(), "Storage", BillingModel.METERED,
                          MeteredConfig(unit_price=10))  # $0.10/GB
        sub = make_sub(product)
        records = [make_usage(sub, Decimal("1.5")), make_usage(sub, Decimal("2.7"))]
        line = calculate_line_item(sub, JAN_START, JAN_END, usage_records=records)
        assert line.quantity == Decimal("4.2")
        assert line.amount == 42    # 4.2 × $0.10 = $0.42


# ══════════════════════════════════════════════════════════════════════════
# 3. ONE-TIME CHARGES
# ══════════════════════════════════════════════════════════════════════════

class TestOneTime:

    def test_first_invoice_generates_charge(self):
        product = Product(uuid4(), "Setup Fee", BillingModel.ONE_TIME,
                          OneTimeConfig(amount=19900))
        sub = make_sub(product)
        line = calculate_line_item(sub, JAN_START, JAN_END,
                                   is_first_invoice=True)
        assert line is not None
        assert line.amount == 19900

    def test_subsequent_invoice_returns_none(self):
        product = Product(uuid4(), "Setup Fee", BillingModel.ONE_TIME,
                          OneTimeConfig(amount=19900))
        sub = make_sub(product)
        line = calculate_line_item(sub, JAN_START, JAN_END,
                                   is_first_invoice=False)
        assert line is None

    def test_default_is_not_first(self):
        """Default is_first_invoice=False → no charge."""
        product = Product(uuid4(), "Setup Fee", BillingModel.ONE_TIME,
                          OneTimeConfig(amount=5000))
        sub = make_sub(product)
        line = calculate_line_item(sub, JAN_START, JAN_END)
        assert line is None


# ══════════════════════════════════════════════════════════════════════════
# 4. TIERED PRICING
# ══════════════════════════════════════════════════════════════════════════

STANDARD_TIERS = (
    Tier(up_to=100,  unit_price=10),   # $0.10 per unit, first 100
    Tier(up_to=500,  unit_price=7),    # $0.07 per unit, 101–500
    Tier(up_to=None, unit_price=5),    # $0.05 per unit, 500+
)

class TestTieredGraduated:

    def _make_sub(self):
        product = Product(uuid4(), "Msgs", BillingModel.TIERED,
                          TieredConfig(tiers=STANDARD_TIERS, tier_mode=TierMode.GRADUATED))
        return make_sub(product)

    def test_within_first_tier(self):
        sub = self._make_sub()
        line = calculate_line_item(sub, JAN_START, JAN_END,
                                   usage_records=[make_usage(sub, Decimal("50"))])
        # 50 × $0.10 = $0.50 → 50 cents
        assert line.amount == 500

    def test_spans_two_tiers(self):
        sub = self._make_sub()
        line = calculate_line_item(sub, JAN_START, JAN_END,
                                   usage_records=[make_usage(sub, Decimal("200"))])
        # 100 × 10 + 100 × 7 = 1000 + 700 = 1700
        assert line.amount == 1700

    def test_spans_all_three_tiers(self):
        sub = self._make_sub()
        line = calculate_line_item(sub, JAN_START, JAN_END,
                                   usage_records=[make_usage(sub, Decimal("600"))])
        # 100×10 + 400×7 + 100×5 = 1000 + 2800 + 500 = 4300
        assert line.amount == 4300

    def test_exactly_at_tier_boundary(self):
        sub = self._make_sub()
        line = calculate_line_item(sub, JAN_START, JAN_END,
                                   usage_records=[make_usage(sub, Decimal("100"))])
        # Exactly 100 → all in first tier: 100 × 10 = 1000
        assert line.amount == 1000


class TestTieredVolume:

    def _make_sub(self):
        product = Product(uuid4(), "Msgs", BillingModel.TIERED,
                          TieredConfig(tiers=STANDARD_TIERS, tier_mode=TierMode.VOLUME))
        return make_sub(product)

    def test_within_first_tier(self):
        sub = self._make_sub()
        line = calculate_line_item(sub, JAN_START, JAN_END,
                                   usage_records=[make_usage(sub, Decimal("50"))])
        # All 50 units at $0.10 = 500
        assert line.amount == 500

    def test_falls_into_second_tier(self):
        sub = self._make_sub()
        line = calculate_line_item(sub, JAN_START, JAN_END,
                                   usage_records=[make_usage(sub, Decimal("200"))])
        # 200 units, falls in tier 2 ($0.07) → all 200 × 7 = 1400
        assert line.amount == 1400

    def test_falls_into_third_tier(self):
        sub = self._make_sub()
        line = calculate_line_item(sub, JAN_START, JAN_END,
                                   usage_records=[make_usage(sub, Decimal("600"))])
        # 600 units, falls in tier 3 ($0.05) → all 600 × 5 = 3000
        assert line.amount == 3000

    def test_volume_cheaper_than_graduated_at_high_volume(self):
        """Volume pricing should be ≤ graduated at high quantities."""
        sub_vol  = self._make_sub()
        prod_g   = Product(uuid4(), "Msgs", BillingModel.TIERED,
                           TieredConfig(tiers=STANDARD_TIERS, tier_mode=TierMode.GRADUATED))
        sub_grad = make_sub(prod_g)
        records_vol  = [make_usage(sub_vol,  Decimal("600"))]
        records_grad = [make_usage(sub_grad, Decimal("600"))]
        line_vol  = calculate_line_item(sub_vol,  JAN_START, JAN_END, usage_records=records_vol)
        line_grad = calculate_line_item(sub_grad, JAN_START, JAN_END, usage_records=records_grad)
        assert line_vol.amount <= line_grad.amount


# ══════════════════════════════════════════════════════════════════════════
# 5. AGGREGATE USAGE
# ══════════════════════════════════════════════════════════════════════════

class TestAggregateUsage:

    def test_empty_records_returns_zero(self):
        assert aggregate_usage([], Aggregation.SUM) == Decimal("0")

    def test_sum(self):
        sub_id = uuid4()
        records = [
            UsageRecord(uuid4(), sub_id, Decimal("10"), datetime(2026,1,1,tzinfo=timezone.utc), "k1"),
            UsageRecord(uuid4(), sub_id, Decimal("20"), datetime(2026,1,2,tzinfo=timezone.utc), "k2"),
        ]
        assert aggregate_usage(records, Aggregation.SUM) == Decimal("30")

    def test_max(self):
        sub_id = uuid4()
        records = [
            UsageRecord(uuid4(), sub_id, Decimal("5"),  datetime(2026,1,1,tzinfo=timezone.utc), "k1"),
            UsageRecord(uuid4(), sub_id, Decimal("99"), datetime(2026,1,2,tzinfo=timezone.utc), "k2"),
            UsageRecord(uuid4(), sub_id, Decimal("50"), datetime(2026,1,3,tzinfo=timezone.utc), "k3"),
        ]
        assert aggregate_usage(records, Aggregation.MAX) == Decimal("99")


# ══════════════════════════════════════════════════════════════════════════
# 6. FULL INVOICE BUILDER
# ══════════════════════════════════════════════════════════════════════════

class TestBuildInvoice:

    def test_invoice_with_mixed_billing_models(self):
        customer_id = uuid4()
        recurring_product = Product(uuid4(), "Pro Plan", BillingModel.RECURRING,
                                    RecurringConfig(amount=9900))
        metered_product   = Product(uuid4(), "API Calls", BillingModel.METERED,
                                    MeteredConfig(unit_price=2))
        setup_product     = Product(uuid4(), "Setup Fee", BillingModel.ONE_TIME,
                                    OneTimeConfig(amount=5000))

        sub_r = make_sub(recurring_product)
        sub_m = make_sub(metered_product)
        sub_o = make_sub(setup_product)

        usage = {sub_m.id: [make_usage(sub_m, Decimal("500"))]}

        invoice = build_invoice(
            invoice_number="INV-2026-00001",
            customer_id=customer_id,
            period_start=JAN_START,
            period_end=JAN_END,
            currency="USD",
            subscriptions=[sub_r, sub_m, sub_o],
            usage_by_subscription=usage,
            first_invoice_subs={sub_o.id},
        )

        assert invoice.invoice_number == "INV-2026-00001"
        assert len(invoice.line_items) == 3
        # Recurring: 9900
        # Metered: 500 × 2 = 1000
        # One-time: 5000
        assert invoice.subtotal == 15900
        assert invoice.total == 15900

    def test_one_time_excluded_on_second_invoice(self):
        customer_id = uuid4()
        setup = Product(uuid4(), "Setup Fee", BillingModel.ONE_TIME,
                        OneTimeConfig(amount=5000))
        sub = make_sub(setup)

        invoice = build_invoice(
            invoice_number="INV-2026-00002",
            customer_id=customer_id,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            currency="USD",
            subscriptions=[sub],
            first_invoice_subs=set(),   # NOT in first invoice set
        )
        assert len(invoice.line_items) == 0
        assert invoice.subtotal == 0

    def test_invoice_status_defaults_to_draft(self):
        customer_id = uuid4()
        product = Product(uuid4(), "Plan", BillingModel.RECURRING,
                          RecurringConfig(amount=1000))
        sub = make_sub(product)
        invoice = build_invoice("INV-001", customer_id, JAN_START, JAN_END,
                                "USD", [sub])
        from engine.models import InvoiceStatus
        assert invoice.status == InvoiceStatus.DRAFT

    def test_empty_subscriptions_produces_zero_invoice(self):
        invoice = build_invoice("INV-000", uuid4(), JAN_START, JAN_END,
                                "EUR", [])
        assert invoice.subtotal == 0
        assert invoice.line_items == []
