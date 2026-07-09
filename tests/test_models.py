import pytest
from pydantic import ValidationError

from app.domain.models import EvaluationCase, EvaluationResult, Finding


def test_evaluation_case_preserves_optional_context_and_metadata():
    case = EvaluationCase.model_validate(
        {
            "case_id": "login-audit-001",
            "artifact_type": "requirement_backlog",
            "input": {"user_prompt": "Track admin logins"},
            "canonical_output": {"summary": "Add admin login auditing"},
            "published_artifacts": {"markdown": "Add admin login auditing"},
            "run_metadata": {"source_app": "AI_Requirement_Tool", "trace_id": "trace-1"},
        }
    )

    assert case.case_id == "login-audit-001"
    assert case.published_artifacts["markdown"] == "Add admin login auditing"
    assert case.run_metadata["trace_id"] == "trace-1"


def test_evaluation_case_requires_canonical_output():
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(
            {
                "case_id": "missing-output",
                "artifact_type": "requirement_backlog",
            }
        )


def test_evaluation_result_serializes_findings_and_metadata():
    result = EvaluationResult(
        case_id="case-1",
        artifact_type="pm_status_report",
        overall_score=75,
        passed=True,
        criteria_scores={"schema_validity": 100},
        findings=[
            Finding(
                code="weak_summary",
                message="Executive summary is short.",
                severity="warning",
            )
        ],
        suggested_improvements=["Add delivery rationale."],
        metadata={"flow_name": "pm_status_agent"},
    )

    payload = result.model_dump()

    assert payload["criteria_scores"]["schema_validity"] == 100
    assert payload["findings"][0]["code"] == "weak_summary"
    assert payload["metadata"]["flow_name"] == "pm_status_agent"

