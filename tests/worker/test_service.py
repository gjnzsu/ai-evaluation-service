import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.models import EvaluationCase, EvaluationResult
from app.worker.judge import DisabledOptionalJudge
from app.worker.service import WorkerService


def payload(case_id: str = "worker-case") -> dict:
    return {
        "case_id": case_id,
        "artifact_type": "requirement_backlog",
        "canonical_output": {"summary": "Audit logins"},
    }


class FakeJobs:
    def __init__(self, request_payload: dict | None = None) -> None:
        self.job = SimpleNamespace(
            evaluation_id=uuid4(),
            request_payload=request_payload or payload(),
            lease_owner="worker-a",
        )
        self.claimed = False
        self.completed: dict | None = None
        self.failed: dict | None = None
        self.renewed = 0
        self.owner = True
        self.renew_error: Exception | None = None

    async def claim_next(self, worker_id: str, lease_seconds: int):
        del worker_id, lease_seconds
        if self.claimed:
            return None
        self.claimed = True
        return self.job

    async def renew_lease(self, evaluation_id, lease_owner: str, lease_seconds: int):
        del evaluation_id, lease_owner, lease_seconds
        self.renewed += 1
        if self.renew_error is not None:
            raise self.renew_error
        return self.job if self.owner else None

    async def complete(self, **arguments):
        self.completed = arguments
        return self.owner

    async def fail(self, **arguments):
        self.failed = arguments
        return self.owner


class StubEngine:
    def __init__(self, passed: bool = True, error: Exception | None = None) -> None:
        self.passed = passed
        self.error = error
        self.case: EvaluationCase | None = None

    def evaluate(self, case: EvaluationCase) -> EvaluationResult:
        self.case = case
        if self.error is not None:
            raise self.error
        return EvaluationResult(
            case_id=case.case_id,
            artifact_type=case.artifact_type,
            overall_score=90 if self.passed else 30,
            passed=self.passed,
        )


class SuccessfulJudge:
    def evaluate(self, case: EvaluationCase, deterministic_result: EvaluationResult) -> dict:
        assert case.case_id == deterministic_result.case_id
        return {"rubric_version": "v1", "label": "clear"}


class SecretFailingJudge:
    def evaluate(self, case: EvaluationCase, deterministic_result: EvaluationResult) -> dict:
        del case, deterministic_result
        raise RuntimeError("provider-secret prompt-secret")


class UnsafeOutputJudge:
    def __init__(self, output: dict) -> None:
        self.output = output

    def evaluate(self, case: EvaluationCase, deterministic_result: EvaluationResult) -> dict:
        del case, deterministic_result
        return self.output


@pytest.mark.asyncio
async def test_no_eligible_job_returns_false() -> None:
    jobs = FakeJobs()
    jobs.claimed = True
    worker = WorkerService(jobs, StubEngine(), DisabledOptionalJudge(), "worker-a", 60)

    assert await worker.process_one() is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("passed", "expected_verdict"), [(True, "pass"), (False, "not_passed")]
)
async def test_worker_persists_authoritative_deterministic_result(
    passed: bool, expected_verdict: str
) -> None:
    jobs = FakeJobs()
    engine = StubEngine(passed=passed)
    worker = WorkerService(jobs, engine, DisabledOptionalJudge(), "worker-a", 60)

    assert await worker.process_one() is True

    assert jobs.completed is not None
    assert jobs.completed["machine_verdict"] == expected_verdict
    assert jobs.completed["deterministic_result"]["passed"] is passed
    assert jobs.completed["llm_judge_result"] is None
    assert jobs.completed["warnings"] == []
    assert engine.case.case_id == "worker-case"


@pytest.mark.asyncio
async def test_optional_judge_result_is_persisted_separately() -> None:
    jobs = FakeJobs()
    worker = WorkerService(jobs, StubEngine(), SuccessfulJudge(), "worker-a", 60)

    await worker.process_one()

    assert jobs.completed["deterministic_result"]["passed"] is True
    assert jobs.completed["llm_judge_result"] == {
        "rubric_version": "v1",
        "label": "clear",
    }
    assert jobs.completed["warnings"] == []


