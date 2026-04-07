"""
Orbi Billing — SQLAlchemy ORM models.

Design rules:
- All PKs are UUIDs (server-side default via uuid4)
- All money stored as Integer (cents) — no Float, no Numeric
- All timestamps in UTC
- BalanceLedger is append-only — never update/delete rows
- Enums defined as Python Enum classes for type safety
"""
from __future__ import annotations

import uuid
from datetime import datetime, date
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, String, Text,
    Enum, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── Utility ───────────────────────────────────────────────────────────────

def new_uuid() -> str:
    return str(uuid.uuid4())

def now_utc() -> datetime:
    return datetime.utcnow()


# ── Enums ─────────────────────────────────────────────────────────────────

class CreditType(str, PyEnum):
    POSTPAID = "postpaid"
    PREPAID  = "prepaid"


class CustomerStatus(str, PyEnum):
    ACTIVE    = "active"
    SUSPENDED = "suspended"
    CLOSED    = "closed"


class ProductType(str, PyEnum):
    BASE    = "base"      # standalone package e.g. Home Mobile
    ADDON   = "addon"     # bolt-on e.g. 1GB data add-on
    ROAMING = "roaming"   # roaming package e.g. Euro Roam


class BillingModel(str, PyEnum):
    RECURRING = "recurring"
    METERED   = "metered"
    ONE_TIME  = "one_time"
    TIERED    = "tiered"


class ProductStatus(str, PyEnum):
    ACTIVE   = "active"
    ARCHIVED = "archived"


class InventoryType(str, PyEnum):
    MSISDN = "msisdn"
    SIM    = "sim"
    OTHER  = "other"


class InventoryStatus(str, PyEnum):
    AVAILABLE      = "available"
    RESERVED       = "reserved"
    ASSIGNED       = "assigned"
    PORTED_OUT     = "ported_out"
    DECOMMISSIONED = "decommissioned"


class OrderStatus(str, PyEnum):
    PENDING   = "pending"
    ACTIVE    = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class SubscriptionStatus(str, PyEnum):
    ACTIVE    = "active"
    PAUSED    = "paused"
    CANCELLED = "cancelled"


class UsageEventStatus(str, PyEnum):
    PENDING = "pending"
    RATED   = "rated"
    FAILED  = "failed"


class MediationFileStatus(str, PyEnum):
    RECEIVED   = "received"
    PROCESSING = "processing"
    PROCESSED  = "processed"
    FAILED     = "failed"


class RejectionCode(str, PyEnum):
    PARSE_ERROR      = "PARSE_ERROR"
    MISSING_FIELD    = "MISSING_FIELD"
    UNKNOWN_MSISDN   = "UNKNOWN_MSISDN"
    DUPLICATE        = "DUPLICATE"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class ChargeType(str, PyEnum):
    USAGE      = "usage"
    RECURRING  = "recurring"
    ONE_TIME   = "one_time"
    ADJUSTMENT = "adjustment"
    ADDON      = "addon"


class InvoiceStatus(str, PyEnum):
    DRAFT      = "draft"
    FINALISED  = "finalised"
    SENT       = "sent"
    PAID       = "paid"
    VOID       = "void"


class LedgerEntryType(str, PyEnum):
    CHARGE     = "charge"
    PAYMENT    = "payment"
    ADJUSTMENT = "adjustment"
    REFUND     = "refund"
    TOPUP      = "topup"


class PaymentMethod(str, PyEnum):
    MANUAL          = "manual"
    BANK_TRANSFER   = "bank_transfer"
    CASH            = "cash"
    CARD_PHASE2     = "card_phase2"


class ServiceType(str, PyEnum):
    """Types of service that can have bundle allowances."""
    DATA  = "data"   # unit: MB
    VOICE = "voice"  # unit: minutes
    SMS   = "sms"    # unit: messages


