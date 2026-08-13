# AI Evaluation Service as a Central AI Platform Capability — POC Design

Date: 2026-08-13
Status: Approved for implementation planning

## 1. Context

The repository currently provides a batch-first Python CLI that evaluates saved AI application outputs. It supports `requirement_backlog` and `pm_status_report`, uses deterministic evaluators, writes results to local files, and exposes a disabled-by-default `LlmJudge` extension point.

The POC will turn this evaluator into a reusable backend capability inside a broader Central AI Platform. It is not a standalone evaluation platform and will not own a business UI, user login, dashboard, or release workflow.

The first consumer will be `AI_Requirement_Tool`. Future AI applications must be able to use the same versioned service contract without depending on evaluator internals.

The editable architecture and flow diagrams are in [`docs/diagrams/ai-evaluation-service-poc.drawio`](../../diagrams/ai-evaluation-service-poc.drawio).

## 2. Goals

- Expose a versioned asynchronous REST API for submitting and querying evaluations.
- Reuse the existing deterministic evaluation engine and evaluator registry.
- Persist evaluations, jobs, results, and human review evidence in PostgreSQL.
- Demonstrate reliable asynchronous execution without requiring Redis or RabbitMQ.
- Isolate data by project and authorize service calls with scoped API keys.
- Preserve deterministic results while allowing optional LLM Judge annotations.
- Record append-only Human Review Evidence for machine evaluation results.
- Provide health checks, metrics, structured logs, and trace correlation.
- Run locally with one Docker Compose command before any GKE work begins.

## 3. Non-goals

- A standalone Evaluation Platform UI or dashboard.
- Enterprise SSO, OIDC login flows, or user lifecycle management.
- A release gate or business publishing workflow.
- Multi-level approval, notifications, escalation, or workflow orchestration.
- Production-grade high availability, autoscaling, or disaster recovery.
- A general-purpose message broker or high-throughput task platform.
- Mandatory LLM Judge usage or calibration in the first POC path.
- GKE deployment manifests in the local debug-first increment.

## 4. Architecture

The POC is a modular monolith deployed as separate API and Worker processes from one application image. PostgreSQL is both the durable business store and the internal job queue.

```text
AI applications / Central Platform workflows
                 |
                 | REST + API key + trace context
                 v
        AI Evaluation Service API
                 |
                 | one transaction
                 v
          PostgreSQL
   evaluations + jobs + results + reviews
                 ^
                 | lease-based claim
                 |
              Worker
                 |
                 v
      Deterministic Evaluation Engine
                 |
                 +---- optional LLM Judge
```

### 4.1 Service responsibilities

The service owns:

- Versioned request and response contracts.
- Evaluator dispatch and evaluator version metadata.
- Asynchronous execution, retries, leases, and idempotency.
- Durable machine results and Human Review Evidence.
- Project isolation, scope checks, audit fields, logs, and metrics.

The service does not own:

- Source application artifact generation or export logic.
- Business UI, dashboards, or final release decisions.
- Enterprise identity authentication. The Central AI Platform may later replace POC API keys with gateway-validated JWT/OIDC claims.

### 4.2 Deployment units

Docker Compose starts three services:

- `api`: REST API, OpenAPI documentation, health checks, and metrics.
- `worker`: PostgreSQL job polling, lease management, evaluation, retry, and result persistence.
- `postgres`: durable local database with a named volume and health check.

The API and Worker use the same image with different startup commands. Database migrations run before either process becomes ready.

## 5. API contract

### 5.1 Authentication and isolation

- Requests use `X-API-Key`.
- Each stored key is hashed and maps to one `project_id` and a set of scopes.
- Initial scopes are `evaluation:submit`, `evaluation:read`, and `evaluation:review`.
- `project_id` in a request, when present, must match the authenticated client.
- Cross-project reads and reviews return `404` to avoid revealing resource existence.
- Review requests include a `reviewer_id` asserted by the trusted upstream platform and stored for audit.

### 5.2 Submit evaluation

`POST /v1/evaluations`

Required headers:

- `X-API-Key`
- `Idempotency-Key`
- Optional W3C `traceparent`

The request body retains the current evaluation case shape:

```json
{
  "case_id": "login-audit-001",
  "artifact_type": "requirement_backlog",
  "canonical_output": {},
  "input": {},
  "published_artifacts": {},
  "run_metadata": {}
}
```

A valid new request returns `202 Accepted`:

