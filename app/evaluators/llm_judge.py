"""Optional LLM judge extension point."""

from __future__ import annotations

from typing import Protocol

from app.domain.models import EvaluationCase, EvaluationResult


class LlmJudge(Protocol):
    """Protocol for semantic evaluator implementations."""

    enabled: bool

    def evaluate(self, case: EvaluationCase, result: EvaluationResult) -> EvaluationResult:
        """Return an enriched result."""


class DisabledJudge:
    """No-op judge used by default for deterministic-only evaluation."""

    enabled = False

    def evaluate(self, case: EvaluationCase, result: EvaluationResult) -> EvaluationResult:
        return result

