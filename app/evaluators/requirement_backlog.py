"""Deterministic evaluator for requirement backlog artifacts."""

from __future__ import annotations

from app.domain.models import EvaluationCase, EvaluationResult, Finding
from app.domain.scoring import average_scores, clamp_score
from app.evaluators.deterministic import (
    list_present,
    published_artifact_fidelity,
    required_field_score,
    text_present,
)


def evaluate_requirement_backlog(case: EvaluationCase) -> EvaluationResult:
    findings: list[Finding] = []
    output = case.canonical_output

    required_fields = [
        "summary",
        "business_value",
        "acceptance_criteria",
        "priority",
        "invest_analysis",
        "description",
    ]
    schema_score = required_field_score(output, required_fields, findings)

    if not text_present(output.get("business_value"), min_length=10):
        findings.append(
            Finding(
                code="missing_business_value",
                message="Business value is missing or too thin.",
                severity="error",
                blocking=True,
            )
        )

    if not list_present(output.get("acceptance_criteria")):
        findings.append(
            Finding(
                code="missing_acceptance_criteria",
                message="Acceptance criteria are missing.",
                severity="error",
                blocking=True,
            )
        )

    acceptance_items = output.get("acceptance_criteria") or []
    testable_items = [
        item
        for item in acceptance_items
        if any(
            signal in str(item).lower()
            for signal in ["record", "filter", "verify", "can", "when"]
        )
    ]

    completeness = schema_score
    acceptance_quality = 100 if len(acceptance_items) >= 2 else 70 if acceptance_items else 0
    testability = (
        clamp_score((len(testable_items) / len(acceptance_items)) * 100)
        if acceptance_items
        else 0
    )
    business_alignment = 100 if text_present(output.get("business_value"), min_length=20) else 50
    invest_signal = 100 if text_present(output.get("invest_analysis"), min_length=10) else 0

    fidelity, fidelity_skipped = published_artifact_fidelity(
        output,
        case.published_artifacts,
        ["summary", "business_value", "acceptance_criteria"],
        findings,
    )

    criteria_scores = {
        "schema_validity": schema_score,
        "completeness": completeness,
        "acceptance_criteria_quality": acceptance_quality,
        "testability": testability,
        "business_alignment": business_alignment,
        "invest_signal": invest_signal,
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
        suggested_improvements=_suggest_improvements(criteria_scores, findings),
        metadata=dict(case.run_metadata),
    )


def _suggest_improvements(scores: dict[str, int], findings: list[Finding]) -> list[str]:
    suggestions: list[str] = []
    if scores["acceptance_criteria_quality"] < 80:
        suggestions.append("Add at least two concrete, verifiable acceptance criteria.")
    if scores["business_alignment"] < 80:
        suggestions.append("Explain the user or business outcome more specifically.")
    if any(finding.code == "published_artifact_missing_fact" for finding in findings):
        suggestions.append(
            "Update published artifacts so they reflect the canonical backlog fields."
        )
    return suggestions
