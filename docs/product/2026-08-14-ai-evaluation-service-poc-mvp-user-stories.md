# AI Evaluation Service POC MVP — User Stories and Acceptance Criteria

Date: 2026-08-14

## Product intent

Prove that AI Evaluation Service can operate as a reusable backend capability inside the Central AI Platform. The POC must let an AI application submit an artifact, receive a durable machine evaluation, and attach Human Review Evidence through one versioned service contract.

### Time box and scope policy

- Stop implementation after **8 elapsed working hours** or **6 implementation tasks**, whichever comes first.
- Implement only work that changes the core experiment result, protects evaluation data, or preserves the existing evaluator/CLI contract.
- Test the happy path, two critical fallbacks (expired Worker lease recovery and optional Judge safe degradation), and one critical trust boundary (cross-project isolation).
- Record production-grade observability, disaster recovery, comprehensive security hardening, deployment automation, and the complete failure matrix in the follow-up backlog instead of implementing them in this POC.
- Review progress every **30–45 minutes** or after **2 implementation tasks**, whichever comes first. Classify discoveries as `POC_BLOCKER`, `FOLLOW_UP`, or `OUT_OF_SCOPE`; discoveries do not expand scope automatically.

Design references:

- [POC design](../superpowers/specs/2026-08-13-ai-evaluation-service-platform-capability-poc-design.md)
- [Chinese Draw.io](../diagrams/ai-evaluation-service-poc.drawio)
- [English Draw.io](../diagrams/ai-evaluation-service-poc-english.drawio)

## POC MVP scope

### Must have

- Asynchronous evaluation submission and status/result query.
- Existing deterministic evaluation for `requirement_backlog` and `pm_status_report`.
- PostgreSQL persistence and a lease-based PostgreSQL Job Worker.
- Idempotent submission.
- Project-scoped API keys and cross-project isolation.
- Append-only Human Review Evidence.
- Health checks and allowlisted logs that do not expose evaluation data or credentials.
- One-command local Docker Compose startup and an automated smoke path.

### Explicitly deferred

- Standalone UI or dashboard.
- Enterprise SSO/OIDC and user lifecycle management.
- A release gate or publishing workflow.
- Multi-level approval, notification, or escalation workflow.
- A real LLM provider integration or LLM Judge calibration.
- Redis, RabbitMQ, Kafka, or another external broker.
- Full Prometheus/OpenTelemetry observability, dashboards, alerting, and production log pipelines.
- Disaster recovery, comprehensive security hardening, and deployment automation.
- Load, capacity, soak, chaos, and exhaustive production failure-matrix testing.
- GKE manifests, high availability, autoscaling, and disaster recovery.
- Trend analytics and quality-per-cost views.

## Personas

- **AI application developer:** integrates an AI application with the shared evaluation API.
- **AI platform reviewer:** records a human decision after reading machine findings.
- **AI platform operator:** runs, diagnoses, and monitors the central capability.

## US-01 — Submit an AI artifact for evaluation

**Card:** As an AI application developer, I want to submit an AI-generated artifact through a stable API, so that my application can use a central evaluation capability without knowing evaluator internals.

**Conversation:** The first consumer is `AI_Requirement_Tool`. The request contract preserves the existing case fields. Submission is asynchronous because a future Judge may add variable latency. The API validates the request before creating durable work.

**Confirmation — Acceptance Criteria:**

1. **Given** a valid API key with `evaluation:submit`, a supported `artifact_type`, and a valid request, **when** the client calls `POST /v1/evaluations` with `Idempotency-Key`, **then** the service returns `202 Accepted`, an `evaluation_id`, and `execution_status = queued`.
2. **Given** a request missing a required case field, **when** it is submitted, **then** the service returns `422` with a stable error code and creates neither an Evaluation nor a Job.
3. **Given** an unsupported `artifact_type`, **when** it is submitted, **then** the service returns `422` and creates no durable work.
4. **Given** an API key without `evaluation:submit`, **when** it submits a case, **then** the service returns `403`.
5. **Given** LLM Judge is disabled and no model credentials exist, **when** a valid case is submitted, **then** the normal evaluation path remains available.

## US-02 — Retry submission safely

