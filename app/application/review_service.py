from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.platform import MachineVerdict, ReviewDecision, validate_review_decision
from app.persistence.models import EvaluationResultRow, EvaluationReviewRow, EvaluationRow


class EvaluationReader(Protocol):
    async def get_for_project(
        self, evaluation_id: UUID, project_id: str
    ) -> EvaluationRow | None: ...

    async def get_result_for_project(
        self, evaluation_id: UUID, project_id: str
    ) -> EvaluationResultRow | None: ...


class ReviewWriter(Protocol):
    async def append(self, **values: object) -> EvaluationReviewRow | None: ...


class ReviewNotFound(LookupError):
    """The evaluation is absent from the authenticated project."""


class EvaluationNotReviewable(ValueError):
    """A review requires a completed deterministic machine result."""


class InvalidReviewDecision(ValueError):
    """The decision does not satisfy the machine-verdict policy."""


@dataclass(frozen=True)
class ReviewEvidence:
    review_id: UUID
    reviewer_id: str
    decision: str
    reason: str
    waiver_rationale: str | None
    created_at: datetime


@dataclass(frozen=True)
class AppendedReview:
    evidence: ReviewEvidence
    review_status: str


class ReviewService:
    def __init__(self, evaluations: EvaluationReader, reviews: ReviewWriter) -> None:
        self._evaluations = evaluations
        self._reviews = reviews

    async def append(
        self,
        *,
        project_id: str,
        evaluation_id: UUID,
        reviewer_id: str,
        decision: str,
        reason: str,
        waiver_rationale: str | None,
    ) -> AppendedReview:
        evaluation = await self._evaluations.get_for_project(evaluation_id, project_id)
        if evaluation is None:
            raise ReviewNotFound
        result = await self._evaluations.get_result_for_project(evaluation_id, project_id)
        if evaluation.execution_status != "completed" or result is None:
            raise EvaluationNotReviewable
        try:
            review_decision = ReviewDecision(decision)
            validate_review_decision(
                MachineVerdict(result.machine_verdict),
                review_decision,
                waiver_rationale,
            )
        except ValueError as error:
            raise InvalidReviewDecision from error

        review = await self._reviews.append(
            project_id=project_id,
            evaluation_id=evaluation_id,
            reviewer_id=reviewer_id,
            decision=review_decision.value,
            reason=reason,
            waiver_rationale=waiver_rationale,
        )
        if review is None:
            raise ReviewNotFound
        return AppendedReview(
            evidence=ReviewEvidence(
                review_id=review.id,
                reviewer_id=review.reviewer_id,
                decision=review.decision,
                reason=review.reason,
                waiver_rationale=review.waiver_rationale,
                created_at=review.created_at,
            ),
            review_status=review.decision,
        )
