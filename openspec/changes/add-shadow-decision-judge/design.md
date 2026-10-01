## Context

The Worker runs the existing deterministic `EvaluationEngine`, then an injected `OptionalJudge`. Its optional output is validated by `SafeJudgeResult` and stored in `evaluation_results.llm_judge_result`. The batch CLI has a separate `LlmJudge` contract and must keep working. The service exposes a versioned evaluation detail API and append-only Human Review evidence.

This change adds a personal Jev experiment. Its judgment is shadow evidence: it cannot change `execution_status`, `machine_verdict`, `review_status`, deterministic scores, or review eligibility. Jev is a hosted provider, so outbound evaluation data requires an explicit opt-in and credentials. The official TypeSafe API supports a bounded `Noul` yes/no question; the first rubric uses that primitive. The adapter uses the official `typesafe-sdk`, with a pinned model name and a timeout. [TypeSafe API](https://api.typesafe.ai/docs)

## Goals / Non-Goals

**Goals:**

- Make the Worker-side optional judgment contract provider-neutral and typed.
- Run a real Jev adapter behind explicit project opt-in, disabled by default.
- Record a per-rubric confidence-gate recommendation without calling an LLM or changing any authoritative state.
- Add a new result field while keeping `llm_judge_result` and old API behavior compatible.
- Keep provider errors, malformed answers, and provider payloads out of persisted results and logs.

**Non-Goals:**

- Promote Jev to an authoritative machine verdict or change Human Review policy.
- Automatically invoke an LLM or assign a Human Review task after uncertainty.
- Build a general rubric management API, provider marketplace, or evaluation dashboard.
- Claim that initial thresholds are calibrated or that Human Review decisions are independent gold labels.
- Change the batch CLI or its `LlmJudge` protocol.

## Decisions

### 1. Provider-neutral Worker boundary

`DecisionProvider.evaluate(case, deterministic_result, rubric)` returns a typed raw decision containing a bounded answer and `p_yes` in `[0, 1]`. A separate `DecisionJudge` runner validates the provider output and applies a gate policy. The Jev adapter is the first provider. The existing Worker-level `OptionalJudge` call path is adapted through this boundary, retaining its legacy `llm_judge_result` response behavior; the batch-engine Judge is untouched. This is smaller than replacing all evaluation results with a multi-judge framework and avoids making the provider responsible for business routing.

### 2. One experimental rubric, policy keyed by version

The initial rubric is `material_quality_issue_v1`: “Does the canonical output contain a material quality issue for this artifact type?” It is asked as a yes/no `Noul` question using the case and deterministic findings. Its versioned policy starts with `accept_positive_at = 0.90` and `accept_negative_at = 0.10`. These values only classify shadow recommendations and are explicitly uncalibrated. The policy registry enforces `0 <= negative < positive <= 1`. Future rubrics can have independent thresholds without changing the provider interface.

For `p_yes >= positive`, the route is `no_escalation_recommended` with answer `yes`. For `p_yes <= negative`, the route is `no_escalation_recommended` with answer `no`. The middle band records `llm_escalation_recommended`; it makes no extra call. The raw `p_yes`, selected answer, threshold values, policy/rubric versions, provider, and model are recorded so a later analysis can replay routing. The route is advisory, not a release gate.

### 3. Additive persistence and API migration

Add nullable JSONB `decision_judge_result` to `evaluation_results` through an Alembic migration. A strict Pydantic model allowlists its JSON shape; no raw prompt, source payload, SDK response, exception, or credentials are stored. `GET /v1/evaluations/{id}` adds nullable `decision_judge_result`. The existing `llm_judge_result` field remains and retains its meaning; historical rows yield `decision_judge_result: null`. No API version bump is needed because the field is additive. The repository still writes the result and job completion atomically and only for the current lease owner.

### 4. Explicit external-data opt-in

Jev is disabled by default. Enabling requires `AI_EVAL_DECISION_JUDGE_PROVIDER=jev`, `TYPESAFE_API_KEY`, and a nonempty allowlist of project IDs. `claim_next` supplies the Evaluation's project ID to the Worker, and only allowed projects are sent to Jev. Missing configuration fails startup with a stable safe code; it does not silently enable calls for every project. The configured model is pinned, rather than `jev-latest`, for reproducibility. Provider calls use a bounded timeout and no automatic retry for this experiment.

### 5. Safe degradation

If an enabled provider times out, raises, or returns invalid data, the Worker completes with the deterministic result, stores `decision_judge_result = null`, and adds only `{"code": "decision_judge_degraded"}`. Existing `judge_degraded` remains valid for the legacy optional LLM path. Safe logs contain provider type and a stable code, never the exception or submitted data. The existing lease-renewal and owner-guarded finalization behavior remains in force during the provider call.

### 6. Calibration evidence

Automated tests use fake providers and a fake TypeSafe client; they never require a live key. The experiment exports or queries shadow decisions for comparison with separately labeled examples. Human Review evidence is useful context but cannot alone serve as a neutral gold label because the current review policy is conditioned on `machine_verdict`.

## Risks / Trade-offs

- **Uncalibrated confidence** → Keep routes advisory; record policy version and test thresholds against a held-out human-labeled set before any promotion.
- **Sensitive data sent to a hosted model** → Require provider, key, and project allowlist opt-in; never send a different project's case.
- **Confident correlated errors** → Compare Jev, any LLM comparator, and humans on the same examples; inspect false passes, not just agreement.
- **Schema and API evolution** → Add nullable field and preserve the legacy field; test old rows, OpenAPI, and batch CLI compatibility.
- **Provider availability** → Bounded timeout and sanitized degradation preserve deterministic completion.

## Migration Plan

1. Apply an additive Alembic migration before starting an updated Worker.
2. Deploy with Jev disabled; old rows and deterministic-only processing retain current behavior.
3. Enable Jev for named test projects after configuring a TypeSafe key and pinned model.
4. If the experiment is stopped, disable the provider. Historical shadow results remain available; no destructive rollback is required.

## Open Questions

No blocking design questions. The first rubric and thresholds are experimental defaults; they are not a quality claim. A later promotion decision requires independently labeled data and a new change proposal.
