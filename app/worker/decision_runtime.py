"""Project-scoped, provider-neutral shadow decision runner."""

import os
from collections.abc import Callable
from typing import Protocol

from app.config import Settings
from app.domain.models import EvaluationCase, EvaluationResult
from app.worker.decision import (
    DecisionJudgeResult,
    DecisionPolicy,
    RawDecision,
    gate_decision,
    material_quality_issue_policy,
)
from app.worker.jev import JevDecisionProvider


class DecisionProvider(Protocol):
    def evaluate(
        self, case: EvaluationCase, deterministic_result: EvaluationResult, rubric: str
    ) -> RawDecision: ...


class DecisionJudgeConfigurationError(ValueError):
    def __init__(self) -> None:
        super().__init__("decision_judge_configuration_invalid")


class DecisionJudge:
    def __init__(
        self,
        provider: DecisionProvider,
        policy: DecisionPolicy,
        allowed_projects: frozenset[str],
        *,
        expected_provider: str,
        expected_model: str,
    ) -> None:
        self.provider = provider
        self.policy = policy
        self.allowed_projects = allowed_projects
        self.expected_provider = expected_provider
        self.expected_model = expected_model

    def evaluate(
        self, project_id: str, case: EvaluationCase, deterministic_result: EvaluationResult
    ) -> DecisionJudgeResult | None:
        if project_id not in self.allowed_projects:
            return None
        raw = RawDecision.model_validate(
            self.provider.evaluate(case, deterministic_result, self.policy.rubric_version)
        )
        if raw.provider != self.expected_provider or raw.model != self.expected_model:
            raise ValueError("decision provider identity mismatch")
        return gate_decision(raw, self.policy)


def build_decision_judge(
    settings: Settings,
    *,
    provider_factory: Callable[..., DecisionProvider] = JevDecisionProvider,
) -> DecisionJudge | None:
    if settings.decision_judge_provider == "disabled":
        return None
    if settings.decision_judge_provider != "jev":
        raise DecisionJudgeConfigurationError()
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    model = settings.decision_judge_model.strip()
    projects = frozenset(
        project.strip() for project in settings.decision_judge_projects.split(",")
        if project.strip()
    )
    if (
        not key or not model or model in {"jev", "jev-latest"}
        or model.endswith("-latest") or not projects
        or settings.decision_judge_timeout_seconds <= 0
    ):
        raise DecisionJudgeConfigurationError()
    return DecisionJudge(
        provider_factory(
            model=model,
            timeout_seconds=settings.decision_judge_timeout_seconds,
            api_key=key,
        ),
        material_quality_issue_policy(),
        projects,
        expected_provider="jev",
        expected_model=model,
    )
