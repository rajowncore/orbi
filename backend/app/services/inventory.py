"""Orbi — Inventory service layer."""
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models import InventoryItem, InventoryStatus, InventoryType
from app.schemas import InventoryItemCreate, InventoryBulkCreate, InventoryItemUpdate


async def list_inventory(db: AsyncSession, type: str | None = None,
                         status: str | None = None) -> list[InventoryItem]:
    q = select(InventoryItem)
    if type:
        q = q.where(InventoryItem.type == type)
    if status:
        q = q.where(InventoryItem.status == status)
    r = await db.execute(q.order_by(InventoryItem.created_at.desc()))
    return r.scalars().all()


async def get_available(db: AsyncSession, type: str | None = None) -> list[InventoryItem]:
    q = select(InventoryItem).where(InventoryItem.status == InventoryStatus.AVAILABLE)
    if type:
        q = q.where(InventoryItem.type == type)
    r = await db.execute(q.order_by(InventoryItem.value))
    return r.scalars().all()


async def get_item(db: AsyncSession, item_id: str) -> InventoryItem:
    r = await db.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = r.scalar_one_or_none()
    if not item:
        raise HTTPException(404, f"Inventory item {item_id} not found")
    return item


async def get_item_by_value(db: AsyncSession, value: str) -> InventoryItem | None:
    r = await db.execute(select(InventoryItem).where(InventoryItem.value == value))
    return r.scalar_one_or_none()


async def create_item(db: AsyncSession, data: InventoryItemCreate) -> InventoryItem:
    existing = await get_item_by_value(db, data.value)
    if existing:
        raise HTTPException(409, f"Inventory item with value '{data.value}' already exists")
    item = InventoryItem(id=str(uuid.uuid4()), type=data.type, value=data.value, extra=data.extra)
    db.add(item)
    await db.flush()
    return item


async def bulk_create(db: AsyncSession, data: InventoryBulkCreate) -> dict:
    created = 0
    skipped = 0
    errors = []
    for value in data.values:
        existing = await get_item_by_value(db, value)
        if existing:
            skipped += 1
            continue
        item = InventoryItem(id=str(uuid.uuid4()), type=data.type, value=value)
        db.add(item)
        created += 1
    await db.flush()
    return {"created": created, "skipped": skipped, "errors": errors}


async def update_item(db: AsyncSession, item_id: str, data: InventoryItemUpdate) -> InventoryItem:
    item = await get_item(db, item_id)
    if data.status:
        item.status = data.status
    await db.flush()
    return item
