from fastapi import Request
from fastapi.responses import JSONResponse

from app.observability.context import get_request_id


class ApiError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
    del request
    request_id = get_request_id()
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "request_id": request_id,
            }
        },
    )