**Card:** As an AI application developer, I want submission retries to be idempotent, so that network retries do not create duplicate evaluations.

**Conversation:** Idempotency is scoped to the authenticated project. The service stores a canonical request hash with the key. A key cannot silently refer to two different payloads.

**Confirmation — Acceptance Criteria:**

1. **Given** a project has submitted a valid request with an idempotency key, **when** it repeats the same request with the same key, **then** the service returns the original `evaluation_id` and does not create another Job.
2. **Given** the same project reuses the key with a different canonical request, **when** it submits, **then** the service returns `409 Conflict`.
3. **Given** two different projects use the same idempotency key, **when** both submit valid requests, **then** each project receives its own Evaluation.
4. **Given** two identical requests race concurrently with the same project and key, **when** both transactions finish, **then** exactly one Evaluation and one active Job exist.

## US-03 — Query evaluation status and result

**Card:** As an AI application developer, I want to query execution state and machine findings, so that my application can react after asynchronous evaluation completes.

**Conversation:** Execution state, machine verdict, and review status are separate. Deterministic evaluation remains authoritative for `machine_verdict`. Query responses expose evaluator metadata without exposing Worker internals.

**Confirmation — Acceptance Criteria:**

1. **Given** an Evaluation is waiting or executing, **when** the owner calls `GET /v1/evaluations/{id}`, **then** the response reports `execution_status` as `queued` or `running` and `machine_verdict` as `null`.
2. **Given** deterministic evaluation finishes without an execution error, **when** the owner queries it, **then** `execution_status = completed`, `machine_verdict` is `pass` or `not_passed`, and deterministic scores, findings, suggestions, and evaluator version are returned.
3. **Given** `machine_verdict = pass`, **when** the result is returned, **then** the baseline `review_status = optional`.
4. **Given** `machine_verdict = not_passed`, **when** the result is returned, **then** the baseline `review_status = required`.
5. **Given** an authenticated project, **when** it lists Evaluations, **then** pagination and artifact type, execution status, verdict, review status, and creation-time filters only return that project's records.

## US-04 — Complete work reliably after Worker or optional Judge failures

**Card:** As an AI platform operator, I want evaluations to recover from Worker failure and safely degrade after optional Judge failure, so that infrastructure or an optional AI dependency cannot discard an authoritative deterministic result.

**Conversation:** PostgreSQL Job provides at-least-once execution. Workers claim with `FOR UPDATE SKIP LOCKED`, evaluate outside the claim transaction, renew a lease, and finalize only while they own that lease. Result uniqueness makes duplicate execution safe. The service Worker uses the existing engine with its default disabled Judge for deterministic output, then calls an independently injected fake Judge adapter. This preserves the batch CLI and prevents Judge annotations from mutating deterministic results. Real providers, provider-specific retries, backoff matrices, and failover remain deferred.

**Confirmation — Acceptance Criteria:**

1. **Given** multiple Workers poll the same queue, **when** eligible Jobs are claimed concurrently, **then** each Job has only one active lease owner.
2. **Given** a Worker exits after claiming a Job, **when** its lease expires, **then** another Worker can reclaim the Job and continue processing.
3. **Given** the same Evaluation is computed more than once near a lease boundary, **when** Workers attempt finalization, **then** only the current lease owner can create the single durable result.
4. **Given** deterministic evaluation succeeds and an enabled fake Judge raises a timeout or provider error, **when** the Worker finalizes the Evaluation, **then** `execution_status = completed`, `machine_verdict` and `deterministic_result` are preserved, `llm_judge_result = null`, and a sanitized `judge_degraded` warning contains no prompt, credential, or raw exception.

## US-05 — Record Human Review Evidence

**Card:** As an AI platform reviewer, I want to record a human decision without changing the machine result, so that downstream systems can use both automated and human evidence.

**Conversation:** Review records are append-only. The Evaluation Service records evidence but does not implement a release gate. Allowed decisions depend on the machine verdict to keep `approved` and `waived` semantically distinct.

**Confirmation — Acceptance Criteria:**

