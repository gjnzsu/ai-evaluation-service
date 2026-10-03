"""TypeSafe Jev adapter for one explicitly opted-in shadow rubric."""

import logging
from typing import Any

from app.domain.models import EvaluationCase, EvaluationResult
from app.worker.decision import RawDecision

RUBRIC_VERSION = "material_quality_issue_v1"
QUESTION_NAME = "material_quality_issue"
QUESTION = "Does the canonical output contain a material quality issue for this artifact type?"


class JevDecisionProvider:
    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: float,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self.client = client

    def evaluate(
        self,
        case: EvaluationCase,
        deterministic_result: EvaluationResult,
        rubric: str,
    ) -> RawDecision:
        if rubric != RUBRIC_VERSION:
            raise ValueError("unsupported decision rubric")
        # The SDK's debug mode can include request/response bodies; never emit them.
        logging.getLogger("typesafe_sdk").setLevel(logging.CRITICAL + 1)
        request = {
            "state": {
                "case_id": case.case_id,
                "artifact_type": case.artifact_type,
                "canonical_output": case.canonical_output,
                "deterministic_result": deterministic_result.model_dump(mode="json"),
            },
            "questions": {QUESTION_NAME: {"type": "noul", "instructions": QUESTION}},
            "model": self.model,
            "timeout": self.timeout_seconds,
        }
        if self.client is not None:
            response = self.client.system_one(**request)
        else:
            from typesafe_sdk import RetryPolicy, TypeSafeClient

            logging.getLogger("typesafe_sdk").setLevel(logging.CRITICAL + 1)
            with TypeSafeClient(
                api_key=self.api_key,
                model=self.model,
                retry=RetryPolicy(max_retries=0),
                timeout=self.timeout_seconds,
            ) as client:
                response = client.system_one(**request)
        probability = response.nouls[QUESTION_NAME].noul
        if not isinstance(probability, float):
            raise ValueError("invalid decision probability")
        return RawDecision(
            provider="jev",
            model=self.model,
            rubric_version=rubric,
            answer="yes" if probability >= 0.5 else "no",
            p_yes=probability,
        )
