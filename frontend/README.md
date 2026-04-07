# Orbi CM — React Frontend

Full CM/CRM interface for Orbi Billing. Built with Vite + React 18 + TanStack Query + Tailwind CSS.

## Quick Start

```bash
# 1. Make sure the backend is running first
cd ../backend
uvicorn app.main:app --reload

# 2. In a new terminal, start the frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

The Vite dev server proxies all `/api` requests to `http://localhost:8000`
so no CORS issues during development.

## Pages

| Route | Page |
|-------|------|
| `/` | Dashboard — KPIs, recent orders, quick actions, inventory snapshot |
| `/customers` | Customer list with search and type filter |
| `/customers/:id` | Customer 360 view — profile, orders, invoices, balance |
| `/products` | Product catalog — base packages, add-ons, roaming |
| `/orders` | Order management — activate, suspend, cancel |
| `/inventory` | MSISDN and SIM pool management |
| `/invoices` | Invoice list with billing run trigger |
| `/usage` | Usage event ingestion — CSV upload + event list |
| `/payments` | Payment recording and history |

## Modals

- **Create Customer** — name, email, phone, credit type, currency, billing day
- **Create Product** — name, type, billing model, price, bundle allowances
- **Create Order** — customer, product, MSISDN/SIM assignment
- **Add Inventory** — single MSISDN/SIM or bulk import (one per line)
- **Record Payment** — amount, method, reference, invoice link

## Project Structure

```
src/
├── App.jsx              # React Router config
├── main.jsx             # Entry point, QueryClient
├── index.css            # Tailwind + custom component classes
├── lib/
│   ├── api.js           # Axios API client — all endpoints
│   └── utils.js         # fmt helpers, status badge mapping
├── components/
│   ├── layout/
│   │   └── Layout.jsx   # Sidebar + topbar shell
│   ├── ui/
│   │   └── index.jsx    # Spinner, Modal, Empty, StatCard, UsageBar etc.
│   └── modals/
│       ├── CreateCustomerModal.jsx
│       ├── CreateProductModal.jsx
│       ├── CreateOrderModal.jsx
│       ├── AddInventoryModal.jsx
│       └── RecordPaymentModal.jsx
└── pages/
    ├── Dashboard.jsx
    ├── Customers.jsx    # List + Customer 360 detail
    └── Pages.jsx        # Products, Orders, Inventory, Invoices, Usage, Payments
```

## Connecting to the Backend

The API base URL is `/api/v1` — proxied to `http://localhost:8000` by Vite.
If you deploy separately, set `VITE_API_BASE_URL` in a `.env` file and
update `src/lib/api.js` accordingly.
