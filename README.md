# AI Evaluation Service

Batch-first MVP for evaluating AI application outputs. The first supported source app is `AI_Requirement_Tool`, with two artifact types:

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
