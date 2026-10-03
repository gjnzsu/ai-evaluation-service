from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.api.main import create_app


def test_liveness_does_not_require_database():
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_openapi_uses_v1_service_metadata():
    client = TestClient(create_app())

    document = client.get("/openapi.json").json()

    assert document["info"]["title"] == "AI Evaluation Service"
    assert document["info"]["version"] == "1.0.0"


class ReadySession:
    def __init__(self, *, revision="0002_shadow_decision_judge", error=None):
        self.revision = revision
        self.error = error
        self.calls = 0

    async def scalar(self, statement):
        del statement
        if self.error:
            raise self.error
        self.calls += 1
        return 1 if self.calls == 1 else self.revision


class ReadyDatabase:
    def __init__(self, session):
        self.session = session

    @asynccontextmanager
    async def sessions(self):
        yield self.session

    async def dispose(self):
        pass


def test_readiness_is_200_when_database_and_revision_are_current():
    client = TestClient(create_app(database=ReadyDatabase(ReadySession())))

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_is_503_without_details_when_database_check_fails():
    secret = "password=never-log-this"
    database = ReadyDatabase(ReadySession(error=RuntimeError(secret)))
    client = TestClient(create_app(database=database))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert secret not in response.text


def test_readiness_is_503_when_migration_revision_is_not_current():
    client = TestClient(
        create_app(database=ReadyDatabase(ReadySession(revision="old_revision")))
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
