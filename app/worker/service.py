import asyncio
import logging
from contextlib import suppress
from time import perf_counter
from typing import Protocol
from uuid import UUID

from app.domain.models import EvaluationCase, EvaluationResult
from app.domain.platform import MachineVerdict
from app.observability.logging import log_safe
from app.worker.judge import OptionalJudge, normalize_judge_result


class DeterministicEngine(Protocol):
    def evaluate(self, case: EvaluationCase) -> EvaluationResult: ...


class JobStore(Protocol):
    async def claim_next(self, lease_owner: str, *, lease_seconds: float): ...

    async def renew_lease(
        self, evaluation_id: UUID, *, lease_owner: str, lease_seconds: float
    ): ...

    async def complete(self, **arguments: object) -> bool: ...

    async def fail(self, **arguments: object) -> bool: ...


class WorkerService:
    def __init__(
        self,
        jobs: JobStore,
        engine: DeterministicEngine,
        judge: OptionalJudge,
        worker_id: str,
        lease_seconds: float,
    ) -> None:
        self._jobs = jobs
        self._engine = engine
        self._judge = judge
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._logger = logging.getLogger("ai_evaluation_service")

    async def process_one(self) -> bool:
        job = await self._jobs.claim_next(
            self._worker_id, lease_seconds=self._lease_seconds
        )
        if job is None:
            return False

        started = perf_counter()
        log_safe(
            self._logger,
            event="evaluation_claimed",
            evaluation_id=job.evaluation_id,
            execution_status="running",
            attempt=getattr(job, "attempt_count", None),
        )

        ownership_lost = asyncio.Event()
        renewal = asyncio.create_task(
            self._renew_lease(job.evaluation_id, ownership_lost)
        )
        try:
            case = EvaluationCase.model_validate(job.request_payload)
            deterministic_result = await asyncio.to_thread(self._engine.evaluate, case)
            llm_judge_result, warnings = await self._evaluate_judge(
                case, deterministic_result
            )
        except Exception:
            await self._stop_renewal(renewal)
            if not ownership_lost.is_set():
                await self._jobs.fail(
                    evaluation_id=job.evaluation_id,
                    lease_owner=self._worker_id,
                    error_code="evaluation_failed",
                )
                log_safe(
                    self._logger,
                    event="evaluation_failed",
                    evaluation_id=job.evaluation_id,
                    execution_status="failed",
                    attempt=getattr(job, "attempt_count", None),
                    duration=round((perf_counter() - started) * 1000, 3),
                    error_code="evaluation_failed",
                )
            return True

        await self._stop_renewal(renewal)
        if ownership_lost.is_set():
            return True

        verdict = (
            MachineVerdict.PASS
            if deterministic_result.passed
            else MachineVerdict.NOT_PASSED
        )
        completed = await self._jobs.complete(
            evaluation_id=job.evaluation_id,
            lease_owner=self._worker_id,
            deterministic_result=deterministic_result.model_dump(mode="json"),
            machine_verdict=verdict.value,
            evaluator_version="deterministic-v1",
            llm_judge_result=llm_judge_result,
            warnings=warnings,
        )
        if completed:
            log_safe(
                self._logger,
                event="evaluation_completed",
                evaluation_id=job.evaluation_id,
                artifact_type=case.artifact_type,
                execution_status="completed",
                attempt=getattr(job, "attempt_count", None),
                duration=round((perf_counter() - started) * 1000, 3),
            )
        return True

    async def _evaluate_judge(
        self, case: EvaluationCase, deterministic_result: EvaluationResult
    ) -> tuple[dict | None, list[dict]]:
        if not getattr(self._judge, "enabled", True):
            return None, []
        try:
            judged = await asyncio.to_thread(
                self._judge.evaluate, case, deterministic_result
            )
            return normalize_judge_result(judged), []
        except Exception:
            return None, [{"code": "judge_degraded"}]

    async def _renew_lease(
        self, evaluation_id: UUID, ownership_lost: asyncio.Event
    ) -> None:
        interval = self._lease_seconds / 3
        while True:
            await asyncio.sleep(interval)
            try:
                renewed = await self._jobs.renew_lease(
                    evaluation_id,
                    lease_owner=self._worker_id,
                    lease_seconds=self._lease_seconds,
                )
            except Exception:
                ownership_lost.set()
                return
            if renewed is None:
                ownership_lost.set()
                return

    @staticmethod
    async def _stop_renewal(task: asyncio.Task[None]) -> None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
