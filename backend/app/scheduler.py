"""
Orbi — Background scheduler

Runs periodic jobs using APScheduler.
Currently schedules:
  - Balance poll every 15 minutes (checks all prepaid CGRateS accounts)

Add to main.py lifespan:
    from app.scheduler import start_scheduler, stop_scheduler
    await start_scheduler()
    yield
    await stop_scheduler()
"""
from __future__ import annotations
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def _run_balance_poll():
    """Job function — runs in scheduler context with its own DB session."""
    from app.database import AsyncSessionLocal
    from app.services.balance_alerts import poll_all_prepaid_balances
    try:
        async with AsyncSessionLocal() as db:
            result = await poll_all_prepaid_balances(db)
            await db.commit()
            if result["checked"] > 0:
                log.info(f"Balance poll: checked={result['checked']} alerts={result['alerts_fired']}")
    except Exception as e:
        log.error(f"Balance poll failed: {e}", exc_info=True)


async def start_scheduler(poll_interval_minutes: int = 15) -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_balance_poll,
        trigger=IntervalTrigger(minutes=poll_interval_minutes),
        id="balance_poll",
        name="Prepaid balance poll",
        replace_existing=True,
    )
    _scheduler.start()
    log.info(f"Scheduler started — balance poll every {poll_interval_minutes} minutes")


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
