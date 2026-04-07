"""
Orbi Billing — Demo Seed Data Script
=====================================
Populates your local database with realistic demo data:

  - 5 products  (2 base packages, 1 roaming, 2 add-ons)
  - 20 MSISDNs + 20 SIM cards in inventory
  - 8 customers (mix of postpaid and prepaid)
  - 10 orders   (active, pending, suspended, cancelled)
  - Usage events per active subscription
  - Invoices + payments

Usage:
  cd orbi/backend
  python seed.py

  # Reset and re-seed:
  python seed.py --reset
"""
import asyncio
import argparse
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

# ── Make sure we can import the app ───────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

#os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./orbi.db")
# UPDATE: Changed to PostgreSQL async driver (asyncpg)
# Logic: Priority 1: OS Env (Docker), Priority 2: Local Postgres, Priority 3: Fallback
POSTGRES_DEFAULT = "postgresql+asyncpg://postgres:pass@localhost:5432/orbi"
os.environ.setdefault("DATABASE_URL", POSTGRES_DEFAULT)

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.config import settings
from app.models import (
    Base,
    Customer, CreditType, CustomerStatus,
    Product, ProductType, BillingModel, ProductStatus,
    InventoryItem, InventoryType, InventoryStatus,
    Order, OrderStatus,
    Subscription, SubscriptionStatus,
    BundleBalance, ServiceType,
    UsageEvent, UsageEventStatus,
    Invoice, InvoiceStatus,
    InvoiceLineItem,
    BalanceLedger, LedgerEntryType,
    Payment, PaymentMethod,
    ChargeRecord, ChargeType,
)

# ── Engine ────────────────────────────────────────────────────────────────
#engine = create_async_engine(settings.DATABASE_URL, echo=False)
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False,
    pool_pre_ping=True
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Helpers ───────────────────────────────────────────────────────────────
def uid() -> str:
    return str(uuid.uuid4())

def ago(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=days)

def ago_date(days: int) -> date:
    return date.today() - timedelta(days=days)

def month_end(d: date) -> date:
    from calendar import monthrange
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


# ══════════════════════════════════════════════════════════════════════════
# DATA DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════

PRODUCTS = [
    # Base packages
    {
        "id": uid(), "name": "Home Mobile",
        "description": "Our flagship monthly plan — 1GB data, 100 minutes, 100 SMS",
        "product_type": ProductType.BASE,
        "billing_model": BillingModel.RECURRING,
        "price_config": {"amount": 1999, "interval": "month", "interval_count": 1},
        "allowances": {"data_mb": 1024, "voice_mins": 100, "sms": 100},
        "out_of_bundle_rates": {"data_mb": 2, "voice_mins": 5, "sms": 10},
        "requires_inventory": True, "inventory_type": "msisdn",
        "currency": "GBP",
    },
    {
        "id": uid(), "name": "Home Mobile Plus",
        "description": "Premium plan — 5GB data, 500 minutes, unlimited SMS",
        "product_type": ProductType.BASE,
        "billing_model": BillingModel.RECURRING,
        "price_config": {"amount": 3499, "interval": "month", "interval_count": 1},
        "allowances": {"data_mb": 5120, "voice_mins": 500, "sms": 9999},
        "out_of_bundle_rates": {"data_mb": 1, "voice_mins": 3, "sms": 0},
        "requires_inventory": True, "inventory_type": "msisdn",
        "currency": "GBP",
    },
    # Roaming
    {
        "id": uid(), "name": "Euro Roam",
        "description": "EU roaming bolt-on — 500MB, 60 minutes, 50 SMS across 30 countries",
        "product_type": ProductType.ROAMING,
        "billing_model": BillingModel.RECURRING,
        "price_config": {"amount": 999, "interval": "month", "interval_count": 1},
        "allowances": {"data_mb": 500, "voice_mins": 60, "sms": 50},
        "out_of_bundle_rates": {"data_mb": 5, "voice_mins": 10, "sms": 15},
        "requires_inventory": False, "inventory_type": None,
        "currency": "GBP",
    },
    # Add-ons
    {
        "id": uid(), "name": "1GB Data Add-on",
        "description": "Extra 1GB data — use it anytime this month",
        "product_type": ProductType.ADDON,
        "billing_model": BillingModel.ONE_TIME,
        "price_config": {"amount": 500},
        "allowances": {"data_mb": 1024},
        "out_of_bundle_rates": None,
        "requires_inventory": False, "inventory_type": None,
        "currency": "GBP",
    },
    {
        "id": uid(), "name": "100 Min Voice Add-on",
        "description": "Extra 100 minutes — perfect for heavy callers",
        "product_type": ProductType.ADDON,
        "billing_model": BillingModel.ONE_TIME,
        "price_config": {"amount": 300},
        "allowances": {"voice_mins": 100},
        "out_of_bundle_rates": None,
        "requires_inventory": False, "inventory_type": None,
        "currency": "GBP",
    },
]

