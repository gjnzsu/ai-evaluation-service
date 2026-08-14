from fastapi.testclient import TestClient

from app.api.main import create_app


def test_openapi_contains_all_poc_operations() -> None:
    client = TestClient(create_app())

    document = client.get("/openapi.json").json()
    paths = document["paths"]

    assert "/v1/evaluations" in paths
    assert {"get", "post"} <= set(paths["/v1/evaluations"])
    assert "/v1/evaluations/{evaluation_id}" in paths
    assert "/v1/evaluations/{evaluation_id}/reviews" in paths
    assert "/health/live" in paths
    assert "/health/ready" in paths
    review_parameters = paths["/v1/evaluations/{evaluation_id}/reviews"]["post"][
        "parameters"
    ]
    assert any(
        parameter["name"] == "X-API-Key" and parameter["in"] == "header"
        for parameter in review_parameters
    )
    assert "ApiErrorResponse" in document["components"]["schemas"]
    assert {"401", "403", "404", "422"} <= set(
        paths["/v1/evaluations/{evaluation_id}/reviews"]["post"]["responses"]
    )
    assert "503" in paths["/health/ready"]["get"]["responses"]

    submit_responses = paths["/v1/evaluations"]["post"]["responses"]
    for code in ("200", "202"):
        assert submit_responses[code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/EvaluationSubmission"
        }

    for operation in (
        paths["/v1/evaluations"]["get"],
        paths["/v1/evaluations/{evaluation_id}"]["get"],
    ):
        assert operation["responses"]["422"]["content"]["application/json"][
            "schema"
        ] == {"$ref": "#/components/schemas/ApiErrorResponse"}

    ready_responses = paths["/health/ready"]["get"]["responses"]
    for code in ("200", "503"):
        assert ready_responses[code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ReadinessResponse"
        }
