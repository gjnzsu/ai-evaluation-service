from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.evaluation_service import (
    EvaluationService,
    IdempotencyConflict,
    InvalidEvaluationRequest,
)
from app.persistence.models import (
    EvaluationResultRow,
    EvaluationReviewRow,
    EvaluationRow,
)


def evaluation_row(
    *, project_id: str = "project-a", execution_status: str = "queued"
) -> EvaluationRow:
    now = datetime.now(UTC)
    return EvaluationRow(
        id=uuid4(),
        project_id=project_id,
        idempotency_key="key-1",
        request_hash="hash",
        request_payload={},
        artifact_type="requirement_backlog",
        execution_status=execution_status,
        created_at=now,
        updated_at=now,
    )


class FakeEvaluations:
    def __init__(self, row: EvaluationRow | None = None) -> None:
        self.row = row
        self.created_payloads: list[dict] = []
        self.raise_conflict = False
        self.result: EvaluationResultRow | None = None
        self.list_records: list[tuple] = []
        self.list_total = 0
        self.list_call: dict | None = None

    async def create_with_job(
        self,
        project_id: str,
        idempotency_key: str,
        request_payload: dict,
        request_hash: str,
    ) -> tuple[EvaluationRow, bool]:
        del idempotency_key, request_hash
        self.created_payloads.append(request_payload)
        if self.raise_conflict:
            raise ValueError("idempotency key conflict")
        return self.row or evaluation_row(project_id=project_id), True

    async def get_for_project(self, evaluation_id, project_id):
        if self.row is None or self.row.id != evaluation_id:
            return None
        return self.row if self.row.project_id == project_id else None

    async def get_result_for_project(self, evaluation_id, project_id):
        if self.row is None or self.row.id != evaluation_id:
            return None
        return self.result if self.row.project_id == project_id else None

    async def list_page_for_project(self, project_id: str, **filters):
        self.list_call = {"project_id": project_id, **filters}
        return self.list_records, self.list_total


class FakeReviews:
    def __init__(self, reviews: list[EvaluationReviewRow] | None = None) -> None:
        self.reviews = reviews or []

    async def list_for_project(self, evaluation_id, project_id):
        del evaluation_id, project_id
        return self.reviews


def valid_payload(**extra) -> dict:
    return {
        "case_id": "case-1",
        "artifact_type": "requirement_backlog",
        "canonical_output": {},
        "input": {},
        "published_artifacts": {},
        "run_metadata": {},
        **extra,
    }


@pytest.mark.asyncio
async def test_unsupported_artifact_type_is_rejected_before_durable_work() -> None:
    evaluations = FakeEvaluations()
    service = EvaluationService(evaluations)

    with pytest.raises(InvalidEvaluationRequest):
        await service.submit(
            project_id="project-a",
            idempotency_key="key-1",
            payload=valid_payload(artifact_type="unknown"),
        )

    assert evaluations.created_payloads == []


@pytest.mark.asyncio
async def test_request_project_must_match_authenticated_project() -> None:
    evaluations = FakeEvaluations()
    service = EvaluationService(evaluations)

    with pytest.raises(InvalidEvaluationRequest):
        await service.submit(
            project_id="project-a",
            idempotency_key="key-1",
            payload=valid_payload(project_id="project-b"),
        )

    assert evaluations.created_payloads == []


@pytest.mark.asyncio
async def test_repository_hash_mismatch_becomes_idempotency_conflict() -> None:
    evaluations = FakeEvaluations()
    evaluations.raise_conflict = True
    service = EvaluationService(evaluations)

    with pytest.raises(IdempotencyConflict):
        await service.submit(
            project_id="project-a",
            idempotency_key="key-1",
            payload=valid_payload(),
        )


@pytest.mark.asyncio
async def test_queued_detail_has_no_machine_or_review_status() -> None:
    row = evaluation_row()
    service = EvaluationService(FakeEvaluations(row), FakeReviews())

    detail = await service.get(project_id="project-a", evaluation_id=row.id)

    assert detail.execution_status == "queued"
    assert detail.machine_verdict is None
    assert detail.review_status is None
    assert detail.deterministic_result is None
    assert detail.review_history == []


@pytest.mark.asyncio
async def test_completed_detail_uses_latest_review_status() -> None:
    row = evaluation_row(execution_status="completed")
    evaluations = FakeEvaluations(row)
    evaluations.result = EvaluationResultRow(
        evaluation_id=row.id,
        deterministic_result={
            "case_id": "case-1",
            "artifact_type": "requirement_backlog",
            "overall_score": 40,
            "passed": False,
            "criteria_scores": {},
            "findings": [],
            "suggested_improvements": [],
            "metadata": {},
        },
        machine_verdict="not_passed",
        evaluator_version="requirement_backlog-v1",
        llm_judge_result={"label": "unclear"},
        warnings=[{"code": "judge_degraded"}],
        completed_at=datetime.now(UTC),
    )
    reviews = [
        EvaluationReviewRow(
            id=uuid4(),
            evaluation_id=row.id,
            reviewer_id="reviewer-1",
            decision="waived",
            reason="Accepted POC limitation",
            waiver_rationale="Known limitation",
            created_at=datetime.now(UTC),
        )
    ]
    service = EvaluationService(evaluations, FakeReviews(reviews))

    detail = await service.get(project_id="project-a", evaluation_id=row.id)

    assert detail.machine_verdict == "not_passed"
    assert detail.review_status == "waived"
    assert detail.llm_judge_result == {"label": "unclear"}
    assert detail.warnings == [{"code": "judge_degraded"}]
    assert [item.decision for item in detail.review_history] == ["waived"]


@pytest.mark.asyncio
async def test_list_forwards_project_pagination_and_all_filters() -> None:
    evaluations = FakeEvaluations()
    service = EvaluationService(evaluations, FakeReviews())
    created_from = datetime(2026, 8, 1, tzinfo=UTC)
    created_to = datetime(2026, 8, 14, tzinfo=UTC)

    page = await service.list(
        project_id="project-a",
        page=2,
        page_size=10,
        artifact_type="requirement_backlog",
        execution_status="completed",
        machine_verdict="pass",
        review_status="approved",
        created_from=created_from,
        created_to=created_to,
    )

    assert page.items == []
    assert page.total == 0
    assert evaluations.list_call == {
        "project_id": "project-a",
        "page": 2,
        "page_size": 10,
        "artifact_type": "requirement_backlog",
        "execution_status": "completed",
        "machine_verdict": "pass",
        "review_status": "approved",
        "created_from": created_from,
        "created_to": created_to,
    }
