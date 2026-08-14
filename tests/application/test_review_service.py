from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.review_service import (
    EvaluationNotReviewable,
    InvalidReviewDecision,
    ReviewNotFound,
    ReviewService,
)
from app.persistence.models import EvaluationResultRow, EvaluationReviewRow, EvaluationRow


def evaluation(*, project_id: str = "project-a", status: str = "completed") -> EvaluationRow:
    now = datetime.now(UTC)
    return EvaluationRow(
        id=uuid4(),
        project_id=project_id,
        idempotency_key="review-case",
        request_hash="hash",
        request_payload={},
        artifact_type="requirement_backlog",
        execution_status=status,
        created_at=now,
        updated_at=now,
    )


def result(row: EvaluationRow, verdict: str) -> EvaluationResultRow:
    return EvaluationResultRow(
        evaluation_id=row.id,
        deterministic_result={"passed": verdict == "pass"},
        machine_verdict=verdict,
        evaluator_version="test-v1",
        llm_judge_result=None,
        warnings=[],
        completed_at=datetime.now(UTC),
    )


class FakeEvaluations:
    def __init__(self, row: EvaluationRow | None, machine_result=None) -> None:
        self.row = row
        self.machine_result = machine_result

    async def get_for_project(self, evaluation_id, project_id):
        if self.row and self.row.id == evaluation_id and self.row.project_id == project_id:
            return self.row
        return None

    async def get_result_for_project(self, evaluation_id, project_id):
        if await self.get_for_project(evaluation_id, project_id):
            return self.machine_result
        return None


class FakeReviews:
    def __init__(self) -> None:
        self.rows: list[EvaluationReviewRow] = []

    async def append(self, **values):
        review = EvaluationReviewRow(
            id=uuid4(),
            evaluation_id=values["evaluation_id"],
            reviewer_id=values["reviewer_id"],
            decision=values["decision"],
            reason=values["reason"],
            waiver_rationale=values["waiver_rationale"],
            created_at=datetime.now(UTC),
        )
        self.rows.append(review)
        return review


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("verdict", "decision", "rationale"),
    [
        ("pass", "approved", None),
        ("pass", "rejected", None),
        ("not_passed", "rejected", None),
        ("not_passed", "waived", "Accepted POC limitation"),
    ],
)
async def test_append_accepts_policy_decisions(verdict, decision, rationale) -> None:
    row = evaluation()
    reviews = FakeReviews()
    service = ReviewService(FakeEvaluations(row, result(row, verdict)), reviews)

    appended = await service.append(
        project_id="project-a",
        evaluation_id=row.id,
        reviewer_id="reviewer-1",
        decision=decision,
        reason="Human evidence",
        waiver_rationale=rationale,
    )

    assert appended.review_status == decision
    assert appended.evidence.decision == decision
    assert len(reviews.rows) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("verdict", "decision", "rationale"),
    [
        ("pass", "waived", "Not allowed"),
        ("not_passed", "approved", None),
        ("not_passed", "waived", "  "),
    ],
)
async def test_invalid_policy_decision_creates_no_review(
    verdict, decision, rationale
) -> None:
    row = evaluation()
    reviews = FakeReviews()
    service = ReviewService(FakeEvaluations(row, result(row, verdict)), reviews)

    with pytest.raises(InvalidReviewDecision):
        await service.append(
            project_id="project-a",
            evaluation_id=row.id,
            reviewer_id="reviewer-1",
            decision=decision,
            reason="Human evidence",
            waiver_rationale=rationale,
        )

    assert reviews.rows == []


@pytest.mark.asyncio
async def test_review_requires_completed_machine_result() -> None:
    row = evaluation(status="queued")
    reviews = FakeReviews()
    service = ReviewService(FakeEvaluations(row), reviews)

    with pytest.raises(EvaluationNotReviewable):
        await service.append(
            project_id="project-a",
            evaluation_id=row.id,
            reviewer_id="reviewer-1",
            decision="approved",
            reason="Too early",
            waiver_rationale=None,
        )

    assert reviews.rows == []


@pytest.mark.asyncio
async def test_cross_project_evaluation_is_not_found() -> None:
    row = evaluation(project_id="project-a")
    service = ReviewService(FakeEvaluations(row, result(row, "pass")), FakeReviews())

    with pytest.raises(ReviewNotFound):
        await service.append(
            project_id="project-b",
            evaluation_id=row.id,
            reviewer_id="reviewer-1",
            decision="approved",
            reason="Must not cross projects",
            waiver_rationale=None,
        )
