"""
Orbi — FastAPI routers. All endpoints use Pydantic schemas and service layer.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

import logging

# This grabs the existing logger Uvicorn is already using
logger = logging.getLogger("uvicorn.error")

from app.database import get_db
from app.schemas import (
    CustomerCreate, CustomerUpdate, CustomerOut, CustomerBalanceOut,
    ProductCreate, ProductUpdate, ProductOut,
    InventoryItemCreate, InventoryBulkCreate, InventoryItemUpdate, InventoryItemOut, InventoryBulkResult,
    OrderCreate, OrderAction, OrderOut,
    SubscriptionOut,
    UsageEventCreate, UsageEventBatch, UsageEventOut, IngestResponse, BatchIngestResponse,
    InvoiceOut,
    PaymentCreate, PaymentOut,
    BillingRunCreate, BillingRunResponse,
    OKResponse,
)
from app.services import customer as customer_svc
from app.services import product as product_svc
from app.services import inventory as inventory_svc
from app.services import order as order_svc
from app.services import payment as payment_svc
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload
from fastapi import HTTPException

from app.models import (
    Subscription, UsageEvent, Invoice, BalanceLedger,Product,
    UsageEventStatus, InventoryStatus,
)

# ══════════════════════════════════════════════════════════════════════════
# CUSTOMERS
# ══════════════════════════════════════════════════════════════════════════
class customers:
    router = APIRouter(prefix="/customers", tags=["Customers"])

    @router.get("", response_model=list[CustomerOut])
    async def list_customers(db: AsyncSession = Depends(get_db)):
        return await customer_svc.list_customers(db)

    @router.post("", response_model=CustomerOut, status_code=201)
    async def create_customer(body: CustomerCreate, db: AsyncSession = Depends(get_db)):
        try:
            # Call your service function
            new_customer = await customer_svc.create_customer(db, body)
        
            # --- EXPLICIT COMMIT ---
            # This is where the magic happens. 
            # Until this line runs, the DB is just "holding" the data.
            await db.commit()
            
            # Refresh to ensure we have the latest state from DB
            await db.refresh(new_customer)
            return new_customer

        except Exception as e:
            # If anything failed (uniqueness, network, etc.), wipe the slate clean
            await db.rollback()
            # Re-raise so FastAPI handles the error response
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail="Internal Database Error")
            #return await customer_svc.create_customer(db, body)

    @router.get("/{customer_id}", response_model=CustomerOut)
    async def get_customer(customer_id: str, db: AsyncSession = Depends(get_db)):
        return await customer_svc.get_customer(db, customer_id)

    @router.patch("/{customer_id}", response_model=CustomerOut)
    async def update_customer(customer_id: str, body: CustomerUpdate, db: AsyncSession = Depends(get_db)):
        return await customer_svc.update_customer(db, customer_id, body)

    @router.get("/{customer_id}/orders", response_model=list[OrderOut])
    async def customer_orders(customer_id: str, db: AsyncSession = Depends(get_db)):
        return await order_svc.list_orders(db, customer_id=customer_id)

    @router.get("/{customer_id}/invoices", response_model=list[InvoiceOut])
    async def customer_invoices(customer_id: str, db: AsyncSession = Depends(get_db)):
        r = await db.execute(select(Invoice).options(selectinload(Invoice.line_items)).where(Invoice.customer_id == customer_id).order_by(Invoice.created_at.desc()))
        return r.scalars().all()

    @router.get("/{customer_id}/balance", response_model=CustomerBalanceOut)
    async def customer_balance(customer_id: str, db: AsyncSession = Depends(get_db)):
        return await customer_svc.get_balance(db, customer_id)


# ══════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ══════════════════════════════════════════════════════════════════════════
class products:
    router = APIRouter(prefix="/products", tags=["Products"])

    @router.get("", response_model=list[ProductOut])
    async def list_products(archived: bool = False, db: AsyncSession = Depends(get_db)):
        return await product_svc.list_products(db, include_archived=archived)

    @router.post("", response_model=ProductOut, status_code=201)
    async def create_product(body: ProductCreate, db: AsyncSession = Depends(get_db)):
        try:
            new_product = await product_svc.create_product(db, body)

            await db.commit()
            await db.refresh(new_product)
            return new_product
        except Exception as e:
            logger.error(f"CRASH IN POST: {str(e)}", exc_info=True)
            # If anything failed (uniqueness, network, etc.), wipe the slate clean
            await db.rollback()
            # Re-raise so FastAPI handles the error response
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail="Internal Database Error")

    @router.get("/{product_id}", response_model=ProductOut)
    async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
        return await product_svc.get_product(db, product_id)

    @router.patch("/{product_id}", response_model=ProductOut)
    async def update_product(product_id: str, body: ProductUpdate, db: AsyncSession = Depends(get_db)):
        return await product_svc.update_product(db, product_id, body)


# ══════════════════════════════════════════════════════════════════════════
# INVENTORY
# ══════════════════════════════════════════════════════════════════════════
class inventory:
    router = APIRouter(prefix="/inventory", tags=["Inventory"])

    @router.get("", response_model=list[InventoryItemOut])
    async def list_inventory(type: Optional[str] = None, status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
        return await inventory_svc.list_inventory(db, type=type, status=status)

    @router.post("", response_model=InventoryItemOut, status_code=201)
    async def create_item(body: InventoryItemCreate, db: AsyncSession = Depends(get_db)):
        try:
            new_item = await inventory_svc.create_item(db, body)

            await db.commit()
            await db.refresh(new_item)
            return new_item
        except Exception as e:
            # If anything failed (uniqueness, network, etc.), wipe the slate clean
            await db.rollback()
            # Re-raise so FastAPI handles the error response
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail="Internal Database Error")

    @router.post("/bulk", response_model=InventoryBulkResult, status_code=201)
    async def bulk_import(body: InventoryBulkCreate, db: AsyncSession = Depends(get_db)):
        try:
            new_item = await inventory_svc.bulk_create(db, body)

            await db.commit()
            await db.refresh(new_item)
            return new_item
        except Exception as e:
            # If anything failed (uniqueness, network, etc.), wipe the slate clean
            await db.rollback()
            # Re-raise so FastAPI handles the error response
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail="Internal Database Error")

    @router.get("/available", response_model=list[InventoryItemOut])
    async def available_items(type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
        return await inventory_svc.get_available(db, type=type)

    @router.patch("/{item_id}", response_model=InventoryItemOut)
    async def update_item(item_id: str, body: InventoryItemUpdate, db: AsyncSession = Depends(get_db)):
        return await inventory_svc.update_item(db, item_id, body)


# ══════════════════════════════════════════════════════════════════════════
# ORDERS
# ══════════════════════════════════════════════════════════════════════════
class orders:
    router = APIRouter(prefix="/orders", tags=["Orders"])

    @router.get("", response_model=list[OrderOut])
    async def list_orders(customer_id: Optional[str] = None, status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
        return await order_svc.list_orders(db, customer_id=customer_id, status=status)

    @router.post("", response_model=OrderOut, status_code=201)
    async def create_order(body: OrderCreate, db: AsyncSession = Depends(get_db)):
        try:
            new_order = await order_svc.create_order(db, body)

            await db.commit()
            await db.refresh(new_order)
            return new_order
        except Exception as e:
            # If anything failed (uniqueness, network, etc.), wipe the slate clean
            await db.rollback()
            # Re-raise so FastAPI handles the error response
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail="Internal Database Error")

    @router.get("/{order_id}", response_model=OrderOut)
    async def get_order(order_id: str, db: AsyncSession = Depends(get_db)):
        return await order_svc.get_order(db, order_id)

    @router.patch("/{order_id}", response_model=OrderOut)
    async def update_order(order_id: str, body: OrderAction, db: AsyncSession = Depends(get_db)):
        try:
            update_order = await order_svc.apply_action(db, order_id, body.action)

            await db.commit()
            await db.refresh(update_order)
            return update_order
        except Exception as e:
            # If anything failed (uniqueness, network, etc.), wipe the slate clean
            await db.rollback()
            # Re-raise so FastAPI handles the error response
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail="Internal Database Error")

# ══════════════════════════════════════════════════════════════════════════
# SUBSCRIPTIONS
# ══════════════════════════════════════════════════════════════════════════
class subscriptions:
    router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

    @router.get("", response_model=list[SubscriptionOut])
    async def list_subscriptions(customer_id: Optional[str] = None, 
                                 sub_type: Optional[str] = None,
                                 db: AsyncSession = Depends(get_db)):
        q = select(Subscription).options(joinedload(Subscription.product))
        if customer_id:
            q = q.where(Subscription.customer_id == customer_id)
        
        if sub_type:
            # Filter by product type (e.g., 'base' or 'addon')
            q = q.join(Product).where(Product.product_type == sub_type)

        r = await db.execute(q.order_by(Subscription.created_at.desc()))
        return r.scalars().all()

    @router.get("/{sub_id}", response_model=SubscriptionOut)
    async def get_subscription(sub_id: str, db: AsyncSession = Depends(get_db)):
        r = await db.execute(select(Subscription).where(Subscription.id == sub_id))
        sub = r.scalar_one_or_none()
        if not sub:
            from fastapi import HTTPException
            raise HTTPException(404, f"Subscription {sub_id} not found")
        return sub


# ══════════════════════════════════════════════════════════════════════════
# USAGE
# ══════════════════════════════════════════════════════════════════════════
class usage:
    router = APIRouter(prefix="/usage", tags=["Usage"])

    @router.post("/events", response_model=IngestResponse, status_code=202)
    async def ingest_event(body: UsageEventCreate, db: AsyncSession = Depends(get_db)):
        event_id = body.event_id or str(uuid.uuid4())
        # Deduplicate
        existing = await db.execute(select(UsageEvent).where(UsageEvent.event_id == event_id))
        if existing.scalar_one_or_none():
            return IngestResponse(status="duplicate", event_id=event_id)
        event = UsageEvent(
            id=str(uuid.uuid4()),
            event_id=event_id,
            msisdn=body.msisdn,
            event_type=body.event_type,
            quantity=str(body.quantity),
            unit=body.unit,
            event_timestamp=body.event_timestamp,
            source_system=body.source_system,
            extra=body.extra,
        )
        db.add(event)
        await db.flush()
        return IngestResponse(event_id=event_id)

    @router.post("/events/batch", response_model=BatchIngestResponse, status_code=202)
    async def ingest_batch(body: UsageEventBatch, db: AsyncSession = Depends(get_db)):
        accepted = 0
        rejected = 0
        for e in body.events:
            event_id = e.event_id or str(uuid.uuid4())
            existing = await db.execute(select(UsageEvent).where(UsageEvent.event_id == event_id))
            if existing.scalar_one_or_none():
                rejected += 1
                continue
            event = UsageEvent(
                id=str(uuid.uuid4()), event_id=event_id,
                msisdn=e.msisdn, event_type=e.event_type,
                quantity=str(e.quantity), unit=e.unit,
                event_timestamp=e.event_timestamp,
                source_system=e.source_system or "api:batch",
            )
            db.add(event)
            accepted += 1
        await db.flush()
        return BatchIngestResponse(accepted=accepted, rejected=rejected)

    @router.get("/events", response_model=list[UsageEventOut])
    async def list_events(customer_id: Optional[str] = None, msisdn: Optional[str] = None, db: AsyncSession = Depends(get_db)):
        q = select(UsageEvent)
        if msisdn:
            q = q.where(UsageEvent.msisdn == msisdn)
        if customer_id:
            q = q.where(UsageEvent.customer_id == customer_id)
        r = await db.execute(q.order_by(UsageEvent.event_timestamp.desc()).limit(500))
        return r.scalars().all()

    @router.get("/rejected")
    async def list_rejected(db: AsyncSession = Depends(get_db)):
        from app.models import DeadLetterRecord
        r = await db.execute(
            select(DeadLetterRecord)
            .where(DeadLetterRecord.replayed_at == None)
            .order_by(DeadLetterRecord.created_at.desc())
            .limit(200)
        )
        return [{"id": x.id, "rejection_code": x.rejection_code, "reason": x.rejection_reason, "created_at": x.created_at.isoformat() if x.created_at else None} for x in r.scalars().all()]


# ══════════════════════════════════════════════════════════════════════════
# INVOICES
# ══════════════════════════════════════════════════════════════════════════
class invoices:
    router = APIRouter(prefix="/invoices", tags=["Invoices"])

    @router.get("", response_model=list[InvoiceOut])
    async def list_invoices(customer_id: Optional[str] = None, status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
        q = select(Invoice).options(selectinload(Invoice.line_items))
        if customer_id:
            q = q.where(Invoice.customer_id == customer_id)
        if status:
            q = q.where(Invoice.status == status)
        r = await db.execute(q.order_by(Invoice.created_at.desc()))
        return r.scalars().all()

    @router.get("/{invoice_id}", response_model=InvoiceOut)
    async def get_invoice(invoice_id: str, db: AsyncSession = Depends(get_db)):
        r = await db.execute(select(Invoice).options(selectinload(Invoice.line_items)).where(Invoice.id == invoice_id))
        inv = r.scalar_one_or_none()
        if not inv:
            from fastapi import HTTPException
            raise HTTPException(404, f"Invoice {invoice_id} not found")
        return inv

    @router.post("/{invoice_id}/finalise", response_model=InvoiceOut)
    async def finalise_invoice(invoice_id: str, db: AsyncSession = Depends(get_db)):
        from fastapi import HTTPException
        from app.models import InvoiceStatus
        r = await db.execute(select(Invoice).options(selectinload(Invoice.line_items)).where(Invoice.id == invoice_id))
        inv = r.scalar_one_or_none()
        if not inv:
            raise HTTPException(404, f"Invoice {invoice_id} not found")
        if inv.status != InvoiceStatus.DRAFT:
            raise HTTPException(409, f"Only draft invoices can be finalised (current: {inv.status.value})")
        inv.status = InvoiceStatus.FINALISED
        await db.flush()
        return inv


# ══════════════════════════════════════════════════════════════════════════
# PAYMENTS
# ══════════════════════════════════════════════════════════════════════════
class payments:
    router = APIRouter(prefix="/payments", tags=["Payments"])

    @router.get("", response_model=list[PaymentOut])
    async def list_payments(customer_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
        return await payment_svc.list_payments(db, customer_id=customer_id)

    @router.post("", response_model=PaymentOut, status_code=201)
    async def create_payment(body: PaymentCreate, db: AsyncSession = Depends(get_db)):
        try:
            new_payment = await payment_svc.create_payment(db, body)

            await db.commit()
            await db.refresh(new_payment)
            return new_payment
        except Exception as e:
            # If anything failed (uniqueness, network, etc.), wipe the slate clean
            await db.rollback()
            # Re-raise so FastAPI handles the error response
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail="Internal Database Error")


# ══════════════════════════════════════════════════════════════════════════
# BILLING RUNS
# ══════════════════════════════════════════════════════════════════════════
class billing_runs:
    router = APIRouter(prefix="/billing-runs", tags=["Billing Runs"])

    @router.post("", response_model=BillingRunResponse, status_code=202)
    async def trigger_billing_run(body: BillingRunCreate, db: AsyncSession = Depends(get_db)):
        return BillingRunResponse(
            status="accepted",
            job_id=str(uuid.uuid4()),
            period_start=body.period_start,
            period_end=body.period_end,
            message="Billing run queued — full implementation Sprint 4",
        )

    @router.get("/{job_id}")
    async def get_billing_run_status(job_id: str):
        return {"job_id": job_id, "status": "pending", "message": "Sprint 4"}


# ══════════════════════════════════════════════════════════════════════════
# BILLING RUNS — Sprint 4 full implementation
# ══════════════════════════════════════════════════════════════════════════
class billing_runs_v2:
    router = APIRouter(prefix="/billing-runs", tags=["Billing Runs"])

    @router.post("", status_code=202)
    async def trigger_billing_run(body: BillingRunCreate, db: AsyncSession = Depends(get_db)):
        from app.services.billing import run_billing
        result = await run_billing(
            db,
            period_start=body.period_start,
            period_end=body.period_end,
            customer_id=body.customer_id,
        )
        return result

    @router.post("/rate-pending", status_code=202)
    async def rate_pending(db: AsyncSession = Depends(get_db)):
        """Rate all pending usage events immediately."""
        from app.services.rating import rate_pending_events
        return await rate_pending_events(db)

    @router.post("/renew-bundles", status_code=202)
    async def renew_bundles(period_start: str, db: AsyncSession = Depends(get_db)):
        """Renew bundle balances for a new billing period."""
        from app.services.billing import renew_bundles
        from datetime import date
        d = date.fromisoformat(period_start)
        count = await renew_bundles(db, d)
        return {"renewed": count, "period_start": period_start}


# ══════════════════════════════════════════════════════════════════════════
# INVOICE PDF DOWNLOAD — Sprint 4
# ══════════════════════════════════════════════════════════════════════════
class invoice_pdf:
    router = APIRouter(prefix="/invoices", tags=["Invoices"])

    @router.get("/{invoice_id}/pdf")
    async def download_pdf(invoice_id: str, db: AsyncSession = Depends(get_db)):
        from fastapi import HTTPException
        from fastapi.responses import FileResponse
        from app.services.pdf import get_invoice_pdf_path, generate_invoice_pdf

        # Get invoice
        r = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
        inv = r.scalar_one_or_none()
        if not inv:
            raise HTTPException(404, "Invoice not found")

        # Check if PDF already exists
        path = await get_invoice_pdf_path(inv.invoice_number)

        # Generate if missing
        if not path:
            pdf_url = await generate_invoice_pdf(inv, db)
            if pdf_url:
                inv.pdf_url = pdf_url
                await db.flush()
                path = await get_invoice_pdf_path(inv.invoice_number)

        if not path:
            raise HTTPException(503, "PDF generation not available — install WeasyPrint")

        media_type = "application/pdf" if str(path).endswith(".pdf") else "text/html"
        return FileResponse(str(path), media_type=media_type,
                          filename=f"{inv.invoice_number}.pdf")


# ══════════════════════════════════════════════════════════════════════════
# SUBSCRIPTIONS — bundle balances endpoint
# ══════════════════════════════════════════════════════════════════════════
class subscription_bundles:
    router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

    @router.get("/{sub_id}/bundles")
    async def get_bundle_balances(sub_id: str, db: AsyncSession = Depends(get_db)):
        from app.models import BundleBalance
        r = await db.execute(
            select(BundleBalance)
            .where(BundleBalance.subscription_id == sub_id)
            .order_by(BundleBalance.period_start.desc())
        )
        balances = r.scalars().all()
        return [
            {
                "id": b.id,
                "service_type": b.service_type,
                "period_start": b.period_start.isoformat(),
                "period_end": b.period_end.isoformat(),
                "allowance_total": b.allowance_total,
                "allowance_used": b.allowance_used,
                "allowance_remaining": b.allowance_remaining,
                "pct_used": round((b.allowance_used / b.allowance_total * 100), 1) if b.allowance_total else 0,
            }
            for b in balances
        ]

# ══════════════════════════════════════════════════════════════════════════
# PROVISIONING — Sprint 5
# ══════════════════════════════════════════════════════════════════════════
class provisioning:
    router = APIRouter(prefix="/provisioning", tags=["Provisioning"])

    @router.get("/workflows")
    async def list_workflows(status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
        from app.provisioning.service import list_workflows as _list_wf
        workflows = await _list_wf(db, status=status)
        return [_workflow_out(w) for w in workflows]

    @router.get("/workflows/{order_id}")
    async def get_workflow(order_id: str, db: AsyncSession = Depends(get_db)):
        from app.provisioning.models import ProvisioningWorkflow, ProvisioningStep
        from sqlalchemy.orm import selectinload
        r = await db.execute(
            select(ProvisioningWorkflow)
            .where(ProvisioningWorkflow.order_id == order_id)
            .options(selectinload(ProvisioningWorkflow.steps))
            .order_by(ProvisioningWorkflow.created_at.desc())
        )
        #wf = r.scalar_one_or_none()
        wf = r.scalars().first()
        
        if not wf:
            from fastapi import HTTPException
            raise HTTPException(404, f"No provisioning workflow found for order {order_id}")
        return _workflow_out(wf)

    @router.post("/provision/{order_id}", status_code=202)
    async def trigger_provision(order_id: str, db: AsyncSession = Depends(get_db)):
        """Manually trigger provisioning for an order (normally auto-triggered on activation)."""
        from app.provisioning.service import trigger_provision
        order = await _get_or_404_simple(db, order_id)
        wf = await trigger_provision(db, order)
        if not wf:
            return {"status": "skipped", "reason": "Provisioning not configured. Set HSS_API_URL and CGRATES_API_URL in .env"}
        return _workflow_out(wf)

    @router.post("/deprovision/{order_id}", status_code=202)
    async def trigger_deprovision(order_id: str, db: AsyncSession = Depends(get_db)):
        """Manually trigger deprovisioning for an order."""
        from app.provisioning.service import trigger_deprovision
        order = await _get_or_404_simple(db, order_id)
        wf = await trigger_deprovision(db, order)
        if not wf:
            return {"status": "skipped", "reason": "Provisioning not configured"}
        return _workflow_out(wf)


def _workflow_out(wf) -> dict:
    return {
        "id":             wf.id,
        "order_id":       wf.order_id,
        "workflow_type":  wf.workflow_type,
        "status":         wf.status,
        "error_message":  wf.error_message,
        "error_step":     wf.error_step,
        "created_at":     wf.created_at.isoformat() if wf.created_at else None,
        "completed_at":   wf.completed_at.isoformat() if wf.completed_at else None,
        "steps": [
            {
                "step_name":     s.step_name,
                "description":   s.step_description,
                "status":        s.status,
                "error_message": s.error_message,
                "started_at":    s.started_at.isoformat() if s.started_at else None,
                "completed_at":  s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in (wf.steps if hasattr(wf, 'steps') and wf.steps else [])
        ],
    }

async def _get_or_404_simple(db, order_id):
    from app.models import Order
    r = await db.execute(select(Order).where(Order.id == order_id))
    o = r.scalar_one_or_none()
    if not o:
        from fastapi import HTTPException
        raise HTTPException(404, f"Order {order_id} not found")
    return o