CUSTOMERS = [
    {
        "id": uid(), "name": "James Okafor",
        "email": "james.okafor@example.com", "phone": "+447700900001",
        "address": "12 Oak Lane, London, E1 6RF",
        "credit_type": CreditType.POSTPAID, "currency": "GBP",
        "billing_cycle_day": 1, "status": CustomerStatus.ACTIVE,
    },
    {
        "id": uid(), "name": "Priya Nair",
        "email": "priya.nair@example.com", "phone": "+447700900002",
        "address": "45 Maple Avenue, Manchester, M1 2AB",
        "credit_type": CreditType.PREPAID, "currency": "GBP",
        "billing_cycle_day": 1, "status": CustomerStatus.ACTIVE,
    },
    {
        "id": uid(), "name": "Lars Eriksen",
        "email": "lars.eriksen@example.com", "phone": "+447700900003",
        "address": "8 Birch Street, Edinburgh, EH1 3CD",
        "credit_type": CreditType.POSTPAID, "currency": "GBP",
        "billing_cycle_day": 1, "status": CustomerStatus.ACTIVE,
    },
    {
        "id": uid(), "name": "Aisha Kamara",
        "email": "aisha.kamara@example.com", "phone": "+447700900004",
        "address": "22 Cedar Road, Birmingham, B1 4EF",
        "credit_type": CreditType.PREPAID, "currency": "GBP",
        "billing_cycle_day": 1, "status": CustomerStatus.ACTIVE,
    },
    {
        "id": uid(), "name": "Tom Whitfield",
        "email": "tom.whitfield@example.com", "phone": "+447700900005",
        "address": "5 Elm Close, Bristol, BS1 5GH",
        "credit_type": CreditType.POSTPAID, "currency": "GBP",
        "billing_cycle_day": 1, "status": CustomerStatus.SUSPENDED,
    },
    {
        "id": uid(), "name": "Sofia Reyes",
        "email": "sofia.reyes@example.com", "phone": "+447700900006",
        "address": "31 Pine Way, Leeds, LS1 6IJ",
        "credit_type": CreditType.POSTPAID, "currency": "GBP",
        "billing_cycle_day": 15, "status": CustomerStatus.ACTIVE,
    },
    {
        "id": uid(), "name": "Mohammed Al-Rashid",
        "email": "m.alrashid@example.com", "phone": "+447700900007",
        "address": "17 Willow Court, Cardiff, CF1 7KL",
        "credit_type": CreditType.POSTPAID, "currency": "GBP",
        "billing_cycle_day": 1, "status": CustomerStatus.ACTIVE,
    },
    {
        "id": uid(), "name": "Yuki Tanaka",
        "email": "yuki.tanaka@example.com", "phone": "+447700900008",
        "address": "99 Ash Boulevard, Glasgow, G1 8MN",
        "credit_type": CreditType.PREPAID, "currency": "GBP",
        "billing_cycle_day": 1, "status": CustomerStatus.ACTIVE,
    },
]

MSISDNS = [
    "+447700900001", "+447700900002", "+447700900003", "+447700900004",
    "+447700900005", "+447700900006", "+447700900007", "+447700900008",
    "+447700900009", "+447700900010", "+447700900011", "+447700900012",
    "+447700900013", "+447700900014", "+447700900015", "+447700900016",
    "+447700900017", "+447700900018", "+447700900019", "+447700900020",
]

SIM_ICCIDS = [
    "8944501000000000001", "8944501000000000002", "8944501000000000003",
    "8944501000000000004", "8944501000000000005", "8944501000000000006",
    "8944501000000000007", "8944501000000000008", "8944501000000000009",
    "8944501000000000010", "8944501000000000011", "8944501000000000012",
    "8944501000000000013", "8944501000000000014", "8944501000000000015",
    "8944501000000000016", "8944501000000000017", "8944501000000000018",
    "8944501000000000019", "8944501000000000020",
]