```json
{
  "evaluation_id": "019...",
  "execution_status": "queued",
  "machine_verdict": null,
  "review_status": null
}
```

`(project_id, idempotency_key)` is unique. Repeating the same key with the same canonical request hash returns the original evaluation. Reusing the key with a different request returns `409 Conflict`.

Invalid input and unsupported artifact types return `422 Unprocessable Entity` and do not create an Evaluation or Job.

### 5.3 Query evaluations

- `GET /v1/evaluations/{evaluation_id}` returns execution state, deterministic result, optional Judge result, and review history.
- `GET /v1/evaluations` supports pagination and filters for artifact type, execution status, machine verdict, review status, and creation time.

The detail response separates three concerns:

```json
{
  "evaluation_id": "019...",
  "execution_status": "completed",
  "machine_verdict": "not_passed",
  "review_status": "required",
  "deterministic_result": {
    "overall_score": 62,
    "passed": false,
    "criteria_scores": {},
    "findings": [],
    "suggested_improvements": [],
    "evaluator_version": "requirement_backlog-v1"
  },
  "llm_judge_result": null,
  "review_history": []
}
```

### 5.4 Submit Human Review Evidence

`POST /v1/evaluations/{evaluation_id}/reviews`

Every review creates a new immutable record. Existing records are never updated or deleted by the POC API.

Rules:

- Machine `pass` permits `approved` or `rejected`.
- Machine `not_passed` permits `waived` or `rejected`.
- Every review requires `reviewer_id` and `reason`.
- `waived` additionally requires `waiver_rationale`.
- The current `review_status` is derived from the latest review; the complete history remains available.
- Reviews never modify the deterministic score, findings, or machine verdict.

## 6. State model

Execution, machine evaluation, and human review are separate state dimensions.

### 6.1 Execution status

```text
queued -> running -> completed
                  -> queued     (retry)
                  -> failed     (retry budget exhausted)
```

Allowed values are `queued`, `running`, `completed`, and `failed`.

### 6.2 Machine verdict

`machine_verdict` is `null` until deterministic evaluation completes. It then becomes `pass` or `not_passed`. Execution failure is not represented as a machine verdict.

### 6.3 Review status

After machine evaluation:

- Machine `pass` produces the baseline `optional` review status.
- Machine `not_passed` produces the baseline `required` review status.
- A new review changes the derived status to `approved`, `rejected`, or `waived` according to the decision rules above.

The service reports these facts but does not decide whether an upstream application may publish or release an artifact.

## 7. Persistence model

The initial schema contains:

- `api_clients`: project binding, hashed API key, scopes, enabled flag, and audit timestamps.
- `evaluations`: immutable request snapshot, request hash, artifact type, execution state, idempotency key, trace metadata, and timestamps.
- `evaluation_jobs`: evaluation reference, status, attempt count, availability time, lease owner, lease expiry, last safe error, and timestamps.
- `evaluation_results`: one row per evaluation with deterministic result JSON, machine verdict, evaluator version, optional Judge result JSON, and completion timestamp.
- `evaluation_reviews`: append-only reviewer decision, reason, waiver rationale, reviewer identity, and timestamp.

Important constraints:

- Unique `evaluations(project_id, idempotency_key)`.
- Unique `evaluation_results(evaluation_id)`.
- Unique active Job per Evaluation.
- Foreign keys prevent orphaned jobs, results, and reviews.
- JSONB stores versioned evaluator-specific details while indexed relational columns support operational queries.

## 8. PostgreSQL Job behavior

### 8.1 Submission

The API validates the request before starting a transaction. It creates the Evaluation and queued Job in one transaction, preventing a durable Evaluation without work to execute.

### 8.2 Claiming

Workers claim eligible work with an ordered `SELECT ... FOR UPDATE SKIP LOCKED`, then set:

- `status = running`
- `lease_owner`
- `lease_expires_at`
- incremented `attempt_count`

The claim transaction is short. Evaluation runs outside the transaction.

### 8.3 Lease and recovery

Workers renew leases during long execution. A Worker only finalizes a Job when it still owns the current lease. Expired running Jobs become eligible for reclamation, allowing recovery after process termination.

### 8.4 Delivery and idempotency

The Job queue provides at-least-once execution, not exactly-once execution. Evaluators must remain free of external side effects. A unique result row, lease-owner check, and transactional result/status update ensure repeated execution does not create multiple business results.

### 8.5 Retry policy

