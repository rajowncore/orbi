"""
Orbi — Order service layer.

State machine:
  pending  → activate  → active
  active   → suspend   → suspended
  suspended→ activate  → active
  any      → cancel    → cancelled  (except already cancelled)

Side effects on activate:
  1. InventoryItem: reserved → assigned, assigned_at set
  2. Subscription: created with start_date = today
  3. BundleBalance: one row per service type in product.allowances
  4. For prepaid: check balance ≥ product price, debit immediately

Side effects on cancel:
  1. InventoryItem: assigned → available, assignment cleared
  2. Subscription: status = cancelled, end_date = today
"""
from __future__ import annotations
import uuid
from datetime import datetime, date
from calendar import monthrange
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException

from app.models import (
    Order, OrderStatus, Customer, CreditType,
    Product, BillingModel,
    InventoryItem, InventoryStatus,
    Subscription, SubscriptionStatus,
    BundleBalance, ServiceType,
    BalanceLedger, LedgerEntryType,
)
from app.schemas import OrderCreate, OrderAction


# ── helpers ───────────────────────────────────────────────────────────────

def _period_end(start: date) -> date:
    """Return the last day of the month for a given start date."""
    last_day = monthrange(start.year, start.month)[1]
    return date(start.year, start.month, last_day)


async def _get_or_404(db, model, id_: str, label: str):
    r = await db.execute(select(model).where(model.id == id_))
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, f"{label} {id_} not found")
    return obj


async def _next_order_number(db: AsyncSession) -> str:
    r = await db.execute(select(func.count()).select_from(Order))
    n = (r.scalar() or 0) + 1
    return f"ORD-{datetime.utcnow().year}-{str(n).zfill(5)}"


# ── list / get ─────────────────────────────────────────────────────────────

async def list_orders(db: AsyncSession, customer_id: str | None = None,
                      status: str | None = None) -> list[Order]:
    q = select(Order)
    if customer_id:
        q = q.where(Order.customer_id == customer_id)
    if status:
        q = q.where(Order.status == status)
    r = await db.execute(q.order_by(Order.created_at.desc()))
    return r.scalars().all()


async def get_order(db: AsyncSession, order_id: str) -> Order:
    return await _get_or_404(db, Order, order_id, "Order")


# ── create ────────────────────────────────────────────────────────────────

async def create_order(db: AsyncSession, data: OrderCreate) -> Order:
    customer = await _get_or_404(db, Customer, data.customer_id, "Customer")
    product  = await _get_or_404(db, Product,  data.product_id,  "Product")

    # Validate add-on has a parent
    if product.product_type.value == "addon" and not data.parent_order_id:
        raise HTTPException(400, "Add-on products require a parent_order_id")

    # Validate parent order belongs to same customer and is active
    if data.parent_order_id:
        parent = await _get_or_404(db, Order, data.parent_order_id, "Parent order")
        if parent.customer_id != data.customer_id:
            raise HTTPException(400, "Parent order belongs to a different customer")
        if parent.status != OrderStatus.ACTIVE:
            raise HTTPException(400, f"Parent order must be active (currently {parent.status.value})")

    # Handle inventory
    inventory_item = None
    if product.requires_inventory:
        if not data.inventory_item_id:
            raise HTTPException(400, f"Product '{product.name}' requires an inventory item ({product.inventory_type})")
        inventory_item = await _get_or_404(db, InventoryItem, data.inventory_item_id, "Inventory item")
        if inventory_item.status != InventoryStatus.AVAILABLE:
            raise HTTPException(409, f"Inventory item is not available (status: {inventory_item.status.value})")
        if product.inventory_type and inventory_item.type.value != product.inventory_type:
            raise HTTPException(400, f"Product requires {product.inventory_type} but got {inventory_item.type.value}")
        # Reserve immediately
        inventory_item.status = InventoryStatus.RESERVED

    order = Order(
        id=str(uuid.uuid4()),
        order_number=await _next_order_number(db),
        customer_id=customer.id,
        product_id=product.id,
        parent_order_id=data.parent_order_id,
        status=OrderStatus.PENDING,
        extra=data.extra,
    )
    db.add(order)
    await db.flush()

    if inventory_item:
        inventory_item.assigned_to_order_id = order.id

    return order


# ── state machine ──────────────────────────────────────────────────────────

async def apply_action(db: AsyncSession, order_id: str, action: str) -> Order:
    order = await get_order(db, order_id)

    if action == "activate":
        # In your service before calling _activate
        await db.refresh(order, ["inventory_item"])     # Added
        await _activate(db, order)
    elif action == "suspend":
        await _suspend(db, order)
    elif action == "cancel":
        await db.refresh(order, ["inventory_item"])     # Added
        await _cancel(db, order)
    else:
        raise HTTPException(400, f"Unknown action: {action}")

    await db.flush()
    return order


