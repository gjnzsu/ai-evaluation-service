import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engine import EvaluationEngine
from app.persistence.models import EvaluationJobRow, EvaluationResultRow, EvaluationRow
from app.persistence.repositories import EvaluationRepository, JobRepository
from app.worker.decision import RawDecision, material_quality_issue_policy
from app.worker.decision_runtime import DecisionJudge
from app.worker.judge import DisabledOptionalJudge
from app.worker.service import WorkerService


def request(case_id: str = "job-case") -> dict:
    return {
        "case_id": case_id,
        "artifact_type": "requirement_backlog",
        "canonical_output": {"summary": "Audit logins"},
    }


async def create_queued(
    sessions: async_sessionmaker[AsyncSession], key: str = "job-key"
):
    evaluation, _ = await EvaluationRepository(sessions).create_with_job(
        "project-a", key, request(key), f"hash-{key}"
    )
    return evaluation


@pytest.mark.asyncio
async def test_only_one_worker_claims_a_job(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluation = await create_queued(session_factory)
    jobs = JobRepository(session_factory)

    first, second = await asyncio.gather(
        jobs.claim_next("worker-a", lease_seconds=60),
        jobs.claim_next("worker-b", lease_seconds=60),
    )

    claimed = [job for job in (first, second) if job is not None]
    assert len(claimed) == 1
    assert claimed[0].evaluation_id == evaluation.id
    assert claimed[0].project_id == "project-a"
    assert claimed[0].attempt_count == 1
    async with session_factory() as session:
        assert (
            await session.get(EvaluationRow, evaluation.id)
        ).execution_status == "running"


@pytest.mark.asyncio
async def test_new_job_is_immediately_claimable_when_api_host_clock_is_ahead(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    class FarFutureApiClock:
        @classmethod
        def now(cls, timezone):
            del timezone
            return datetime(2100, 1, 1, tzinfo=UTC)

    evaluations = EvaluationRepository(session_factory)
    with patch("app.persistence.repositories.datetime", FarFutureApiClock):
        evaluation, created = await evaluations.create_with_job(
            "project-a",
            "skewed-api-clock",
            request("skewed-api-clock"),
            "hash-skewed-api-clock",
        )

    async with session_factory() as session:
        job = await session.get(EvaluationJobRow, evaluation.id)
        database_now = await session.scalar(select(func.now()))

    claimed = await JobRepository(session_factory).claim_next(
        "worker-a", lease_seconds=60
    )

    assert created is True
    assert job.available_at <= database_now
    assert job.available_at >= database_now - timedelta(seconds=5)
    assert claimed is not None
    assert claimed.evaluation_id == evaluation.id


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluation = await create_queued(session_factory)
    jobs = JobRepository(session_factory)
    await jobs.claim_next("worker-a", lease_seconds=60)
    async with session_factory.begin() as session:
        await session.execute(
            update(EvaluationJobRow)
            .where(EvaluationJobRow.evaluation_id == evaluation.id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    claimed = await jobs.claim_next("worker-b", lease_seconds=60)

    assert claimed is not None
    assert claimed.evaluation_id == evaluation.id
    assert claimed.lease_owner == "worker-b"
    assert claimed.attempt_count == 2
    assert claimed.lease_recovery_count == 1


@pytest.mark.asyncio
async def test_current_owner_can_renew_lease(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await create_queued(session_factory)
    jobs = JobRepository(session_factory)
    claimed = await jobs.claim_next("worker-a", lease_seconds=1)
    assert claimed is not None

    renewed = await jobs.renew_lease(
        claimed.evaluation_id,
        lease_owner="worker-a",
        lease_seconds=60,
    )

    assert renewed is not None
    assert renewed.lease_expires_at > claimed.lease_expires_at


@pytest.mark.asyncio
async def test_claim_and_renew_use_postgres_clock_when_host_clock_is_unavailable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await create_queued(session_factory, "database-clock")
    jobs = JobRepository(session_factory)

    class ForbiddenHostClock:
        @classmethod
        def now(cls, timezone):
            del timezone
            raise AssertionError("lease semantics must not read the Worker host clock")

    async with session_factory() as session:
        database_now = await session.scalar(select(func.now()))
    with patch("app.persistence.repositories.datetime", ForbiddenHostClock):
        claimed = await jobs.claim_next("worker-a", lease_seconds=1)
        assert claimed is not None
        renewed = await jobs.renew_lease(
            claimed.evaluation_id,
            lease_owner="worker-a",
            lease_seconds=60,
        )

    assert database_now + timedelta(milliseconds=500) <= claimed.lease_expires_at
    assert renewed is not None
    assert database_now + timedelta(seconds=59) <= renewed.lease_expires_at


@pytest.mark.asyncio
async def test_stale_owner_cannot_finalize_after_reclaim(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluation = await create_queued(session_factory)
    jobs = JobRepository(session_factory)
    await jobs.claim_next("worker-a", lease_seconds=60)
    async with session_factory.begin() as session:
        await session.execute(
            update(EvaluationJobRow)
            .where(EvaluationJobRow.evaluation_id == evaluation.id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    await jobs.claim_next("worker-b", lease_seconds=60)

    completed = await jobs.complete(
        evaluation_id=evaluation.id,
        lease_owner="worker-a",
        deterministic_result={"passed": True},
        machine_verdict="pass",
        evaluator_version="deterministic-v1",
        llm_judge_result=None,
        warnings=[],
    )

    assert completed is False
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(EvaluationResultRow)) == 0
        assert (await session.get(EvaluationRow, evaluation.id)).execution_status == "running"


@pytest.mark.asyncio
async def test_only_current_owner_completes_once_with_one_result(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluation = await create_queued(session_factory)
    jobs = JobRepository(session_factory)
    await jobs.claim_next("worker-a", lease_seconds=60)
    arguments = {
        "evaluation_id": evaluation.id,
        "lease_owner": "worker-a",
        "deterministic_result": {"passed": True},
        "machine_verdict": "pass",
        "evaluator_version": "deterministic-v1",
        "llm_judge_result": None,
        "warnings": [],
    }

    assert await jobs.complete(**arguments) is True
    assert await jobs.complete(**arguments) is False

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(EvaluationResultRow)) == 1
        assert (await session.get(EvaluationRow, evaluation.id)).execution_status == "completed"


@pytest.mark.asyncio
async def test_fail_uses_stable_code_and_requires_current_owner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluation = await create_queued(session_factory)
    jobs = JobRepository(session_factory)
    await jobs.claim_next("worker-a", lease_seconds=60)

    assert (
        await jobs.fail(
            evaluation_id=evaluation.id,
            lease_owner="worker-b",
            error_code="evaluation_failed",
        )
        is False
    )
    assert (
        await jobs.fail(
            evaluation_id=evaluation.id,
            lease_owner="worker-a",
            error_code="evaluation_failed",
        )
        is True
    )
    async with session_factory() as session:
        job = await session.get(EvaluationJobRow, evaluation.id)
        assert job.last_error_code == "evaluation_failed"
        assert job.last_error_message is None
        assert (await session.get(EvaluationRow, evaluation.id)).execution_status == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_payload", "expected_verdict"),
    [
        (
            {
                "case_id": "strong",
                "artifact_type": "requirement_backlog",
                "canonical_output": {
                    "summary": "Add admin login auditing",
                    "business_value": "Improves security audit traceability for administrators.",
                    "acceptance_criteria": [
                        "Every login attempt is recorded.",
                        "Administrators can filter login records.",
                    ],
                    "priority": "High",
                    "invest_analysis": "Small, valuable, and independently testable.",
                    "description": "Record and expose administrative login audit events.",
                },
            },
            "pass",
        ),
        (request("weak"), "not_passed"),
    ],
)
async def test_worker_maps_and_persists_real_engine_verdict(
    session_factory: async_sessionmaker[AsyncSession],
    case_payload: dict,
    expected_verdict: str,
) -> None:
    evaluation, _ = await EvaluationRepository(session_factory).create_with_job(
        "project-a", case_payload["case_id"], case_payload, f"hash-{case_payload['case_id']}"
    )
    worker = WorkerService(
        JobRepository(session_factory),
        EvaluationEngine(),
        DisabledOptionalJudge(),
        "worker-a",
        60,
    )

    assert await worker.process_one() is True

    async with session_factory() as session:
        result = await session.get(EvaluationResultRow, evaluation.id)
        row = await session.get(EvaluationRow, evaluation.id)
        assert row.execution_status == "completed"
        assert result.machine_verdict == expected_verdict
        assert result.deterministic_result["passed"] is (expected_verdict == "pass")
        assert result.llm_judge_result is None
        assert result.warnings == []


@pytest.mark.asyncio
async def test_worker_persists_only_safe_warning_when_judge_fails(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluation = await create_queued(session_factory, "judge-failure")

    class FailingJudge:
        enabled = True

        def evaluate(self, case, deterministic_result):
            del case, deterministic_result
            raise RuntimeError("provider-key-secret and full-prompt-secret")

    worker = WorkerService(
        JobRepository(session_factory),
        EvaluationEngine(),
        FailingJudge(),
        "worker-a",
        60,
    )

    assert await worker.process_one() is True

    async with session_factory() as session:
        result = await session.get(EvaluationResultRow, evaluation.id)
        row = await session.get(EvaluationRow, evaluation.id)
        assert row.execution_status == "completed"
        assert result.deterministic_result is not None
        assert result.llm_judge_result is None
        assert result.warnings == [{"code": "judge_degraded"}]
        assert "secret" not in repr(result.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_output",
    [
        {"rubric_version": "v1", "label": b"not-json-safe"},
        {
            "rubric_version": "v1",
            "label": "clear",
            "raw_provider_response": {"prompt": "full-prompt-secret"},
            "api_key": "provider-key-secret",
        },
    ],
)
async def test_worker_degrades_unsafe_judge_output_before_jsonb_persistence(
    session_factory: async_sessionmaker[AsyncSession],
    unsafe_output: dict,
) -> None:
    evaluation = await create_queued(session_factory, "unsafe-judge-output")

    class UnsafeJudge:
        enabled = True

        def evaluate(self, case, deterministic_result):
            del case, deterministic_result
            return unsafe_output

    worker = WorkerService(
        JobRepository(session_factory),
        EvaluationEngine(),
        UnsafeJudge(),
        "worker-a",
        60,
    )

    assert await worker.process_one() is True

    async with session_factory() as session:
        result = await session.get(EvaluationResultRow, evaluation.id)
        row = await session.get(EvaluationRow, evaluation.id)
        assert row.execution_status == "completed"
        assert result.deterministic_result is not None
        assert result.llm_judge_result is None
        assert result.warnings == [{"code": "judge_degraded"}]
        assert "secret" not in repr(result.warnings)


@pytest.mark.asyncio
async def test_shadow_result_is_durable_without_changing_review_policy(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluation = await create_queued(session_factory, "shadow-durable")

    class ShadowProvider:
        def evaluate(self, case, deterministic_result, rubric):
            del case, deterministic_result
            return RawDecision(
                provider="jev", model="jev-pinned", rubric_version=rubric,
                answer="yes", p_yes=0.95,
            )

    worker = WorkerService(
        JobRepository(session_factory), EvaluationEngine(), DisabledOptionalJudge(),
        "worker-a", 60,
        decision_judge=DecisionJudge(
            ShadowProvider(), material_quality_issue_policy(), frozenset({"project-a"}),
            expected_provider="jev", expected_model="jev-pinned",
        ),
    )
    assert await worker.process_one() is True

    evaluations = EvaluationRepository(session_factory)
    result = await evaluations.get_result_for_project(evaluation.id, "project-a")
    assert result.machine_verdict == "not_passed"
    assert result.decision_judge_result["p_yes"] == 0.95
    assert result.llm_judge_result is None
    assert await evaluations.get_result_for_project(evaluation.id, "project-b") is None


@pytest.mark.asyncio
async def test_shadow_provider_failure_persists_only_safe_warning(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluation = await create_queued(session_factory, "shadow-failure")

    class FailingProvider:
        def evaluate(self, case, deterministic_result, rubric):
            del case, deterministic_result, rubric
            raise RuntimeError("private-input-secret")

    worker = WorkerService(
        JobRepository(session_factory), EvaluationEngine(), DisabledOptionalJudge(),
        "worker-a", 60,
        decision_judge=DecisionJudge(
            FailingProvider(), material_quality_issue_policy(), frozenset({"project-a"}),
            expected_provider="jev", expected_model="jev-pinned",
        ),
    )
    assert await worker.process_one() is True
    async with session_factory() as session:
        result = await session.get(EvaluationResultRow, evaluation.id)
        assert result.machine_verdict == "not_passed"
        assert result.decision_judge_result is None
        assert result.warnings == [{"code": "decision_judge_degraded"}]
        assert "secret" not in repr(result.warnings)
