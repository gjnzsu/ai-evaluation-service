# AI Evaluation Service Platform Capability POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing deterministic batch evaluator into an asynchronous, project-isolated REST service that runs locally with PostgreSQL, records Human Review Evidence, and preserves the existing CLI.

**Architecture:** A modular Python service runs the API and Worker as separate processes from one image. PostgreSQL stores domain records and implements an at-least-once Job queue with row locks and leases; the existing `EvaluationEngine` remains the evaluator boundary. API, machine verdict, and Human Review states remain separate.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, psycopg 3, Alembic, PostgreSQL 16, pytest, pytest-asyncio, httpx, Testcontainers, Docker Compose.

## Global Constraints

- The service is a Central AI Platform backend capability, not a standalone Evaluation Platform.
- Keep the existing `requirement_backlog` and `pm_status_report` evaluators and CLI working.
- Use PostgreSQL Job; do not introduce Redis, RabbitMQ, Kafka, or Celery.
- LLM Judge remains optional and disabled by default; no real provider integration is required.
- Human Review Evidence is append-only and never mutates deterministic results.
- Project access uses hashed API keys and exact scopes; cross-project resource access returns `404`.
- Do not log API keys, canonical payloads, full Judge prompts, provider secrets, or raw secret-bearing exceptions.
- The POC must start locally with `docker compose up --build` before GKE work begins.
- Implement only US-01 through US-08 in the [POC MVP backlog](../../product/2026-08-14-ai-evaluation-service-poc-mvp-user-stories.md).
- Stop implementation after 8 elapsed working hours or 6 implementation tasks, whichever comes first.
- Only implement work that affects the core experiment, evaluation-data safety, or compatibility with the existing evaluator and CLI.
- Limit verification to the happy path, expired Worker lease recovery and optional Judge safe degradation as the two critical fallbacks, and cross-project isolation as the critical trust boundary, plus regression tests required to preserve the existing CLI.
- Production observability, disaster recovery, comprehensive security hardening, deployment automation, and the complete production failure matrix are follow-up backlog items.

---

## Time-boxed POC execution charter

**Core hypothesis:** The AI Evaluation Service can operate as a reusable Central AI Platform capability by accepting an artifact through a project-scoped asynchronous API, executing the existing deterministic evaluator through a durable PostgreSQL Job, persisting its machine verdict, and appending independent Human Review Evidence.

**Hard budget:** 8 elapsed working hours or 6 implementation tasks, whichever is reached first. Rework required to pass an existing task's review consumes the same time budget but does not create a seventh task.

**Successful experiment evidence:**

1. Docker Compose starts API, Worker, and PostgreSQL locally without model credentials.
2. The smoke path submits supported artifacts, observes asynchronous completion, and distinguishes `pass/optional` from `not_passed/required`.
3. Reusing an idempotency key returns the same Evaluation, an expired Worker lease is recovered, and only one deterministic result is finalized.
4. When an enabled fake Judge fails, the Evaluation still completes with the deterministic result and a sanitized `judge_degraded` warning.
5. Project B receives `404` when reading or reviewing Project A's Evaluation.
6. Human Review Evidence is append-only and does not modify `machine_verdict`.
7. Existing evaluator and CLI regression tests still pass.

### Review checkpoints and scope control

- At Task 1 dispatch, initialize `.superpowers/sdd/progress.md` with `started_at`, the 8-hour deadline, `tasks_completed: 0/6`, and the current commit. This ledger is the authoritative budget and recovery record.
- Pause after every 2 completed implementation tasks or after 30–45 minutes of elapsed implementation work, whichever comes first.
- At each checkpoint record completed deliverables, commits, test evidence, elapsed time, remaining task budget, open findings, and the next experiment risk.
- Update the ledger immediately after every clean task review; after context compaction or interruption, resume from the first task not marked complete instead of repeating work.
- Classify every new finding before acting:
  - `POC_BLOCKER`: changes the experiment conclusion, exposes evaluation data, breaks project isolation, or breaks the existing evaluator/CLI; it may be fixed within the remaining budget.
  - `FOLLOW_UP`: useful production work that does not change the POC conclusion; record it without implementation.
  - `OUT_OF_SCOPE`: unrelated to the core hypothesis; do not implement it.
- Reviewer suggestions never expand scope automatically. A plan conflict or proposed scope expansion requires the user's decision.
- When either hard limit is reached, stop adding implementation, run the verification available in the current state, and report `validated`, `invalidated`, or `inconclusive` with supporting evidence.

### Planned checkpoints

| Checkpoint | Trigger | Required review |
| --- | --- | --- |
| Pre-flight | Before Task 1 | Confirm clean task boundaries, baseline tests, budget start time, and no plan/spec conflict |
| CP-1 | Tasks 1–2 complete or 30–45 minutes | Foundation/domain and PostgreSQL persistence evidence; classify schema or compatibility discoveries |
| CP-2 | Tasks 3–4 complete or next 30–45 minutes | Trust-boundary and asynchronous API evidence; check remaining budget before Worker work |
| CP-3 | Tasks 5–6 complete or next 30–45 minutes | Lease recovery, Judge degradation, Human Review, local smoke, AC traceability, and POC conclusion |

