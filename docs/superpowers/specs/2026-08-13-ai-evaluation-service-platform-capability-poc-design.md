# AI Evaluation Service as a Central AI Platform Capability — POC Design

Date: 2026-08-13
Amended: 2026-08-14
Status: Approved for time-boxed POC implementation

## 1. Context

The repository currently provides a batch-first Python CLI that evaluates saved AI application outputs. It supports `requirement_backlog` and `pm_status_report`, uses deterministic evaluators, writes results to local files, and exposes a disabled-by-default `LlmJudge` extension point.

The POC will turn this evaluator into a reusable backend capability inside a broader Central AI Platform. It is not a standalone evaluation platform and will not own a business UI, user login, dashboard, or release workflow.

The first consumer will be `AI_Requirement_Tool`. Future AI applications must be able to use the same versioned service contract without depending on evaluator internals.

The editable architecture and flow diagrams are available in both
[`Chinese`](../../diagrams/ai-evaluation-service-poc.drawio) and
[`English`](../../diagrams/ai-evaluation-service-poc-english.drawio) versions.

### 1.1 Time-box amendment

This amendment aligns the approved design with the implementation charter. Implementation stops after **8 elapsed working hours** or **6 implementation tasks**, whichever comes first. The POC proves the happy path, two critical fallbacks—expired Worker lease recovery and optional Judge safe degradation—and one critical trust boundary, cross-project isolation.

Only work that changes the experiment conclusion, protects evaluation data, or preserves the existing evaluator/CLI contract is implemented. Full production observability, disaster recovery, comprehensive security hardening, deployment automation, provider-specific retry matrices, load/capacity/soak/chaos testing, and production LLM provider integration remain follow-up work. New findings do not expand this boundary automatically.

## 2. Goals

- Expose a versioned asynchronous REST API for submitting and querying evaluations.
- Reuse the existing deterministic evaluation engine and evaluator registry.
- Persist evaluations, jobs, results, and human review evidence in PostgreSQL.
- Demonstrate reliable asynchronous execution without requiring Redis or RabbitMQ.
- Isolate data by project and authorize service calls with scoped API keys.
- Preserve deterministic results while allowing optional LLM Judge annotations.
- Record append-only Human Review Evidence for machine evaluation results.
- Provide liveness/readiness checks and allowlisted logs that do not expose evaluation data or credentials.
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
- Full Prometheus/OpenTelemetry observability, dashboards, alerting, distributed trace propagation, and production log pipelines.
- Provider-specific retry/backoff matrices, Judge failover, and comprehensive production failure testing.

## 4. Architecture

The POC is a modular monolith deployed as separate API and Worker processes from one application image. PostgreSQL is both the durable business store and the internal job queue.

```text
AI applications / Central Platform workflows
                 |
                 | REST + API key
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
- Project isolation, scope checks, audit fields, health checks, and safe logs.

The service does not own:

- Source application artifact generation or export logic.
- Business UI, dashboards, or final release decisions.
- Enterprise identity authentication. The Central AI Platform may later replace POC API keys with gateway-validated JWT/OIDC claims.

### 4.2 Deployment units

Docker Compose starts three services:

- `api`: REST API, OpenAPI documentation, and health checks.
- `worker`: PostgreSQL job polling, lease management, expired-lease recovery, evaluation, and result persistence.
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
  "warnings": [],
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
                  -> failed     (unexpected deterministic-engine error)
```

Allowed values are `queued`, `running`, `completed`, and `failed`.

An expired Job lease becomes eligible for reclamation while the Evaluation remains `running`. Optional Judge failure does not produce execution failure when deterministic evaluation has succeeded.

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
- `evaluations`: immutable request snapshot, request hash, artifact type, execution state, idempotency key, and timestamps.
- `evaluation_jobs`: evaluation reference, status, attempt count, availability time, lease owner, lease expiry, last safe error, and timestamps.
- `evaluation_results`: one row per evaluation with deterministic result JSON, machine verdict, evaluator version, optional Judge result JSON, safe warning JSON, and completion timestamp.
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

