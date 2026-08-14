from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

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


class SafeJudgeResult(BaseModel):
    """Narrow, JSON-safe POC contract for optional Judge annotations."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    rubric_version: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    provider: str | None = Field(default=None, max_length=100)
    prompt_version: str | None = Field(default=None, max_length=100)
    dimensions: dict[str, float] = Field(default_factory=dict)
    findings: list[str] = Field(default_factory=list, max_length=100)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)


def normalize_judge_result(result: object) -> dict[str, Any]:
    """Reject extra/raw fields and return only JSON-mode safe values."""

    return SafeJudgeResult.model_validate(result).model_dump(
        mode="json", exclude_none=True, exclude_defaults=True
    )
