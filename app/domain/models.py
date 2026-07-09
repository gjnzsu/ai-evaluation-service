"""Pydantic models for evaluation inputs and outputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EvaluationCase(BaseModel):
    """Input case for evaluating one AI application output."""

    model_config = ConfigDict(extra="allow")

    case_id: str
    artifact_type: str
    canonical_output: dict[str, Any]
    input: dict[str, Any] = Field(default_factory=dict)
    published_artifacts: dict[str, Any] = Field(default_factory=dict)
    run_metadata: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    """Actionable issue, warning, or info note produced during evaluation."""

    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    blocking: bool = False


class EvaluationResult(BaseModel):
    """Evaluation output for one case."""

    case_id: str
    artifact_type: str
    overall_score: int
    passed: bool
    criteria_scores: dict[str, int] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    suggested_improvements: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