# ══════════════════════════════════════════════════════════════════════════
# SEED FUNCTION
# ══════════════════════════════════════════════════════════════════════════

async def seed(db: AsyncSession):
    print("\n🌱  Orbi seed data — starting...\n")

    # ── Products ───────────────────────────────────────────────────────────
    print("  📦  Creating products...")
    product_objs = {}
    for p in PRODUCTS:
        obj = Product(
            id=p["id"], name=p["name"], description=p["description"],
            product_type=p["product_type"], billing_model=p["billing_model"],
            price_config=p["price_config"], allowances=p["allowances"],
            out_of_bundle_rates=p.get("out_of_bundle_rates"),
            requires_inventory=p["requires_inventory"],
            inventory_type=p["inventory_type"], currency=p["currency"],
        )
        db.add(obj)
        product_objs[p["name"]] = obj
    await db.flush()
    print(f"     ✓  {len(PRODUCTS)} products created")

    # ── Inventory ──────────────────────────────────────────────────────────
    print("  📱  Creating inventory...")
    msisdn_objs = []
    for msisdn in MSISDNS:
        item = InventoryItem(id=uid(), type=InventoryType.MSISDN, value=msisdn)
        db.add(item)
        msisdn_objs.append(item)
    sim_objs = []
    for iccid in SIM_ICCIDS:
        item = InventoryItem(id=uid(), type=InventoryType.SIM, value=iccid)
        db.add(item)
        sim_objs.append(item)
    await db.flush()
    print(f"     ✓  {len(MSISDNS)} MSISDNs + {len(SIM_ICCIDS)} SIMs created")

    # ── Customers ──────────────────────────────────────────────────────────
    print("  👤  Creating customers...")
    customer_objs = {}
    for i, c in enumerate(CUSTOMERS):
        obj = Customer(
            id=c["id"], name=c["name"], email=c["email"],
            phone=c["phone"], address=c["address"],
            credit_type=c["credit_type"], currency=c["currency"],
            billing_cycle_day=c["billing_cycle_day"], status=c["status"],
            created_at=ago(90 - i * 8),
        )
        db.add(obj)
        customer_objs[c["name"]] = obj
    await db.flush()
    print(f"     ✓  {len(CUSTOMERS)} customers created")

    # ── Prepaid top-ups (before orders) ───────────────────────────────────
    print("  💳  Adding prepaid top-ups...")
    prepaid_customers = ["Priya Nair", "Aisha Kamara", "Yuki Tanaka"]
    topup_amounts = [3000, 5000, 2000]  # £30, £50, £20
    for name, amount in zip(prepaid_customers, topup_amounts):
        c = customer_objs[name]
        entry = BalanceLedger(
            id=uid(), customer_id=c.id,
            entry_type=LedgerEntryType.TOPUP,
            amount=amount,
            description=f"Initial top-up",
            created_at=ago(60),
        )
        db.add(entry)
    await db.flush()

    # ── Orders + Subscriptions + Bundle balances ───────────────────────────
    print("  📋  Creating orders and subscriptions...")

    today = date.today()
    period_start = date(today.year, today.month, 1)
    period_end_d = month_end(period_start)

    order_counter = [0]

    async def make_active_order(customer_name, product_name, msisdn_obj, days_ago=30, parent_order_id=None):
        order_counter[0] += 1
        c = customer_objs[customer_name]
        p = product_objs[product_name]
        activated = ago(days_ago)
        order_num = f"ORD-{datetime.utcnow().year}-{str(order_counter[0]).zfill(5)}"

        order = Order(
            id=uid(), order_number=order_num,
            customer_id=c.id, product_id=p.id,
            parent_order_id=parent_order_id,
            status=OrderStatus.ACTIVE,
            activated_at=activated, created_at=activated,
        )
        db.add(order)
        await db.flush()

        if msisdn_obj:
            msisdn_obj.status = InventoryStatus.ASSIGNED
            msisdn_obj.assigned_to_order_id = order.id
            msisdn_obj.assigned_at = activated

        sub = Subscription(
            id=uid(), order_id=order.id,
            customer_id=c.id, product_id=p.id,
            quantity="1", start_date=activated.date(),
            status=SubscriptionStatus.ACTIVE,
            created_at=activated,
        )
        db.add(sub)
        await db.flush()

        # Bundle balances
        if p.allowances:
            svc_map = {"data_mb": ServiceType.DATA, "voice_mins": ServiceType.VOICE, "sms": ServiceType.SMS}
            for field, svc in svc_map.items():
                total = p.allowances.get(field)
                if not total:
                    continue
                # Simulate some usage
                used_pct = {"data_mb": 0.74, "voice_mins": 0.32, "sms": 0.15}.get(field, 0.5)
                used = int(total * used_pct)
                bb = BundleBalance(
                    id=uid(), subscription_id=sub.id,
                    period_start=period_start, period_end=period_end_d,
                    service_type=svc,
                    allowance_total=total, allowance_used=used,
                    allowance_remaining=total - used,
                )
                db.add(bb)

        # Debit prepaid on activation
        if c.credit_type == CreditType.PREPAID:
            price = p.price_config.get("amount", 0)
            if price > 0:
                debit = BalanceLedger(
                    id=uid(), customer_id=c.id,
                    entry_type=LedgerEntryType.CHARGE,
                    amount=-price,
                    reference_id=order.id,
                    description=f"Package activation: {p.name}",
                    created_at=activated,
                )
                db.add(debit)

        return order, sub

    # ── Active orders ──────────────────────────────────────────────────────
    o1, s1 = await make_active_order("James Okafor",      "Home Mobile",       msisdn_objs[0], 45)
    o2, s2 = await make_active_order("Priya Nair",        "Home Mobile",       msisdn_objs[1], 30)
    o3, s3 = await make_active_order("Lars Eriksen",      "Home Mobile Plus",  msisdn_objs[2], 60)
    o4, s4 = await make_active_order("Aisha Kamara",      "Home Mobile",       msisdn_objs[3], 20)
    o5, s5 = await make_active_order("Sofia Reyes",       "Home Mobile Plus",  msisdn_objs[5], 35)
    o6, s6 = await make_active_order("Mohammed Al-Rashid","Home Mobile",       msisdn_objs[6], 25)
    o7, s7 = await make_active_order("Yuki Tanaka",       "Home Mobile",       msisdn_objs[7], 15)

    # Add-on for James (stacked on o1)
    o_addon, s_addon = await make_active_order(
        "James Okafor", "1GB Data Add-on", None, 10, parent_order_id=o1.id
    )

    # Euro Roam for Lars
    o_roam, s_roam = await make_active_order(
        "Lars Eriksen", "Euro Roam", None, 20, parent_order_id=o3.id
    )

    # ── Pending order ──────────────────────────────────────────────────────
    order_counter[0] += 1
    pend_order = Order(
        id=uid(), order_number=f"ORD-{datetime.utcnow().year}-{str(order_counter[0]).zfill(5)}",
        customer_id=customer_objs["Mohammed Al-Rashid"].id,
        product_id=product_objs["100 Min Voice Add-on"].id,
        parent_order_id=o6.id,
        status=OrderStatus.PENDING, created_at=ago(2),
    )
    db.add(pend_order)

    # ── Suspended order (Tom Whitfield) ───────────────────────────────────
    order_counter[0] += 1
    susp_inv = msisdn_objs[4]
    susp_inv.status = InventoryStatus.ASSIGNED
    susp_order = Order(
        id=uid(), order_number=f"ORD-{datetime.utcnow().year}-{str(order_counter[0]).zfill(5)}",
        customer_id=customer_objs["Tom Whitfield"].id,
        product_id=product_objs["Home Mobile"].id,
        status=OrderStatus.SUSPENDED,
        activated_at=ago(60), suspended_at=ago(5), created_at=ago(60),
    )
    db.add(susp_order)
    susp_inv.assigned_to_order_id = susp_order.id

    # ── Cancelled order ────────────────────────────────────────────────────
    order_counter[0] += 1
    canc_order = Order(
        id=uid(), order_number=f"ORD-{datetime.utcnow().year}-{str(order_counter[0]).zfill(5)}",
        customer_id=customer_objs["Tom Whitfield"].id,
        product_id=product_objs["1GB Data Add-on"].id,
        status=OrderStatus.CANCELLED,
        activated_at=ago(90), cancelled_at=ago(30), created_at=ago(90),
    )
    db.add(canc_order)

    await db.flush()
    print(f"     ✓  {order_counter[0]} orders created (8 active, 1 pending, 1 suspended, 1 cancelled)")

    # ── Usage events ───────────────────────────────────────────────────────
    print("  📡  Generating usage events...")
    usage_count = 0

    usage_scenarios = [
        # (subscription, msisdn, event_type, qty, unit, days_ago_list)
        (s1, "+447700900001", "data",  "102.5",  "mb",      [0, 0, 1, 1, 2, 2, 3]),
        (s1, "+447700900001", "voice", "4",       "minutes", [0, 1, 2, 3, 4]),
        (s1, "+447700900001", "sms",   "3",       "messages",[0, 1, 2]),
        (s2, "+447700900002", "data",  "256",     "mb",      [0, 1, 2, 3]),
        (s2, "+447700900002", "voice", "12",      "minutes", [0, 1]),
        (s3, "+447700900003", "data",  "512",     "mb",      [0, 0, 1, 1, 2]),
        (s3, "+447700900003", "voice", "45",      "minutes", [0, 1, 2]),
        (s4, "+447700900004", "data",  "88",      "mb",      [0, 1, 2]),
        (s5, "+447700900006", "data",  "1024",    "mb",      [0, 1]),
        (s6, "+447700900007", "data",  "50",      "mb",      [0, 1, 2, 3]),
        (s7, "+447700900008", "data",  "200",     "mb",      [0, 1]),
    ]

    for sub, msisdn, etype, qty, unit, days_list in usage_scenarios:
        for i, d in enumerate(days_list):
            event = UsageEvent(
                id=uid(),
                event_id=uid(),
                msisdn=msisdn,
                subscription_id=sub.id,
                customer_id=sub.customer_id,
                event_type=etype,
                quantity=qty,
                unit=unit,
                event_timestamp=ago(d) - timedelta(hours=i*2),
                source_system="sftp:pgw01",
                status=UsageEventStatus.RATED,
            )
            db.add(event)
            usage_count += 1

    await db.flush()
    print(f"     ✓  {usage_count} usage events created")

    # ── Charge records ─────────────────────────────────────────────────────
    print("  💰  Creating charge records...")
    charge_count = 0

    prev_period_start = date(today.year, today.month - 1 if today.month > 1 else 12, 1)
    prev_period_end   = month_end(prev_period_start)

    charge_scenarios = [
        # (sub, customer_name, product_name, billed, period)
        (s1, "James Okafor",       "Home Mobile",      True,  (prev_period_start, prev_period_end)),
        (s2, "Priya Nair",         "Home Mobile",      True,  (prev_period_start, prev_period_end)),
        (s3, "Lars Eriksen",       "Home Mobile Plus", True,  (prev_period_start, prev_period_end)),
        (s4, "Aisha Kamara",       "Home Mobile",      True,  (prev_period_start, prev_period_end)),
        (s5, "Sofia Reyes",        "Home Mobile Plus", False, (period_start, period_end_d)),
        (s6, "Mohammed Al-Rashid", "Home Mobile",      False, (period_start, period_end_d)),
        (s7, "Yuki Tanaka",        "Home Mobile",      False, (period_start, period_end_d)),
    ]

    invoice_map = {}  # customer_name -> Invoice (for billed charges)

    for sub, cname, pname, billed, (ps, pe) in charge_scenarios:
        c = customer_objs[cname]
        p = product_objs[pname]
        amount = p.price_config.get("amount", 0)

        cr = ChargeRecord(
            id=uid(), customer_id=c.id, subscription_id=sub.id,
            amount=amount, currency="GBP",
            charge_type=ChargeType.RECURRING,
            description=f"{p.name} — monthly subscription",
            period_start=ps, period_end=pe,
            billed=billed, rated_at=ago(35 if billed else 5),
        )
        db.add(cr)
        charge_count += 1

        if billed and cname not in invoice_map:
            invoice_map[cname] = (cr, c, p, ps, pe)

    await db.flush()
    print(f"     ✓  {charge_count} charge records created")

    # ── Invoices ───────────────────────────────────────────────────────────
    print("  🧾  Generating invoices...")
    inv_count = 0

    inv_statuses = {
        "James Okafor":  InvoiceStatus.PAID,
        "Priya Nair":    InvoiceStatus.PAID,
        "Lars Eriksen":  InvoiceStatus.SENT,
        "Aisha Kamara":  InvoiceStatus.DRAFT,
    }

    inv_num_base = 1
    for cname, (cr, c, p, ps, pe) in invoice_map.items():
        inv_num = f"INV-{datetime.utcnow().year}-{str(inv_num_base).zfill(5)}"
        inv_num_base += 1
        amount = p.price_config.get("amount", 0)
        status = inv_statuses.get(cname, InvoiceStatus.SENT)

        inv = Invoice(
            id=uid(), invoice_number=inv_num,
            customer_id=c.id,
            period_start=ps, period_end=pe,
            status=status,
            subtotal=amount, total=amount,
            currency="GBP",
            due_date=pe + timedelta(days=5),
            created_at=ago(30),
        )
        db.add(inv)
        await db.flush()

        # Link charge record to invoice
        cr.invoice_id = inv.id
        cr.billed = True

        # Line item
        li = InvoiceLineItem(
            id=uid(), invoice_id=inv.id, charge_record_id=cr.id,
            description=f"{p.name} — {ps.strftime('%B %Y')}",
            quantity="1", unit_price=amount, amount=amount,
        )
        db.add(li)
        inv_count += 1

    await db.flush()
    print(f"     ✓  {inv_count} invoices created")

    # ── Payments ───────────────────────────────────────────────────────────
    print("  💸  Recording payments...")
    pay_count = 0

    paid_customers = ["James Okafor", "Priya Nair"]
    for cname in paid_customers:
        c = customer_objs[cname]
        p_obj = product_objs["Home Mobile"]
        amount = p_obj.price_config["amount"]

        payment = Payment(
            id=uid(), customer_id=c.id,
            amount=amount, currency="GBP",
            method=PaymentMethod.BANK_TRANSFER,
            reference=f"REF-{str(pay_count+1).zfill(4)}",
            payment_date=ago_date(25),
            recorded_at=ago(25),
            recorded_by="operator",
        )
        db.add(payment)

        ledger = BalanceLedger(
            id=uid(), customer_id=c.id,
            entry_type=LedgerEntryType.PAYMENT,
            amount=amount,
            reference_id=payment.id,
            description=f"Payment received — {payment.reference}",
            created_at=ago(25),
        )
        db.add(ledger)
        pay_count += 1

    # Extra top-up for Aisha
    aisha = customer_objs["Aisha Kamara"]
    topup2 = BalanceLedger(
        id=uid(), customer_id=aisha.id,
        entry_type=LedgerEntryType.TOPUP,
        amount=1000,
        description="Top-up via voucher",
        created_at=ago(10),
    )
    db.add(topup2)

    await db.flush()
    print(f"     ✓  {pay_count} payments + ledger entries created")

    print("\n  ✅  Seed complete!\n")
    print("  Summary:")
    print(f"     Products   : {len(PRODUCTS)}")
    print(f"     MSISDNs    : {len(MSISDNS)}  ({len(MSISDNS)-8} available)")
    print(f"     SIM cards  : {len(SIM_ICCIDS)}  ({len(SIM_ICCIDS)-0} available)")
    print(f"     Customers  : {len(CUSTOMERS)}  (6 postpaid, 3 prepaid)")
    print(f"     Orders     : {order_counter[0]}  (8 active, 1 pending, 1 suspended, 1 cancelled)")
    print(f"     Usage events: {usage_count}")
    print(f"     Invoices   : {inv_count}")
    print(f"     Payments   : {pay_count}")
    print()
    print("  Open http://localhost:5173 to see it all in the frontend.\n")


# ══════════════════════════════════════════════════════════════════════════
# RESET
# ══════════════════════════════════════════════════════════════════════════

async def reset_db():
    print("  🗑️   Dropping and recreating all tables (CASCADE)...")
    async with engine.begin() as conn:
        # 1. Drop the public schema and everything in it
        await conn.execute(text("DROP SCHEMA public CASCADE;"))
        # 2. Recreate the schema
        await conn.execute(text("CREATE SCHEMA public;"))
        # 3. Grant permissions back (standard for Postgres)
        await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        
        # 4. Rebuild tables from models
        await conn.run_sync(Base.metadata.create_all)
    print("  ✓   Tables reset\n")

# ══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="Orbi seed data script")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables first")
    args = parser.parse_args()

    if args.reset:
        await reset_db()
    else:
        # Ensure tables exist without wiping data
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        try:
            await seed(db)
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"\n  ❌  Seed failed: {e}")
            import traceback; traceback.print_exc()
            raise

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
