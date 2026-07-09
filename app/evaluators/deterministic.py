"""Shared deterministic evaluation helpers."""

from __future__ import annotations

from typing import Any

from app.domain.models import Finding
from app.domain.scoring import clamp_score


def text_present(value: Any, *, min_length: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_length


def list_present(value: Any, *, min_items: int = 1) -> bool:
    if not isinstance(value, list):
        return False
    return len([item for item in value if str(item).strip()]) >= min_items


def required_field_score(
    payload: dict[str, Any],
    fields: list[str],
    findings: list[Finding],
) -> int:
    missing = [field for field in fields if not _field_has_value(payload.get(field))]
    for field in missing:
        findings.append(
            Finding(
                code=f"missing_{field}",
                message=f"Required field `{field}` is missing or empty.",
                severity="error",
                blocking=True,
            )
        )
    return clamp_score(((len(fields) - len(missing)) / len(fields)) * 100)


def published_artifact_fidelity(
    canonical_output: dict[str, Any],
    published_artifacts: dict[str, Any],
    important_fields: list[str],
    findings: list[Finding],
) -> tuple[int, bool]:
    """Return fidelity score and whether the criterion was skipped."""

    if not published_artifacts:
        findings.append(
            Finding(
                code="published_artifacts_skipped",
                message="No published artifacts were supplied; fidelity evaluation was skipped.",
                severity="info",
            )
        )
        return 0, True

    rendered = _flatten_artifacts(published_artifacts).lower()
    missing: list[str] = []
    for field in important_fields:
        expected_values = _field_expected_values(canonical_output.get(field))
        has_match = any(_matches_rendered(expected, rendered) for expected in expected_values)
        if expected_values and not has_match:
            missing.append(field)

    for field in missing:
        findings.append(
            Finding(
                code="published_artifact_missing_fact",
                message=f"Published artifact does not include canonical field `{field}`.",
                severity="warning",
            )
        )

    if not important_fields:
        return 100, False
    score = ((len(important_fields) - len(missing)) / len(important_fields)) * 100
    return clamp_score(score), False


def _field_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    if isinstance(value, dict):
        return bool(value)
    return True


def _flatten_artifacts(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_flatten_artifacts(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_flatten_artifacts(item) for item in value)
    return str(value)


def _field_expected_values(value: Any) -> list[str]:
    if isinstance(value, list):
        expected: list[str] = []
        for item in value:
            if isinstance(item, dict):
                summary = str(item.get("summary") or "").strip()
                if summary:
                    expected.append(summary)
            else:
                text = str(item).strip()
                if text:
                    expected.append(text)
        return expected
    text = str(value or "").strip()
    return [text] if text else []


def _matches_rendered(expected: str, rendered: str) -> bool:
    normalized = expected.lower()
    if normalized in rendered:
        return True
    words = [word.strip(".,:;()[]{}") for word in normalized.split() if len(word) > 2]
    if len(words) < 2:
        return False
    for phrase_length in range(min(4, len(words)), 1, -1):
        if " ".join(words[:phrase_length]) in rendered:
            return True
    return False
