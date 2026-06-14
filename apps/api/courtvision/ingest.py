from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from courtvision.database import SessionFactory
from courtvision.models import IngestionRun
from courtvision.repository import save_source_health
from courtvision.sources import (
    DelayedLiveSource,
    SourceDisabledError,
    SourcePoller,
)

logger = structlog.get_logger()


async def run_ingestion() -> None:
    async with SessionFactory() as session:
        async def record_health(health) -> None:
            await save_source_health(session, health)

        poller = SourcePoller(
            DelayedLiveSource(),
            health_recorder=record_health,
        )
        status = "completed"
        error_message: str | None = None
        records_seen = 0
        try:
            batch = await poller.poll_once("league")
            records_seen = len(batch.events)
        except SourceDisabledError as exc:
            status = "skipped"
            error_message = str(exc)
        except Exception as exc:
            status = "failed"
            error_message = str(exc)

        run = IngestionRun(
            source="delayed-live",
            status=status,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            records_seen=records_seen,
            records_written=0,
            error_message=error_message,
        )
        session.add(run)
        await session.commit()
        logger.info("ingestion_completed", status=run.status, source=run.source)


if __name__ == "__main__":
    asyncio.run(run_ingestion())
