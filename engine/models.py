"""
Orbi Billing Engine — Pure domain models.
No ORM, no HTTP, no I/O. Just data.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class BillingModel(str, Enum):
    RECURRING = "recurring"
    METERED   = "metered"
    ONE_TIME  = "one_time"
    TIERED    = "tiered"


class TierMode(str, Enum):
    VOLUME    = "volume"
    GRADUATED = "graduated"


class Aggregation(str, Enum):
    SUM  = "sum"
    MAX  = "max"
    LAST = "last"


class InvoiceStatus(str, Enum):
    DRAFT      = "draft"
    FINALISED  = "finalised"
    SENT       = "sent"
    PAID       = "paid"
    VOID       = "void"


# ── Price config shapes ───────────────────────────────────────────────────

@dataclass(frozen=True)
class RecurringConfig:
    amount: int                        # smallest currency unit (e.g. cents)
    interval: str = "month"            # "month" | "year"
    interval_count: int = 1


@dataclass(frozen=True)
class MeteredConfig:
    unit_price: int                    # cents per unit
    aggregation: Aggregation = Aggregation.SUM


@dataclass(frozen=True)
class OneTimeConfig:
    amount: int                        # cents


@dataclass(frozen=True)
class Tier:
    up_to: Optional[int]               # None = infinity
    unit_price: int                    # cents per unit


@dataclass(frozen=True)
class TieredConfig:
    tiers: tuple[Tier, ...]
    tier_mode: TierMode = TierMode.GRADUATED


PriceConfig = RecurringConfig | MeteredConfig | OneTimeConfig | TieredConfig


# ── Domain entities ───────────────────────────────────────────────────────

@dataclass
class Product:
    id: UUID
    name: str
    billing_model: BillingModel
    price_config: PriceConfig
    currency: str = "USD"
    unit_label: str = "unit"


@dataclass
class Subscription:
    id: UUID
    customer_id: UUID
    product: Product
    quantity: Decimal = Decimal("1")
    start_date: date  = field(default_factory=date.today)
    end_date: Optional[date] = None
    trial_end_date: Optional[date] = None


@dataclass
class UsageRecord:
    id: UUID
    subscription_id: UUID
    quantity: Decimal
    recorded_at: datetime
    idempotency_key: str


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit_price: int                    # cents
    amount: int                        # cents
    product_id: Optional[UUID] = None
    subscription_id: Optional[UUID] = None


@dataclass
class Invoice:
    id: UUID
    invoice_number: str
    customer_id: UUID
    period_start: date
    period_end: date
    currency: str
    line_items: list[LineItem] = field(default_factory=list)
    status: InvoiceStatus = InvoiceStatus.DRAFT

    @property
    def subtotal(self) -> int:
        return sum(li.amount for li in self.line_items)

    @property
    def total(self) -> int:
        return self.subtotal   # tax / discounts: Phase 2
