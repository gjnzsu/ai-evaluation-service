"""Typed, advisory decisions and rubric-specific confidence routing."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RawDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    rubric_version: str = Field(min_length=1, max_length=100)
    answer: Literal["yes", "no"]
    p_yes: float = Field(ge=0, le=1)


class DecisionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    rubric_version: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=100)
    accept_negative_at: float = Field(ge=0, le=1)
    accept_positive_at: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_order(self) -> "DecisionPolicy":
        if self.accept_negative_at >= self.accept_positive_at:
            raise ValueError("invalid decision thresholds")
        return self


class DecisionJudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    rubric_version: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=100)
    answer: Literal["yes", "no"]
    p_yes: float = Field(ge=0, le=1)
    accept_negative_at: float = Field(ge=0, le=1)
    accept_positive_at: float = Field(ge=0, le=1)
    recommended_route: Literal[
        "no_escalation_recommended", "llm_escalation_recommended"
    ]


def material_quality_issue_policy() -> DecisionPolicy:
    return DecisionPolicy(
        rubric_version="material_quality_issue_v1",
        policy_version="v1",
        accept_negative_at=0.1,
        accept_positive_at=0.9,
    )


def gate_decision(raw: RawDecision, policy: DecisionPolicy) -> DecisionJudgeResult:
    if raw.rubric_version != policy.rubric_version:
        raise ValueError("decision rubric does not match policy")
    no_escalation = (
        raw.p_yes >= policy.accept_positive_at
        or raw.p_yes <= policy.accept_negative_at
    )
    return DecisionJudgeResult(
        **raw.model_dump(),
        policy_version=policy.policy_version,
        accept_negative_at=policy.accept_negative_at,
        accept_positive_at=policy.accept_positive_at,
        recommended_route=(
            "no_escalation_recommended"
            if no_escalation
            else "llm_escalation_recommended"
        ),
    )
