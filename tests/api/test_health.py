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
