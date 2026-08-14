from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    request_validation_error_handler,
)
from app.api.routes.health import router as health_router
from app.observability.context import RequestContextMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="AI Evaluation Service", version="1.0.0")
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(
        RequestValidationError, request_validation_error_handler
    )
    app.include_router(health_router)
    return app


app = create_app()