- Retry transient database, provider timeout, provider rate-limit, and temporary availability errors.
- Use exponential backoff for at most three attempts.
- Mark execution `failed` after the retry budget is exhausted and store a structured, sanitized error.
- Validation and unsupported artifact errors are rejected before Job creation.
- If the optional LLM Judge exhausts its retry policy, record a warning and complete with the deterministic result.

## 9. Evaluation pipeline

The Worker calls the existing `EvaluationEngine` through an application-layer use case. The existing artifact evaluator registry remains the extension mechanism.

Deterministic evaluation remains authoritative for `machine_verdict`. An enabled LLM Judge may add a separate structured result with model, provider, rubric version, prompt version, dimensions, findings, token/cost metadata when available, and provider timing. It does not replace deterministic criteria scores or become a release gate in the POC.

## 10. Error handling

- API validation errors use stable machine-readable error codes.
- Authentication failures return `401`; insufficient scope returns `403`; cross-project access returns `404`.
- Idempotency payload conflicts return `409`.
- Execution errors are categorized as retryable or terminal and stored without secrets or raw stack traces.
- Unexpected API exceptions return a correlation identifier and a generic response.
- Database unavailability makes readiness fail while liveness remains independent of database state.

## 11. Observability and security

### 11.1 Logs

Emit structured JSON logs with `request_id`, `trace_id`, `evaluation_id`, `project_id`, artifact type, execution status, attempt, duration, and safe error code.

Do not log API keys, canonical payloads, full Judge prompts, provider credentials, or raw exceptions containing request content.

### 11.2 Metrics

Expose Prometheus metrics for:

- Requests, status codes, and latency.
- Evaluation throughput and duration by artifact type and outcome.
- Queued and running Job counts.
- Oldest queued Job age.
- Retry, terminal failure, and expired lease recovery counts.
- Optional Judge calls, duration, and failure count without high-cardinality identifiers.

### 11.3 Health and trace context

- `GET /health/live` verifies process liveness.
- `GET /health/ready` verifies database connectivity and expected migration revision.
- `GET /metrics` exposes Prometheus text format.
- Incoming W3C `traceparent` is propagated into logs, stored correlation metadata, and optional provider calls.

## 12. Local deployment and developer experience

The primary local workflow is:

```powershell
docker compose up --build
```

Compose automatically starts PostgreSQL, waits for database health, applies migrations, starts the API and Worker, and persists database files in a named volume. Swagger/OpenAPI is available from the API service.

A PowerShell smoke script will:

1. Wait for readiness.
2. Submit both supported artifact examples.
3. Poll until completion.
4. Verify one `pass` and one `not_passed` path.
5. Add valid review evidence.
6. Verify idempotent replay and project isolation.

No local LLM provider configuration is required when the Judge is disabled.

## 13. Testing strategy

- Unit tests retain coverage of models, scoring, evaluators, state derivation, and error classification.
- Repository integration tests run against real PostgreSQL and cover migrations, concurrent claims, lease recovery, retries, unique constraints, and transaction rollback.
- API contract tests cover authentication, scopes, validation, idempotency, pagination, project isolation, and review rules.
- Worker integration tests cover successful execution, deterministic failure verdicts, retry exhaustion, Judge degradation, and duplicate execution protection.
- Docker Compose smoke testing covers the consumer-facing POC path.

## 14. POC acceptance criteria

The POC is complete when all of the following are demonstrated:

1. One Compose command starts API, Worker, and PostgreSQL and applies migrations.
2. OpenAPI documents the complete consumer contract and authentication requirements.
3. A client submits both supported artifact types and polls deterministic results.
4. Idempotent replay produces one Evaluation, while conflicting replay returns `409`.
5. Machine `pass` produces review `optional`; `not_passed` produces review `required`.
6. Review Evidence is append-only and enforces the decision and waiver rules.
7. A terminated Worker leaves a Job that is reclaimed after lease expiry and completes once durably.
8. Another project cannot read or review the Evaluation.
9. Logs and metrics expose operational correlation without exposing evaluation payloads or secrets.
10. The full path works with LLM Judge disabled and no external model credentials.

## 15. Deferred evolution

- Replace API keys with Central AI Platform gateway identity claims.
- Replace PostgreSQL Job with a managed broker when measured throughput, routing, or operational requirements justify it.
- Deploy API and Worker independently on GKE with managed PostgreSQL.
- Calibrate LLM Judge results against Human Review Evidence before using them in any gate.
- Join preserved trace and model metadata with platform cost and observability data.
- Add Central AI Platform UI and trend views outside this service boundary.
