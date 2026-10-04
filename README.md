# AI Evaluation Service

Central AI Platform evaluation capability POC with a preserved batch CLI and an asynchronous service API. The first supported source app is `AI_Requirement_Tool`, with two artifact types:

- `requirement_backlog`
- `pm_status_report`

The service evaluates canonical structured outputs first and evaluates published artifacts when they are supplied.

## Install

```powershell
python -m pip install -e .[dev]
```

## Run A Single Case

```powershell
python -m app.cli evaluate-case --file examples/requirement_backlog/login-audit.json --output results --run-id login-audit-smoke
```

## Run A Batch

```powershell
python -m app.cli evaluate --input examples --output results --run-id local-smoke
```

The CLI treats `--output` as a local result store root. Each execution writes a run folder:

```text
results/
  runs/
    local-smoke/
      run.json
      summary.json
      summary.md
      cases/
        login-audit-001.result.json
        ai-platform-green-001.result.json
```

`--run-id` is optional. When omitted, the CLI generates a UTC timestamp-based run id.

## Result Shape

Each result includes:

- `overall_score`: 0-100 aggregate score
- `passed`: boolean pass/fail result
- `criteria_scores`: criterion-level scores
- `findings`: blocking errors, warnings, and informational notes
- `suggested_improvements`: practical improvement suggestions
- `metadata`: copied run metadata plus evaluator metadata

## Evaluation Layers

Canonical output evaluation is required. Published artifact evaluation is optional and skipped when no rendered artifacts are supplied.

Requirement backlog canonical output is evaluated for schema validity, completeness, business value, acceptance criteria quality, testability, and INVEST signal.

PM status report canonical output is evaluated for schema validity, health validity, section completeness, source grounding, stakeholder readability, PM reasoning quality, and confidence notes.

## Future Cost Metrics

MVP 1 does not score cost or latency. Cases can include `run_metadata` values such as `source_app`, `flow_name`, `run_id`, `trace_id`, `model`, and `provider`. These fields are preserved in results so future MVPs can join quality scores with platform observability and gateway cost metrics.

## Source App Exporters

Exporter code is not included in this service build. Source applications, such as `AI_Requirement_Tool`, own small producer-side adapters that convert live agent outputs into evaluation case JSON. This service owns the input case contract, evaluator logic, CLI, and run-result storage.

For GKE testing, the expected flow is:

```text
AI_Requirement_Tool UI
  -> source app exporter writes evaluation case JSON
  -> ai-evaluation-service reads those files with `evaluate --input`
  -> local run artifacts are written under `results/runs/<run_id>/`
```

## Product Roadmap

- Human approval evidence: add optional post-evaluation review records under each run, such as `reviews/<case_id>.review.json`, without mutating machine evaluation results. This should support reviewer role, approval status, decision reason, timestamp, and waiver rationale.
- LLM-as-judge MVP 1: add an offline, opt-in semantic judge for saved batch cases. It should use versioned rubrics and structured JSON judge output, record judge model/prompt/rubric metadata, and compare judge findings against human approval evidence for calibration. It should annotate results, not replace deterministic scores or act as a release gate yet.
- Cost and observability join: combine quality scores with gateway and platform observability metrics through preserved run metadata.
- Persistent run index: add SQLite or another lightweight index when local run folders need trend queries or dashboard support.

