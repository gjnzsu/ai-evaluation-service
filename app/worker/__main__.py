import asyncio
import os
import socket

from app.config import get_settings
from app.engine import EvaluationEngine
from app.observability.logging import configure_json_logging, log_safe
from app.persistence import Database, JobRepository
from app.worker.decision_runtime import (
    DecisionJudgeConfigurationError,
    build_decision_judge,
)
from app.worker.judge import DisabledOptionalJudge
from app.worker.runner import run
from app.worker.service import WorkerService


async def main() -> None:
    configure_json_logging()
    settings = get_settings()
    decision_judge = build_decision_judge(settings)
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    async with Database(settings.database_url) as database:
        worker = WorkerService(
            JobRepository(database.sessions),
            EvaluationEngine(),
            DisabledOptionalJudge(),
            worker_id,
            settings.job_lease_seconds,
            decision_judge=decision_judge,
        )
        await run(worker, settings.worker_poll_seconds)


def entrypoint() -> int:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        return 0
    except DecisionJudgeConfigurationError:
        logger = configure_json_logging()
        log_safe(
            logger,
            event="worker_terminal_failure",
            error_code="decision_judge_configuration_invalid",
        )
        return 1
    except Exception:
        logger = configure_json_logging()
        log_safe(
            logger,
            event="worker_terminal_failure",
            error_code="worker_startup_failed",
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(entrypoint())
