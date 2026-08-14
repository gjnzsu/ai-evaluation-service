from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.api.dependencies import AuthenticatedClient, authenticate_client
from app.api.errors import ApiError
from app.api.schemas import (
    EvaluationDetail,
    EvaluationListPage,
    EvaluationSubmission,
)
from app.application.evaluation_service import (
    EvaluationNotFound,
    EvaluationService,
    IdempotencyConflict,
    InvalidEvaluationRequest,
)
from app.domain.models import EvaluationCase
from app.domain.platform import ExecutionStatus, MachineVerdict, ReviewStatus

router = APIRouter(prefix="/v1/evaluations", tags=["evaluations"])


def get_evaluation_service(request: Request) -> EvaluationService:
    return request.app.state.evaluation_service


@router.post("", response_model=EvaluationSubmission)
async def submit_evaluation(
    payload: EvaluationCase,
    response: Response,
    authenticated: Annotated[
        AuthenticatedClient, Depends(authenticate_client("evaluation:submit"))
    ],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
) -> EvaluationSubmission:
    try:
        submission = await service.submit(
            project_id=authenticated.project_id,
            idempotency_key=idempotency_key,
            payload=payload.model_dump(mode="json"),
        )
    except InvalidEvaluationRequest as error:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="The request is invalid.",
        ) from error
    except IdempotencyConflict as error:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="idempotency_conflict",
            message="The idempotency key is already used for a different request.",
        ) from error

    response.status_code = (
        status.HTTP_202_ACCEPTED if submission.created else status.HTTP_200_OK
    )
    return EvaluationSubmission(
        evaluation_id=submission.evaluation_id,
        execution_status=submission.execution_status,
    )


@router.get("", response_model=EvaluationListPage)
async def list_evaluations(
    authenticated: Annotated[
        AuthenticatedClient, Depends(authenticate_client("evaluation:read"))
    ],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    artifact_type: str | None = None,
    execution_status: ExecutionStatus | None = None,
    machine_verdict: MachineVerdict | None = None,
    review_status: ReviewStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> EvaluationListPage:
    result = await service.list(
        project_id=authenticated.project_id,
        page=page,
        page_size=page_size,
        artifact_type=artifact_type,
        execution_status=(execution_status.value if execution_status else None),
        machine_verdict=(machine_verdict.value if machine_verdict else None),
        review_status=(review_status.value if review_status else None),
        created_from=created_from,
        created_to=created_to,
    )
    return EvaluationListPage.model_validate(result)


@router.get("/{evaluation_id}", response_model=EvaluationDetail)
async def get_evaluation(
    evaluation_id: UUID,
    authenticated: Annotated[
        AuthenticatedClient, Depends(authenticate_client("evaluation:read"))
    ],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationDetail:
    try:
        detail = await service.get(
            project_id=authenticated.project_id, evaluation_id=evaluation_id
        )
    except EvaluationNotFound as error:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="The requested resource was not found.",
        ) from error
    return EvaluationDetail.model_validate(detail)
