## 1. Project Foundation

- [x] 1.1 Create Python package structure under `app/`, `app/domain/`, `app/evaluators/`, and `tests/`
- [x] 1.2 Add project metadata and dependencies for a small Python CLI service
- [x] 1.3 Add a repository quality command for linting and tests

## 2. Domain Models

- [x] 2.1 Implement evaluation case and published artifact models
- [x] 2.2 Implement evaluation result, criteria score, finding, and metadata models
- [x] 2.3 Add tests for valid cases, missing canonical output, unknown artifact type, and metadata preservation

## 3. Deterministic Evaluators

- [x] 3.1 Implement shared deterministic validation helpers for required fields, non-empty text, list quality, and score aggregation
- [x] 3.2 Implement `requirement_backlog` canonical evaluator for schema validity, completeness, business value, acceptance criteria quality, testability, and INVEST signal
- [x] 3.3 Implement `pm_status_report` canonical evaluator for schema validity, health validity, section completeness, source grounding, stakeholder update quality, and confidence notes
- [x] 3.4 Implement optional published artifact fidelity checks for missing canonical facts and skipped artifact criteria
- [x] 3.5 Add focused unit tests for strong and weak requirement backlog and PM status report cases

## 4. Engine and Optional LLM Judge

- [x] 4.1 Implement evaluator registry and `EvaluationEngine.evaluate(case)` dispatch by artifact type
- [x] 4.2 Return clear failed results for unregistered artifact types
- [x] 4.3 Add LLM judge interface with deterministic-only default behavior
- [x] 4.4 Preserve deterministic results and add warning findings when an enabled judge fails
- [x] 4.5 Add engine tests for dispatch, unknown type, disabled judge, and judge failure behavior

## 5. Batch CLI and Result Writers

- [x] 5.1 Implement `evaluate-case --file <case-file> --output <directory>` CLI command
- [x] 5.2 Implement `evaluate --input <directory> --output <directory>` batch CLI command
- [x] 5.3 Continue batch evaluation after invalid JSON or invalid case files
- [x] 5.4 Write per-case JSON results and a compact Markdown batch summary
- [x] 5.5 Add CLI tests for single-case success, batch success, and invalid-file continuation

## 6. Examples and Documentation

- [x] 6.1 Add example `requirement_backlog` evaluation cases with canonical output and optional published artifacts
- [x] 6.2 Add example `pm_status_report` evaluation cases with canonical output and optional Markdown artifact
- [x] 6.3 Add README usage instructions for local batch evaluation and result interpretation
- [x] 6.4 Document how future cost and observability metrics will join through `run_metadata`

## 7. Quality Gate

- [x] 7.1 Run the repository quality command
- [x] 7.2 Fix lint or test failures
- [x] 7.3 Re-run the full quality command and record passing commands in the final handoff
