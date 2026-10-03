import pytest

from app.config import Settings
from app.domain.models import EvaluationCase, EvaluationResult
from app.worker.decision import RawDecision
from app.worker.decision_runtime import (
    DecisionJudgeConfigurationError,
    build_decision_judge,
)


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def evaluate(self, case, deterministic_result, rubric):
        del case, deterministic_result
        self.calls.append(rubric)
        return RawDecision(
            provider="jev", model="jev-2026-09", rubric_version=rubric,
            answer="yes", p_yes=0.95,
        )


def sample() -> tuple[EvaluationCase, EvaluationResult]:
    case = EvaluationCase.model_validate({
        "case_id": "c", "artifact_type": "requirement_backlog", "canonical_output": {},
    })
    result = EvaluationResult(
        case_id="c", artifact_type="requirement_backlog", overall_score=80, passed=True,
    )
    return case, result


def test_decision_judge_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert build_decision_judge(Settings()) is None


@pytest.mark.parametrize(
    "key,model,projects",
    [
        (None, "jev-2026-09", "project-a"),
        ("fake-key", "", "project-a"),
        ("fake-key", "jev-latest", "project-a"),
        ("fake-key", "jev-2026-09", ""),
    ],
)
def test_enabled_jev_requires_key_pinned_model_and_allowlist(
    monkeypatch, key: str | None, model: str, projects: str,
) -> None:
    if key is None:
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("TYPESAFE_API_KEY", key)
    settings = Settings(
        decision_judge_provider="jev", decision_judge_model=model,
        decision_judge_projects=projects,
    )
    with pytest.raises(DecisionJudgeConfigurationError) as error:
        build_decision_judge(settings)
    assert str(error.value) == "decision_judge_configuration_invalid"


def test_only_allowlisted_project_reaches_provider(monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-key")
    provider = FakeProvider()
    settings = Settings(
        decision_judge_provider="jev", decision_judge_model="jev-2026-09",
        decision_judge_projects="project-a, project-c",
    )
    judge = build_decision_judge(settings, provider_factory=lambda **kwargs: provider)
    case, result = sample()

    assert judge.evaluate("project-b", case, result) is None
    assert provider.calls == []
    decision = judge.evaluate("project-a", case, result)
    assert decision.recommended_route == "no_escalation_recommended"
    assert provider.calls == ["material_quality_issue_v1"]
