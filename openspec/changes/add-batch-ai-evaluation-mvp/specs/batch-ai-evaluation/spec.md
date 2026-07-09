## ADDED Requirements

### Requirement: Evaluation cases separate canonical and published artifacts

The system SHALL accept evaluation case files that include a case identifier, artifact type, input context, required canonical output, optional published artifacts, and optional run metadata.

#### Scenario: Valid evaluation case is loaded
- **WHEN** a JSON case file contains `case_id`, `artifact_type`, and `canonical_output`
- **THEN** the system loads the case for evaluation and preserves `input`, `published_artifacts`, and `run_metadata` when present

#### Scenario: Missing canonical output is rejected
- **WHEN** a JSON case file omits `canonical_output`
- **THEN** the system records a blocking validation failure for that case

### Requirement: Requirement backlog canonical output is evaluated

The system SHALL evaluate `requirement_backlog` canonical outputs for schema validity, completeness, clarity, business value, acceptance criteria quality, testability, INVEST signal, and gap detection.

#### Scenario: Requirement backlog receives deterministic scores
- **WHEN** a `requirement_backlog` case contains canonical output with summary, business value, acceptance criteria, priority, INVEST analysis, and description
- **THEN** the system returns criteria scores for schema validity, completeness, acceptance criteria quality, testability, and business alignment

#### Scenario: Weak requirement backlog records findings
- **WHEN** a `requirement_backlog` case has empty acceptance criteria or missing business value
- **THEN** the system records findings that identify the weak or missing sections

### Requirement: PM status report canonical output is evaluated

The system SHALL evaluate `pm_status_report` canonical outputs for schema validity, health validity, executive summary quality, delivery signal completeness, source grounding, stakeholder update quality, and confidence notes.

#### Scenario: PM status report receives deterministic scores
- **WHEN** a `pm_status_report` case contains canonical output with project metadata, health, executive summary, status sections, stakeholder update, and source references
- **THEN** the system returns criteria scores for schema validity, completeness, evidence grounding, stakeholder readability, and PM reasoning quality

#### Scenario: Invalid health value is rejected
- **WHEN** a `pm_status_report` case has a health value other than Green, Amber, or Red
- **THEN** the system records a blocking validation failure for health validity

### Requirement: Published artifacts are evaluated when supplied

The system SHALL evaluate supplied published artifacts for fidelity to canonical output, missing sections, formatting readability, and traceability.

#### Scenario: Published artifact evaluation is skipped when absent
- **WHEN** an evaluation case has no published artifacts
- **THEN** the system returns canonical evaluation results and marks published artifact criteria as skipped

#### Scenario: Published artifact missing canonical facts records findings
- **WHEN** a published artifact omits important canonical fields such as summary, health, business value, or next actions
- **THEN** the system records fidelity findings for the missing facts

### Requirement: Evaluation engine dispatches by artifact type

The system SHALL dispatch each evaluation case to the evaluator registered for its artifact type.

#### Scenario: Known artifact type is evaluated
- **WHEN** a case has artifact type `requirement_backlog` or `pm_status_report`
- **THEN** the system evaluates the case with the matching evaluator

#### Scenario: Unknown artifact type fails clearly
- **WHEN** a case has an unregistered artifact type
- **THEN** the system returns a failed evaluation result with an unknown artifact type finding

### Requirement: Batch CLI evaluates files from disk

The system SHALL provide a CLI that evaluates one JSON case file or all JSON case files under an input directory and writes results to an output directory.

#### Scenario: Single case evaluation writes result
- **WHEN** the user runs the CLI with `evaluate-case --file <case-file>`
- **THEN** the system writes a JSON result for that case

#### Scenario: Batch evaluation continues after invalid file
- **WHEN** the user runs the CLI with `evaluate --input <directory>` and one file is invalid
- **THEN** the system records a failed result for the invalid file and continues evaluating remaining valid files

### Requirement: LLM judge is optional

The system SHALL support an optional LLM judge while allowing deterministic-only evaluation by default.

#### Scenario: LLM judge disabled by default
- **WHEN** LLM judge configuration is disabled or absent
- **THEN** the system completes evaluation using deterministic evaluators only

#### Scenario: LLM judge failure does not hide deterministic results
- **WHEN** the LLM judge is enabled but fails during evaluation
- **THEN** the system preserves deterministic scores and records a warning finding for the judge failure

### Requirement: Run metadata is preserved for future metric joins

The system SHALL preserve run metadata in evaluation results without using cost or latency metrics in MVP 1 scoring.

#### Scenario: Observability metadata is echoed
- **WHEN** a case includes run metadata such as source app, flow name, run id, trace id, model, or provider
- **THEN** the system includes that metadata in the evaluation result metadata
