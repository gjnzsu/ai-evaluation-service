"""Command-line interface for batch AI evaluation."""

from __future__ import annotations

import argparse
import json
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

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--input", required=True)
    evaluate.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    engine = EvaluationEngine()

    if args.command == "evaluate-case":
        result = _evaluate_file(Path(args.file), Path(args.output), engine)
        _write_summary(Path(args.output), [result])
        return 0 if result.passed else 1

    results = []
    for case_file in sorted(Path(args.input).rglob("*.json")):
        results.append(_evaluate_file(case_file, Path(args.output), engine))
    _write_summary(Path(args.output), results)
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


def _write_summary(output_dir: Path, results: list[EvaluationResult]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
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


if __name__ == "__main__":
    raise SystemExit(main())