### Follow-up backlog boundary

- Full Prometheus/OpenTelemetry dashboards, alerting, SLOs, and production log pipeline.
- Backup/restore, regional recovery, queue disaster recovery, and operational runbooks.
- Enterprise IAM/SSO, key rotation, rate limiting, abuse controls, and a comprehensive security review.
- Kubernetes/GKE manifests, CI/CD, cloud secrets integration, and deployment automation.
- Exhaustive retry/provider/database/network failure combinations, load, capacity, soak, and chaos testing.
- Production LLM-as-Judge provider integration and provider failover.

## Story-to-task traceability

| User story | Implementation tasks | Primary verification |
| --- | --- | --- |
| US-01 Submit an artifact | 1, 2, 4, 5 | API contract and Worker integration tests |
| US-02 Retry safely | 2, 4 | Concurrent idempotency integration tests |
| US-03 Query status/result | 1, 2, 4, 5 | API response and filter tests |
| US-04 Recover Worker failures | 2, 5 | Lease recovery and duplicate-finalization tests |
| US-05 Human Review Evidence | 1, 2, 6 | Review validation and append-only tests |
| US-06 Project isolation | 2, 3, 4, 6 | Auth, scope, and cross-project tests |
| US-07 Basic health and safe diagnostics | 1, 6 | Health and sensitive-log tests |
| US-08 Run locally | 6 | Clean Compose smoke run |

## Target file structure

```text
app/
  api/
    __init__.py
    dependencies.py        # database, authenticated client, request context
    errors.py              # stable API error envelope and handlers
    main.py                # FastAPI application factory
    schemas.py             # versioned API request/response models
    routes/
      evaluations.py       # submit, detail, list
      health.py            # live and ready
      reviews.py           # append Human Review Evidence
  application/
    evaluation_service.py  # submit/query application use cases
    review_service.py      # review use case
  config.py                # environment settings
  domain/
    models.py              # existing evaluation case/result models
    platform.py            # platform states and review rules
  observability/
    context.py             # request identifier context
    logging.py             # minimal allowlisted safe logging
  persistence/
    db.py                  # SQLAlchemy engine/session setup
    models.py              # ORM rows and constraints
    repositories.py        # Evaluation, Job, result, review persistence
  worker/
    __init__.py
    __main__.py            # Worker process entry point
    judge.py               # independent optional Judge adapter
    runner.py              # polling loop and graceful shutdown
    service.py             # claim, evaluate, recover leases, finalize
migrations/
  env.py
  versions/0001_platform_poc.py
scripts/
  seed-api-client.py
  smoke-poc.ps1
tests/
  api/
  application/
  domain/
  integration/
  observability/
  worker/
```

### Task 1: FastAPI foundation, platform states, and liveness

**Stories:** US-01, US-03, US-05, US-07

**Files:**
- Modify: `pyproject.toml`
- Create: `app/config.py`
- Create: `app/api/__init__.py`
- Create: `app/api/main.py`
- Create: `app/api/routes/__init__.py`
- Create: `app/api/routes/health.py`
- Create: `tests/api/test_health.py`

**Interfaces:**
- Produces: `Settings`, `get_settings()`, and `create_app() -> FastAPI`.
- Produces: `GET /health/live` returning `{"status": "alive"}` without database access.

- [ ] **Step 1: Add the failing liveness and OpenAPI tests**

```python
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
```

- [ ] **Step 2: Run the tests and verify the missing API package failure**

Run: `python -m pytest tests/api/test_health.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.api'`.

- [ ] **Step 3: Add service dependencies and settings**

Add these runtime dependencies to `pyproject.toml`:

```toml
dependencies = [
    "alembic>=1.13,<2",
    "fastapi>=0.115,<1",
    "psycopg[binary,pool]>=3.2,<4",
    "pydantic>=2.0",
    "pydantic-settings>=2.5,<3",
    "sqlalchemy>=2.0,<3",
    "uvicorn[standard]>=0.30,<1",
]

[project.optional-dependencies]
dev = [
    "httpx>=0.27,<1",
    "pytest>=8.0",
    "pytest-asyncio>=0.24,<1",
    "ruff>=0.5",
    "testcontainers[postgres]>=4.8,<5",
]
```

Create `app/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_EVAL_", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+psycopg://ai_eval:ai_eval@localhost:5432/ai_eval"
    worker_poll_seconds: float = 0.5
    job_lease_seconds: int = 60
    job_max_attempts: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Implement the application factory and liveness route**

```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}
```

```python
from fastapi import FastAPI

from app.api.routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Evaluation Service", version="1.0.0")
    app.include_router(health_router)
    return app


