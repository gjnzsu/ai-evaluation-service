## 1. Typed decision contract and gate

- [x] 1.1 Add failing tests for finite probability validation, forbidden fields, rubric-policy validation, and exact threshold boundaries.
- [x] 1.2 Implement provider-neutral decision models, the experimental `material_quality_issue_v1` policy registry, and a pure confidence gate; make focused tests pass.

## 2. Durable additive result contract

- [x] 2.1 Add failing PostgreSQL migration/repository tests for nullable `decision_judge_result`, old-row reads, atomic owned completion, and one-result uniqueness.
- [x] 2.2 Add the migration, ORM/repository field, and `decision_judge_result` in detail API/OpenAPI; make integration and API tests pass without changing `llm_judge_result`.

## 3. Jev adapter and explicit opt-in

- [x] 3.1 Add failing adapter tests using a fake TypeSafe client for the pinned `Noul` request, typed probability extraction, malformed response, timeout, and no raw payload/exception persistence.
- [x] 3.2 Implement the real Jev adapter through the official SDK with a bounded timeout and no automatic retry; keep automated tests credential-free.
- [x] 3.3 Add failing configuration/project-isolation tests for disabled default, missing key/model/allowlist, an allowed project, and an unlisted project.
- [x] 3.4 Wire safe startup configuration and project ID from PostgreSQL claim to the Worker so only allowed projects invoke Jev; make tests pass.

## 4. Worker integration and safe degradation

- [x] 4.1 Add failing Worker tests showing shadow disagreement cannot change `machine_verdict` or `review_status`, uncertainty only records a route, and provider failure preserves deterministic completion.
- [x] 4.2 Integrate the provider-neutral decision runner while preserving legacy Worker-level LLM result behavior and batch CLI interfaces; persist only allowlisted shadow result or `decision_judge_degraded`.
- [x] 4.3 Add real PostgreSQL and API tests for shadow result retrieval, degraded result, lease ownership, and project-scoped access.

## 5. Documentation and verification

- [x] 5.1 Document configuration, external-data opt-in, uncalibrated thresholds, shadow routing, data contract, and how to gather separately labeled calibration examples.
- [x] 5.2 Run focused red/green evidence, the repository quality gate, existing CLI regression tests, and default Compose smoke with Jev disabled.
- [x] 5.3 Review the implementation against every OpenSpec scenario and confirm no real credential or raw provider data entered tests, persisted results, or logs.
