from contextvars import ContextVar
from re import compile
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_project_id: ContextVar[str | None] = ContextVar("project_id", default=None)
_SAFE_REQUEST_ID = compile(r"[A-Za-z0-9._:-]{1,128}")


def get_request_id() -> str | None:
    return _request_id.get()


def get_project_id() -> str | None:
    return _project_id.get()


def set_project_id(project_id: str) -> None:
    _project_id.set(project_id)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        candidate_request_id = Headers(scope=scope).get("X-Request-ID")
        request_id = (
            candidate_request_id
            if candidate_request_id
            and _SAFE_REQUEST_ID.fullmatch(candidate_request_id) is not None
            else str(uuid4())
        )
        request_token = _request_id.set(request_id)
        project_token = _project_id.set(None)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _project_id.reset(project_token)
            _request_id.reset(request_token)
