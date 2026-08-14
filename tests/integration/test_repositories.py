import asyncio
from datetime import UTC, datetime

import conftest as integration_fixtures
import pytest
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.core.config import testcontainers_config

from app.persistence.db import Database
from app.persistence.models import (
    EvaluationJobRow,
    EvaluationResultRow,
    EvaluationReviewRow,
    EvaluationRow,
)
from app.persistence.repositories import (
    EvaluationRepository,
    JobRepository,
    ReviewRepository,
)


def request(case_id: str = "login-audit") -> dict:
    return {
        "case_id": case_id,
        "artifact_type": "requirement_backlog",
        "canonical_output": {"summary": "Audit logins"},
    }


def test_ryuk_override_restores_prior_configuration() -> None:
    original = testcontainers_config.ryuk_disabled
    try:
        testcontainers_config.ryuk_disabled = False
        fixture = getattr(integration_fixtures, "ryuk_disabled_for_postgres", None)
        assert fixture is not None, "scoped Ryuk override fixture is missing"

        lifecycle = fixture.__wrapped__()
        assert next(lifecycle) is None
        assert testcontainers_config.ryuk_disabled is True

        with pytest.raises(StopIteration):
            next(lifecycle)
        assert testcontainers_config.ryuk_disabled is False
    finally:
        testcontainers_config.ryuk_disabled = original


@pytest.mark.asyncio
async def test_database_provides_managed_async_sessions(migrated_database: str) -> None:
    async with Database(migrated_database) as database:
        async with database.sessions() as session:
            assert await session.scalar(text("SELECT 1")) == 1


@pytest.mark.asyncio
async def test_migration_creates_expected_schema(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        table_names = await session.run_sync(
            lambda sync_session: set(inspect(sync_session.connection()).get_table_names())
        )
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))

    assert {
        "alembic_version",
        "api_clients",
        "evaluations",
        "evaluation_jobs",
        "evaluation_results",
        "evaluation_reviews",
    } <= table_names
    assert revision == "0001_platform_poc"


@pytest.mark.asyncio
async def test_create_with_job_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = EvaluationRepository(session_factory)

    first, first_created = await repository.create_with_job(
        project_id="project-a",
        idempotency_key="key-1",
        request_payload=request(),
        request_hash="hash-1",
    )
    second, second_created = await repository.create_with_job(
        project_id="project-a",
        idempotency_key="key-1",
        request_payload=request(),
        request_hash="hash-1",
    )

    assert first.id == second.id
    assert first_created is True
    assert second_created is False
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(EvaluationRow)) == 1
        assert await session.scalar(select(func.count()).select_from(EvaluationJobRow)) == 1


@pytest.mark.asyncio
async def test_same_key_with_different_hash_conflicts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = EvaluationRepository(session_factory)
    await repository.create_with_job("project-a", "key-1", request("a"), "hash-a")

    with pytest.raises(ValueError, match="idempotency key"):
        await repository.create_with_job("project-a", "key-1", request("b"), "hash-b")


