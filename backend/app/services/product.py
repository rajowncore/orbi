"""Orbi — Product service layer."""
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models import Product, ProductStatus
from app.schemas import ProductCreate, ProductUpdate


async def list_products(db: AsyncSession, include_archived: bool = False) -> list[Product]:
    q = select(Product)
    if not include_archived:
        q = q.where(Product.status == ProductStatus.ACTIVE)
    r = await db.execute(q.order_by(Product.created_at.desc()))
    return r.scalars().all()


async def get_product(db: AsyncSession, product_id: str) -> Product:
    r = await db.execute(select(Product).where(Product.id == product_id))
    p = r.scalar_one_or_none()
    if not p:
        raise HTTPException(404, f"Product {product_id} not found")
    return p


async def create_product(db: AsyncSession, data: ProductCreate) -> Product:
    allowances_dict = data.allowances.model_dump(exclude_none=True) if data.allowances else None
    oob_dict = data.out_of_bundle_rates.model_dump(exclude_none=True) if data.out_of_bundle_rates else None

    product = Product(
        id=str(uuid.uuid4()),
        name=data.name,
        description=data.description,
        product_type=data.product_type,
        billing_model=data.billing_model,
        price_config=data.price_config,
        allowances=allowances_dict,
        out_of_bundle_rates=oob_dict,
        requires_inventory=data.requires_inventory,
        inventory_type=data.inventory_type,
        currency=data.currency,
    )
    db.add(product)
    await db.flush()
    return product


async def update_product(db: AsyncSession, product_id: str, data: ProductUpdate) -> Product:
    product = await get_product(db, product_id)
    updates = data.model_dump(exclude_none=True)

    if "allowances" in updates and data.allowances:
        updates["allowances"] = data.allowances.model_dump(exclude_none=True)
    if "out_of_bundle_rates" in updates and data.out_of_bundle_rates:
        updates["out_of_bundle_rates"] = data.out_of_bundle_rates.model_dump(exclude_none=True)

    for field, value in updates.items():
        setattr(product, field, value)
    await db.flush()
    return product
