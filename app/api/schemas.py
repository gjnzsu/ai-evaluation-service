from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import EvaluationResult
from app.domain.platform import ExecutionStatus, MachineVerdict, ReviewStatus


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ApiErrorResponse(BaseModel):
    error: ApiErrorDetail


class EvaluationSubmission(BaseModel):
    evaluation_id: UUID
    execution_status: ExecutionStatus
    machine_verdict: MachineVerdict | None = None
    review_status: ReviewStatus | None = None


class SafeWarning(BaseModel):
    code: Literal["judge_degraded"]


class ReviewEvidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: UUID
    reviewer_id: str
    decision: Literal["approved", "rejected", "waived"]
    reason: str
    waiver_rationale: str | None
    created_at: datetime


class ReviewRequest(BaseModel):
    reviewer_id: str = Field(min_length=1, max_length=100)
    decision: Literal["approved", "rejected", "waived"]
    reason: str = Field(min_length=1, max_length=1000)
    waiver_rationale: str | None = Field(default=None, max_length=2000)


class ReviewSubmission(ReviewEvidence):
    review_status: ReviewStatus


class DeterministicEvaluationResult(EvaluationResult):
    evaluator_version: str


class EvaluationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evaluation_id: UUID
    artifact_type: str
    execution_status: ExecutionStatus
    machine_verdict: MachineVerdict | None
    review_status: ReviewStatus | None
    deterministic_result: DeterministicEvaluationResult | None
    llm_judge_result: dict[str, Any] | None
    warnings: list[SafeWarning]
    review_history: list[ReviewEvidence]
    created_at: datetime
    updated_at: datetime


class EvaluationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evaluation_id: UUID
    artifact_type: str
    execution_status: ExecutionStatus
    machine_verdict: MachineVerdict | None
    review_status: ReviewStatus | None
    created_at: datetime
    updated_at: datetime


class EvaluationListPage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[EvaluationListItem]
    page: int
    page_size: int
    total: int