app = create_app()
```

- [ ] **Step 5: Install and verify the foundation**

Run: `python -m pip install -e .[dev]`

Run: `python -m pytest tests/api/test_health.py -q`

Expected: `2 passed`.

- [ ] **Step 6: Commit the foundation**

```powershell
git add pyproject.toml app/config.py app/api tests/api/test_health.py
git commit -m "feat: add evaluation service API foundation"
```

#### Part B: Platform state model and Human Review rules

**Stories:** US-03, US-05

**Files:**
- Create: `app/domain/platform.py`
- Create: `tests/domain/test_platform.py`

**Interfaces:**
- Produces: `ExecutionStatus`, `MachineVerdict`, `ReviewStatus`, `ReviewDecision`.
- Produces: `baseline_review_status(verdict)` and `validate_review_decision(verdict, decision, waiver_rationale)`.

- [ ] **Step 1: Write failing state and decision tests**

```python
import pytest

from app.domain.platform import (
    MachineVerdict,
    ReviewDecision,
    ReviewStatus,
    baseline_review_status,
    validate_review_decision,
)


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        (MachineVerdict.PASS, ReviewStatus.OPTIONAL),
        (MachineVerdict.NOT_PASSED, ReviewStatus.REQUIRED),
    ],
)
def test_baseline_review_status(verdict, expected):
    assert baseline_review_status(verdict) is expected


def test_not_passed_requires_waiver_rationale():
    with pytest.raises(ValueError, match="waiver_rationale"):
        validate_review_decision(
            MachineVerdict.NOT_PASSED,
            ReviewDecision.WAIVED,
            waiver_rationale=None,
        )


def test_approved_is_not_valid_for_not_passed():
    with pytest.raises(ValueError, match="not valid"):
        validate_review_decision(
            MachineVerdict.NOT_PASSED,
            ReviewDecision.APPROVED,
            waiver_rationale=None,
        )
```

- [ ] **Step 2: Verify the tests fail before implementation**

Run: `python -m pytest tests/domain/test_platform.py -q`

Expected: FAIL importing `app.domain.platform`.

- [ ] **Step 3: Implement enums and review policy**

```python
from enum import StrEnum


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MachineVerdict(StrEnum):
    PASS = "pass"
    NOT_PASSED = "not_passed"


class ReviewStatus(StrEnum):
    OPTIONAL = "optional"
    REQUIRED = "required"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAIVED = "waived"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    WAIVED = "waived"


def baseline_review_status(verdict: MachineVerdict) -> ReviewStatus:
    if verdict is MachineVerdict.PASS:
        return ReviewStatus.OPTIONAL
    return ReviewStatus.REQUIRED


def validate_review_decision(
    verdict: MachineVerdict,
    decision: ReviewDecision,
    waiver_rationale: str | None,
) -> None:
    allowed = {
        MachineVerdict.PASS: {ReviewDecision.APPROVED, ReviewDecision.REJECTED},
        MachineVerdict.NOT_PASSED: {ReviewDecision.WAIVED, ReviewDecision.REJECTED},
    }
    if decision not in allowed[verdict]:
        raise ValueError(f"Decision {decision} is not valid for {verdict}")
    if decision is ReviewDecision.WAIVED and not (waiver_rationale or "").strip():
        raise ValueError("waiver_rationale is required for waived decisions")
```

- [ ] **Step 4: Run state tests and existing evaluator tests**

Run: `python -m pytest tests/domain/test_platform.py tests/test_engine.py tests/test_evaluators.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the domain policy**

```powershell
git add app/domain/platform.py tests/domain/test_platform.py
git commit -m "feat: define evaluation platform states"
```

### Task 2: PostgreSQL schema, migrations, and repositories

**Stories:** US-01, US-02, US-03, US-04, US-05, US-06

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/0001_platform_poc.py`
- Create: `app/persistence/__init__.py`
- Create: `app/persistence/db.py`
- Create: `app/persistence/models.py`
- Create: `app/persistence/repositories.py`
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_repositories.py`

**Interfaces:**
- Produces: `Database`, `EvaluationRepository`, `JobRepository`, `ReviewRepository`.
- Produces: ORM rows `ApiClientRow`, `EvaluationRow`, `EvaluationJobRow`, `EvaluationResultRow`, `EvaluationReviewRow`.
- `EvaluationRepository.create_with_job(...) -> tuple[EvaluationRow, bool]`, where the boolean is `created`.

- [ ] **Step 1: Write failing repository integration tests against PostgreSQL**

