"""Score aggregation helpers."""

from __future__ import annotations


def clamp_score(value: int | float) -> int:
    """Clamp a score to the 0-100 range."""

    return max(0, min(100, int(round(value))))


def average_scores(scores: dict[str, int], *, exclude: set[str] | None = None) -> int:
    """Average score values, optionally excluding non-applicable criteria."""

    excluded = exclude or set()
    included = [score for name, score in scores.items() if name not in excluded]
    if not included:
        return 0
    return clamp_score(sum(included) / len(included))

