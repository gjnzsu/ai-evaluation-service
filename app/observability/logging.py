import json
import logging
from enum import Enum
from time import perf_counter
from uuid import UUID

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.context import get_project_id, get_request_id

_SAFE_FIELDS = frozenset(
    {
        "event",
        "request_id",
        "project_id",
        "evaluation_id",
        "artifact_type",
        "execution_status",
        "attempt",
        "duration",
        "error_code",
    }
)


def safe_log_fields(**fields: object) -> dict[str, str | int | float | bool]:
    """Return scalar diagnostic fields from the explicit platform allowlist."""
    safe: dict[str, str | int | float | bool] = {}
    for name, value in fields.items():
        if name not in _SAFE_FIELDS or value is None:
            continue
        if isinstance(value, Enum):
            value = value.value
        if isinstance(value, UUID):
            value = str(value)
        if isinstance(value, str | int | float | bool):
            safe[name] = value
    return safe


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        candidate = getattr(record, "safe_fields", {})
        fields = candidate if isinstance(candidate, dict) else {}
        return json.dumps(safe_log_fields(**fields), separators=(",", ":"))


def configure_json_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("ai_evaluation_service")
    if not any(getattr(handler, "_ai_eval_safe", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._ai_eval_safe = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def log_safe(logger: logging.Logger, **fields: object) -> None:
    logger.info("safe_event", extra={"safe_fields": safe_log_fields(**fields)})


class SafeRequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("ai_evaluation_service")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            log_safe(
                self.logger,
                event="request_completed",
                request_id=get_request_id(),
                project_id=get_project_id(),
                execution_status=status_code,
                duration=round((perf_counter() - started) * 1000, 3),
                error_code="internal_error" if status_code >= 500 else None,
            )