@pytest.mark.asyncio
async def test_same_key_is_scoped_to_project(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = EvaluationRepository(session_factory)

    first, _ = await repository.create_with_job(
        "project-a", "shared-key", request(), "hash-1"
    )
    second, _ = await repository.create_with_job(
        "project-b", "shared-key", request(), "hash-1"
    )

    assert first.id != second.id


@pytest.mark.asyncio
async def test_concurrent_same_key_creates_one_evaluation_and_job(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = EvaluationRepository(session_factory)

    first, second = await asyncio.gather(
        repository.create_with_job("project-a", "race-key", request(), "hash-1"),
        repository.create_with_job("project-a", "race-key", request(), "hash-1"),
    )

    assert first[0].id == second[0].id
    assert sorted((first[1], second[1])) == [False, True]
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(EvaluationRow)) == 1
        assert await session.scalar(select(func.count()).select_from(EvaluationJobRow)) == 1


@pytest.mark.asyncio
async def test_evaluation_and_job_creation_roll_back_together(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = EvaluationRepository(session_factory)

    async with session_factory.begin() as session:
        await session.execute(
            text(
                """
                CREATE FUNCTION reject_test_job() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'reject test job';
                END;
                $$ LANGUAGE plpgsql
                """
            )
        )
        await session.execute(
            text(
                """
                CREATE TRIGGER reject_test_job
                BEFORE INSERT ON evaluation_jobs
                FOR EACH ROW EXECUTE FUNCTION reject_test_job()
                """
            )
        )

    try:
        with pytest.raises(ProgrammingError, match="reject test job"):
            await repository.create_with_job(
                "project-a", "bad-job", request(), "hash-1"
            )
    finally:
        async with session_factory.begin() as session:
            await session.execute(text("DROP TRIGGER reject_test_job ON evaluation_jobs"))
            await session.execute(text("DROP FUNCTION reject_test_job()"))

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(EvaluationRow)) == 0
        assert await session.scalar(select(func.count()).select_from(EvaluationJobRow)) == 0


@pytest.mark.asyncio
async def test_evaluation_reads_are_project_scoped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = EvaluationRepository(session_factory)
    evaluation, _ = await repository.create_with_job(
        "project-a", "key-1", request(), "hash-1"
    )

    assert await repository.get_for_project(evaluation.id, "project-a") is not None
    assert await repository.get_for_project(evaluation.id, "project-b") is None
    assert [row.id for row in await repository.list_for_project("project-a")] == [
        evaluation.id
    ]
    assert await repository.list_for_project("project-b") == []


@pytest.mark.asyncio
async def test_result_fields_are_separate_and_unique(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluations = EvaluationRepository(session_factory)
    jobs = JobRepository(session_factory)
    evaluation, _ = await evaluations.create_with_job(
        "project-a", "key-1", request(), "hash-1"
    )
    completed_at = datetime.now(UTC)

    result = await jobs.insert_result(
        evaluation_id=evaluation.id,
        deterministic_result={"score": 1.0},
        machine_verdict="pass",
        evaluator_version="1.0",
        llm_judge_result={"label": "clear"},
        warnings=[{"code": "judge_degraded"}],
        completed_at=completed_at,
    )

    assert result.deterministic_result == {"score": 1.0}
    assert result.llm_judge_result == {"label": "clear"}
    assert result.warnings == [{"code": "judge_degraded"}]
    with pytest.raises(ValueError, match="warning"):
        await jobs.insert_result(
            evaluation_id=evaluation.id,
            deterministic_result={"score": 1.0},
            machine_verdict="pass",
            evaluator_version="1.0",
            llm_judge_result=None,
            warnings=[{"code": "unsafe", "raw_error": "secret"}],
            completed_at=completed_at,
        )
    with pytest.raises(IntegrityError):
        await jobs.insert_result(
            evaluation_id=evaluation.id,
            deterministic_result={"score": 0.0},
            machine_verdict="not_passed",
            evaluator_version="1.0",
            llm_judge_result=None,
            warnings=[],
            completed_at=completed_at,
        )

    async with session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(EvaluationResultRow))
            == 1
        )


@pytest.mark.asyncio
async def test_reviews_are_appended_in_chronological_order_and_project_scoped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluations = EvaluationRepository(session_factory)
    reviews = ReviewRepository(session_factory)
    evaluation, _ = await evaluations.create_with_job(
        "project-a", "key-1", request(), "hash-1"
    )

    first = await reviews.append(
        project_id="project-a",
        evaluation_id=evaluation.id,
        reviewer_id="reviewer-1",
        decision="approved",
        reason="Looks good",
        waiver_rationale=None,
    )
    second = await reviews.append(
        project_id="project-a",
        evaluation_id=evaluation.id,
        reviewer_id="reviewer-2",
        decision="rejected",
        reason="Needs revision",
        waiver_rationale=None,
    )

    history = await reviews.list_for_project(evaluation.id, "project-a")
    assert [row.id for row in history] == [first.id, second.id]
    assert await reviews.list_for_project(evaluation.id, "project-b") == []
    async with session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(EvaluationReviewRow))
            == 2
        )


