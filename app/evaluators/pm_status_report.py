"""Deterministic evaluator for PM status report artifacts."""

from __future__ import annotations

from app.domain.models import EvaluationCase, EvaluationResult, Finding
from app.domain.scoring import average_scores
from app.evaluators.deterministic import (
    published_artifact_fidelity,
    required_field_score,
    text_present,
)

VALID_HEALTH = {"green", "amber", "red"}


def evaluate_pm_status_report(case: EvaluationCase) -> EvaluationResult:
    findings: list[Finding] = []
    output = case.canonical_output

    required_fields = [
        "project_key",
        "project_name",
        "time_window",
        "audience",
        "health",
        "executive_summary",
    ]
    schema_score = required_field_score(output, required_fields, findings)

    health = str(output.get("health") or "").strip().lower()
    if health not in VALID_HEALTH:
        findings.append(
            Finding(
                code="invalid_health",
                message="Health must be one of Green, Amber, or Red.",
                severity="error",
                blocking=True,
            )
        )
        health_score = 0
    else:
        health_score = 100

    status_sections = [
        "progress",
        "completed",
        "risks",
        "blockers",
        "decisions_needed",
        "owner_gaps",
        "next_actions",
    ]
    populated_sections = [section for section in status_sections if output.get(section)]
    completeness = int((len(populated_sections) / len(status_sections)) * 100)
    if not populated_sections:
        findings.append(
            Finding(
                code="missing_delivery_signals",
                message="No delivery signal sections are populated.",
                severity="warning",
            )
        )

    source_grounding = 100 if output.get("source_references") else 40
    if source_grounding < 100:
        findings.append(
            Finding(
                code="weak_source_grounding",
                message="Source references are missing or sparse.",
                severity="warning",
            )
        )

    stakeholder_readability = (
        100 if text_present(output.get("stakeholder_update"), min_length=20) else 50
    )
    pm_reasoning_quality = (
        100 if text_present(output.get("executive_summary"), min_length=20) else 50
    )
    confidence_notes = 100 if output.get("confidence_notes") else 50

    fidelity, fidelity_skipped = published_artifact_fidelity(
        output,
        case.published_artifacts,
        ["project_name", "health", "next_actions"],
        findings,
    )

    criteria_scores = {
        "schema_validity": schema_score,
        "health_validity": health_score,
        "completeness": completeness,
        "evidence_grounding": source_grounding,
        "stakeholder_readability": stakeholder_readability,
        "pm_reasoning_quality": pm_reasoning_quality,
        "confidence_notes": confidence_notes,
        "published_artifact_fidelity": fidelity,
    }
    overall_score = average_scores(
        criteria_scores,
        exclude={"published_artifact_fidelity"} if fidelity_skipped else set(),
    )
    blocking = any(finding.blocking for finding in findings)

    return EvaluationResult(
        case_id=case.case_id,
        artifact_type=case.artifact_type,
        overall_score=overall_score,
        passed=not blocking and overall_score >= 70,
        criteria_scores=criteria_scores,
        findings=findings,
        suggested_improvements=_suggest_improvements(criteria_scores),
        metadata=dict(case.run_metadata),
    )


def _suggest_improvements(scores: dict[str, int]) -> list[str]:
    suggestions: list[str] = []
    if scores["evidence_grounding"] < 80:
        suggestions.append("Add Jira or Confluence source references to ground the status report.")
    if scores["stakeholder_readability"] < 80:
        suggestions.append("Add a concise stakeholder update suitable for the target audience.")
    if scores["completeness"] < 50:
        suggestions.append(
            "Populate relevant delivery signal sections such as progress and next actions."
        )
    return suggestions
