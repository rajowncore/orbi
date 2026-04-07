"""Orbi — Customer service layer."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException

from app.models import Customer, BalanceLedger, LedgerEntryType
from app.schemas import CustomerCreate, CustomerUpdate


async def list_customers(db: AsyncSession) -> list[Customer]:
    r = await db.execute(select(Customer).order_by(Customer.created_at.desc()))
    return r.scalars().all()


async def get_customer(db: AsyncSession, customer_id: str) -> Customer:
    r = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, f"Customer {customer_id} not found")
    return c


async def create_customer(db: AsyncSession, data: CustomerCreate) -> Customer:
    # Check email uniqueness
    existing = await db.execute(select(Customer).where(Customer.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Email {data.email} already registered")

    customer = Customer(
        id=str(uuid.uuid4()),
        name=data.name,
        email=data.email,
        phone=data.phone,
        address=data.address,
        credit_type=data.credit_type,
        currency=data.currency,
        billing_cycle_day=data.billing_cycle_day,
        extra=data.extra,
    )
    db.add(customer)
    
    # Flush to get database-generated defaults (like created_at)
    # but DON'T commit yet in case the caller has more work to do.
    await db.flush()
    return customer


async def update_customer(db: AsyncSession, customer_id: str, data: CustomerUpdate) -> Customer:
    customer = await get_customer(db, customer_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(customer, field, value)
    customer.updated_at = datetime.utcnow()
    await db.flush()
    return customer


async def get_balance(db: AsyncSession, customer_id: str) -> dict:
    await get_customer(db, customer_id)  # 404 check
    r = await db.execute(
        select(func.sum(BalanceLedger.amount)).where(BalanceLedger.customer_id == customer_id)
    )
    balance = r.scalar() or 0
    entries_r = await db.execute(
        select(BalanceLedger)
        .where(BalanceLedger.customer_id == customer_id)
        .order_by(BalanceLedger.created_at.desc())
        .limit(50)
    )
    return {
        "customer_id": customer_id,
        "balance_cents": balance,
        "currency": "GBP",
        "entries": entries_r.scalars().all(),
    }
