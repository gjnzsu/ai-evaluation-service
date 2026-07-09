from app.domain.models import EvaluationCase
from app.evaluators.pm_status_report import evaluate_pm_status_report
from app.evaluators.requirement_backlog import evaluate_requirement_backlog


def test_requirement_backlog_strong_case_scores_and_passes():
    case = EvaluationCase(
        case_id="login-audit",
        artifact_type="requirement_backlog",
        canonical_output={
            "summary": "Add admin login auditing",
            "business_value": "Improves traceability for privileged access reviews.",
            "acceptance_criteria": [
                "Every admin login attempt is recorded with timestamp and outcome.",
                "Security reviewers can filter login attempts by user and date.",
            ],
            "priority": "High",
            "invest_analysis": "Independent, valuable, small, and testable.",
            "description": (
                "Business Value: Improves traceability\n\n"
                "Acceptance Criteria:\n"
                "- Every admin login attempt is recorded"
            ),
        },
        published_artifacts={
            "markdown": (
                "Add admin login auditing\n"
                "Improves traceability\n"
                "Every admin login attempt"
            )
        },
    )

    result = evaluate_requirement_backlog(case)

    assert result.passed is True
    assert result.criteria_scores["schema_validity"] == 100
    assert result.criteria_scores["published_artifact_fidelity"] == 100
    assert result.overall_score >= 80


def test_requirement_backlog_weak_case_records_findings():
    case = EvaluationCase(
        case_id="weak-backlog",
        artifact_type="requirement_backlog",
        canonical_output={
            "summary": "Do AI thing",
            "business_value": "",
            "acceptance_criteria": [],
            "priority": "Medium",
            "invest_analysis": "",
            "description": "",
        },
    )

    result = evaluate_requirement_backlog(case)

    assert result.passed is False
    assert result.criteria_scores["completeness"] < 70
    assert any(finding.code == "missing_business_value" for finding in result.findings)
    assert any(finding.code == "missing_acceptance_criteria" for finding in result.findings)
    assert result.criteria_scores["published_artifact_fidelity"] == 0
    assert any(finding.code == "published_artifacts_skipped" for finding in result.findings)


def test_pm_status_report_strong_case_scores_and_passes():
    case = EvaluationCase(
        case_id="pm-green",
        artifact_type="pm_status_report",
        canonical_output={
            "project_key": "AIP",
            "project_name": "AI Platform",
            "time_window": "This week",
            "audience": "Steering Committee",
            "health": "Green",
            "executive_summary": "AI Platform is green with delivery scope on track.",
            "progress": [{"summary": "Gateway integration complete", "source_key": "AIP-1"}],
            "completed": [{"summary": "RAG ingestion validated", "source_key": "AIP-2"}],
            "risks": [],
            "blockers": [],
            "decisions_needed": [],
            "owner_gaps": [],
            "next_actions": [{"summary": "Run SIT smoke tests", "owner": "PMO"}],
            "stakeholder_update": "AI Platform status is Green. Next: Run SIT smoke tests.",
            "source_references": [{"source_type": "jira", "key": "AIP-1"}],
            "confidence_notes": ["Analyzed current sprint data."],
        },
        published_artifacts={
            "markdown": "# AI Platform Status\n## Health: Green\nRun SIT smoke tests"
        },
    )

    result = evaluate_pm_status_report(case)

    assert result.passed is True
    assert result.criteria_scores["health_validity"] == 100
    assert result.criteria_scores["published_artifact_fidelity"] == 100
    assert result.overall_score >= 80


def test_pm_status_report_invalid_health_is_blocking():
    case = EvaluationCase(
        case_id="pm-blue",
        artifact_type="pm_status_report",
        canonical_output={
            "project_key": "AIP",
            "project_name": "AI Platform",
            "time_window": "Today",
            "audience": "Team",
            "health": "Blue",
            "executive_summary": "Invalid color.",
        },
    )

    result = evaluate_pm_status_report(case)

    assert result.passed is False
    assert result.criteria_scores["health_validity"] == 0
    assert any(finding.code == "invalid_health" for finding in result.findings)
