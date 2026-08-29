"""Rebuild the RevenueDaily rollup from source records (drift repair / audit).

Re-derives every daily bucket from PaymentTransactions + Refunds, so any
divergence between the incremental rollup and the underlying data is corrected.

    python scripts/reconcile_revenue.py
"""
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.services import billing_admin_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reconcile_revenue")


async def main() -> None:
    """Rebuild RevenueDaily and print the number of days recomputed."""
    async with AsyncSessionLocal() as db:
        summary = await billing_admin_service.rebuild_revenue(db)
        await db.commit()
    logger.info("Revenue rebuild: %s", summary)
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
