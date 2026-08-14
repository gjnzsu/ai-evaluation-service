import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from importlib import import_module
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.main import create_app
from app.persistence.models import ApiClientRow


class ValidationFixture(BaseModel):
    count: int


class StubSession:
    def __init__(self, client_row: ApiClientRow | None) -> None:
        self.client_row = client_row
        self.query_parameters: list[object] = []

    async def scalar(self, statement: object) -> ApiClientRow | None:
        compiled = statement.compile()
        self.query_parameters.extend(compiled.params.values())
        return self.client_row


def api_client_row(
    *,
    raw_key: str,
    project_id: str = "project-a",
    scopes: list[str] | None = None,
    enabled: bool = True,
) -> ApiClientRow:
    dependencies = import_module("app.api.dependencies")
    now = datetime.now(UTC)
    return ApiClientRow(
        id=uuid4(),
        project_id=project_id,
        key_hash=dependencies.hash_api_key(raw_key),
        scopes=scopes or ["evaluation:read"],
        enabled=enabled,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def protected_client_factory():
    def factory(
        client_row: ApiClientRow | None,
        *,
        raise_server_exceptions: bool = True,
    ) -> tuple[TestClient, StubSession]:
        dependencies = import_module("app.api.dependencies")
        context = import_module("app.observability.context")
        app = create_app()
        session = StubSession(client_row)

        async def override_session() -> AsyncIterator[StubSession]:
            yield session

        app.dependency_overrides[dependencies.get_database_session] = override_session
        read_authentication = dependencies.authenticate_client("evaluation:read")
        submit_authentication = dependencies.authenticate_client("evaluation:submit")

        @app.get("/_test/auth/read")
        async def read_fixture(
            authenticated: Annotated[
                dependencies.AuthenticatedClient, Depends(read_authentication)
            ],
        ):
            return {
                "project_id": authenticated.project_id,
                "scopes": sorted(authenticated.scopes),
                "context_project_id": context.get_project_id(),
                "request_id": context.get_request_id(),
            }

        @app.post("/_test/auth/submit")
        async def submit_fixture(
            authenticated: Annotated[
                dependencies.AuthenticatedClient, Depends(submit_authentication)
            ],
        ):
            return {"project_id": authenticated.project_id}

        @app.post("/_test/errors/validation")
        async def validation_fixture(payload: ValidationFixture):
            return payload

        @app.get("/_test/errors/unexpected")
        async def unexpected_fixture():
            raise RuntimeError("database password=secret-value")

        return TestClient(
            app, raise_server_exceptions=raise_server_exceptions
        ), session

    return factory


def test_hash_api_key_uses_sha256() -> None:
    dependencies = import_module("app.api.dependencies")

    assert dependencies.hash_api_key("secret-key") == (
        "85dbe15d75ef9308c7ae0f33c7a324cc6f4bf519a2ed2f3027bd33c140a4f9aa"
    )


def test_missing_api_key_returns_stable_401_envelope(
    protected_client_factory,
) -> None:
    client, _ = protected_client_factory(None)

    response = client.get(
        "/_test/auth/read", headers={"X-Request-ID": "request-from-client"}
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_api_key",
            "message": "The API key is missing, invalid, or disabled.",
            "request_id": "request-from-client",
        }
    }
    assert response.headers["X-Request-ID"] == "request-from-client"


def test_invalid_api_key_returns_401_without_echoing_raw_key(
    protected_client_factory,
) -> None:
    raw_key = "never-echo-this-raw-key"
    client, session = protected_client_factory(None)

    response = client.get("/_test/auth/read", headers={"X-API-Key": raw_key})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
    assert raw_key not in response.text
    assert raw_key not in session.query_parameters
    assert len(session.query_parameters) == 1
    assert session.query_parameters[0] != raw_key


