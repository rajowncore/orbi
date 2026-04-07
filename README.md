# Orbi Billing

Generic billing engine — domain agnostic, BSS-grade.

## Quick Start

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate.bat    # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for interactive API documentation.

## Project Structure

```
orbi/
├── backend/
│   ├── app/
│   │   ├── models/       # SQLAlchemy ORM — all 14 database tables
│   │   ├── routers/      # FastAPI route handlers — all 9 domains
│   │   ├── services/     # Business logic (Sprint 2+)
│   │   ├── engine/       # Billing engine wrappers (Sprint 4)
│   │   ├── mediation/    # Mediation layer (Sprint 3)
│   │   ├── schemas/      # Pydantic request/response schemas (Sprint 2)
│   │   ├── main.py       # FastAPI app entry point
│   │   ├── database.py   # DB engine and session factory
│   │   └── config.py     # Settings (reads from .env)
│   ├── alembic/          # Database migrations
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── engine/               # Pure Python billing engine (no I/O)
│   ├── models.py         # Domain dataclasses
│   └── calculator.py     # Billing calculation logic
├── tests/
│   └── test_engine.py    # 28 billing engine tests
└── docker-compose.yml
```

## Database Tables (Sprint 1)

| Table | Purpose |
|-------|---------|
| customers | Customer profiles, prepaid/postpaid flag |
| products | Package catalog with pricing and allowances |
| inventory_items | MSISDN and SIM card pool |
| orders | Customer package purchases |
| subscriptions | Active billing relationships |
| bundle_balances | Remaining allowance per sub per period |
| mediation_files | CSV file tracking |
| usage_events | Canonical usage records |
| dead_letter_records | Failed/rejected events (replayable) |
| charge_records | Rating engine output |
| invoices | Generated invoices |
| invoice_line_items | Invoice line details |
| balance_ledger | Append-only financial ledger |
| payments | Recorded payments |

## API Endpoints

All endpoints available at http://localhost:8000/docs

- `/api/v1/customers` — customer management
- `/api/v1/products` — product catalog
- `/api/v1/inventory` — MSISDN/SIM pool
- `/api/v1/orders` — order lifecycle (activate/suspend/cancel)
- `/api/v1/subscriptions` — active subscriptions
- `/api/v1/usage/events` — usage event ingestion
- `/api/v1/invoices` — invoice management
- `/api/v1/payments` — payment recording
- `/api/v1/billing-runs` — billing run triggers

## Sprint Plan

- ✅ Sprint 1 — Models, migrations, FastAPI skeleton
- 🔜 Sprint 2 — Order service, inventory assignment, state machine
- 🔜 Sprint 3 — Mediation layer (CSV + REST)
- 🔜 Sprint 4 — Rating engine, billing runs, invoice PDF
- 🔜 Sprint 5 — React CM/CRM frontend
- 🔜 Sprint 6 — Integration testing, Docker, demo data
