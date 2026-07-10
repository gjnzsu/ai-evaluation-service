"""Command-line interface for batch AI evaluation."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.domain.models import EvaluationCase, EvaluationResult, Finding
from app.engine import EvaluationEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_case = subparsers.add_parser("evaluate-case")
    evaluate_case.add_argument("--file", required=True)
    evaluate_case.add_argument("--output", required=True)
    evaluate_case.add_argument("--run-id")

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--input", required=True)
    evaluate.add_argument("--output", required=True)
    evaluate.add_argument("--run-id")

    args = parser.parse_args(argv)
    engine = EvaluationEngine()
    started_at = _utc_now()
    run_id = _safe_name(args.run_id or _default_run_id(started_at))
    run_dir = Path(args.output) / "runs" / run_id
    cases_dir = run_dir / "cases"

    if args.command == "evaluate-case":
        result = _evaluate_file(Path(args.file), cases_dir, engine)
        _write_run_artifacts(
            run_dir,
            run_id=run_id,
            command=args.command,
            input_path=Path(args.file),
            results=[result],
            started_at=started_at,
        )
        return 0 if result.passed else 1

    results = []
    for case_file in sorted(Path(args.input).rglob("*.json")):
        results.append(_evaluate_file(case_file, cases_dir, engine))
    _write_run_artifacts(
        run_dir,
        run_id=run_id,
        command=args.command,
        input_path=Path(args.input),
        results=results,
        started_at=started_at,
    )
    return 0 if all(result.passed for result in results) else 1


def _evaluate_file(path: Path, output_dir: Path, engine: EvaluationEngine) -> EvaluationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        case = EvaluationCase.model_validate(payload)
        result = engine.evaluate(case)
    except (json.JSONDecodeError, ValidationError) as error:
        result = _invalid_file_result(path, error)

    result_path = output_dir / f"{_safe_name(result.case_id)}.result.json"
    result_path.write_text(
        json.dumps(result.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def _invalid_file_result(path: Path, error: Exception) -> EvaluationResult:
    return EvaluationResult(
        case_id=path.stem,
        artifact_type="invalid",
        overall_score=0,
        passed=False,
        criteria_scores={},
        findings=[
            Finding(
                code="invalid_case_file",
                message=str(error),
                severity="error",
                blocking=True,
            )
        ],
        metadata={"source_file": str(path)},
    )


def _write_run_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    command: str,
    input_path: Path,
    results: list[EvaluationResult],
    started_at: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = _build_summary(results)
    completed_at = _utc_now()
    run_payload = {
        "run_id": run_id,
        "command": command,
        "input_path": str(input_path),
        "started_at": started_at,
        "completed_at": completed_at,
        "summary": summary,
    }
    (output_dir / "run.json").write_text(
        json.dumps(run_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_summary(output_dir, results)


def _build_summary(results: list[EvaluationResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    average_score = round(
        sum(result.overall_score for result in results) / total,
        2,
    ) if total else 0
    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "average_score": average_score,
        "case_ids": [result.case_id for result in results],
    }


def _write_summary(output_dir: Path, results: list[EvaluationResult]) -> None:
    lines = [
        "# Evaluation Summary",
        "",
        "| Case | Type | Passed | Score | Findings |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            f"| {result.case_id} | {result.artifact_type} | {result.passed} | "
            f"{result.overall_score} | {len(result.findings)} |"
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _safe_name(value: Any) -> str:
    text = str(value or "case").strip() or "case"
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in text)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _default_run_id(started_at: str) -> str:
    return started_at.replace("+00:00", "Z").replace(":", "").replace("-", "")


if __name__ == "__main__":
    raise SystemExit(main())
