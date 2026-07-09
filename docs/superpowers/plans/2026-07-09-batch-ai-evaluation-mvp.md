# Batch AI Evaluation MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the offline batch MVP for evaluating requirement backlog and PM status report AI outputs.

**Architecture:** The implementation centers on typed domain models, deterministic artifact-specific evaluators, an engine registry, and a CLI that reads JSON cases and writes JSON/Markdown results. LLM judging is represented as an optional interface and defaults to disabled deterministic-only behavior.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, ruff, argparse.

---

## File Structure

- Create `pyproject.toml`: package metadata, dependencies, pytest config, ruff config.
- Create `scripts/quality-check.ps1`: repo-owned quality gate.
- Create `app/domain/artifact_types.py`: artifact type constants.
- Create `app/domain/models.py`: Pydantic models for cases, artifacts, findings, scores, and results.
- Create `app/domain/scoring.py`: score aggregation helpers.
- Create `app/evaluators/deterministic.py`: shared validation and fidelity helpers.
- Create `app/evaluators/requirement_backlog.py`: requirement backlog deterministic evaluator.
- Create `app/evaluators/pm_status_report.py`: PM status deterministic evaluator.
- Create `app/evaluators/llm_judge.py`: optional judge protocol and disabled default.
- Create `app/engine.py`: evaluator registry and judge orchestration.
- Create `app/cli.py`: single-case and batch CLI.
- Create `tests/`: model, evaluator, engine, and CLI tests.
- Create `examples/`: sample requirement backlog and PM status report cases.
- Modify `README.md`: usage, architecture, run metadata guidance.
- Modify `openspec/changes/add-batch-ai-evaluation-mvp/tasks.md`: mark tasks complete as implementation lands.

## Task 1: Domain Models and Project Foundation

- [ ] **Step 1: Write failing model tests**

Create tests that import `EvaluationCase`, `EvaluationResult`, and `Finding`, verify valid case loading, missing canonical output failure, result serialization, and metadata preservation.

Run: `python -m pytest tests/test_models.py -q`
Expected: import failures because the package does not exist yet.

- [ ] **Step 2: Add project skeleton and models**

Create package directories, `pyproject.toml`, `scripts/quality-check.ps1`, and model classes. `canonical_output` must be required, `published_artifacts` and `run_metadata` must default to dictionaries, and result models must serialize cleanly.

- [ ] **Step 3: Verify model tests pass**

Run: `python -m pytest tests/test_models.py -q`
Expected: all model tests pass.

## Task 2: Deterministic Evaluators

- [ ] **Step 1: Write failing evaluator tests**

Create tests for strong/weak `requirement_backlog`, strong/invalid `pm_status_report`, skipped published artifacts, and fidelity findings for missing canonical facts.

Run: `python -m pytest tests/test_evaluators.py -q`
Expected: import failures or missing evaluator behavior.

- [ ] **Step 2: Implement evaluator helpers and artifact evaluators**

Implement score aggregation, findings, blocking failures, required-field checks, text/list quality checks, PM health validation, and basic published artifact fidelity.

- [ ] **Step 3: Verify evaluator tests pass**

Run: `python -m pytest tests/test_evaluators.py -q`
Expected: all evaluator tests pass.

## Task 3: Engine and Optional Judge

- [ ] **Step 1: Write failing engine tests**

Create tests for dispatch by artifact type, unknown artifact failure, disabled judge default, and enabled judge exception preserving deterministic scores.

Run: `python -m pytest tests/test_engine.py -q`
Expected: import failures or missing engine behavior.

- [ ] **Step 2: Implement engine and judge interface**

Implement `EvaluationEngine.evaluate(case)`, registered evaluators, `DisabledJudge`, and judge warning handling.

- [ ] **Step 3: Verify engine tests pass**

Run: `python -m pytest tests/test_engine.py -q`
Expected: all engine tests pass.

## Task 4: CLI, Examples, and Documentation

- [ ] **Step 1: Write failing CLI tests**

Create tests for `evaluate-case`, batch evaluation, invalid JSON continuation, JSON result files, and Markdown summary.

Run: `python -m pytest tests/test_cli.py -q`
Expected: CLI import or behavior failures.

- [ ] **Step 2: Implement CLI and result writers**

Implement `python -m app.cli evaluate-case --file <case-file> --output <directory>` and `python -m app.cli evaluate --input <directory> --output <directory>`. Batch mode must continue after invalid files and emit failed results.

- [ ] **Step 3: Add examples and README**

Add one requirement backlog case and one PM status case. Document commands, result interpretation, deterministic-only default, and future cost metadata joins.

- [ ] **Step 4: Verify CLI tests pass**

Run: `python -m pytest tests/test_cli.py -q`
Expected: all CLI tests pass.

## Task 5: OpenSpec Completion and Review

- [ ] **Step 1: Run full quality gate**

Run: `powershell -ExecutionPolicy Bypass -File .\scripts\quality-check.ps1`
Expected: ruff and pytest pass.

- [ ] **Step 2: Mark OpenSpec tasks complete**

Update every completed checkbox in `openspec/changes/add-batch-ai-evaluation-mvp/tasks.md`.

- [ ] **Step 3: QA review**

Check tests against the OpenSpec scenarios: valid case loading, missing canonical output, weak backlog findings, invalid PM health, published artifact skip/fidelity, unknown type, CLI continuation, disabled/failing judge, and metadata preservation.

- [ ] **Step 4: Product manager review**

Check that MVP 1 stays batch-first, canonical-first, API-ready, cost-aware through metadata, and useful for the two `AI_Requirement_Tool` flows.

- [ ] **Step 5: Archive readiness check**

Run `openspec list --json`, `openspec status --change add-batch-ai-evaluation-mvp --json`, and confirm no remaining `- [ ]` checkboxes.