# ══════════════════════════════════════════════════════════════════════════
# CUSTOMER
# ══════════════════════════════════════════════════════════════════════════

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(Text)
    credit_type: Mapped[CreditType] = mapped_column(
        Enum(CreditType), nullable=False, default=CreditType.POSTPAID
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    billing_cycle_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[CustomerStatus] = mapped_column(
        Enum(CustomerStatus), nullable=False, default=CustomerStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)
    extra: Mapped[dict | None] = mapped_column(JSON)  # extensible metadata

    # Relationships
    orders: Mapped[list[Order]] = relationship("Order", back_populates="customer")
    subscriptions: Mapped[list[Subscription]] = relationship("Subscription", back_populates="customer")
    invoices: Mapped[list[Invoice]] = relationship("Invoice", back_populates="customer")
    ledger_entries: Mapped[list[BalanceLedger]] = relationship("BalanceLedger", back_populates="customer")
    payments: Mapped[list[Payment]] = relationship("Payment", back_populates="customer")

    def __repr__(self) -> str:
        # Use .__dict__.get to avoid triggering a refresh if the object is expired
        name = self.__dict__.get("name", "Unknown")
        return f"<Customer {name}>"


# ══════════════════════════════════════════════════════════════════════════
# PRODUCT / PACKAGE
# ══════════════════════════════════════════════════════════════════════════

class Product(Base):
    """
    A product/package in the catalog.

    price_config JSON shapes:
      Recurring:  { "amount": 9900, "interval": "month", "interval_count": 1 }
      Metered:    { "unit_price": 10, "aggregation": "sum" }
      One-time:   { "amount": 19900 }
      Tiered:     { "tiers": [...], "tier_mode": "graduated" }

    allowances JSON (optional — for bundle products):
      { "data_mb": 1024, "voice_mins": 100, "sms": 100 }

    out_of_bundle_rates JSON (optional — rate applied when bundle exhausted):
      { "data_mb": 2, "voice_mins": 5, "sms": 10 }
      (values in cents per unit)
    """
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType), nullable=False, default=ProductType.BASE
    )
    billing_model: Mapped[BillingModel] = mapped_column(
        Enum(BillingModel), nullable=False, default=BillingModel.RECURRING
    )
    price_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    allowances: Mapped[dict | None] = mapped_column(JSON)
    out_of_bundle_rates: Mapped[dict | None] = mapped_column(JSON)
    requires_inventory: Mapped[bool] = mapped_column(Boolean, default=False)
    inventory_type: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus), nullable=False, default=ProductStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)

    # Relationships
    orders: Mapped[list[Order]] = relationship("Order", back_populates="product")
    subscriptions: Mapped[list[Subscription]] = relationship("Subscription", back_populates="product")

    def __repr__(self) -> str:
        return f"<Product {self.name} ({self.product_type.value})>"


# ══════════════════════════════════════════════════════════════════════════
# INVENTORY
# ══════════════════════════════════════════════════════════════════════════

class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    type: Mapped[InventoryType] = mapped_column(Enum(InventoryType), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)  # MSISDN or ICCID
    status: Mapped[InventoryStatus] = mapped_column(
        Enum(InventoryStatus), nullable=False, default=InventoryStatus.AVAILABLE
    )
    assigned_to_order_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orders.id"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    extra: Mapped[dict | None] = mapped_column(JSON)  # batch, supplier, range

    # Relationships
    order: Mapped[Order | None] = relationship("Order", back_populates="inventory_item", foreign_keys=[assigned_to_order_id])

    __table_args__ = (
        UniqueConstraint("type", "value", name="uq_inventory_type_value"),
        Index("ix_inventory_status", "status"),
        Index("ix_inventory_value", "value"),
    )

    def __repr__(self) -> str:
        return f"<InventoryItem {self.type.value}:{self.value} [{self.status.value}]>"


