## ADDED Requirements

### Requirement: Shadow decision judge preserves authoritative evaluation

The service SHALL run an enabled decision provider after deterministic evaluation and SHALL NOT let the decision provider change `machine_verdict`, deterministic results, execution completion, Human Review policy, or derived `review_status`.

#### Scenario: Jev disagrees with deterministic verdict
- **WHEN** deterministic evaluation returns `pass` and Jev reports a high probability of a material issue
- **THEN** the Evaluation completes with `machine_verdict = pass` and stores the Jev decision only as shadow evidence

#### Scenario: Decision judge disabled
- **WHEN** the decision judge is disabled by default
- **THEN** the Worker completes without a provider call and returns `decision_judge_result = null`

### Requirement: Decision providers return a typed bounded judgment

The Worker SHALL validate provider, model, rubric version, answer, and a finite `p_yes` in `[0, 1]` before persistence and SHALL discard all unapproved fields.

#### Scenario: Valid bounded answer
- **WHEN** an enabled decision provider returns a valid yes/no probability for the configured rubric
- **THEN** the service stores only the allowlisted typed decision fields

#### Scenario: Unsafe or invalid answer
- **WHEN** a provider returns a nonfinite probability, an out-of-range probability, or raw prompt or credential fields
- **THEN** the service stores no decision result and a sanitized `decision_judge_degraded` warning

### Requirement: Rubric-specific confidence gate records routing recommendation

The service SHALL apply the policy for the judgment's rubric version and SHALL record the policy version, thresholds, answer, probability, and recommended route without executing that route.

#### Scenario: High positive or negative confidence
- **WHEN** `p_yes` reaches the rubric's positive threshold or is at or below its negative threshold
- **THEN** the service records `no_escalation_recommended` and the corresponding yes/no answer

#### Scenario: Uncertain decision
- **WHEN** `p_yes` lies strictly between the negative and positive thresholds
- **THEN** the service records `llm_escalation_recommended` and does not call an LLM or change Human Review status

#### Scenario: Invalid rubric policy
- **WHEN** a rubric policy has thresholds outside `[0, 1]` or its negative threshold is not lower than its positive threshold
- **THEN** configuration is rejected before processing jobs

### Requirement: Jev calls require explicit project opt-in

The service SHALL keep Jev disabled by default and SHALL send an Evaluation to Jev only when provider configuration, credentials, a pinned model, and the Evaluation's project allowlist entry are present.

#### Scenario: Allowed project uses Jev
- **WHEN** Jev is configured and a claimed Evaluation belongs to an allowed project
- **THEN** the Worker asks the configured bounded rubric question through the TypeSafe client

#### Scenario: Other project is not sent
- **WHEN** Jev is configured but the claimed Evaluation belongs to a project outside the allowlist
- **THEN** the Worker completes deterministically without sending its data to TypeSafe

#### Scenario: Missing enabled-provider configuration
- **WHEN** Jev is enabled without credentials, an allowed project, or a pinned model
- **THEN** Worker startup fails with a stable sanitized code and no provider request

### Requirement: Shadow result is additive and durable

The service SHALL persist a nullable `decision_judge_result` separately from `deterministic_result` and `llm_judge_result`, and SHALL expose it in the evaluation detail API.

#### Scenario: Existing result row
- **WHEN** an Evaluation was completed before the decision-judge migration
- **THEN** its detail response retains the existing fields and shows `decision_judge_result = null`

#### Scenario: Shadow result is persisted atomically
- **WHEN** an owned Worker completes a Job with a valid decision result
- **THEN** one result row contains the deterministic verdict and the shadow result in the same completion transaction

#### Scenario: Provider fails
- **WHEN** Jev times out or raises after deterministic evaluation succeeds
- **THEN** execution completes with the deterministic result, `decision_judge_result = null`, and only a safe `decision_judge_degraded` warning for that provider failure

### Requirement: Batch evaluation remains compatible

The service change SHALL preserve the batch `EvaluationEngine` and CLI `LlmJudge` interfaces.

#### Scenario: Existing CLI evaluation
- **WHEN** the existing batch CLI evaluates a case with its current optional Judge configuration
- **THEN** its behavior and output contract remain unchanged