def test_disabled_api_key_returns_401(protected_client_factory) -> None:
    raw_key = "disabled-key"
    client, _ = protected_client_factory(
        api_client_row(raw_key=raw_key, enabled=False)
    )

    response = client.get("/_test/auth/read", headers={"X-API-Key": raw_key})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_hash_lookup_result_is_validated_before_authentication(
    protected_client_factory,
) -> None:
    client, _ = protected_client_factory(api_client_row(raw_key="different-key"))

    response = client.get(
        "/_test/auth/read", headers={"X-API-Key": "presented-key"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_missing_exact_scope_returns_stable_403_envelope(
    protected_client_factory,
) -> None:
    raw_key = "read-only-key"
    client, _ = protected_client_factory(
        api_client_row(raw_key=raw_key, scopes=["evaluation:read"])
    )

    response = client.post(
        "/_test/auth/submit",
        headers={"X-API-Key": raw_key, "X-Request-ID": "scope-request"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "insufficient_scope",
            "message": "The API key does not grant evaluation:submit.",
            "request_id": "scope-request",
        }
    }


def test_scope_prefix_does_not_grant_required_scope(protected_client_factory) -> None:
    raw_key = "similar-scope-key"
    client, _ = protected_client_factory(
        api_client_row(raw_key=raw_key, scopes=["evaluation:read:all"])
    )

    response = client.get("/_test/auth/read", headers={"X-API-Key": raw_key})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_scope"


def test_authenticated_client_sets_project_and_request_context(
    protected_client_factory,
) -> None:
    raw_key = "valid-key"
    client, session = protected_client_factory(
        api_client_row(
            raw_key=raw_key,
            project_id="project-context",
            scopes=["evaluation:read", "evaluation:submit"],
        )
    )

    response = client.get(
        "/_test/auth/read",
        headers={"X-API-Key": raw_key, "X-Request-ID": "context-request"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "project_id": "project-context",
        "scopes": ["evaluation:read", "evaluation:submit"],
        "context_project_id": "project-context",
        "request_id": "context-request",
    }
    assert session.query_parameters == [
        "cc358b85b8b74a6f82504e141c2cb5c45c70711c2420cc98bcc230843f8def6d"
    ]


def test_request_context_generates_distinct_uuid_request_ids(
    protected_client_factory,
) -> None:
    raw_key = "valid-key"
    client, _ = protected_client_factory(api_client_row(raw_key=raw_key))

    first = client.get("/_test/auth/read", headers={"X-API-Key": raw_key})
    second = client.get("/_test/auth/read", headers={"X-API-Key": raw_key})

    first_id = first.json()["request_id"]
    second_id = second.json()["request_id"]
    assert UUID(first_id)
    assert UUID(second_id)
    assert first_id != second_id
    assert first.headers["X-Request-ID"] == first_id
    assert second.headers["X-Request-ID"] == second_id


def test_request_context_replaces_unsafe_client_request_id(
    protected_client_factory,
) -> None:
    raw_key = "valid-key"
    client, _ = protected_client_factory(api_client_row(raw_key=raw_key))

    response = client.get(
        "/_test/auth/read",
        headers={"X-API-Key": raw_key, "X-Request-ID": "unsafe/request-id"},
    )

    generated_id = response.json()["request_id"]
    assert UUID(generated_id)
    assert generated_id != "unsafe/request-id"
    assert response.headers["X-Request-ID"] == generated_id


def test_framework_404_uses_stable_error_envelope(
    protected_client_factory,
) -> None:
    client, _ = protected_client_factory(None)

    response = client.get(
        "/_test/does-not-exist", headers={"X-Request-ID": "not-found-request"}
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "The requested resource was not found.",
            "request_id": "not-found-request",
        }
    }
    assert response.headers["X-Request-ID"] == "not-found-request"


def test_request_validation_uses_stable_422_error_envelope(
    protected_client_factory,
) -> None:
    client, _ = protected_client_factory(None)

    response = client.post(
        "/_test/errors/validation",
        headers={"X-Request-ID": "validation-request"},
        json={"count": "not-an-integer"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "The request is invalid.",
            "request_id": "validation-request",
        }
    }
    assert response.headers["X-Request-ID"] == "validation-request"


def test_unexpected_exception_uses_sanitized_500_error_envelope(
    protected_client_factory,
    caplog,
    capsys,
) -> None:
    secret = "secret-value"
    client, _ = protected_client_factory(None)

    with caplog.at_level(logging.DEBUG):
        response = client.get(
            "/_test/errors/unexpected",
            headers={"X-Request-ID": "unexpected-request"},
        )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "request_id": "unexpected-request",
        }
    }
    assert response.headers["X-Request-ID"] == "unexpected-request"
    assert secret not in response.text
    captured = capsys.readouterr()
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err