@pytest.mark.asyncio
async def test_judge_failure_completes_without_persisting_secret_exception() -> None:
    jobs = FakeJobs()
    worker = WorkerService(jobs, StubEngine(), SecretFailingJudge(), "worker-a", 60)

    assert await worker.process_one() is True

    assert jobs.completed["machine_verdict"] == "pass"
    assert jobs.completed["deterministic_result"] is not None
    assert jobs.completed["llm_judge_result"] is None
    assert jobs.completed["warnings"] == [{"code": "judge_degraded"}]
    assert "secret" not in repr(jobs.completed)
    assert jobs.failed is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_output",
    [
        {"rubric_version": "v1", "label": b"not-json-safe"},
        {
            "rubric_version": "v1",
            "label": "clear",
            "prompt": "full-prompt-secret",
            "credential": "provider-key-secret",
        },
    ],
)
async def test_unsafe_judge_output_degrades_without_persisting_output(
    unsafe_output: dict,
) -> None:
    jobs = FakeJobs()
    worker = WorkerService(
        jobs,
        StubEngine(),
        UnsafeOutputJudge(unsafe_output),
        "worker-a",
        60,
    )

    assert await worker.process_one() is True

    assert jobs.completed["machine_verdict"] == "pass"
    assert jobs.completed["deterministic_result"] is not None
    assert jobs.completed["llm_judge_result"] is None
    assert jobs.completed["warnings"] == [{"code": "judge_degraded"}]
    assert "secret" not in repr(jobs.completed)


@pytest.mark.asyncio
async def test_deterministic_failure_uses_only_stable_generic_code() -> None:
    jobs = FakeJobs()
    worker = WorkerService(
        jobs,
        StubEngine(error=RuntimeError("payload-secret credential-secret")),
        DisabledOptionalJudge(),
        "worker-a",
        60,
    )

    assert await worker.process_one() is True

    assert jobs.completed is None
    assert jobs.failed == {
        "evaluation_id": jobs.job.evaluation_id,
        "lease_owner": "worker-a",
        "error_code": "evaluation_failed",
    }
    assert "secret" not in repr(jobs.failed)


@pytest.mark.asyncio
async def test_lost_lease_refuses_finalization() -> None:
    jobs = FakeJobs()

    class SlowEngine(StubEngine):
        def evaluate(self, case: EvaluationCase) -> EvaluationResult:
            import time

            time.sleep(0.08)
            return super().evaluate(case)

    worker = WorkerService(jobs, SlowEngine(), DisabledOptionalJudge(), "worker-a", 0.03)
    jobs.owner = False

    assert await worker.process_one() is True

    assert jobs.renewed >= 1
    assert jobs.completed is None
    assert jobs.failed is None


@pytest.mark.asyncio
async def test_lease_renewal_runs_while_engine_is_evaluating() -> None:
    jobs = FakeJobs()

    class BlockingEngine(StubEngine):
        def evaluate(self, case: EvaluationCase) -> EvaluationResult:
            import time

            time.sleep(0.08)
            return super().evaluate(case)

    worker = WorkerService(jobs, BlockingEngine(), DisabledOptionalJudge(), "worker-a", 0.03)

    await asyncio.wait_for(worker.process_one(), timeout=1)

    assert jobs.renewed >= 1
    assert jobs.completed is not None


@pytest.mark.asyncio
async def test_lease_renewal_error_is_treated_as_lost_ownership() -> None:
    jobs = FakeJobs()
    jobs.renew_error = RuntimeError("database-detail-secret")

    class BlockingEngine(StubEngine):
        def evaluate(self, case: EvaluationCase) -> EvaluationResult:
            import time

            time.sleep(0.08)
            return super().evaluate(case)

    worker = WorkerService(jobs, BlockingEngine(), DisabledOptionalJudge(), "worker-a", 0.03)

    assert await worker.process_one() is True

    assert jobs.renewed >= 1
    assert jobs.completed is None
    assert jobs.failed is None