@pytest.mark.asyncio
async def test_review_cannot_be_appended_across_projects(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluations = EvaluationRepository(session_factory)
    reviews = ReviewRepository(session_factory)
    evaluation, _ = await evaluations.create_with_job(
        "project-a", "key-1", request(), "hash-1"
    )

    assert (
        await reviews.append(
            project_id="project-b",
            evaluation_id=evaluation.id,
            reviewer_id="reviewer-1",
            decision="approved",
            reason="Looks good",
            waiver_rationale=None,
        )
        is None
    )


@pytest.mark.asyncio
async def test_result_read_is_project_scoped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluations = EvaluationRepository(session_factory)
    jobs = JobRepository(session_factory)
    evaluation, _ = await evaluations.create_with_job(
        "project-a", "result-scope", request(), "hash-1"
    )
    await jobs.insert_result(
        evaluation_id=evaluation.id,
        deterministic_result={"score": 1.0},
        machine_verdict="pass",
        evaluator_version="1.0",
        llm_judge_result=None,
        warnings=[],
        completed_at=datetime.now(UTC),
    )

    assert (
        await evaluations.get_result_for_project(evaluation.id, "project-a")
    ).machine_verdict == "pass"
    assert await evaluations.get_result_for_project(evaluation.id, "project-b") is None


@pytest.mark.asyncio
async def test_list_page_applies_pagination_filters_and_project_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluations = EvaluationRepository(session_factory)
    jobs = JobRepository(session_factory)
    reviews = ReviewRepository(session_factory)
    first, _ = await evaluations.create_with_job(
        "project-a", "first", request("first"), "hash-first"
    )
    second_payload = request("second") | {"artifact_type": "pm_status_report"}
    second, _ = await evaluations.create_with_job(
        "project-a", "second", second_payload, "hash-second"
    )
    third, _ = await evaluations.create_with_job(
        "project-a", "third", request("third"), "hash-third"
    )
    other, _ = await evaluations.create_with_job(
        "project-b", "other", request("other"), "hash-other"
    )
    dates = {
        first.id: datetime(2026, 8, 1, tzinfo=UTC),
        second.id: datetime(2026, 8, 2, tzinfo=UTC),
        third.id: datetime(2026, 8, 3, tzinfo=UTC),
        other.id: datetime(2026, 8, 4, tzinfo=UTC),
    }
    async with session_factory.begin() as session:
        for evaluation_id, created_at in dates.items():
            await session.execute(
                update(EvaluationRow)
                .where(EvaluationRow.id == evaluation_id)
                .values(
                    execution_status=(
                        "queued" if evaluation_id == third.id else "completed"
                    ),
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
    for evaluation, verdict in ((first, "pass"), (second, "not_passed"), (other, "pass")):
        await jobs.insert_result(
            evaluation_id=evaluation.id,
            deterministic_result={"score": 1.0},
            machine_verdict=verdict,
            evaluator_version="1.0",
            llm_judge_result=None,
            warnings=[],
            completed_at=datetime.now(UTC),
        )
    await reviews.append(
        project_id="project-a",
        evaluation_id=first.id,
        reviewer_id="reviewer-1",
        decision="approved",
        reason="Looks good",
        waiver_rationale=None,
    )

    page_one, total = await evaluations.list_page_for_project(
        "project-a", page=1, page_size=1
    )
    page_two, _ = await evaluations.list_page_for_project(
        "project-a", page=2, page_size=1
    )
    assert [record[0].id for record in page_one] == [third.id]
    assert [record[0].id for record in page_two] == [second.id]
    assert total == 3

    filters = [
        ({"artifact_type": "pm_status_report"}, [second.id]),
        ({"execution_status": "queued"}, [third.id]),
        ({"machine_verdict": "pass"}, [first.id]),
        ({"review_status": "approved"}, [first.id]),
        ({"review_status": "required"}, [second.id]),
        (
            {
                "created_from": datetime(2026, 8, 2, tzinfo=UTC),
                "created_to": datetime(2026, 8, 2, tzinfo=UTC),
            },
            [second.id],
        ),
    ]
    for query, expected_ids in filters:
        records, filtered_total = await evaluations.list_page_for_project(
            "project-a", page=1, page_size=20, **query
        )
        assert [record[0].id for record in records] == expected_ids
        assert filtered_total == len(expected_ids)


@pytest.mark.asyncio
async def test_review_status_filters_exclude_no_result_row_with_review_history(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    evaluations = EvaluationRepository(session_factory)
    queued, _ = await evaluations.create_with_job(
        "project-a", "queued-with-review", request(), "hash-queued"
    )
    async with session_factory.begin() as session:
        session.add(
            EvaluationReviewRow(
                evaluation_id=queued.id,
                reviewer_id="low-level-fixture",
                decision="approved",
                reason="Historical low-level data",
                waiver_rationale=None,
                created_at=datetime.now(UTC),
            )
        )

    unfiltered, unfiltered_total = await evaluations.list_page_for_project(
        "project-a", page=1, page_size=20
    )
    assert unfiltered_total == 1
    assert unfiltered[0][1] is None
    assert unfiltered[0][2].decision == "approved"

    for review_status in ("approved", "rejected", "waived", "optional", "required"):
        records, total = await evaluations.list_page_for_project(
            "project-a", page=1, page_size=20, review_status=review_status
        )
        assert records == []
        assert total == 0
