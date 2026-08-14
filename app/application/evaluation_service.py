import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.domain.artifact_types import SUPPORTED_ARTIFACT_TYPES
from app.domain.platform import MachineVerdict, baseline_review_status
from app.persistence.models import EvaluationResultRow, EvaluationReviewRow, EvaluationRow


class EvaluationWriter(Protocol):
    async def create_with_job(
        self,
        project_id: str,
        idempotency_key: str,
        request_payload: dict,
        request_hash: str,
    ) -> tuple[EvaluationRow, bool]: ...

    async def get_for_project(
        self, evaluation_id: UUID, project_id: str
    ) -> EvaluationRow | None: ...

    async def get_result_for_project(
        self, evaluation_id: UUID, project_id: str
    ) -> EvaluationResultRow | None: ...

    async def list_page_for_project(
        self,
        project_id: str,
        **filters: object,
    ) -> tuple[
        list[tuple[EvaluationRow, EvaluationResultRow | None, EvaluationReviewRow | None]],
        int,
    ]: ...


class ReviewReader(Protocol):
    async def list_for_project(
        self, evaluation_id: UUID, project_id: str
    ) -> list[EvaluationReviewRow]: ...


class InvalidEvaluationRequest(ValueError):
    """The request must be rejected before durable work is created."""


class IdempotencyConflict(ValueError):
    """An idempotency key already names a different canonical request."""


class EvaluationNotFound(LookupError):
    """The evaluation is absent from the authenticated project."""


@dataclass(frozen=True)
class Submission:
    evaluation_id: UUID
    execution_status: str
    created: bool


@dataclass(frozen=True)
class ReviewEvidence:
    review_id: UUID
    reviewer_id: str
    decision: str
    reason: str
    waiver_rationale: str | None
    created_at: datetime


@dataclass(frozen=True)
class EvaluationDetail:
    evaluation_id: UUID
    artifact_type: str
    execution_status: str
    machine_verdict: str | None
    review_status: str | None
    deterministic_result: dict[str, Any] | None
    llm_judge_result: dict[str, Any] | None
    warnings: list[dict]
    review_history: list[ReviewEvidence]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EvaluationListItem:
    evaluation_id: UUID
    artifact_type: str
    execution_status: str
    machine_verdict: str | None
    review_status: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EvaluationPage:
    items: list[EvaluationListItem]
    page: int
    page_size: int
    total: int


def canonical_request_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class EvaluationService:
    def __init__(
        self, evaluations: EvaluationWriter, reviews: ReviewReader | None = None
    ) -> None:
        self._evaluations = evaluations
        self._reviews = reviews

    async def submit(
        self,
        *,
        project_id: str,
        idempotency_key: str,
        payload: dict,
    ) -> Submission:
        if payload.get("artifact_type") not in SUPPORTED_ARTIFACT_TYPES:
            raise InvalidEvaluationRequest("unsupported artifact_type")
        request_project_id = payload.get("project_id")
        if request_project_id is not None and request_project_id != project_id:
            raise InvalidEvaluationRequest("request project_id does not match authentication")

        try:
            evaluation, created = await self._evaluations.create_with_job(
                project_id,
                idempotency_key,
                payload,
                canonical_request_hash(payload),
            )
        except ValueError as error:
            raise IdempotencyConflict from error
        return Submission(
            evaluation_id=evaluation.id,
            execution_status=evaluation.execution_status,
            created=created,
        )

    async def get(self, *, project_id: str, evaluation_id: UUID) -> EvaluationDetail:
        evaluation = await self._evaluations.get_for_project(evaluation_id, project_id)
        if evaluation is None:
            raise EvaluationNotFound
        result = await self._evaluations.get_result_for_project(
            evaluation_id, project_id
        )
        reviews = (
            await self._reviews.list_for_project(evaluation_id, project_id)
            if self._reviews is not None
            else []
        )
        review_history = [_review_evidence(review) for review in reviews]
        return EvaluationDetail(
            evaluation_id=evaluation.id,
            artifact_type=evaluation.artifact_type,
            execution_status=evaluation.execution_status,
            machine_verdict=result.machine_verdict if result is not None else None,
            review_status=_review_status(result, reviews[-1] if reviews else None),
            deterministic_result=(
                {
                    **result.deterministic_result,
                    "evaluator_version": result.evaluator_version,
                }
                if result is not None
                else None
            ),
            llm_judge_result=result.llm_judge_result if result is not None else None,
            warnings=result.warnings if result is not None else [],
            review_history=review_history,
            created_at=evaluation.created_at,
            updated_at=evaluation.updated_at,
        )

    async def list(
        self,
        *,
        project_id: str,
        page: int,
        page_size: int,
        artifact_type: str | None = None,
        execution_status: str | None = None,
        machine_verdict: str | None = None,
        review_status: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> EvaluationPage:
        records, total = await self._evaluations.list_page_for_project(
            project_id,
            page=page,
            page_size=page_size,
            artifact_type=artifact_type,
            execution_status=execution_status,
            machine_verdict=machine_verdict,
            review_status=review_status,
            created_from=created_from,
            created_to=created_to,
        )
        items = [
            EvaluationListItem(
                evaluation_id=evaluation.id,
                artifact_type=evaluation.artifact_type,
                execution_status=evaluation.execution_status,
                machine_verdict=result.machine_verdict if result is not None else None,
                review_status=_review_status(result, latest_review),
                created_at=evaluation.created_at,
                updated_at=evaluation.updated_at,
            )
            for evaluation, result, latest_review in records
        ]
        return EvaluationPage(items=items, page=page, page_size=page_size, total=total)


def _review_status(
    result: EvaluationResultRow | None,
    latest_review: EvaluationReviewRow | None,
) -> str | None:
    if result is None:
        return None
    if latest_review is not None:
        return latest_review.decision
    return baseline_review_status(MachineVerdict(result.machine_verdict)).value


def _review_evidence(review: EvaluationReviewRow) -> ReviewEvidence:
    return ReviewEvidence(
        review_id=review.id,
        reviewer_id=review.reviewer_id,
        decision=review.decision,
        reason=review.reason,
        waiver_rationale=review.waiver_rationale,
        created_at=review.created_at,
    )
