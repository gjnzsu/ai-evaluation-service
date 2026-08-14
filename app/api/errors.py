from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.observability.context import get_request_id


class ApiError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
    return _error_response(
        request=request,
        status_code=error.status_code,
        code=error.code,
        message=error.message,
    )


async def http_exception_handler(
    request: Request, error: HTTPException
) -> JSONResponse:
    code, message = (
        ("not_found", "The requested resource was not found.")
        if error.status_code == 404
        else ("http_error", "The request could not be completed.")
    )
    return _error_response(
        request=request,
        status_code=error.status_code,
        code=code,
        message=message,
        headers=error.headers,
    )


async def request_validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    del error
    return _error_response(
        request=request,
        status_code=422,
        code="validation_error",
        message="The request is invalid.",
    )


async def unexpected_error_handler(
    request: Request, error: Exception
) -> JSONResponse:
    del error
    return _error_response(
        request=request,
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred.",
    )


def _error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id() or request.state.request_id
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
            }
        },
        headers=response_headers,
    )
