from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import hash_api_key
from app.api.main import create_app
from app.application.evaluation_service import EvaluationService
from app.persistence.models import (
    ApiClientRow,
    EvaluationResultRow,
    EvaluationReviewRow,
    EvaluationRow,
)


class StubSession:
    def __init__(self, client: ApiClientRow) -> None:
        self.client = client

    async def scalar(self, statement: object) -> ApiClientRow:
        del statement
        return self.client


class StubDatabase:
    def __init__(self, client: ApiClientRow) -> None:
        self.session = StubSession(client)
        self.disposed = False

    @asynccontextmanager
    async def sessions(self):
        yield self.session

    async def dispose(self) -> None:
        self.disposed = True


class InMemoryEvaluations:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], EvaluationRow] = {}
        self.results: dict = {}
        self.list_call: dict | None = None

    async def create_with_job(
        self,
        project_id: str,
        idempotency_key: str,
        request_payload: dict,
        request_hash: str,
    ) -> tuple[EvaluationRow, bool]:
        key = (project_id, idempotency_key)
        existing = self.rows.get(key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ValueError("idempotency key conflict")
            return existing, False
        now = datetime.now(UTC)
        row = EvaluationRow(
            id=uuid4(),
            project_id=project_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            request_payload=request_payload,
            artifact_type=request_payload["artifact_type"],
            execution_status="queued",
            created_at=now,
            updated_at=now,
        )
        self.rows[key] = row
        return row, True

    async def get_for_project(self, evaluation_id, project_id):
        return next(
            (
                row
                for row in self.rows.values()
                if row.id == evaluation_id and row.project_id == project_id
            ),
            None,
        )

    async def get_result_for_project(self, evaluation_id, project_id):
        row = await self.get_for_project(evaluation_id, project_id)
        return self.results.get(evaluation_id) if row is not None else None

    async def list_page_for_project(self, project_id: str, **filters):
        self.list_call = {"project_id": project_id, **filters}
        records = []
        reviews = filters.pop("reviews") if "reviews" in filters else {}
        for row in self.rows.values():
            if row.project_id != project_id:
                continue
            result = self.results.get(row.id)
            latest_review = (reviews.get(row.id) or [None])[-1]
            records.append((row, result, latest_review))
        records.sort(key=lambda record: record[0].created_at, reverse=True)
        total = len(records)
        page = filters["page"]
        page_size = filters["page_size"]
        start = (page - 1) * page_size
        return records[start : start + page_size], total


class InMemoryReviews:
    def __init__(self) -> None:
        self.rows: dict = {}

    async def list_for_project(self, evaluation_id, project_id):
        del project_id
        return self.rows.get(evaluation_id, [])


@pytest.fixture
def client():
    now = datetime.now(UTC)
    database = StubDatabase(
        ApiClientRow(
            id=uuid4(),
            project_id="project-a",
            key_hash=hash_api_key("submit-key"),
            scopes=["evaluation:submit", "evaluation:read"],
            enabled=True,
            created_at=now,
            updated_at=now,
        )
    )
    evaluations = InMemoryEvaluations()
    reviews = InMemoryReviews()
    with TestClient(
        create_app(
            database=database,
            evaluation_service=EvaluationService(evaluations, reviews),
        )
    ) as test_client:
        test_client.app.state.test_evaluations = evaluations
        test_client.app.state.test_reviews = reviews
        yield test_client
    assert database.disposed is True


def valid_requirement_case() -> dict:
    return {
        "case_id": "login-audit-001",
        "artifact_type": "requirement_backlog",
        "canonical_output": {"summary": "Audit logins"},
        "input": {},
        "published_artifacts": {},
        "run_metadata": {},
    }


def test_submit_returns_202_and_queued(client: TestClient) -> None:
    response = client.post(
        "/v1/evaluations",
        headers={"X-API-Key": "submit-key", "Idempotency-Key": "case-1"},
        json=valid_requirement_case(),
    )

    assert response.status_code == 202
    assert response.json()["execution_status"] == "queued"
    assert response.json()["machine_verdict"] is None


def test_replay_returns_original_evaluation(client: TestClient) -> None:
    headers = {"X-API-Key": "submit-key", "Idempotency-Key": "case-1"}

    first = client.post("/v1/evaluations", headers=headers, json=valid_requirement_case())
    second = client.post("/v1/evaluations", headers=headers, json=valid_requirement_case())

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["evaluation_id"] == first.json()["evaluation_id"]


def test_replay_uses_canonical_hash_independent_of_object_key_order(
    client: TestClient,
) -> None:
    headers = {"X-API-Key": "submit-key", "Idempotency-Key": "canonical"}
    first_payload = valid_requirement_case()
    first_payload["canonical_output"] = {"summary": "Audit logins", "priority": "high"}
    reordered_payload = {
        "run_metadata": {},
        "published_artifacts": {},
        "input": {},
        "canonical_output": {"priority": "high", "summary": "Audit logins"},
        "artifact_type": "requirement_backlog",
        "case_id": "login-audit-001",
    }

    first = client.post("/v1/evaluations", headers=headers, json=first_payload)
    replay = client.post("/v1/evaluations", headers=headers, json=reordered_payload)

    assert first.status_code == 202
    assert replay.status_code == 200
    assert replay.json()["evaluation_id"] == first.json()["evaluation_id"]


def test_missing_required_case_field_returns_422_without_durable_work(
    client: TestClient,
) -> None:
    payload = valid_requirement_case()
    del payload["canonical_output"]

    response = client.post(
        "/v1/evaluations",
        headers={"X-API-Key": "submit-key", "Idempotency-Key": "missing-field"},
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert client.app.state.test_evaluations.rows == {}


@pytest.mark.parametrize(
    "payload",
    [
        valid_requirement_case() | {"artifact_type": "unsupported"},
        valid_requirement_case() | {"project_id": "project-b"},
    ],
)
def test_invalid_submission_is_rejected_without_durable_work(
    client: TestClient, payload: dict
) -> None:
    response = client.post(
        "/v1/evaluations",
        headers={"X-API-Key": "submit-key", "Idempotency-Key": "invalid"},
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert client.app.state.test_evaluations.rows == {}


def test_reusing_key_with_different_payload_returns_409(client: TestClient) -> None:
    headers = {"X-API-Key": "submit-key", "Idempotency-Key": "conflict"}
    first = client.post("/v1/evaluations", headers=headers, json=valid_requirement_case())
    changed = valid_requirement_case() | {"case_id": "different-case"}

    second = client.post("/v1/evaluations", headers=headers, json=changed)

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_conflict"
    assert len(client.app.state.test_evaluations.rows) == 1


def test_queued_detail_keeps_machine_and_review_status_null(client: TestClient) -> None:
    submission = client.post(
        "/v1/evaluations",
        headers={"X-API-Key": "submit-key", "Idempotency-Key": "detail"},
        json=valid_requirement_case(),
    )

    response = client.get(
        f"/v1/evaluations/{submission.json()['evaluation_id']}",
        headers={"X-API-Key": "submit-key"},
    )

    assert response.status_code == 200
    assert response.json()["execution_status"] == "queued"
    assert response.json()["machine_verdict"] is None
    assert response.json()["review_status"] is None
    assert response.json()["deterministic_result"] is None
    assert response.json()["decision_judge_result"] is None


def test_cross_project_detail_is_hidden_as_404(client: TestClient) -> None:
    evaluations = client.app.state.test_evaluations
    now = datetime.now(UTC)
    foreign = EvaluationRow(
        id=uuid4(),
        project_id="project-b",
        idempotency_key="foreign",
        request_hash="hash",
        request_payload=valid_requirement_case(),
        artifact_type="requirement_backlog",
        execution_status="queued",
        created_at=now,
        updated_at=now,
    )
    evaluations.rows[("project-b", "foreign")] = foreign

    response = client.get(
        f"/v1/evaluations/{foreign.id}", headers={"X-API-Key": "submit-key"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_completed_detail_keeps_result_judge_warning_and_reviews_separate(
    client: TestClient,
) -> None:
    evaluations = client.app.state.test_evaluations
    reviews = client.app.state.test_reviews
    now = datetime.now(UTC)
    row = EvaluationRow(
        id=uuid4(),
        project_id="project-a",
        idempotency_key="completed",
        request_hash="hash",
        request_payload=valid_requirement_case(),
        artifact_type="requirement_backlog",
        execution_status="completed",
        created_at=now,
        updated_at=now,
    )
    evaluations.rows[("project-a", "completed")] = row
    evaluations.results[row.id] = EvaluationResultRow(
        evaluation_id=row.id,
        deterministic_result={
            "case_id": "login-audit-001",
            "artifact_type": "requirement_backlog",
            "overall_score": 40,
            "passed": False,
            "criteria_scores": {},
            "findings": [],
            "suggested_improvements": [],
            "metadata": {},
        },
        machine_verdict="not_passed",
        evaluator_version="requirement_backlog-v1",
        llm_judge_result={"label": "unclear"},
        decision_judge_result={
            "provider": "jev", "model": "jev-pinned",
            "rubric_version": "material_quality_issue_v1", "policy_version": "v1",
            "answer": "yes", "p_yes": 0.95,
            "accept_negative_at": 0.1, "accept_positive_at": 0.9,
            "recommended_route": "no_escalation_recommended",
        },
        warnings=[{"code": "judge_degraded"}],
        completed_at=now,
    )
    reviews.rows[row.id] = [
        EvaluationReviewRow(
            id=uuid4(),
            evaluation_id=row.id,
            reviewer_id="reviewer-1",
            decision="waived",
            reason="Known limitation",
            waiver_rationale="Accepted for POC",
            created_at=now,
        )
    ]

    response = client.get(
        f"/v1/evaluations/{row.id}", headers={"X-API-Key": "submit-key"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["machine_verdict"] == "not_passed"
    assert body["review_status"] == "waived"
    assert body["deterministic_result"]["overall_score"] == 40
    assert (
        body["deterministic_result"]["evaluator_version"]
        == "requirement_backlog-v1"
    )
    assert body["llm_judge_result"] == {"label": "unclear"}
    assert body["decision_judge_result"]["p_yes"] == 0.95
    assert body["warnings"] == [{"code": "judge_degraded"}]
    assert [item["decision"] for item in body["review_history"]] == ["waived"]


def test_list_returns_pagination_and_forwards_all_filters(client: TestClient) -> None:
    client.post(
        "/v1/evaluations",
        headers={"X-API-Key": "submit-key", "Idempotency-Key": "list"},
        json=valid_requirement_case(),
    )

    response = client.get(
        "/v1/evaluations",
        headers={"X-API-Key": "submit-key"},
        params={
            "page": 1,
            "page_size": 10,
            "artifact_type": "requirement_backlog",
            "execution_status": "queued",
            "machine_verdict": "pass",
            "review_status": "optional",
            "created_from": "2026-08-01T00:00:00Z",
            "created_to": "2026-08-14T00:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json()["page"] == 1
    assert response.json()["page_size"] == 10
    assert response.json()["total"] == 1
    call = client.app.state.test_evaluations.list_call
    assert call["project_id"] == "project-a"
    assert call["artifact_type"] == "requirement_backlog"
    assert call["execution_status"] == "queued"
    assert call["machine_verdict"] == "pass"
    assert call["review_status"] == "optional"
    assert call["created_from"] == datetime(2026, 8, 1, tzinfo=UTC)
    assert call["created_to"] == datetime(2026, 8, 14, tzinfo=UTC)
