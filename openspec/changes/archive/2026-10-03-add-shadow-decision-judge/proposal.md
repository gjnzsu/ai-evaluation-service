## Why

The service's optional judge is named and shaped for an LLM even though bounded decisions can be made by typed decision models such as Jev. A provider-neutral shadow result lets us experiment with lower-cost judgments and confidence routing without changing the deterministic machine verdict or Human Review policy.

## What Changes

- Introduce a provider-neutral decision judge interface and a versioned, allowlisted result with a rubric answer, probability, and routing recommendation.
- Add a real TypeSafe Jev adapter, disabled by default, that asks one bounded yes/no question for the first experimental rubric.
- Apply positive and negative probability thresholds from a rubric-version policy; the middle band recommends LLM escalation but makes no extra model call.
- Persist and expose a new `decision_judge_result` alongside the existing `llm_judge_result` for backward compatibility.
- Preserve deterministic results on provider, output-validation, or policy failures and record a sanitized judge warning.
- Document experimental calibration requirements and test with fake providers and real PostgreSQL; no live credential is required for automated tests.

## Capabilities

### New Capabilities

- `shadow-decision-judge`: Provider-neutral typed shadow judgments, per-rubric confidence routing, Jev integration, and safe degradation.

### Modified Capabilities

- None. The existing `batch-ai-evaluation` specification and CLI judge behavior remain unchanged.

## Impact

- Worker judge boundary and startup configuration, result normalization, PostgreSQL result schema/migration, evaluation detail API/OpenAPI, tests, and local documentation.
- Optional TypeSafe Python SDK dependency and `TYPESAFE_API_KEY` only when Jev is explicitly enabled.
- No change to `machine_verdict`, `review_status`, Human Review decision rules, batch `EvaluationEngine`, or existing `llm_judge_result` response semantics.
