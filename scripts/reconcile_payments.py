"""Reconcile pending payments against the gateway (recover lost IPN/return).

Queries each expired-pending order via the gateway's QueryDr and fulfils or
expires it. Run on a schedule (cron / Task Scheduler) or manually:

    python scripts/reconcile_payments.py
"""
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.services import payment_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reconcile_payments")


async def main() -> None:
    """Run one reconciliation pass and print the summary."""
    async with AsyncSessionLocal() as db:
        summary = await payment_service.reconcile_pending(db)
        await db.commit()
    logger.info("Reconciliation summary: %s", summary)
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
