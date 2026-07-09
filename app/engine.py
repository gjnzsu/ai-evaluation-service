"""Evaluation engine and artifact evaluator registry."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.artifact_types import PM_STATUS_REPORT, REQUIREMENT_BACKLOG
from app.domain.models import EvaluationCase, EvaluationResult, Finding
from app.evaluators.llm_judge import DisabledJudge, LlmJudge
from app.evaluators.pm_status_report import evaluate_pm_status_report
from app.evaluators.requirement_backlog import evaluate_requirement_backlog

Evaluator = Callable[[EvaluationCase], EvaluationResult]


class EvaluationEngine:
    """Dispatch evaluation cases to artifact-specific evaluators."""

    def __init__(
        self,
        *,
        evaluators: dict[str, Evaluator] | None = None,
        judge: LlmJudge | None = None,
    ) -> None:
        self.evaluators = evaluators or {
            REQUIREMENT_BACKLOG: evaluate_requirement_backlog,
            PM_STATUS_REPORT: evaluate_pm_status_report,
        }
        self.judge = judge or DisabledJudge()

    def evaluate(self, case: EvaluationCase) -> EvaluationResult:
        evaluator = self.evaluators.get(case.artifact_type)
        if evaluator is None:
            return EvaluationResult(
                case_id=case.case_id,
                artifact_type=case.artifact_type,
                overall_score=0,
                passed=False,
                criteria_scores={},
                findings=[
                    Finding(
                        code="unknown_artifact_type",
                        message=(
                            "No evaluator is registered for artifact type "
                            f"`{case.artifact_type}`."
                        ),
                        severity="error",
                        blocking=True,
                    )
                ],
                metadata={**case.run_metadata, "judge_enabled": bool(self.judge.enabled)},
            )

        result = evaluator(case)
        result.metadata.update(case.run_metadata)
        result.metadata["judge_enabled"] = bool(self.judge.enabled)

        if not self.judge.enabled:
            return result

        try:
            judged = self.judge.evaluate(case, result)
            judged.metadata["judge_enabled"] = True
            return judged
        except Exception as error:
            result.findings.append(
                Finding(
                    code="llm_judge_failed",
                    message=f"LLM judge failed: {error}",
                    severity="warning",
                )
            )
            return result
