from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import AuthenticatedClient, authenticate_client
from app.api.errors import ApiError
from app.api.schemas import ReviewRequest, ReviewSubmission
from app.application.review_service import (
    EvaluationNotReviewable,
    InvalidReviewDecision,
    ReviewNotFound,
    ReviewService,
)

router = APIRouter(prefix="/v1/evaluations", tags=["reviews"])


def get_review_service(request: Request) -> ReviewService:
    return request.app.state.review_service


@router.post(
    "/{evaluation_id}/reviews",
    response_model=ReviewSubmission,
    status_code=status.HTTP_201_CREATED,
)
async def append_review(
    evaluation_id: UUID,
    payload: ReviewRequest,
    authenticated: Annotated[
        AuthenticatedClient, Depends(authenticate_client("evaluation:review"))
    ],
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> ReviewSubmission:
    try:
        appended = await service.append(
            project_id=authenticated.project_id,
            evaluation_id=evaluation_id,
            reviewer_id=payload.reviewer_id,
            decision=payload.decision,
            reason=payload.reason,
            waiver_rationale=payload.waiver_rationale,
        )
    except ReviewNotFound as error:
        raise ApiError(
            status_code=404,
            code="not_found",
            message="The requested resource was not found.",
        ) from error
    except (EvaluationNotReviewable, InvalidReviewDecision) as error:
        raise ApiError(
            status_code=422,
            code="validation_error",
            message="The review is invalid.",
        ) from error
    return ReviewSubmission(
        **appended.evidence.__dict__, review_status=appended.review_status
    )
