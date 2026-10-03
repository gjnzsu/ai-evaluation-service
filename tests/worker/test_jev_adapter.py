import logging
import sys
from types import SimpleNamespace

import pytest

from app.domain.models import EvaluationCase, EvaluationResult
from app.worker.jev import JevDecisionProvider


def case_and_result() -> tuple[EvaluationCase, EvaluationResult]:
    case = EvaluationCase.model_validate({
        "case_id": "case-a", "artifact_type": "requirement_backlog",
        "canonical_output": {"summary": "Audit logins"},
    })
    result = EvaluationResult(
        case_id="case-a", artifact_type="requirement_backlog",
        overall_score=30, passed=False,
    )
    return case, result


class FakeTypeSafeClient:
    def __init__(self, probability: object = 0.93) -> None:
        self.probability = probability
        self.calls: list[dict] = []

    def system_one(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(nouls={
            "material_quality_issue": SimpleNamespace(noul=self.probability)
        })


def test_jev_sends_bounded_question_and_extracts_probability() -> None:
    client = FakeTypeSafeClient()
    case, result = case_and_result()
    provider = JevDecisionProvider(model="jev-pinned", timeout_seconds=3, client=client)

    decision = provider.evaluate(case, result, "material_quality_issue_v1")

    assert decision.provider == "jev"
    assert decision.model == "jev-pinned"
    assert decision.answer == "yes"
    assert decision.p_yes == 0.93
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["model"] == "jev-pinned"
    assert call["timeout"] == 3
    assert call["questions"] == {
        "material_quality_issue": {
            "type": "noul",
            "instructions": (
                "Does the canonical output contain a material quality issue "
                "for this artifact type?"
            ),
        }
    }
    assert call["state"]["case_id"] == "case-a"
    assert call["state"]["artifact_type"] == "requirement_backlog"
    assert call["state"]["canonical_output"] == {"summary": "Audit logins"}
    assert call["state"]["deterministic_result"]["passed"] is False


@pytest.mark.parametrize("probability", [-0.1, 1.1, float("nan"), "secret"])
def test_jev_rejects_malformed_probability(probability: object) -> None:
    case, result = case_and_result()
    provider = JevDecisionProvider(
        model="jev-pinned", timeout_seconds=3, client=FakeTypeSafeClient(probability)
    )
    with pytest.raises(ValueError):
        provider.evaluate(case, result, "material_quality_issue_v1")


def test_jev_propagates_timeout_for_worker_degradation() -> None:
    class TimeoutClient:
        def system_one(self, **kwargs):
            del kwargs
            raise TimeoutError("private-input-secret")

    case, result = case_and_result()
    provider = JevDecisionProvider(model="jev-pinned", timeout_seconds=3, client=TimeoutClient())
    with pytest.raises(TimeoutError):
        provider.evaluate(case, result, "material_quality_issue_v1")


def test_jev_rejects_unknown_rubric_before_any_call() -> None:
    client = FakeTypeSafeClient()
    case, result = case_and_result()
    provider = JevDecisionProvider(model="jev-pinned", timeout_seconds=3, client=client)
    with pytest.raises(ValueError, match="rubric"):
        provider.evaluate(case, result, "unknown_v1")
    assert client.calls == []


def test_real_sdk_client_is_configured_without_retries(monkeypatch) -> None:
    seen: dict = {}

    class FakeRetryPolicy:
        def __init__(self, max_retries):
            seen["max_retries"] = max_retries

    class FakeSdkClient:
        def __init__(self, **kwargs):
            seen["client"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            del args

        def system_one(self, **kwargs):
            seen["call"] = kwargs
            return SimpleNamespace(nouls={
                "material_quality_issue": SimpleNamespace(noul=0.8)
            })

    monkeypatch.setitem(sys.modules, "typesafe_sdk", SimpleNamespace(
        RetryPolicy=FakeRetryPolicy, TypeSafeClient=FakeSdkClient,
    ))
    case, result = case_and_result()
    provider = JevDecisionProvider(
        model="jev-pinned", timeout_seconds=3, api_key="fake-test-key"
    )
    assert provider.evaluate(case, result, "material_quality_issue_v1").p_yes == 0.8
    assert seen["max_retries"] == 0
    assert seen["client"]["model"] == "jev-pinned"
    assert seen["client"]["api_key"] == "fake-test-key"
    assert seen["client"]["timeout"] == 3
    assert seen["call"]["timeout"] == 3


def test_jev_adapter_suppresses_sdk_debug_request_bodies(caplog) -> None:
    class LoggingClient:
        def system_one(self, **kwargs):
            del kwargs
            logging.getLogger("typesafe_sdk").debug("private-input-secret")
            return SimpleNamespace(nouls={
                "material_quality_issue": SimpleNamespace(noul=0.7)
            })

    logger = logging.getLogger("typesafe_sdk")
    prior = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        case, result = case_and_result()
        provider = JevDecisionProvider(
            model="jev-pinned", timeout_seconds=3, client=LoggingClient()
        )
        with caplog.at_level(logging.DEBUG):
            provider.evaluate(case, result, "material_quality_issue_v1")
        assert "private-input-secret" not in caplog.text
    finally:
        logger.setLevel(prior)
