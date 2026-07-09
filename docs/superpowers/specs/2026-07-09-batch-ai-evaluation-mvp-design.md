# Batch AI Evaluation MVP Design

## Context

The service will evaluate outputs from proof-of-concept AI applications, starting with `AI_Requirement_Tool`. The first two target flows are requirement backlog generation and PM status report generation.

The current source app uses two output layers:

- Canonical outputs: structured JSON-like objects that represent the agent's intended result.
- Published artifacts: Jira issues, Confluence pages, Markdown reports, or chat-facing text rendered from the canonical output.

This distinction is the core platform pattern for the MVP.

## Goals

- Provide a batch-first evaluation service for saved AI application outputs.
- Evaluate canonical outputs as the first-class quality target.
- Evaluate published artifacts for fidelity and readability when present.
- Keep the engine API-ready so a future FastAPI layer can call the same core logic.
- Preserve run metadata for future joins with observability, gateway, latency, and cost metrics.

## Non-Goals

- No live integration with Jira, Confluence, or `AI_Requirement_Tool` runtime callbacks in MVP 1.
- No cost scoring in MVP 1.
- No dashboard UI in MVP 1.
- No production authentication or multi-tenant storage in MVP 1.

## Artifact Model

Each evaluation case is a JSON file with:

- `case_id`: stable case identifier.
- `artifact_type`: `requirement_backlog` or `pm_status_report`.
- `input`: prompt, source context, or scenario data used to produce the output.
- `canonical_output`: structured output to evaluate.
- `published_artifacts`: optional rendered or published outputs.
- `run_metadata`: optional source app, flow name, model, provider, run id, and trace keys.

The canonical output is required. Published artifacts are optional because the first batch workflows may only export structured results.

## Evaluation Layers

Layer 1 is canonical output evaluation.

- Requirement backlog checks schema validity, completeness, business value, acceptance criteria quality, testability, INVEST signal, clarity, and gaps.
- PM status report checks schema validity, health status validity, executive summary quality, progress/risk/blocker/decision/action completeness, evidence/source references, stakeholder update quality, and confidence notes.

Layer 2 is published artifact evaluation.

- Fidelity: the published artifact reflects the canonical output without dropping important facts.
- Formatting and readability: the artifact is usable by its target audience.
- Traceability: links or source references are present when expected.

Layer 2 runs only when published artifacts are supplied.

## Evaluator Strategy

The MVP uses a hybrid evaluator:

- Deterministic gates always run. They validate artifact type, required fields, field types, empty sections, and basic quality heuristics.
- LLM judge is optional. It scores semantic quality such as clarity, business alignment, testability, PM reasoning, evidence grounding, and suggested improvements.

LLM evaluation must be configurable and disabled by default for local smoke tests.

Suggested configuration:

- `EVAL_LLM_ENABLED=false`
- `EVAL_LLM_PROVIDER=stub`
- `EVAL_LLM_MODEL=`

## Output Model

Each evaluation result contains:

- `case_id`
- `artifact_type`
- `overall_score`
- `passed`
- `criteria_scores`
- `findings`
- `suggested_improvements`
- `metadata`

Scores use a 0-100 scale. Deterministic blocking failures can force `passed=false` even when non-blocking semantic scores are present.

## CLI First

MVP 1 exposes a CLI:

```powershell
python -m app.cli evaluate --input examples --output results
python -m app.cli evaluate-case --file examples/requirement_backlog/login-audit.json
```

The CLI writes JSON run results and a compact Markdown report. The internal engine remains independent of CLI concerns.

## Proposed File Structure

```text
app/
  domain/
    artifact_types.py
    models.py
    scoring.py
  evaluators/
    deterministic.py
    llm_judge.py
    requirement_backlog.py
    pm_status_report.py
  engine.py
  cli.py
  config.py
examples/
  requirement_backlog/
  pm_status_report/
results/
tests/
```

## Error Handling

- Invalid JSON files fail the individual case and do not stop the whole batch.
- Unknown artifact types fail with a clear validation finding.
- Missing canonical outputs fail as blocking errors.
- LLM judge failures produce a warning finding and do not hide deterministic results.

## Testing

Tests should cover:

- Pydantic model validation for evaluation cases and results.
- Requirement backlog deterministic scoring.
- PM status report deterministic scoring.
- Published artifact fidelity checks when artifacts are present.
- Batch CLI behavior for valid and invalid files.
- LLM-disabled default behavior.

## Open Decisions Resolved

- MVP 1 is offline/batch first.
- Hybrid evaluation is the default architecture.
- Cost metrics are not scored in MVP 1, but metadata join keys are preserved.
- Requirement backlog canonical JSON is the primary eval target; Jira and Confluence are derived artifacts.
- PM status report uses `PmStatusReport.to_dict()` as canonical JSON and Markdown/Confluence as published artifacts.