async def _activate(db: AsyncSession, order: Order) -> None:
    allowed = {OrderStatus.PENDING, OrderStatus.SUSPENDED}
    if order.status not in allowed:
        raise HTTPException(409, f"Cannot activate order with status '{order.status.value}'")

    now = datetime.utcnow()
    today = now.date()

    # Load product and customer
    product  = await _get_or_404(db, Product,  order.product_id,  "Product")
    customer = await _get_or_404(db, Customer, order.customer_id, "Customer")

    # Prepaid: check and debit balance
    if customer.credit_type == CreditType.PREPAID:
        price = product.price_config.get("amount", 0)
        if price > 0:
            balance_r = await db.execute(
                select(func.sum(BalanceLedger.amount))
                .where(BalanceLedger.customer_id == customer.id)
            )
            current_balance = balance_r.scalar() or 0
            if current_balance < price:
                raise HTTPException(
                    402,
                    f"Insufficient balance. Required: {price}p, Available: {current_balance}p"
                )
            # Debit balance
            debit = BalanceLedger(
                id=str(uuid.uuid4()),
                customer_id=customer.id,
                entry_type=LedgerEntryType.CHARGE,
                amount=-price,
                reference_id=order.id,
                description=f"Package activation: {product.name}",
            )
            db.add(debit)

    # Assign inventory
    if order.inventory_item:
        order.inventory_item.status = InventoryStatus.ASSIGNED
        order.inventory_item.assigned_at = now

    # Create or reactivate subscription
    existing_sub_r = await db.execute(
        select(Subscription).where(Subscription.order_id == order.id)
    )
    existing_sub = existing_sub_r.scalar_one_or_none()

    if existing_sub:
        # Reactivating a suspended order
        existing_sub.status = SubscriptionStatus.ACTIVE
        existing_sub.end_date = None
        sub = existing_sub
    else:
        sub = Subscription(
            id=str(uuid.uuid4()),
            order_id=order.id,
            customer_id=order.customer_id,
            product_id=order.product_id,
            quantity="1",
            start_date=today,
            status=SubscriptionStatus.ACTIVE,
        )
        db.add(sub)
        await db.flush()  # get sub.id

    # Initialise bundle balances from product allowances
    if product.allowances:
        period_start = today
        period_end   = _period_end(today)
        await _init_bundle_balances(db, sub.id, product.allowances, period_start, period_end)

    order.status = OrderStatus.ACTIVE
    order.activated_at = now


async def _init_bundle_balances(
    db: AsyncSession,
    subscription_id: str,
    allowances: dict,
    period_start: date,
    period_end: date,
) -> None:
    """Create BundleBalance rows for each service type in the allowances dict."""
    service_map = {
        "data_mb":    ServiceType.DATA,
        "voice_mins": ServiceType.VOICE,
        "sms":        ServiceType.SMS,
    }
    for field, service_type in service_map.items():
        total = allowances.get(field)
        if not total:
            continue
        # Avoid duplicates (e.g. re-activation)
        existing_r = await db.execute(
            select(BundleBalance).where(
                BundleBalance.subscription_id == subscription_id,
                BundleBalance.period_start    == period_start,
                BundleBalance.service_type    == service_type,
            )
        )
        if existing_r.scalar_one_or_none():
            continue
        bb = BundleBalance(
            id=str(uuid.uuid4()),
            subscription_id=subscription_id,
            period_start=period_start,
            period_end=period_end,
            service_type=service_type,
            allowance_total=total,
            allowance_used=0,
            allowance_remaining=total,
        )
        db.add(bb)


async def _suspend(db: AsyncSession, order: Order) -> None:
    if order.status != OrderStatus.ACTIVE:
        raise HTTPException(409, f"Cannot suspend order with status '{order.status.value}'")
    now = datetime.utcnow()
    order.status = OrderStatus.SUSPENDED
    order.suspended_at = now
    # Pause subscription
    sub_r = await db.execute(select(Subscription).where(Subscription.order_id == order.id))
    sub = sub_r.scalar_one_or_none()
    if sub:
        sub.status = SubscriptionStatus.PAUSED


async def _cancel(db: AsyncSession, order: Order) -> None:
    if order.status == OrderStatus.CANCELLED:
        raise HTTPException(409, "Order is already cancelled")
    now = datetime.utcnow()
    order.status = OrderStatus.CANCELLED
    order.cancelled_at = now

    # Release inventory back to pool
    if order.inventory_item:
        order.inventory_item.status = InventoryStatus.AVAILABLE
        order.inventory_item.assigned_to_order_id = None
        order.inventory_item.assigned_at = None

    # Cancel subscription
    sub_r = await db.execute(select(Subscription).where(Subscription.order_id == order.id))
    sub = sub_r.scalar_one_or_none()
    if sub:
        sub.status = SubscriptionStatus.CANCELLED
        sub.end_date = now.date()
