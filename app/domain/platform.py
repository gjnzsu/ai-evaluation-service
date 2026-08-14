from enum import StrEnum


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MachineVerdict(StrEnum):
    PASS = "pass"
    NOT_PASSED = "not_passed"


class ReviewStatus(StrEnum):
    OPTIONAL = "optional"
    REQUIRED = "required"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAIVED = "waived"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    WAIVED = "waived"


def baseline_review_status(verdict: MachineVerdict) -> ReviewStatus:
    if verdict is MachineVerdict.PASS:
        return ReviewStatus.OPTIONAL
    return ReviewStatus.REQUIRED


def validate_review_decision(
    verdict: MachineVerdict,
    decision: ReviewDecision,
    waiver_rationale: str | None,
) -> None:
    allowed = {
        MachineVerdict.PASS: {ReviewDecision.APPROVED, ReviewDecision.REJECTED},
        MachineVerdict.NOT_PASSED: {ReviewDecision.WAIVED, ReviewDecision.REJECTED},
    }
    if decision not in allowed[verdict]:
        raise ValueError(f"Decision {decision} is not valid for {verdict}")
    if decision is ReviewDecision.WAIVED and not (waiver_rationale or "").strip():
        raise ValueError("waiver_rationale is required for waived decisions")
