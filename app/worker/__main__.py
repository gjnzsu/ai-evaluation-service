import asyncio
import os
import socket

from app.config import get_settings
from app.engine import EvaluationEngine
from app.observability.logging import configure_json_logging
from app.persistence import Database, JobRepository
from app.worker.judge import DisabledOptionalJudge
from app.worker.runner import run
from app.worker.service import WorkerService


async def main() -> None:
    configure_json_logging()
    settings = get_settings()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    async with Database(settings.database_url) as database:
        worker = WorkerService(
            JobRepository(database.sessions),
            EvaluationEngine(),
            DisabledOptionalJudge(),
            worker_id,
            settings.job_lease_seconds,
        )
        await run(worker, settings.worker_poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
