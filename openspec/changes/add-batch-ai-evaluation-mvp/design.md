## Context

`ai-evulation-service` starts as an empty repository for a platform-level evaluation service. The first source application is `AI_Requirement_Tool`, whose latest implementation exposes two important flow outputs:

- Requirement backlog flow: canonical `backlog_data` JSON with optional Jira and Confluence derived artifacts.
- PM status flow: canonical `PmStatusReport.to_dict()` JSON with Markdown and optional Confluence derived artifacts.

The MVP must evaluate saved output files offline first, while keeping the evaluation engine independent enough to expose through an API later.

## Goals / Non-Goals

**Goals:**

- Build a batch-first evaluation engine for saved AI output cases.
- Treat canonical structured output as the primary quality target.
- Evaluate published artifacts for fidelity when they are supplied.
- Use deterministic validation and scoring as the stable baseline.
- Add an optional LLM judge extension point without requiring an LLM for local smoke tests.
- Preserve metadata that can later be joined with observability and gateway cost metrics.

**Non-Goals:**

- No live Jira, Confluence, gateway, or observability integration in MVP 1.
- No dashboard UI in MVP 1.
- No production persistence beyond filesystem result files in MVP 1.
- No cost, latency, or value-per-quality scoring in MVP 1.

## Decisions

### Decision: Batch-first, API-ready engine

The core implementation will expose an `EvaluationEngine.evaluate(case)` function and a batch CLI that reads JSON files from disk. This keeps the MVP simple while preserving the same internal contract for a future FastAPI endpoint.

Alternative considered: build the API first. That would introduce request routing, deployment, and auth decisions before evaluator quality is proven.

### Decision: Canonical and published artifact layers

Each evaluation case will separate `canonical_output` from optional `published_artifacts`. Canonical output is required because it is the closest representation of the AI application's intended result. Published artifacts are optional because Jira, Confluence, and Markdown outputs may not exist for every saved case.

Alternative considered: evaluate only rendered text. That would make requirement backlog evaluation depend on Jira or Confluence formatting and would hide structured quality defects.

### Decision: Hybrid evaluator

Deterministic gates always run for schema, required fields, field types, empty sections, and basic quality heuristics. An optional LLM judge can add semantic scoring for clarity, business alignment, testability, evidence grounding, and improvements.

Alternative considered: LLM-only judge. That would be quicker to prototype but harder to reproduce, more expensive, and weaker as a platform foundation.

### Decision: Filesystem result storage for MVP 1

The CLI will write JSON results and a Markdown summary into an output directory. This avoids database setup while still giving repeatable artifacts for comparison.

Alternative considered: add SQLite immediately. SQLite may be useful later, but it is not required for the first closed-loop MVP.

## Risks / Trade-offs

- Deterministic scores can be too shallow for nuanced AI output quality. → Keep LLM judge as an optional evaluator and include findings rather than only numeric scores.
- LLM judge consistency can vary across models and prompts. → Make LLM judge disabled by default and record judge metadata when enabled.
- Published artifacts may be missing or partial in early batches. → Treat published artifact evaluation as optional and report skipped criteria clearly.
- Future source apps may introduce different artifact shapes. → Route by `artifact_type` and keep artifact-specific evaluators isolated.
- Cost metrics are not scored in MVP 1. → Preserve `run_metadata` join keys so observability and gateway metrics can be added without changing case identity.

## Migration Plan

No production migration is required because this is a new service.

Implementation should proceed in small increments:

1. Add Python project structure and domain models.
2. Add deterministic evaluators for requirement backlog and PM status report.
3. Add engine dispatch and batch CLI.
4. Add examples and result writers.
5. Add optional LLM judge abstraction with a disabled default.

Rollback is deletion or non-use of the new service because no external system is modified.

## Open Questions

No blocking MVP 1 questions remain. Future MVPs should decide how to ingest live outputs from `AI_Requirement_Tool`, how to join observability cost metrics, and whether to add persistent run history.