```python
import pytest

from app.persistence.repositories import EvaluationRepository


@pytest.mark.asyncio
async def test_create_with_job_is_idempotent(session_factory):
    repository = EvaluationRepository(session_factory)
    request = {
        "case_id": "login-audit",
        "artifact_type": "requirement_backlog",
        "canonical_output": {"summary": "Audit logins"},
    }

    first, first_created = await repository.create_with_job(
        project_id="project-a",
        idempotency_key="key-1",
        request_payload=request,
        request_hash="hash-1",
    )
    second, second_created = await repository.create_with_job(
        project_id="project-a",
        idempotency_key="key-1",
        request_payload=request,
        request_hash="hash-1",
    )

    assert first.id == second.id
    assert first_created is True
    assert second_created is False


@pytest.mark.asyncio
async def test_same_key_with_different_hash_conflicts(session_factory):
    repository = EvaluationRepository(session_factory)
    await repository.create_with_job(
        "project-a", "key-1", {"case_id": "a"}, "hash-a"
    )

    with pytest.raises(ValueError, match="idempotency key"):
        await repository.create_with_job(
            "project-a", "key-1", {"case_id": "b"}, "hash-b"
        )
```

- [ ] **Step 2: Add a Testcontainers PostgreSQL fixture and verify failure**

```python
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres.get_connection_url().replace("psycopg2", "psycopg")


@pytest.fixture(scope="session")
def migrated_database(postgres_url):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(config, "head")
    return postgres_url


@pytest.fixture
async def session_factory(postgres_url, migrated_database):
    engine = create_async_engine(postgres_url)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
```

Run: `python -m pytest tests/integration/test_repositories.py -q`

Expected: FAIL because persistence modules and migrations do not exist.

- [ ] **Step 3: Implement the ORM schema and constraints**

Define these exact relational columns in `app/persistence/models.py`:

```python
class EvaluationRow(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_eval_project_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[str] = mapped_column(String(100), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict] = mapped_column(JSONB)
    artifact_type: Mapped[str] = mapped_column(String(100), index=True)
    execution_status: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationJobRow(Base):
    __tablename__ = "evaluation_jobs"

    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(30), index=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_recovery_count: Mapped[int] = mapped_column(default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
```

Also create API client and append-only review rows with the constraints from the design spec. Define the result row with separate deterministic, Judge, and warning fields:

```python
class EvaluationResultRow(Base):
    __tablename__ = "evaluation_results"

    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), primary_key=True
    )
    deterministic_result: Mapped[dict] = mapped_column(JSONB)
    machine_verdict: Mapped[str] = mapped_column(String(30), index=True)
    evaluator_version: Mapped[str] = mapped_column(String(100))
    llm_judge_result: Mapped[dict | None] = mapped_column(JSONB)
    warnings: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Create and apply the initial Alembic migration**

Run: `python -m alembic revision --autogenerate -m "platform poc schema"`

Rename the generated file to `migrations/versions/0001_platform_poc.py`, review every table/constraint, then run:

Set the migration module's `revision = "0001_platform_poc"` so readiness has one stable expected revision.

`python -m alembic upgrade head`

Expected: all five tables and `alembic_version` exist.

- [ ] **Step 5: Implement transactional repository methods**

Implement `create_with_job` with one transaction and conflict recovery. Implement list/detail scoping by `project_id`, result insertion with unique `evaluation_id`, and append-only review insertion. Never accept a repository read without `project_id`.

```python
async def get_for_project(self, evaluation_id: UUID, project_id: str) -> EvaluationRow | None:
    async with self._sessions() as session:
        statement = select(EvaluationRow).where(
            EvaluationRow.id == evaluation_id,
            EvaluationRow.project_id == project_id,
        )
        return await session.scalar(statement)
