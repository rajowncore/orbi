"""
Orbi — Provisioning Service

Bridges the order service and the workflow engine.
Called by the order router on activate/cancel actions.

Config is read from environment variables or app settings.
If HSS/CGRateS URLs are not configured, provisioning is skipped
and the order activates normally (useful for MVP/dev without real network).
"""
from __future__ import annotations
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload                                       

from app.config import settings
from app.models import BundleBalance, ServiceType, Order, Subscription, SubscriptionStatus, InventoryItem, Product, Customer
from app.provisioning.adapters import OmniHSSAdapter, CGRatesAdapter
from app.provisioning.runner import WorkflowRunner
from app.provisioning.models import ProvisioningWorkflow
from app.provisioning import WorkflowStatus

log = logging.getLogger(__name__)


def _get_runner() -> WorkflowRunner | None:
    """
    Build a WorkflowRunner if external systems are configured.
    Returns None if HSS/CGRateS URLs are not set — provisioning is skipped.
    """
    hss_url     = getattr(settings, "HSS_API_URL", "")
    cgrates_url = getattr(settings, "CGRATES_API_URL", "")
    tenant      = getattr(settings, "CGRATES_TENANT", "cgrates.org")

    if not hss_url or not cgrates_url:
        return None

    hss     = OmniHSSAdapter(hss_url)
    cgrates = CGRatesAdapter(cgrates_url, tenant)
    return WorkflowRunner(hss, cgrates)


async def trigger_provision(
    db: AsyncSession,
    order: Order,
) -> ProvisioningWorkflow | None:

    runner = _get_runner()
    if not runner:
        log.info(f"Provisioning not configured — skipping for order {order.order_number}")
        return None

    # Build provisioning context from order + related objects
    ctx = await _build_context(db, order)
    if not ctx:
        log.warning(f"Could not build provisioning context for order {order.order_number}")
        return None

    log.info(f"Starting provisioning workflow for order {order.order_number}")
    workflow = await runner.run_provision(db, order.id, ctx)

    if workflow.status == WorkflowStatus.COMPLETED:
        log.info(f"✓ Provisioning complete for {order.order_number}")
        # Now safe to create subscription — network is provisioned
        await _ensure_subscription(db, order, workflow.context)
    else:
        log.error(f"✗ Provisioning failed for {order.order_number}: {workflow.error_message}")
        # Rollback order status back to pending so operator can retry
        # Re-fetch order in same session to avoid stale object
        r = await db.execute(select(Order).where(Order.id == order.id))
        db_order = r.scalar_one_or_none()
        if db_order:
            from app.models import OrderStatus
            order.status = OrderStatus.PENDING
            order.activated_at = None
            await db.flush()
            log.warning(f"Order {order.order_number} reverted to pending after provisioning failure")

    return workflow

async def _ensure_subscription(db: AsyncSession, order: Order, context: dict) -> None:
    """
    Create subscription after successful provisioning.
    Called only when provisioning is configured and completes successfully.
    Skips if subscription already exists (idempotent).
    """
    from datetime import date, datetime
    # from app.models import (
    #     Subscription, SubscriptionStatus, Product,
    #     Customer, CreditType, BundleBalance, ServiceType,
    #     BalanceLedger, LedgerEntryType,
    # )
    #from sqlalchemy import select
    from calendar import monthrange
    import uuid

    # Check if subscription already exists
    existing_r = await db.execute(
        select(Subscription).where(Subscription.order_id == order.id)
    )
    if existing_r.scalar_one_or_none():
        log.info(f"Subscription already exists for order {order.id}")
        return  # already created

    now   = datetime.utcnow()
    today = now.date()
    year, month = today.year, today.month
    last_day = monthrange(year, month)[1]
    period_end = date(year, month, last_day)

    prod_r = await db.execute(select(Product).where(Product.id == order.product_id))
    product = prod_r.scalar_one_or_none()

    sub = Subscription(
        id=str(uuid.uuid4()),
        order_id=order.id,
        customer_id=order.customer_id,
        product_id=order.product_id,
        quantity="1",
        start_date=today,
        status=SubscriptionStatus.ACTIVE,
        created_at=now,
    )
    db.add(sub)
    await db.flush()

    # Initialise bundle balances
    if product and product.allowances:
        svc_map = {
            "data_mb":    ServiceType.DATA,
            "voice_mins": ServiceType.VOICE,
            "sms":        ServiceType.SMS,
        }
        for field, svc in svc_map.items():
            total = product.allowances.get(field)
            if not total:
                continue
            bb = BundleBalance(
                id=str(uuid.uuid4()),
                subscription_id=sub.id,
                period_start=today,
                period_end=period_end,
                service_type=svc,
                allowance_total=total,
                allowance_used=0,
                allowance_remaining=total,
            )
            db.add(bb)

    await db.flush()
    log.info(f"Subscription created after provisioning: {sub.id}")

