from typing import Any, Protocol

from app.domain.models import EvaluationCase, EvaluationResult


class OptionalJudge(Protocol):
    """Independent service-level Judge that cannot mutate deterministic output."""

    enabled: bool

    def evaluate(
        self, case: EvaluationCase, deterministic_result: EvaluationResult
    ) -> dict[str, Any]: ...


class DisabledOptionalJudge:
    enabled = False

    def evaluate(
        self, case: EvaluationCase, deterministic_result: EvaluationResult
    ) -> dict[str, Any]:
        del case, deterministic_result
        return {}
