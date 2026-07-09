## 1. Project Foundation

- [ ] 1.1 Create Python package structure under `app/`, `app/domain/`, `app/evaluators/`, and `tests/`
- [ ] 1.2 Add project metadata and dependencies for a small Python CLI service
- [ ] 1.3 Add a repository quality command for linting and tests

## 2. Domain Models

- [ ] 2.1 Implement evaluation case and published artifact models
- [ ] 2.2 Implement evaluation result, criteria score, finding, and metadata models
- [ ] 2.3 Add tests for valid cases, missing canonical output, unknown artifact type, and metadata preservation

## 3. Deterministic Evaluators

- [ ] 3.1 Implement shared deterministic validation helpers for required fields, non-empty text, list quality, and score aggregation
- [ ] 3.2 Implement `requirement_backlog` canonical evaluator for schema validity, completeness, business value, acceptance criteria quality, testability, and INVEST signal
- [ ] 3.3 Implement `pm_status_report` canonical evaluator for schema validity, health validity, section completeness, source grounding, stakeholder update quality, and confidence notes
- [ ] 3.4 Implement optional published artifact fidelity checks for missing canonical facts and skipped artifact criteria
- [ ] 3.5 Add focused unit tests for strong and weak requirement backlog and PM status report cases

## 4. Engine and Optional LLM Judge

- [ ] 4.1 Implement evaluator registry and `EvaluationEngine.evaluate(case)` dispatch by artifact type
- [ ] 4.2 Return clear failed results for unregistered artifact types
- [ ] 4.3 Add LLM judge interface with deterministic-only default behavior
- [ ] 4.4 Preserve deterministic results and add warning findings when an enabled judge fails
- [ ] 4.5 Add engine tests for dispatch, unknown type, disabled judge, and judge failure behavior

## 5. Batch CLI and Result Writers

- [ ] 5.1 Implement `evaluate-case --file <case-file> --output <directory>` CLI command
- [ ] 5.2 Implement `evaluate --input <directory> --output <directory>` batch CLI command
- [ ] 5.3 Continue batch evaluation after invalid JSON or invalid case files
- [ ] 5.4 Write per-case JSON results and a compact Markdown batch summary
- [ ] 5.5 Add CLI tests for single-case success, batch success, and invalid-file continuation

## 6. Examples and Documentation

- [ ] 6.1 Add example `requirement_backlog` evaluation cases with canonical output and optional published artifacts
- [ ] 6.2 Add example `pm_status_report` evaluation cases with canonical output and optional Markdown artifact
- [ ] 6.3 Add README usage instructions for local batch evaluation and result interpretation
- [ ] 6.4 Document how future cost and observability metrics will join through `run_metadata`

## 7. Quality Gate

- [ ] 7.1 Run the repository quality command
- [ ] 7.2 Fix lint or test failures
- [ ] 7.3 Re-run the full quality command and record passing commands in the final handoff