async def trigger_deprovision(
    db: AsyncSession,
    order: Order,
) -> ProvisioningWorkflow | None:
    """
    Trigger deprovisioning workflow on order cancel.
    """
    runner = _get_runner()
    if not runner:
        log.info(f"Provisioning not configured — skipping deprovision for {order.order_number}")
        return None

    # Try to recover context from existing provision workflow
    ctx = await _recover_context(db, order)
    if not ctx:
        ctx = await _build_context(db, order) or {}

    log.info(f"Starting deprovision workflow for order {order.order_number}")
    return await runner.run_deprovision(db, order.id, ctx)


async def _build_context(db: AsyncSession, order: Order) -> dict | None:
    """
    Build the initial context dict from order + related DB objects.
    Explicitly loads all relationships with selectinload to avoid
    the greenlet_spawn / lazy-load error in async SQLAlchemy.
    """
    try:
        # ── Reload order with all relationships eagerly loaded ──────────
        order_r = await db.execute(
            select(Order)
            .where(Order.id == order.id)
            .options(selectinload(Order.inventory_item))
        )
        order = order_r.scalar_one_or_none()
        if not order:
            return None

        # ── Product ──────────────────────────────────────────────────────
        prod_r = await db.execute(
            select(Product).where(Product.id == order.product_id)
        )
        product = prod_r.scalar_one_or_none()

        # ── Customer ─────────────────────────────────────────────────────
        cust_r = await db.execute(
            select(Customer).where(Customer.id == order.customer_id)
        )
        customer = cust_r.scalar_one_or_none()

        # ── Subscription ─────────────────────────────────────────────────
        sub_r = await db.execute(
            select(Subscription).where(Subscription.order_id == order.id)
        )
        sub = sub_r.scalar_one_or_none()

        if not product or not customer:
            log.warning(f"Missing product or customer for order {order.id}")
            return None

        ctx: dict = {
            "order_id":        order.id,
            "order_number":    order.order_number,
            "customer_id":     customer.id,
            "customer_name":   customer.name,
            "product_id":      product.id,
            "package_name":    product.name,
            "subscription_id": sub.id if sub else None,
            "is_prepaid":      customer.credit_type.value == "prepaid",
            "initial_balance_pence": 0,
            "cgrates_tenant":  getattr(settings, "CGRATES_TENANT", "cgrates.org"),
        }

        # ── Inventory — now safely accessible via eager load ─────────────
                                
        inv = order.inventory_item  # safe — loaded above with selectinload

        if inv:
            if inv.type.value == "msisdn":
                ctx["msisdn"]           = inv.value
                ctx["inventory_item_id"] = inv.id
            elif inv.type.value == "sim":
                ctx["iccid"]            = inv.value
                ctx["inventory_item_id"] = inv.id
                                                      
                if inv.extra and inv.extra.get("imsi"):
                    ctx["imsi"] = inv.extra["imsi"]
        else:
            # Fallback: query inventory assigned to this order directly
            inv_r = await db.execute(
                select(InventoryItem).where(
                    InventoryItem.assigned_to_order_id == order.id
                )
            )
            items = inv_r.scalars().all()
            for item in items:
                if item.type.value == "msisdn":
                    ctx["msisdn"]            = item.value
                    ctx["inventory_item_id"] = item.id
                elif item.type.value == "sim":
                    ctx["iccid"]             = item.value
                    ctx["inventory_item_id"] = item.id
                    if item.extra and item.extra.get("imsi"):
                        ctx["imsi"] = item.extra["imsi"]

        log.info(f"Built provisioning context: msisdn={ctx.get('msisdn','N/A')} "
                 f"iccid={ctx.get('iccid','N/A')} "
                 f"package={ctx.get('package_name')}")
        return ctx

    except Exception as e:
        log.error(f"Failed to build provisioning context: {e}", exc_info=True)
        return None


async def _recover_context(db: AsyncSession, order: Order) -> dict | None:
       
    """Recover context from a previous completed provision workflow."""
                                                                       
       
    r = await db.execute(
        select(ProvisioningWorkflow).where(
            ProvisioningWorkflow.order_id      == order.id,
            ProvisioningWorkflow.workflow_type == "provision_sim",
            ProvisioningWorkflow.status        == WorkflowStatus.COMPLETED,
        ).order_by(ProvisioningWorkflow.created_at.desc())
    )
    wf = r.scalar_one_or_none()
    return wf.context if wf else None


async def get_workflow_status(
    db: AsyncSession, order_id: str
) -> ProvisioningWorkflow | None:
                                                            
    r = await db.execute(
        select(ProvisioningWorkflow)
        .where(ProvisioningWorkflow.order_id == order_id)
        .order_by(ProvisioningWorkflow.created_at.desc())
    )
    return r.scalar_one_or_none()


async def list_workflows(
    db: AsyncSession,
    status: str | None = None,
    limit: int = 50,
) -> list[ProvisioningWorkflow]:
    q = (
        select(ProvisioningWorkflow)
        .options(selectinload(ProvisioningWorkflow.steps))
        .order_by(ProvisioningWorkflow.created_at.desc())
        .limit(limit)
    )
    if status:
        q = q.where(ProvisioningWorkflow.status == status)
    r = await db.execute(q)
    return r.scalars().all()