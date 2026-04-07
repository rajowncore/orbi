"""
Orbi — Pydantic v2 schemas for all API request and response models.
"""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict

from app.models import (
    CreditType, CustomerStatus, BillingModel, ProductType, ProductStatus,
    InventoryType, InventoryStatus, OrderStatus, SubscriptionStatus,
    UsageEventStatus, InvoiceStatus, LedgerEntryType, PaymentMethod,
    ChargeType, ServiceType,
)

class OKResponse(BaseModel):
    ok: bool = True
    message: str = "Success"

# ── Customer ──────────────────────────────────────────────────────────────
class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=32)
    address: Optional[str] = None
    credit_type: CreditType = CreditType.POSTPAID
    currency: str = Field("GBP", min_length=3, max_length=3)
    billing_cycle_day: int = Field(1, ge=1, le=28)
    extra: Optional[dict] = None

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, v): return v.upper()

class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)
    address: Optional[str] = None
    billing_cycle_day: Optional[int] = Field(None, ge=1, le=28)
    status: Optional[CustomerStatus] = None

class CustomerOut(BaseModel):
    id: str; name: str; email: str; phone: Optional[str]; address: Optional[str]
    credit_type: CreditType; currency: str; billing_cycle_day: int
    status: CustomerStatus; created_at: Optional[datetime]; updated_at: Optional[datetime]
    model_config = {"from_attributes": True}

# ── Product ───────────────────────────────────────────────────────────────
class ProductAllowances(BaseModel):
    data_mb: Optional[int] = Field(None, ge=0)
    voice_mins: Optional[int] = Field(None, ge=0)
    sms: Optional[int] = Field(None, ge=0)

class OutOfBundleRates(BaseModel):
    data_mb: Optional[int] = Field(None, ge=0)
    voice_mins: Optional[int] = Field(None, ge=0)
    sms: Optional[int] = Field(None, ge=0)

class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    product_type: ProductType = ProductType.BASE
    billing_model: BillingModel = BillingModel.RECURRING
    price_config: dict = Field(default_factory=dict)
    allowances: Optional[ProductAllowances] = None
    out_of_bundle_rates: Optional[OutOfBundleRates] = None
    requires_inventory: bool = False
    inventory_type: Optional[str] = None
    currency: str = Field("GBP", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, v): return v.upper()

    @model_validator(mode="after")
    def validate_price_config(self):
        model, cfg = self.billing_model, self.price_config
        if model in (BillingModel.RECURRING, BillingModel.ONE_TIME):
            if "amount" not in cfg:
                raise ValueError(f"{model.value} products need price_config.amount (cents)")
        elif model == BillingModel.METERED:
            if "unit_price" not in cfg:
                raise ValueError("Metered products need price_config.unit_price (cents)")
        elif model == BillingModel.TIERED:
            if "tiers" not in cfg or not cfg["tiers"]:
                raise ValueError("Tiered products need price_config.tiers list")
        return self

    @model_validator(mode="after")
    def validate_inventory(self):
        if self.requires_inventory and not self.inventory_type:
            raise ValueError("inventory_type required when requires_inventory is True")
        return self

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    price_config: Optional[dict] = None
    allowances: Optional[ProductAllowances] = None
    out_of_bundle_rates: Optional[OutOfBundleRates] = None
    status: Optional[ProductStatus] = None

class ProductOut(BaseModel):
    id: str; name: str; description: Optional[str]; product_type: ProductType
    billing_model: BillingModel; price_config: dict; allowances: Optional[dict]
    out_of_bundle_rates: Optional[dict]; requires_inventory: bool
    inventory_type: Optional[str]; currency: str; status: ProductStatus
    created_at: Optional[datetime]
    model_config = {"from_attributes": True}

# ── Inventory ─────────────────────────────────────────────────────────────
class InventoryItemCreate(BaseModel):
    type: InventoryType
    value: str = Field(..., min_length=1, max_length=64)
    extra: Optional[dict] = None
    @field_validator("value")
    @classmethod
    def value_strip(cls, v): return v.strip()

class InventoryBulkCreate(BaseModel):
    type: InventoryType
    values: list[str] = Field(..., min_length=1, max_length=1000)
    @field_validator("values")
    @classmethod
    def values_clean(cls, v):
        cleaned = [x.strip() for x in v if x.strip()]
        if not cleaned: raise ValueError("At least one valid value required")
        return cleaned

class InventoryItemUpdate(BaseModel):
    status: Optional[InventoryStatus] = None

class InventoryItemOut(BaseModel):
    id: str; type: InventoryType; value: str; status: InventoryStatus
    assigned_to_order_id: Optional[str]; assigned_at: Optional[datetime]
    created_at: Optional[datetime]
    model_config = {"from_attributes": True}

class InventoryBulkResult(BaseModel):
    created: int; skipped: int; errors: list[str] = []

# ── Order ─────────────────────────────────────────────────────────────────
class OrderCreate(BaseModel):
    customer_id: str = Field(..., min_length=36, max_length=36)
    product_id: str = Field(..., min_length=36, max_length=36)
    inventory_item_id: Optional[str] = Field(None, min_length=36, max_length=36)
    parent_order_id: Optional[str] = Field(None, min_length=36, max_length=36)
    extra: Optional[dict] = None

