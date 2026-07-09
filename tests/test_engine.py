from app.domain.models import EvaluationCase
from app.engine import EvaluationEngine
from app.evaluators.llm_judge import LlmJudge


class ExplodingJudge(LlmJudge):
    enabled = True

    def evaluate(self, case, result):
        raise RuntimeError("judge unavailable")


def test_engine_dispatches_known_artifact_type_with_disabled_judge():
    engine = EvaluationEngine()
    case = EvaluationCase(
        case_id="login-audit",
        artifact_type="requirement_backlog",
        canonical_output={
            "summary": "Add admin login auditing",
            "business_value": "Improves traceability.",
            "acceptance_criteria": ["Every login attempt is recorded."],
            "priority": "High",
            "invest_analysis": "Small and testable.",
            "description": "Business Value: Improves traceability.",
        },
    )

    result = engine.evaluate(case)

    assert result.case_id == "login-audit"
    assert result.artifact_type == "requirement_backlog"
    assert "judge_enabled" in result.metadata
    assert result.metadata["judge_enabled"] is False


def test_engine_returns_failed_result_for_unknown_artifact_type():
    engine = EvaluationEngine()
    case = EvaluationCase(
        case_id="unknown",
        artifact_type="new_flow",
        canonical_output={"value": "x"},
    )

    result = engine.evaluate(case)

    assert result.passed is False
    assert result.overall_score == 0
    assert any(finding.code == "unknown_artifact_type" for finding in result.findings)


def test_engine_preserves_deterministic_result_when_enabled_judge_fails():
    engine = EvaluationEngine(judge=ExplodingJudge())
    case = EvaluationCase(
        case_id="pm-green",
        artifact_type="pm_status_report",
        canonical_output={
            "project_key": "AIP",
            "project_name": "AI Platform",
            "time_window": "This week",
            "audience": "Team",
            "health": "Green",
            "executive_summary": "AI Platform is green and on track.",
        },
    )

    result = engine.evaluate(case)

    assert "schema_validity" in result.criteria_scores
    assert any(finding.code == "llm_judge_failed" for finding in result.findings)
    assert result.metadata["judge_enabled"] is True

