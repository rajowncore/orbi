"""
Orbi Billing — FastAPI application entry point.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InternalError

from app.config import settings
from app.database import engine
from app.models import Base
from app.provisioning import models as _prov_models  # noqa: registers tables
from app.routers import (
    customers, products, inventory, orders,
    subscriptions, usage, invoices, payments, billing_runs,
    billing_runs_v2, invoice_pdf, subscription_bundles, provisioning
)

PDF_DIR = Path(__file__).parent.parent / "pdfs"
PDF_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    _log = logging.getLogger(__name__)

    # Create DB tables if they don't exist. In production, use Alembic migrations instead.
    async with engine.begin() as conn:
        try:
            # This is the "safe" way to run creation in multi-worker environments
            await conn.run_sync(Base.metadata.create_all)
        except (IntegrityError, InternalError) as e:
            # If workers race to create the same Enum, just ignore it
            print(f"Database sync skipped or already handled: {e}")
        
        # Initialise OCS engine based on OCS_MODE config
        from app.engine import init_engine_from_config
        ocs = init_engine_from_config()
        _log.info(f"Orbi started — OCS engine: {ocs.get_name()}")

        # Health check CGRateS if active
        from app.engine.cgrates import CGRatesChargingEngine
        if isinstance(ocs, CGRatesChargingEngine):
            health = await ocs.health_check()
            _log.info(f"CGRateS health: {health}")
            if health["status"] != "ok":
                _log.warning(
                    "CGRateS is unreachable at startup. "
                    "Rating and billing will fail until CGRateS is available. "
                    "Check CGRATES_API_URL in .env"
                )
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Generic billing engine — domain agnostic, BSS-grade.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated PDFs as static files
app.mount("/pdfs", StaticFiles(directory=str(PDF_DIR)), name="pdfs")

PREFIX = "/api/v1"

# Sprint 1+2 routers
app.include_router(customers.router,             prefix=PREFIX)
app.include_router(products.router,              prefix=PREFIX)
app.include_router(inventory.router,             prefix=PREFIX)
app.include_router(orders.router,                prefix=PREFIX)
app.include_router(subscriptions.router,         prefix=PREFIX)
app.include_router(usage.router,                 prefix=PREFIX)
app.include_router(invoices.router,              prefix=PREFIX)
app.include_router(payments.router,              prefix=PREFIX)

# Sprint 4 routers (replace billing_runs stub)
app.include_router(billing_runs_v2.router,       prefix=PREFIX)
app.include_router(invoice_pdf.router,           prefix=PREFIX)
app.include_router(subscription_bundles.router,  prefix=PREFIX)
app.include_router(provisioning.router,          prefix=PREFIX)

@app.get("/health")
async def health():
    from app.engine import get_active_engine
    return {
        "status":  "ok",
        "version": settings.APP_VERSION,
        "engine":  get_active_engine().get_name(),
        "ocs_mode": settings.OCS_MODE,
    }

@app.get("/api/v1/engine/status")
async def engine_status():
    from app.config import settings
    from app.engine import get_active_engine, _ENGINES
    engine = get_active_engine()
    result = {
        "ocs_mode":          settings.OCS_MODE,
        "active_engine":     engine.get_name(),
        "registered_engines": list(_ENGINES.keys()),
    }
    from app.engine.cgrates import CGRatesChargingEngine
    if isinstance(engine, CGRatesChargingEngine):
        result["cgrates_health"] = await engine.health_check()
        result["cgrates_url"]    = settings.CGRATES_API_URL
        result["cgrates_tenant"] = settings.CGRATES_TENANT
    return result