class OrderAction(BaseModel):
    action: str = Field(..., pattern="^(activate|suspend|cancel)$")

class OrderOut(BaseModel):
    id: str; order_number: str; customer_id: str; product_id: str
    inventory_item_id: Optional[str] = None
    parent_order_id: Optional[str]; status: OrderStatus
    activated_at: Optional[datetime]; suspended_at: Optional[datetime]
    cancelled_at: Optional[datetime]; created_at: Optional[datetime]
    model_config = {"from_attributes": True}

# ── Subscription ──────────────────────────────────────────────────────────
class SubscriptionOut(BaseModel):
    id: str; order_id: str; customer_id: str; product_id: str; quantity: str
    start_date: Optional[date]; end_date: Optional[date]; trial_end_date: Optional[date]
    status: SubscriptionStatus; created_at: Optional[datetime]
    model_config = {"from_attributes": True}

class BundleBalanceOut(BaseModel):
    id: str; subscription_id: str; period_start: date; period_end: date
    service_type: ServiceType; allowance_total: int; allowance_used: int
    allowance_remaining: int; updated_at: Optional[datetime]
    model_config = {"from_attributes": True}

# ── Usage ─────────────────────────────────────────────────────────────────
class UsageEventCreate(BaseModel):
    event_id: Optional[str] = None
    msisdn: str = Field(..., min_length=1, max_length=32)
    event_type: str = Field(..., pattern="^(voice|data|sms|custom)$")
    quantity: Decimal = Field(..., gt=0)
    unit: str = Field(..., pattern="^(bytes|seconds|messages|mb|minutes|units)$")
    event_timestamp: datetime
    source_system: str = "api:manual"
    extra: Optional[dict] = None

class UsageEventBatch(BaseModel):
    events: list[UsageEventCreate] = Field(..., min_length=1, max_length=1000)

class UsageEventOut(BaseModel):
    id: str; event_id: str; msisdn: str; subscription_id: Optional[str]
    customer_id: Optional[str]; event_type: str; quantity: str; unit: str
    event_timestamp: Optional[datetime]; ingested_at: Optional[datetime]
    source_system: str; status: UsageEventStatus
    model_config = {"from_attributes": True}

class IngestResponse(BaseModel):
    status: str = "accepted"; event_id: str; accepted: int = 1

class BatchIngestResponse(BaseModel):
    status: str = "accepted"; accepted: int; rejected: int = 0

# ── Invoice ───────────────────────────────────────────────────────────────
class InvoiceLineItemOut(BaseModel):
    id: str; description: str; quantity: str; unit_price: int; amount: int
    model_config = {"from_attributes": True}

class InvoiceOut(BaseModel):
    id: str; invoice_number: str; customer_id: str; period_start: Optional[date]
    period_end: Optional[date]; status: InvoiceStatus; subtotal: int; total: int
    currency: str; due_date: Optional[date]; pdf_url: Optional[str]
    created_at: Optional[datetime]; line_items: list[InvoiceLineItemOut] = []
    
    model_config = ConfigDict(from_attributes=True)

# ── Payments ──────────────────────────────────────────────────────────────
class PaymentCreate(BaseModel):
    customer_id: str = Field(..., min_length=36, max_length=36)
    invoice_id: Optional[str] = None
    amount: int = Field(..., gt=0, description="Amount in cents")
    currency: str = Field("GBP", min_length=3, max_length=3)
    method: PaymentMethod = PaymentMethod.MANUAL
    reference: Optional[str] = Field(None, max_length=255)
    payment_date: date
    recorded_by: Optional[str] = None
    description: Optional[str] = None
    @field_validator("invoice_id")
    @classmethod
    def empty_str_to_none(cls, v):
        # If the frontend sends "", " ", or nothing, treat it as None
        if v is not None and not v.strip():
            return None
        return v
    @field_validator("currency")
    @classmethod
    def currency_upper(cls, v): return v.upper()

class PaymentOut(BaseModel):
    id: str; customer_id: str; invoice_id: Optional[str]; amount: int
    currency: str; method: PaymentMethod; reference: Optional[str]
    payment_date: date; recorded_at: Optional[datetime]; recorded_by: Optional[str]
    model_config = {"from_attributes": True}

class LedgerEntryOut(BaseModel):
    id: str; entry_type: LedgerEntryType; amount: int; description: str
    reference_id: Optional[str]; created_at: Optional[datetime]
    model_config = {"from_attributes": True}

class CustomerBalanceOut(BaseModel):
    customer_id: str; balance_cents: int; currency: str
    entries: list[LedgerEntryOut] = []

# ── Billing runs ──────────────────────────────────────────────────────────
class BillingRunCreate(BaseModel):
    period_start: date
    period_end: date
    customer_id: Optional[str] = None
    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be >= period_start")
        return self

class BillingRunResponse(BaseModel):
    status: str; job_id: str; period_start: date; period_end: date; message: str
