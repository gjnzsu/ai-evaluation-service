from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import hash_api_key
from app.api.main import create_app
from app.application.evaluation_service import EvaluationService
from app.application.review_service import ReviewService
from app.persistence.models import (
    ApiClientRow,
    EvaluationResultRow,
    EvaluationReviewRow,
    EvaluationRow,
)


class StubSession:
    def __init__(self, client: ApiClientRow) -> None:
        self.client = client

    async def scalar(self, statement):
        del statement
        return self.client


class StubDatabase:
    def __init__(self, client: ApiClientRow) -> None:
        self.client = client

    @asynccontextmanager
    async def sessions(self):
        yield StubSession(self.client)

    async def dispose(self):
        pass


class MemoryStore:
    def __init__(self, row: EvaluationRow, result: EvaluationResultRow) -> None:
        self.row = row
        self.result = result
        self.reviews: list[EvaluationReviewRow] = []

    async def get_for_project(self, evaluation_id, project_id):
        if self.row.id == evaluation_id and self.row.project_id == project_id:
            return self.row
        return None

    async def get_result_for_project(self, evaluation_id, project_id):
        return self.result if await self.get_for_project(evaluation_id, project_id) else None

    async def list_page_for_project(self, project_id, **filters):
        del project_id, filters
        return [], 0

    async def create_with_job(self, *args, **kwargs):
        raise AssertionError("not used")

    async def append(self, **values):
        review = EvaluationReviewRow(
            id=uuid4(),
            evaluation_id=values["evaluation_id"],
            reviewer_id=values["reviewer_id"],
            decision=values["decision"],
            reason=values["reason"],
            waiver_rationale=values["waiver_rationale"],
            created_at=datetime.now(UTC),
        )
        self.reviews.append(review)
        return review

    async def list_for_project(self, evaluation_id, project_id):
        if await self.get_for_project(evaluation_id, project_id):
            return list(self.reviews)
        return []


def make_client(*, verdict="pass", scopes=None, project_id="project-a"):
    now = datetime.now(UTC)
    row = EvaluationRow(
        id=uuid4(),
        project_id="project-a",
        idempotency_key="review-case",
        request_hash="hash",
        request_payload={},
        artifact_type="requirement_backlog",
        execution_status="completed",
        created_at=now,
        updated_at=now,
    )
    result = EvaluationResultRow(
        evaluation_id=row.id,
        deterministic_result={
            "case_id": "review-case",
            "artifact_type": "requirement_backlog",
            "overall_score": 90 if verdict == "pass" else 30,
            "passed": verdict == "pass",
            "criteria_scores": {},
            "findings": [],
            "suggested_improvements": [],
            "metadata": {},
        },
        machine_verdict=verdict,
        evaluator_version="test-v1",
        llm_judge_result=None,
        warnings=[],
        completed_at=now,
    )
    store = MemoryStore(row, result)
    raw_key = "review-key"
    database = StubDatabase(
        ApiClientRow(
            id=uuid4(),
            project_id=project_id,
            key_hash=hash_api_key(raw_key),
            scopes=scopes if scopes is not None else ["evaluation:review", "evaluation:read"],
            enabled=True,
            created_at=now,
            updated_at=now,
        )
    )
    app = create_app(
        database=database,
        evaluation_service=EvaluationService(store, store),
        review_service=ReviewService(store, store),
    )
    return TestClient(app), store, row, raw_key


def append(client, key, evaluation_id, decision, waiver_rationale=None):
    return client.post(
        f"/v1/evaluations/{evaluation_id}/reviews",
        headers={"X-API-Key": key},
        json={
            "reviewer_id": "reviewer-1",
            "decision": decision,
            "reason": "Human evidence",
            "waiver_rationale": waiver_rationale,
        },
    )


def test_review_is_created_and_latest_status_is_returned() -> None:
    client, _, row, key = make_client()

    response = append(client, key, row.id, "approved")

    assert response.status_code == 201
    assert response.json()["review_status"] == "approved"
    assert response.json()["decision"] == "approved"


def test_not_passed_can_be_waived_with_rationale() -> None:
    client, _, row, key = make_client(verdict="not_passed")

    response = append(client, key, row.id, "waived", "Known POC limitation")

    assert response.status_code == 201
    assert response.json()["review_status"] == "waived"


def test_invalid_decision_returns_422_without_appending() -> None:
    client, store, row, key = make_client(verdict="not_passed")

    response = append(client, key, row.id, "approved")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert store.reviews == []


def test_review_requires_exact_scope() -> None:
    client, _, row, key = make_client(scopes=["evaluation:review:all"])

    response = append(client, key, row.id, "approved")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_scope"


def test_cross_project_review_returns_404() -> None:
    client, _, row, key = make_client(project_id="project-b")

    response = append(client, key, row.id, "approved")

    assert response.status_code == 404


def test_second_review_is_append_only_and_detail_is_chronological() -> None:
    client, store, row, key = make_client()
    assert append(client, key, row.id, "approved").status_code == 201
    assert append(client, key, row.id, "rejected").status_code == 201

    detail = client.get(f"/v1/evaluations/{row.id}", headers={"X-API-Key": key})

    assert [item["decision"] for item in detail.json()["review_history"]] == [
        "approved",
        "rejected",
    ]
    assert detail.json()["review_status"] == "rejected"
    assert detail.json()["machine_verdict"] == "pass"
    assert len(store.reviews) == 2
