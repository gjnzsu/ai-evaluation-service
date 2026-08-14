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
from app.application.evaluation_service import EvaluationService
from app.config import get_settings
from app.observability.context import RequestContextMiddleware
from app.persistence.db import Database
from app.persistence.repositories import EvaluationRepository, ReviewRepository


def create_app(
    database: Database | None = None,
    evaluation_service: EvaluationService | None = None,
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
    app.state.evaluation_service = evaluation_service or EvaluationService(
        EvaluationRepository(configured_database.sessions),
        ReviewRepository(configured_database.sessions),
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(
        RequestValidationError, request_validation_error_handler
    )
    app.include_router(health_router)
    app.include_router(evaluations_router)
    return app


app = create_app()