```

- [ ] **Step 6: Verify repository and migration behavior**

Run: `python -m pytest tests/integration/test_repositories.py -q`

Expected: all tests pass, including concurrent same-key submission and rollback tests.

- [ ] **Step 7: Commit persistence**

```powershell
git add alembic.ini migrations app/persistence tests/integration
git commit -m "feat: persist evaluations and jobs in postgres"
```

### Task 3: API-key authentication, scopes, and request context

**Stories:** US-06, US-07

**Files:**
- Create: `app/api/dependencies.py`
- Create: `app/api/errors.py`
- Create: `app/observability/__init__.py`
- Create: `app/observability/context.py`
- Create: `tests/api/test_auth.py`

**Interfaces:**
- Produces: `AuthenticatedClient(project_id: str, scopes: frozenset[str])`.
- Produces: `authenticate_client(required_scope: str)` FastAPI dependency factory.
- Produces: request-scoped `request_id` and authenticated `project_id` context.

- [ ] **Step 1: Write failing authentication and isolation tests**

```python
def test_missing_api_key_returns_401(client):
    response = client.get("/v1/evaluations")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_missing_scope_returns_403(read_only_client):
    response = read_only_client.post(
        "/v1/evaluations",
        headers={"Idempotency-Key": "key-1"},
        json=valid_case_payload(),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_scope"
```

- [ ] **Step 2: Verify authentication tests fail**

Run: `python -m pytest tests/api/test_auth.py -q`

Expected: FAIL because protected routes and authentication dependencies do not exist.

- [ ] **Step 3: Implement hash lookup and constant-time validation**

```python
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class AuthenticatedClient:
    project_id: str
    scopes: frozenset[str]


def hash_api_key(raw_key: str) -> str:
    return sha256(raw_key.encode("utf-8")).hexdigest()
```

Look up the hash in `api_clients`, reject disabled keys, and require the exact scope. Never log or persist the raw key.

- [ ] **Step 4: Implement stable error envelopes and correlation middleware**

All errors use:

```json
{
  "error": {
    "code": "insufficient_scope",
    "message": "The API key does not grant evaluation:submit.",
    "request_id": "019..."
  }
}
```

Accept or create a request identifier and store it with the authenticated project ID in context variables for error responses and safe logs. Distributed trace propagation is follow-up work.

- [ ] **Step 5: Run auth tests**

Run: `python -m pytest tests/api/test_auth.py -q`

Expected: all tests pass for missing, invalid, disabled, and insufficient-scope keys.

- [ ] **Step 6: Commit authentication**

```powershell
git add app/api/dependencies.py app/api/errors.py app/observability tests/api/test_auth.py
git commit -m "feat: authorize project-scoped API clients"
```

### Task 4: Asynchronous submission and query API

**Stories:** US-01, US-02, US-03, US-06

**Files:**
- Create: `app/api/schemas.py`
- Create: `app/application/__init__.py`
- Create: `app/application/evaluation_service.py`
- Create: `app/api/routes/evaluations.py`
- Modify: `app/api/main.py`
- Create: `tests/application/test_evaluation_service.py`
- Create: `tests/api/test_evaluations.py`

**Interfaces:**
- Produces: `EvaluationService.submit`, `.get`, and `.list`.
- Produces endpoints `POST /v1/evaluations`, `GET /v1/evaluations/{id}`, and `GET /v1/evaluations`.
- Consumes: project-scoped repositories and authentication from Tasks 3-4.

- [ ] **Step 1: Write failing API contract tests for US-01 through US-03**

```python
def test_submit_returns_202_and_queued(client, submit_headers):
    response = client.post(
        "/v1/evaluations",
        headers=submit_headers | {"Idempotency-Key": "case-1"},
        json=valid_requirement_case(),
    )
    assert response.status_code == 202
    assert response.json()["execution_status"] == "queued"
    assert response.json()["machine_verdict"] is None


def test_replay_returns_original_evaluation(client, submit_headers):
    first = client.post(
        "/v1/evaluations",
        headers=submit_headers | {"Idempotency-Key": "case-1"},
        json=valid_requirement_case(),
    )
    second = client.post(
        "/v1/evaluations",
        headers=submit_headers | {"Idempotency-Key": "case-1"},
        json=valid_requirement_case(),
    )
    assert second.status_code == 200
    assert second.json()["evaluation_id"] == first.json()["evaluation_id"]
```

- [ ] **Step 2: Run API tests and confirm missing routes**

Run: `python -m pytest tests/api/test_evaluations.py -q`

Expected: FAIL with `404 Not Found`.

- [ ] **Step 3: Implement canonical request hashing and submit use case**

```python
import hashlib
import json


def canonical_request_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

Validate `artifact_type` against `SUPPORTED_ARTIFACT_TYPES`, call `create_with_job`, return `202` for a new Evaluation, `200` for an idempotent replay, and translate hash mismatch to `409`.

- [ ] **Step 4: Implement detail and filtered list response assembly**

Return separate fields:

```python
class EvaluationDetail(BaseModel):
    evaluation_id: UUID
    execution_status: ExecutionStatus
    machine_verdict: MachineVerdict | None
    review_status: ReviewStatus | None
    deterministic_result: EvaluationResult | None
    llm_judge_result: dict[str, Any] | None
    warnings: list[SafeWarning]
    review_history: list[ReviewEvidence]
```

Define the only POC warning contract explicitly:

```python
class SafeWarning(BaseModel):
    code: Literal["judge_degraded"]
```

Derive baseline review status only after a result exists; use the latest review decision when history is non-empty.

- [ ] **Step 5: Verify API validation, idempotency, query, filtering, and isolation**

Run: `python -m pytest tests/application/test_evaluation_service.py tests/api/test_evaluations.py -q`

Expected: all tests pass, including `422`, `409`, pagination, filters, and cross-project `404`.

- [ ] **Step 6: Commit evaluation API**

```powershell
git add app/api app/application tests/api/test_evaluations.py tests/application
git commit -m "feat: expose asynchronous evaluation API"
```

### Task 5: PostgreSQL Job Worker, lease recovery, Judge degradation, and engine integration

**Stories:** US-01, US-03, US-04

**Files:**
- Modify: `app/persistence/repositories.py`
- Create: `app/worker/__init__.py`
- Create: `app/worker/__main__.py`
- Create: `app/worker/judge.py`
- Create: `app/worker/runner.py`
- Create: `app/worker/service.py`
- Create: `tests/worker/test_service.py`
- Create: `tests/integration/test_job_claims.py`

**Interfaces:**
- Produces: `JobRepository.claim_next`, `.renew_lease`, `.complete`, and `.fail`.
- Produces: `WorkerService.process_one() -> bool`; `False` means no eligible Job.
- Consumes: existing `EvaluationEngine.evaluate(EvaluationCase) -> EvaluationResult`.
- Produces: `OptionalJudge.evaluate(case, deterministic_result) -> dict[str, Any]` and `DisabledOptionalJudge`; this adapter is independent from the existing batch-engine `LlmJudge` protocol.

- [ ] **Step 1: Write failing concurrent claim and recovery tests**

```python
@pytest.mark.asyncio
async def test_only_one_worker_claims_a_job(job_repository, queued_evaluation):
    first, second = await asyncio.gather(
        job_repository.claim_next("worker-a", lease_seconds=60),
        job_repository.claim_next("worker-b", lease_seconds=60),
    )
    claimed = [job for job in (first, second) if job is not None]
    assert len(claimed) == 1


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed(job_repository, expired_running_job):
    claimed = await job_repository.claim_next("worker-b", lease_seconds=60)
    assert claimed.evaluation_id == expired_running_job.evaluation_id
    assert claimed.lease_recovery_count == 1


@pytest.mark.asyncio
async def test_current_owner_can_renew_lease(job_repository, claimed_job):
    renewed = await job_repository.renew_lease(
        claimed_job.evaluation_id,
        lease_owner=claimed_job.lease_owner,
        lease_seconds=60,
    )
    assert renewed.lease_expires_at > claimed_job.lease_expires_at
```

- [ ] **Step 2: Write failing Worker outcome tests**

```python
@pytest.mark.asyncio
async def test_worker_persists_deterministic_result(worker_service, queued_evaluation):
    processed = await worker_service.process_one()
    detail = await queued_evaluation.reload()
    assert processed is True
    assert detail.execution_status == "completed"
    assert detail.result.machine_verdict in {"pass", "not_passed"}


@pytest.mark.asyncio
async def test_judge_failure_preserves_deterministic_completion(
    worker_with_failing_judge,
    queued_evaluation,
):
    await worker_with_failing_judge.process_one()
    detail = await queued_evaluation.reload()
    assert detail.execution_status == "completed"
    assert detail.result.machine_verdict in {"pass", "not_passed"}
    assert detail.result.deterministic_result is not None
    assert detail.result.llm_judge_result is None
    assert detail.result.warnings == [{"code": "judge_degraded"}]
```

- [ ] **Step 3: Verify Worker tests fail before implementation**

Run: `python -m pytest tests/worker/test_service.py tests/integration/test_job_claims.py -q`

Expected: FAIL because Job claim and Worker services do not exist.

- [ ] **Step 4: Implement atomic claim with `SKIP LOCKED`**

```python
statement = (
    select(EvaluationJobRow)
    .where(
        or_(
            and_(
                EvaluationJobRow.status == "queued",
                EvaluationJobRow.available_at <= now,
            ),
            and_(
                EvaluationJobRow.status == "running",
                EvaluationJobRow.lease_expires_at < now,
            ),
        )
    )
    .order_by(EvaluationJobRow.available_at, EvaluationJobRow.evaluation_id)
    .with_for_update(skip_locked=True)
    .limit(1)
)
```

Set owner, expiry, status, and attempt count in the same short transaction. Increment recovery count only when reclaiming an expired running Job.

- [ ] **Step 5: Implement evaluation and guarded finalization**

Load the immutable request snapshot, validate `EvaluationCase`, call the existing engine outside a database transaction, map `result.passed` to `pass` or `not_passed`, and finalize only when `lease_owner` still matches.

```python
verdict = MachineVerdict.PASS if result.passed else MachineVerdict.NOT_PASSED
await self._jobs.complete(
    evaluation_id=job.evaluation_id,
    lease_owner=self._worker_id,
    deterministic_result=result.model_dump(mode="json"),
    machine_verdict=verdict,
)
```

Start a lease-renewal coroutine before invoking the engine. Renew at one-third of the configured lease duration, cancel the coroutine after evaluation, and refuse finalization when renewal reports that ownership was lost.

- [ ] **Step 6: Implement Judge safe degradation and a sanitized terminal boundary**

Construct the existing `EvaluationEngine` with its default disabled Judge and treat its output as authoritative deterministic data. Then invoke the independently injected `OptionalJudge`. Use a fake implementation in tests. When it raises, complete the Evaluation with the deterministic verdict and result, set `llm_judge_result` to `null`, and persist only `{"code": "judge_degraded"}` in result warnings. Do not modify the existing batch `EvaluationEngine` or `LlmJudge` public interfaces. Never persist prompts, credentials, provider payloads, or `repr(error)`. An unexpected deterministic-engine exception may mark execution `failed` with a stable generic code; provider-specific classification, retry/backoff, and failover are follow-up work.

- [ ] **Step 7: Implement the polling runner and graceful shutdown**

```python
async def run(worker: WorkerService, poll_seconds: float) -> None:
    stop = asyncio.Event()
    install_signal_handlers(stop)
    while not stop.is_set():
        processed = await worker.process_one()
        if not processed:
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
```

- [ ] **Step 8: Verify concurrent claim, lease recovery, guarded finalization, verdicts, and Judge degradation**

Run: `python -m pytest tests/worker tests/integration/test_job_claims.py tests/test_engine.py -q`

Expected: all tests pass, including fake-Judge failure completing with the deterministic result and sanitized `judge_degraded` warning.

- [ ] **Step 9: Commit Worker implementation**

```powershell
git add app/persistence/repositories.py app/worker tests/worker tests/integration/test_job_claims.py
git commit -m "feat: process evaluations with postgres jobs"
```

### Task 6: Human Review, safe local operation, Compose, and POC evidence

#### Part A: Append-only Human Review Evidence API

**Stories:** US-05, US-06

**Files:**
- Create: `app/application/review_service.py`
- Create: `app/api/routes/reviews.py`
- Modify: `app/api/schemas.py`
- Modify: `app/api/main.py`
- Create: `tests/application/test_review_service.py`
- Create: `tests/api/test_reviews.py`

**Interfaces:**
- Produces: `ReviewService.append(project_id, evaluation_id, reviewer_id, decision, reason, waiver_rationale)`.
- Produces: `POST /v1/evaluations/{evaluation_id}/reviews` requiring `evaluation:review`.

- [ ] **Step 1: Write failing review policy and append-only API tests**

```python
def test_not_passed_can_be_waived(client, review_headers, not_passed_evaluation):
    response = client.post(
        f"/v1/evaluations/{not_passed_evaluation}/reviews",
        headers=review_headers,
        json={
            "reviewer_id": "reviewer-1",
            "decision": "waived",
            "reason": "Known POC limitation",
            "waiver_rationale": "The missing field is not used in this demonstration.",
        },
    )
    assert response.status_code == 201
    assert response.json()["review_status"] == "waived"


def test_second_review_does_not_overwrite_first(client, review_headers, passed_evaluation):
    append_review(client, passed_evaluation, "approved")
    append_review(client, passed_evaluation, "rejected")
    detail = client.get(f"/v1/evaluations/{passed_evaluation}", headers=review_headers)
    assert [item["decision"] for item in detail.json()["review_history"]] == [
        "approved",
        "rejected",
    ]
```

- [ ] **Step 2: Verify review tests fail**

Run: `python -m pytest tests/application/test_review_service.py tests/api/test_reviews.py -q`

Expected: FAIL because review use case and route do not exist.

- [ ] **Step 3: Implement review validation and append**

Require a completed machine result, validate the decision with the platform policy defined in Task 1 Part B, verify project ownership, then insert a new review row. Do not add update or delete repository methods for reviews.

- [ ] **Step 4: Implement route and response**

Return `201 Created` with the new evidence and latest derived status. Translate invalid decision/rationale to `422`; return `404` for missing or cross-project Evaluation.

- [ ] **Step 5: Verify every US-05 acceptance criterion**

Run: `python -m pytest tests/domain/test_platform.py tests/application/test_review_service.py tests/api/test_reviews.py -q`

Expected: all tests pass for pass/not-passed decision matrices, rationale, history order, scope, and isolation.

- [ ] **Step 6: Commit Human Review Evidence**

```powershell
git add app/application/review_service.py app/api tests/application/test_review_service.py tests/api/test_reviews.py
git commit -m "feat: record human review evidence"
```

#### Part B: Readiness and safe logs

**Stories:** US-07

**Files:**
- Modify: `app/api/routes/health.py`
- Create: `app/observability/logging.py`
- Modify: `app/api/main.py`
- Modify: `app/worker/service.py`
- Create: `tests/observability/test_logging.py`
- Modify: `tests/api/test_health.py`

**Interfaces:**
- Produces: `/health/ready`.
- Produces: `configure_json_logging()` and allowlisted `safe_log_fields()`.

- [ ] **Step 7: Write failing readiness and sensitive-log tests**

```python
def test_readiness_is_503_when_database_check_fails(client, broken_database):
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_logs_omit_payload_and_api_key(caplog, client, submit_headers):
    client.post(
        "/v1/evaluations",
        headers=submit_headers | {"Idempotency-Key": "safe-log-test"},
        json=valid_requirement_case(),
    )
    rendered = "\n".join(record.message for record in caplog.records)
    assert submit_headers["X-API-Key"] not in rendered
    assert "canonical_output" not in rendered
```

- [ ] **Step 8: Implement minimal readiness and safe logging**

Readiness runs `SELECT 1` and verifies `alembic_version.version_num == "0001_platform_poc"`. It returns `503` without exception details on failure. Logs are built only from an explicit allowlist containing event, request ID, project ID, Evaluation ID, artifact type, execution status, attempt, duration, and safe error code; never serialize request objects, evaluation payloads, credentials, prompts, or raw exceptions.

- [ ] **Step 9: Verify US-07**

Run: `python -m pytest tests/api/test_health.py tests/observability/test_logging.py -q`

Expected: liveness/readiness and sensitive-log tests pass.

#### Part C: Docker Compose, seed client, smoke path, and final documentation

**Stories:** US-08 and final verification of US-01 through US-07

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `compose.yaml`
- Create: `.env.example`
- Create: `scripts/seed-api-client.py`
- Create: `scripts/smoke-poc.ps1`
- Modify: `scripts/quality-check.ps1`
- Modify: `README.md`
- Create: `tests/e2e/test_openapi_contract.py`

**Interfaces:**
- Produces local services `api`, `worker`, and `postgres`.
- Produces demo keys with submit/read/review scopes.
- Produces a non-interactive smoke command that returns exit code `0` only when the full POC path succeeds.

- [ ] **Step 1: Add a failing OpenAPI contract test**

```python
def test_openapi_contains_all_poc_operations(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/evaluations" in paths
    assert "/v1/evaluations/{evaluation_id}" in paths
    assert "/v1/evaluations/{evaluation_id}/reviews" in paths
    assert "/health/live" in paths
    assert "/health/ready" in paths
```

- [ ] **Step 2: Verify the complete automated suite before container work**

Run: `powershell -ExecutionPolicy Bypass -File .\scripts\quality-check.ps1`

Expected: current lint and all unit/API/integration/Worker tests pass.

- [ ] **Step 3: Create the production-shaped Docker image**

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /service

COPY pyproject.toml README.md ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./
RUN python -m pip install --no-cache-dir .

USER 65532:65532
```

- [ ] **Step 4: Create three-service Compose orchestration**

`compose.yaml` must define:

- `postgres`: PostgreSQL 16-alpine, health check, named volume.
- `api`: run `alembic upgrade head`, seed the demo API client idempotently, then start Uvicorn; depend on healthy PostgreSQL.
- `worker`: start `python -m app.worker`; depend on healthy API so migrations are complete.

Use only local development credentials from `.env.example`. Do not commit a production key.

- [ ] **Step 5: Implement the smoke script with explicit assertions**

The PowerShell script must:

1. Wait for `/health/ready` with a bounded timeout.
2. Submit one strong requirement case and one weak PM status case.
3. Poll each Evaluation until `completed` or fail on timeout/`failed`.
4. Assert one `pass/optional` and one `not_passed/required` result.
5. Replay one submission and assert the same Evaluation ID.
6. Append `approved` to the pass result and `waived` with rationale to the not-passed result.
7. Use a second project key and assert cross-project detail returns `404`.
8. Exit `0` only if every assertion succeeds.

- [ ] **Step 6: Run the clean local POC**

Run:

```powershell
docker compose down -v
docker compose up --build -d
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-poc.ps1
```

Expected: smoke script prints `POC smoke passed` and exits `0` without model credentials.

- [ ] **Step 7: Verify Worker lease recovery manually and automate the assertion**

Submit an Evaluation, stop the Worker after claim, wait beyond the configured local lease, restart the Worker, and assert the Evaluation reaches `completed` with one result row and `lease_recovery_count >= 1`. Add this as a second mode:

`powershell -ExecutionPolicy Bypass -File .\scripts\smoke-poc.ps1 -TestLeaseRecovery`

- [ ] **Step 8: Update README and quality command**

Document local startup, demo keys, Swagger URL, smoke commands, state meanings, disabled Judge behavior, and cleanup. Update `scripts/quality-check.ps1` to run lint plus all automated tests; keep the Compose smoke as an explicit POC gate because it destroys only the named local test volume.

- [ ] **Step 9: Run final quality and smoke gates**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\quality-check.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-poc.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-poc.ps1 -TestLeaseRecovery
```

Expected: lint passes, all tests pass, normal smoke passes, and lease recovery smoke passes.

- [ ] **Step 10: Commit the complete local POC**

```powershell
git add Dockerfile .dockerignore compose.yaml .env.example app/api app/observability app/worker/service.py scripts README.md tests/api/test_health.py tests/e2e tests/observability
git commit -m "feat: run evaluation service poc locally"
```

## Final self-review checklist

- [ ] Every AC in US-01 through US-08 maps to an automated test or smoke assertion.
- [ ] `EvaluationEngine` remains usable by the batch CLI and all original tests pass.
- [ ] `machine_verdict` is never used to represent execution failure.
- [ ] Deterministic result, optional Judge result, and review history remain separate.
- [ ] No repository method can read an Evaluation without `project_id`.
- [ ] Reviews have insert-only application and repository interfaces.
- [ ] Job execution is described and tested as at-least-once, not exactly-once.
- [ ] Logs do not contain API keys, canonical payloads, prompts, credentials, or raw secret-bearing exceptions.
- [ ] Docker Compose contains only API, Worker, and PostgreSQL services.
- [ ] The POC runs with LLM Judge disabled and no model credentials.