## Quality Check

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\quality-check.ps1
```

## Local platform POC

The local stack contains exactly three services: FastAPI, a PostgreSQL Job Worker, and PostgreSQL 16. The Worker provides at-least-once execution with an expiring lease; the unique result row and lease-owner check protect finalization. The optional LLM Judge is disabled, so no model credentials are required. Deterministic results, optional Judge annotations, and Human Review Evidence remain separate.

### Design diagrams

The current architecture shows the deterministic evaluation path alongside the optional, project-allowlisted shadow Decision Judge. Jev remains disabled by default and does not change the machine verdict or Human Review status.

![AI Evaluation Service POC architecture, including the optional Jev shadow decision path](docs/diagrams/ai-evaluation-service-poc-english-01%20Service%20Architecture.drawio.png)

The latest architecture is also available as an [SVG export](docs/diagrams/ai-evaluation-service-poc-english-architecture.drawio.svg).

See also the [asynchronous evaluation flow](docs/diagrams/ai-evaluation-service-poc-english-async-flow.drawio.svg) and [state and Human Review diagram](docs/diagrams/ai-evaluation-service-poc-english-state-hitl.drawio.svg). Editable three-page sources are available in [English](docs/diagrams/ai-evaluation-service-poc-english.drawio) and [Chinese](docs/diagrams/ai-evaluation-service-poc.drawio).

Start from a clean local POC database:

```powershell
docker compose down -v
docker compose up --build -d
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-poc.ps1
```

`docker compose down -v` removes only the `ai-evaluation-service-poc` Compose project's containers, network, and named PostgreSQL volume. Do not change the Compose project name to a broad or shared environment name.

Local endpoints:

- Swagger/OpenAPI: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health/live>
- Readiness: <http://localhost:8000/health/ready>

The committed keys are intentionally local demonstration credentials only:

- Project A: `local-project-a-submit-read-review-key`
- Project B: `local-project-b-submit-read-review-key`

Both keys have `evaluation:submit`, `evaluation:read`, and `evaluation:review`. The seed command stores only SHA-256 hashes and is idempotent. Copy `.env.example` to `.env` to override local values; never reuse these keys or the local database password outside this disposable stack.

Compose and the smoke script use the same local configuration precedence: process environment, project `.env`, then `.env.example`. The smoke URL is derived from `AI_EVAL_API_PORT`, and its project keys come from `AI_EVAL_DEMO_PROJECT_A_KEY` and `AI_EVAL_DEMO_PROJECT_B_KEY`. Lease mode reads `POSTGRES_USER` and `POSTGRES_DB` from the running PostgreSQL container before invoking `psql`, so changing the local port, keys, database user, or database name remains consistent. `-BaseUrl` is available only when the caller intentionally needs to target an equivalent local endpoint.

Run the bounded expired-lease recovery evidence separately:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-poc.ps1 -TestLeaseRecovery
```

The normal smoke submits both supported artifact types, waits for `completed`, verifies `pass/optional` and `not_passed/required`, replays an idempotent submission, appends `approved` and `waived` review evidence, and verifies cross-project reads return `404`. The lease mode prepares one expired claimed Job while the Worker is stopped, restarts it, and verifies one result plus an incremented recovery count.

State meanings:

- `execution_status`: `queued`, `running`, `completed`, or `failed`; it describes processing only.
- `machine_verdict`: `pass` or `not_passed`; it exists only after deterministic completion and never represents an execution failure.
- `review_status`: `optional` for pass and `required` for not-passed until the latest append-only human decision becomes `approved`, `rejected`, or `waived`.

Inspect the API and Worker logs with `docker compose logs api worker`. Log records contain only allowlisted correlation and status fields; payloads, API keys, prompts, credentials, and raw exceptions are intentionally excluded.

## Experimental shadow decision judge

The Worker can optionally ask TypeSafe Jev one yes/no question, `material_quality_issue_v1`, about the canonical output and deterministic findings. This is a **shadow experiment**: Jev cannot change `machine_verdict`, deterministic scores, job completion, or `review_status`. The batch CLI and its existing optional LLM Judge are unchanged. The nullable API field `decision_judge_result` is separate from `llm_judge_result`; older results return `null`.

Jev is disabled in the default installation and Compose stack. The automated tests use fake clients and need no TypeSafe account. For an opt-in local run, obtain a TypeSafe API key and an actual version-pinned model ID available to that account, then set these values in your private environment (or a local, untracked `.env`):

```text
AI_EVAL_INSTALL_JEV=true
AI_EVAL_DECISION_JUDGE_PROVIDER=jev
AI_EVAL_DECISION_JUDGE_MODEL=<version-pinned-model-id>
AI_EVAL_DECISION_JUDGE_PROJECTS=project-a
TYPESAFE_API_KEY=<private-key>
```

Rebuild the Worker with `docker compose up --build -d`; the API and PostgreSQL remain the same. The Worker refuses to start when Jev is enabled without a key, pinned model, or nonempty project allowlist. Only evaluations owned by listed project IDs are sent to TypeSafe. Do not commit the key, put it in a request payload, or reuse local demo credentials outside the disposable stack. Container environment variables are visible to people who can inspect the local Docker installation.

The initial per-rubric policy is deliberately **uncalibrated**: `p_yes >= 0.90` or `p_yes <= 0.10` records `no_escalation_recommended`; the middle band records `llm_escalation_recommended`. These are recommendations only—no LLM call or Human Review assignment follows. The result stores only provider/model, rubric and policy versions, answer, probability, thresholds, and route. A timeout, malformed answer, or provider error leaves `decision_judge_result` null and records only `decision_judge_degraded`; deterministic completion continues.

Before using this gate for authoritative decisions, collect a separately labeled held-out set covering both artifact types and analyze false passes and calibration by rubric. Current Human Review evidence is not an independent gold label because review eligibility depends on `machine_verdict`. Promotion beyond shadow mode requires a new design change.
