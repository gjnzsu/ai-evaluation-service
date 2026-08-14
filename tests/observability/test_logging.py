import json
import logging

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.observability.logging import JsonFormatter, safe_log_fields


def test_safe_log_fields_keeps_only_explicit_allowlist() -> None:
    fields = safe_log_fields(
        event="evaluation_submitted",
        request_id="request-1",
        project_id="project-a",
        evaluation_id="evaluation-1",
        artifact_type="requirement_backlog",
        execution_status="queued",
        attempt=1,
        duration=12,
        error_code="safe_code",
        api_key="api-key-secret",
        canonical_output={"secret": "payload-secret"},
        prompt="prompt-secret",
        raw_exception="exception-secret",
    )

    assert fields == {
        "event": "evaluation_submitted",
        "request_id": "request-1",
        "project_id": "project-a",
        "evaluation_id": "evaluation-1",
        "artifact_type": "requirement_backlog",
        "execution_status": "queued",
        "attempt": 1,
        "duration": 12,
        "error_code": "safe_code",
    }
    assert "secret" not in repr(fields)


def test_json_formatter_serializes_only_safe_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "ignored payload-secret",
        (),
        None,
    )
    record.safe_fields = {
        "event": "evaluation_completed",
        "project_id": "project-a",
        "canonical_output": "payload-secret",
    }

    rendered = formatter.format(record)

    assert json.loads(rendered) == {
        "event": "evaluation_completed",
        "project_id": "project-a",
    }
    assert "payload-secret" not in rendered


def test_request_logs_do_not_inspect_headers_or_payload(caplog) -> None:
    client = TestClient(create_app())
    api_key = "api-key-secret"
    payload_value = "canonical-payload-secret"

    with caplog.at_level(logging.INFO, logger="ai_evaluation_service"):
        response = client.post(
            "/does-not-exist",
            headers={"X-API-Key": api_key},
            json={"canonical_output": payload_value},
        )

    assert response.status_code == 404
    rendered = caplog.text
    assert api_key not in rendered
    assert payload_value not in rendered
    assert "canonical_output" not in rendered