# ══════════════════════════════════════════════════════════════════════════
# ORDER
# ══════════════════════════════════════════════════════════════════════════

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    # For add-ons: the parent base order this bolt-on is attached to
    parent_order_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orders.id"), nullable=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    extra: Mapped[dict | None] = mapped_column(JSON)

    # Relationships
    customer: Mapped[Customer] = relationship("Customer", back_populates="orders")
    product: Mapped[Product] = relationship("Product", back_populates="orders")
    inventory_item: Mapped[InventoryItem | None] = relationship(
        "InventoryItem", back_populates="order",
        foreign_keys="InventoryItem.assigned_to_order_id"
    )
    subscription: Mapped[Subscription | None] = relationship(
        "Subscription", back_populates="order", uselist=False
    )
    # Add-on relationships
    addons: Mapped[list[Order]] = relationship(
        "Order", back_populates="parent_order",
        foreign_keys="Order.parent_order_id"
    )
    parent_order: Mapped[Order | None] = relationship(
        "Order", back_populates="addons",
        foreign_keys=[parent_order_id], remote_side="Order.id"
    )

    __table_args__ = (
        Index("ix_order_customer", "customer_id"),
        Index("ix_order_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Order {self.order_number} [{self.status.value}]>"


# ══════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION
# ══════════════════════════════════════════════════════════════════════════

class Subscription(Base):
    """
    Created automatically when an order is activated.
    Drives billing run selection.
    """
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id"), nullable=False, unique=True
    )
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    quantity: Mapped[str] = mapped_column(String(32), nullable=False, default="1")  # stored as string, cast to Decimal
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    trial_end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    # Relationships
    order: Mapped[Order] = relationship("Order", back_populates="subscription")
    customer: Mapped[Customer] = relationship("Customer", back_populates="subscriptions")
    product: Mapped[Product] = relationship("Product", back_populates="subscriptions")
    bundle_balances: Mapped[list[BundleBalance]] = relationship("BundleBalance", back_populates="subscription")
    charge_records: Mapped[list[ChargeRecord]] = relationship("ChargeRecord", back_populates="subscription")
    usage_events: Mapped[list[UsageEvent]] = relationship("UsageEvent", back_populates="subscription")

    __table_args__ = (
        Index("ix_subscription_customer", "customer_id"),
        Index("ix_subscription_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Subscription {self.id[:8]} [{self.status.value}]>"


# ══════════════════════════════════════════════════════════════════════════
# BUNDLE BALANCE
# ══════════════════════════════════════════════════════════════════════════

class BundleBalance(Base):
    """
    Tracks remaining allowance per subscription per billing period per service type.
    One row per (subscription, period_start, service_type).

    For prepaid: deducted in real-time as usage events are rated.
    For postpaid: deducted to track OOB usage; does not affect cash balance.

    When allowance_remaining reaches 0 → out-of-bundle rates apply.
    """
    __tablename__ = "bundle_balances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    subscription_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subscriptions.id"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    service_type: Mapped[ServiceType] = mapped_column(Enum(ServiceType), nullable=False)
    # Allowance in natural units: MB for data, mins for voice, count for SMS
    allowance_total: Mapped[int] = mapped_column(Integer, nullable=False)
    allowance_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allowance_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)

    # Relationships
    subscription: Mapped[Subscription] = relationship("Subscription", back_populates="bundle_balances")

    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "period_start", "service_type",
            name="uq_bundle_balance_sub_period_service"
        ),
        Index("ix_bundle_balance_sub_period", "subscription_id", "period_start"),
    )

    def __repr__(self) -> str:
        return f"<BundleBalance {self.service_type.value} {self.allowance_remaining}/{self.allowance_total}>"


# ══════════════════════════════════════════════════════════════════════════
# MEDIATION
# ══════════════════════════════════════════════════════════════════════════

class MediationFile(Base):
    """Tracks every CSV file received via SFTP or UI upload."""
    __tablename__ = "mediation_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)  # 'sftp:pgw01' | 'ui:upload'
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    status: Mapped[MediationFileStatus] = mapped_column(
        Enum(MediationFileStatus), nullable=False, default=MediationFileStatus.RECEIVED
    )
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    accepted_records: Mapped[int] = mapped_column(Integer, default=0)
    rejected_records: Mapped[int] = mapped_column(Integer, default=0)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Relationships
    usage_events: Mapped[list[UsageEvent]] = relationship("UsageEvent", back_populates="mediation_file")
    dead_letters: Mapped[list[DeadLetterRecord]] = relationship("DeadLetterRecord", back_populates="mediation_file")

    def __repr__(self) -> str:
        return f"<MediationFile {self.filename} [{self.status.value}]>"