### 8.5 Selected failure behavior

- The implemented infrastructure fallback is expired-lease reclamation with guarded finalization; this proves crash recovery without a general retry matrix.
- Validation and unsupported artifact errors are rejected before Job creation.
- An unexpected deterministic-engine exception may mark execution `failed` with a stable sanitized code.
- If an enabled optional Judge raises a timeout or provider error, complete with the authoritative deterministic result, set `llm_judge_result` to `null`, and store only a sanitized `judge_degraded` warning.
- Real-provider integration, provider-specific classification, retry/backoff, rate-limit behavior, and failover are deferred.

## 9. Evaluation pipeline

The Worker calls the existing `EvaluationEngine` through an application-layer use case. The existing artifact evaluator registry remains the extension mechanism.

Deterministic evaluation remains authoritative for `machine_verdict`. An enabled LLM Judge may add a separate structured result with model, provider, rubric version, prompt version, dimensions, findings, token/cost metadata when available, and provider timing. It does not replace deterministic criteria scores or become a release gate in the POC.

For compatibility, the POC Worker constructs the existing `EvaluationEngine` with its default disabled Judge and uses it only for deterministic evaluation. A Worker-level optional Judge adapter is injected separately and returns a Judge-specific dictionary. This leaves the existing batch CLI and `EvaluationEngine` public interface unchanged while enforcing separate persistence fields in the service contract.

## 10. Error handling

- API validation errors use stable machine-readable error codes.
- Authentication failures return `401`; insufficient scope returns `403`; cross-project access returns `404`.
- Idempotency payload conflicts return `409`.
- Execution errors use stable sanitized codes and are stored without secrets or raw stack traces; comprehensive retryable/terminal classification is deferred.
- Unexpected API exceptions return a correlation identifier and a generic response.
- Database unavailability makes readiness fail while liveness remains independent of database state.

## 11. Basic operations and data safety

### 11.1 Logs

Emit allowlisted JSON logs with `request_id`, `evaluation_id`, `project_id`, artifact type, execution status, attempt, duration, and safe error code.

Do not log API keys, canonical payloads, full Judge prompts, provider credentials, or raw exceptions containing request content.

### 11.2 Health

- `GET /health/live` verifies process liveness.
- `GET /health/ready` verifies database connectivity and expected migration revision.

Prometheus/OpenTelemetry metrics, distributed trace propagation, dashboards, alerting, and production log shipping are explicitly deferred by the time-box amendment.

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

- Unit tests retain coverage of models, scoring, evaluators, state derivation, and the two selected fallback contracts.
- Repository integration tests run against real PostgreSQL and cover migrations, idempotency, concurrent claims, expired-lease recovery, guarded finalization, and required unique constraints.
- API contract tests cover authentication, scopes, validation, idempotency, pagination, project isolation, and review rules.
- Worker tests cover successful execution, lease recovery, duplicate-result protection, and fake-Judge safe degradation. Provider-specific retry exhaustion and failure permutations are deferred.
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
8. When an enabled fake Judge fails, execution still completes with the deterministic result, `llm_judge_result = null`, and only a sanitized `judge_degraded` warning.
9. Another project cannot read or review the Evaluation.
10. Health checks and allowlisted logs support local diagnosis without exposing evaluation payloads or secrets.
11. The normal full path works with LLM Judge disabled and no external model credentials.

## 15. Deferred evolution

- Replace API keys with Central AI Platform gateway identity claims.
- Replace PostgreSQL Job with a managed broker when measured throughput, routing, or operational requirements justify it.
- Deploy API and Worker independently on GKE with managed PostgreSQL.
- Calibrate LLM Judge results against Human Review Evidence before using them in any gate.
- Add Prometheus/OpenTelemetry metrics, trace propagation and metadata, dashboards, alerting, and production log pipelines.
- Add provider-specific Judge retry/backoff, rate-limit handling, and failover after a real provider is selected.
- Join model metadata with platform cost and observability data.
- Add Central AI Platform UI and trend views outside this service boundary.
