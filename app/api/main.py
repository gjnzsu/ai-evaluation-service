from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    request_validation_error_handler,
)
from app.api.routes.evaluations import router as evaluations_router
from app.api.routes.health import router as health_router
from app.api.routes.reviews import router as reviews_router
from app.application.evaluation_service import EvaluationService
from app.application.review_service import ReviewService
from app.config import get_settings
from app.observability.context import RequestContextMiddleware
from app.observability.logging import SafeRequestLoggingMiddleware, configure_json_logging
from app.persistence.db import Database
from app.persistence.repositories import EvaluationRepository, ReviewRepository


def create_app(
    database: Database | None = None,
    evaluation_service: EvaluationService | None = None,
    review_service: ReviewService | None = None,
) -> FastAPI:
    configured_database = database or Database(get_settings().database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await configured_database.dispose()

    app = FastAPI(
        title="AI Evaluation Service", version="1.0.0", lifespan=lifespan
    )
    app.state.database = configured_database
    evaluations = EvaluationRepository(configured_database.sessions)
    reviews = ReviewRepository(configured_database.sessions)
    app.state.evaluation_service = evaluation_service or EvaluationService(evaluations, reviews)
    app.state.review_service = review_service or ReviewService(evaluations, reviews)
    app.add_middleware(SafeRequestLoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(
        RequestValidationError, request_validation_error_handler
    )
    app.include_router(health_router)
    app.include_router(evaluations_router)
    app.include_router(reviews_router)
    return app


configure_json_logging()
app = create_app()