class UsageEvent(Base):
    """
    The canonical usage record — output of the mediation layer.
    Every usage event from any source is normalised to this format.
    The rating engine only ever sees UsageEvents.
    """
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)  # idempotency key
    msisdn: Mapped[str] = mapped_column(String(32), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("subscriptions.id"), nullable=True
    )
    customer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("customers.id"), nullable=True
    )
    mediation_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("mediation_files.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)  # 'voice'|'data'|'sms'|'custom'
    quantity: Mapped[str] = mapped_column(String(32), nullable=False)    # stored as string, Decimal in code
    unit: Mapped[str] = mapped_column(String(32), nullable=False)        # 'bytes'|'seconds'|'messages'|'units'
    event_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    source_system: Mapped[str] = mapped_column(String(128), nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(512))
    source_line: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[UsageEventStatus] = mapped_column(
        Enum(UsageEventStatus), nullable=False, default=UsageEventStatus.PENDING
    )
    extra: Mapped[dict | None] = mapped_column(JSON)  # preserved unmapped fields

    # Relationships
    subscription: Mapped[Subscription | None] = relationship("Subscription", back_populates="usage_events")
    mediation_file: Mapped[MediationFile | None] = relationship("MediationFile", back_populates="usage_events")
    charge_record: Mapped[ChargeRecord | None] = relationship("ChargeRecord", back_populates="usage_event", uselist=False)

    __table_args__ = (
        Index("ix_usage_event_msisdn", "msisdn"),
        Index("ix_usage_event_subscription", "subscription_id"),
        Index("ix_usage_event_timestamp", "event_timestamp"),
        Index("ix_usage_event_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<UsageEvent {self.event_type} {self.quantity}{self.unit} [{self.status.value}]>"


class DeadLetterRecord(Base):
    """Usage records that failed normalisation or validation. Replayable."""
    __tablename__ = "dead_letter_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    mediation_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("mediation_files.id"), nullable=True
    )
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    source_line: Mapped[int | None] = mapped_column(Integer)
    rejection_reason: Mapped[str] = mapped_column(String(512), nullable=False)
    rejection_code: Mapped[RejectionCode] = mapped_column(Enum(RejectionCode), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    mediation_file: Mapped[MediationFile | None] = relationship("MediationFile", back_populates="dead_letters")

    def __repr__(self) -> str:
        return f"<DeadLetterRecord {self.rejection_code.value}>"


# ══════════════════════════════════════════════════════════════════════════
# CHARGING / BILLING
# ══════════════════════════════════════════════════════════════════════════

class ChargeRecord(Base):
    """
    Output of the rating engine.
    Bridge between rating and billing — billing engine aggregates these
    into invoice line items. Unbilled = not yet on an invoice.
    """
    __tablename__ = "charge_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscriptions.id"), nullable=False)
    usage_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("usage_events.id"), nullable=True
    )  # null for recurring / one-time
    amount: Mapped[int] = mapped_column(Integer, nullable=False)         # cents
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    charge_type: Mapped[ChargeType] = mapped_column(Enum(ChargeType), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    billed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invoice_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("invoices.id"), nullable=True
    )
    rated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    # Relationships
    subscription: Mapped[Subscription] = relationship("Subscription", back_populates="charge_records")
    usage_event: Mapped[UsageEvent | None] = relationship("UsageEvent", back_populates="charge_record")
    invoice: Mapped[Invoice | None] = relationship("Invoice", back_populates="charge_records")

    __table_args__ = (
        Index("ix_charge_record_customer", "customer_id"),
        Index("ix_charge_record_billed", "billed"),
        Index("ix_charge_record_period", "period_start", "period_end"),
    )

    def __repr__(self) -> str:
        return f"<ChargeRecord {self.charge_type.value} {self.amount}c [{'' if self.billed else 'un'}billed]>"


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT
    )
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # cents
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # cents (tax Phase 2)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    due_date: Mapped[date | None] = mapped_column(Date)
    pdf_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    # Relationships
    customer: Mapped[Customer] = relationship("Customer", back_populates="invoices")
    line_items: Mapped[list[InvoiceLineItem]] = relationship(
        "InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan"
    )
    charge_records: Mapped[list[ChargeRecord]] = relationship("ChargeRecord", back_populates="invoice")

    __table_args__ = (
        Index("ix_invoice_customer", "customer_id"),
        Index("ix_invoice_status", "status"),
    )

    @property
    def computed_subtotal(self) -> int:
        return sum(li.amount for li in self.line_items)

    def __repr__(self) -> str:
        return f"<Invoice {self.invoice_number} [{self.status.value}]>"


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"), nullable=False)
    charge_record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("charge_records.id"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    quantity: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)  # cents
    amount: Mapped[int] = mapped_column(Integer, nullable=False)       # cents

    # Relationships
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="line_items")

    def __repr__(self) -> str:
        return f"<LineItem {self.description[:30]} {self.amount}c>"


# ══════════════════════════════════════════════════════════════════════════
# BALANCE & PAYMENTS
# ══════════════════════════════════════════════════════════════════════════

class BalanceLedger(Base):
    """
    Append-only financial ledger per customer.
    NEVER update or delete rows.
    Running balance = SUM(amount) per customer.
    Positive = credit, Negative = debit.
    """
    __tablename__ = "balance_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False)
    entry_type: Mapped[LedgerEntryType] = mapped_column(Enum(LedgerEntryType), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)   # cents, +credit / -debit
    reference_id: Mapped[str | None] = mapped_column(String(36))   # invoice_id / payment_id / manual ref
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    # Relationships
    customer: Mapped[Customer] = relationship("Customer", back_populates="ledger_entries")

    __table_args__ = (
        Index("ix_ledger_customer", "customer_id"),
        Index("ix_ledger_created", "created_at"),
    )

    def __repr__(self) -> str:
        sign = "+" if self.amount >= 0 else ""
        return f"<LedgerEntry {self.entry_type.value} {sign}{self.amount}c>"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False)
    invoice_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("invoices.id"), nullable=True
    )  # null for prepaid top-ups
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # cents
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod), nullable=False, default=PaymentMethod.MANUAL
    )
    reference: Mapped[str | None] = mapped_column(String(255))
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    recorded_by: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    customer: Mapped[Customer] = relationship("Customer", back_populates="payments")

    __table_args__ = (
        Index("ix_payment_customer", "customer_id"),
    )

    def __repr__(self) -> str:
        return f"<Payment {self.amount}c via {self.method.value}>"
