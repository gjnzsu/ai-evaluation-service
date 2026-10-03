import math

import pytest
from pydantic import ValidationError

from app.worker.decision import (
    DecisionPolicy,
    RawDecision,
    gate_decision,
    material_quality_issue_policy,
)


@pytest.mark.parametrize("probability", [-0.01, 1.01, math.nan, math.inf, -math.inf])
def test_raw_decision_rejects_unbounded_probability(probability: float) -> None:
    with pytest.raises(ValidationError):
        RawDecision(
            provider="jev", model="jev-2026-09", rubric_version="material_quality_issue_v1",
            answer="yes", p_yes=probability,
        )


def test_raw_decision_rejects_provider_payload_fields() -> None:
    with pytest.raises(ValidationError):
        RawDecision.model_validate({
            "provider": "jev", "model": "jev-2026-09",
            "rubric_version": "material_quality_issue_v1", "answer": "yes",
            "p_yes": 0.9, "prompt": "private input", "credential": "secret",
        })


@pytest.mark.parametrize("negative,positive", [(-0.1, 0.9), (0.1, 1.1), (0.5, 0.5), (0.9, 0.1)])
def test_policy_rejects_invalid_thresholds(negative: float, positive: float) -> None:
    with pytest.raises(ValidationError):
        DecisionPolicy(
            rubric_version="material_quality_issue_v1", policy_version="v1",
            accept_negative_at=negative, accept_positive_at=positive,
        )


@pytest.mark.parametrize(
    "probability,answer,route",
    [
        (0.1, "no", "no_escalation_recommended"),
        (0.10001, "no", "llm_escalation_recommended"),
        (0.89999, "yes", "llm_escalation_recommended"),
        (0.9, "yes", "no_escalation_recommended"),
    ],
)
def test_gate_exact_boundaries(probability: float, answer: str, route: str) -> None:
    raw = RawDecision(
        provider="jev", model="jev-2026-09", rubric_version="material_quality_issue_v1",
        answer=answer, p_yes=probability,
    )
    result = gate_decision(raw, material_quality_issue_policy())

    assert result.answer == answer
    assert result.recommended_route == route
    assert result.p_yes == probability
    assert result.accept_negative_at == 0.1
    assert result.accept_positive_at == 0.9
    assert result.policy_version == "v1"
    assert set(result.model_dump()) == {
        "provider", "model", "rubric_version", "policy_version", "answer", "p_yes",
        "accept_negative_at", "accept_positive_at", "recommended_route",
    }


def test_gate_rejects_rubric_mismatch() -> None:
    raw = RawDecision(
        provider="jev", model="jev-2026-09", rubric_version="other_v1",
        answer="no", p_yes=0.05,
    )
    with pytest.raises(ValueError, match="rubric"):
        gate_decision(raw, material_quality_issue_policy())
