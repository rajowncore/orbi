"""Orbi — Payment service layer."""
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models import Payment, Customer, BalanceLedger, LedgerEntryType, CreditType
from app.schemas import PaymentCreate


async def list_payments(db: AsyncSession, customer_id: str | None = None) -> list[Payment]:
    q = select(Payment)
    if customer_id:
        q = q.where(Payment.customer_id == customer_id)
    r = await db.execute(q.order_by(Payment.recorded_at.desc()))
    return r.scalars().all()


async def create_payment(db: AsyncSession, data: PaymentCreate) -> Payment:
    # Validate customer exists
    c_r = await db.execute(select(Customer).where(Customer.id == data.customer_id))
    customer = c_r.scalar_one_or_none()
    if not customer:
        raise HTTPException(404, f"Customer {data.customer_id} not found")

    payment = Payment(
        id=str(uuid.uuid4()),
        customer_id=data.customer_id,
        invoice_id=data.invoice_id,
        amount=data.amount,
        currency=data.currency,
        method=data.method,
        reference=data.reference,
        payment_date=data.payment_date,
        recorded_by=data.recorded_by,
    )
    db.add(payment)
    await db.flush()

    # Write ledger entry — topup for prepaid, payment for postpaid
    entry_type = (
        LedgerEntryType.TOPUP
        if customer.credit_type == CreditType.PREPAID
        else LedgerEntryType.PAYMENT
    )
    desc = data.description or (
        f"Top-up ref: {data.reference or payment.id}"
        if entry_type == LedgerEntryType.TOPUP
        else f"Payment ref: {data.reference or payment.id}"
    )
    ledger = BalanceLedger(
        id=str(uuid.uuid4()),
        customer_id=data.customer_id,
        entry_type=entry_type,
        amount=data.amount,       # positive = credit
        reference_id=payment.id,
        description=desc,
    )
    db.add(ledger)
    return payment