1. **Given** a completed Evaluation with `machine_verdict = pass`, **when** a scoped reviewer submits a review, **then** only `approved` or `rejected` is accepted.
2. **Given** a completed Evaluation with `machine_verdict = not_passed`, **when** a scoped reviewer submits a review, **then** only `waived` or `rejected` is accepted.
3. **Given** a `waived` decision without `waiver_rationale`, **when** it is submitted, **then** the service returns `422` and creates no review record.
4. **Given** any accepted decision, **when** it is stored, **then** reviewer identity, reason, optional waiver rationale, and timestamp are appended without changing prior reviews or the deterministic result.
5. **Given** multiple reviews exist, **when** the Evaluation is queried, **then** complete chronological `review_history` and the latest derived `review_status` are returned.

## US-06 — Isolate projects and audit callers

**Card:** As an AI platform owner, I want project-scoped access, so that one application cannot see or alter another application's evaluation data.

**Conversation:** POC authentication uses high-entropy API keys stored only as hashes. Each key maps to one project and scopes. A trusted upstream supplies `reviewer_id`; enterprise identity integration is deferred.

**Confirmation — Acceptance Criteria:**

1. **Given** a missing, disabled, or invalid API key, **when** a protected endpoint is called, **then** the service returns `401`.
2. **Given** a valid key without the required scope, **when** a protected action is attempted, **then** the service returns `403`.
3. **Given** Project B knows an Evaluation ID owned by Project A, **when** Project B reads or reviews it, **then** the service returns `404`.
4. **Given** a valid API key is stored, **when** the database is inspected, **then** only its hash, project binding, scopes, enabled state, and audit timestamps are present.
5. **Given** an accepted request or review, **when** it is logged and persisted, **then** project and caller correlation fields are present without the raw API key.

## US-07 — Verify basic service health and safe diagnostics

**Card:** As an AI platform operator, I want basic health checks and safe logs, so that I can run the local POC without exposing evaluation data or credentials.

**Conversation:** Liveness is process-only. Readiness checks database access and the expected migration revision. Logs use an explicit safe-field allowlist. Metrics dashboards, distributed trace propagation, alerting, and production log pipelines are follow-up work.

**Confirmation — Acceptance Criteria:**

1. **Given** the process is running, **when** `/health/live` is called, **then** it returns `200` without requiring database access.
2. **Given** PostgreSQL is reachable and migration revision is current, **when** `/health/ready` is called, **then** it returns `200`; otherwise it returns `503`.
3. **Given** any normal or error path, **when** logs are inspected, **then** API keys, canonical payloads, full Judge prompts, provider credentials, and raw secret-bearing exceptions are absent.

## US-08 — Run the POC locally end to end

**Card:** As an AI platform developer, I want one-command local startup and a smoke script, so that I can debug and demonstrate the capability before GKE deployment work begins.

**Conversation:** Docker Compose runs API, Worker, and PostgreSQL. It creates the local database, applies migrations, seeds scoped demo API keys, and persists database data in a named volume. The smoke path uses no LLM credentials.

**Confirmation — Acceptance Criteria:**

1. **Given** Docker Desktop is running, **when** `docker compose up --build` is executed from a clean checkout, **then** PostgreSQL becomes healthy, migrations apply, and API and Worker become ready.
2. **Given** the stack is ready, **when** the developer opens `/docs`, **then** OpenAPI documents authentication, submission, query, review, health, and error schemas.
3. **Given** the stack is ready, **when** `scripts/smoke-poc.ps1` runs, **then** it submits both supported artifact types, polls completion, checks pass/not-passed behavior, and appends valid review evidence.
4. **Given** the smoke script retries a submission, **when** the same idempotency key and payload are used, **then** it observes the same Evaluation ID.
5. **Given** no model provider environment variables are configured, **when** the complete smoke path runs, **then** it passes with LLM Judge disabled.

## POC MVP Definition of Done

The POC MVP is accepted only when:

- Every acceptance criterion in US-01 through US-08 has an automated test or an explicit smoke assertion.
- `scripts/quality-check.ps1` passes lint, unit, API, repository, and Worker tests.
- The Docker Compose smoke path passes from a clean local database volume.
- The OpenAPI document can be used by a new consumer without reading evaluator implementation code.
- The existing batch CLI remains operational and its current tests continue to pass.
