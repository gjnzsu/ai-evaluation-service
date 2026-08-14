import pytest

from app.domain.platform import (
    MachineVerdict,
    ReviewDecision,
    ReviewStatus,
    baseline_review_status,
    validate_review_decision,
)


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        (MachineVerdict.PASS, ReviewStatus.OPTIONAL),
        (MachineVerdict.NOT_PASSED, ReviewStatus.REQUIRED),
    ],
)
def test_baseline_review_status(verdict, expected):
    assert baseline_review_status(verdict) is expected


def test_not_passed_requires_waiver_rationale():
    with pytest.raises(ValueError, match="waiver_rationale"):
        validate_review_decision(
            MachineVerdict.NOT_PASSED,
            ReviewDecision.WAIVED,
            waiver_rationale=None,
        )


def test_approved_is_not_valid_for_not_passed():
    with pytest.raises(ValueError, match="not valid"):
        validate_review_decision(
            MachineVerdict.NOT_PASSED,
            ReviewDecision.APPROVED,
            waiver_rationale=None,
        )
