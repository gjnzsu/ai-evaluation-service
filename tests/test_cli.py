import json
import subprocess
import sys


def test_cli_evaluate_case_writes_json_result(tmp_path):
    case_file = tmp_path / "case.json"
    output_dir = tmp_path / "results"
    case_file.write_text(
        json.dumps(
            {
                "case_id": "login-audit",
                "artifact_type": "requirement_backlog",
                "canonical_output": {
                    "summary": "Add admin login auditing",
                    "business_value": "Improves traceability.",
                    "acceptance_criteria": ["Every login attempt is recorded."],
                    "priority": "High",
                    "invest_analysis": "Small and testable.",
                    "description": "Business Value: Improves traceability.",
                },
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "evaluate-case",
            "--file",
            str(case_file),
            "--output",
            str(output_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    result_file = output_dir / "login-audit.result.json"
    assert result_file.exists()
    payload = json.loads(result_file.read_text(encoding="utf-8"))
    assert payload["case_id"] == "login-audit"


def test_cli_batch_continues_after_invalid_json(tmp_path):
    input_dir = tmp_path / "cases"
    output_dir = tmp_path / "results"
    input_dir.mkdir()
    (input_dir / "bad.json").write_text("{not-json", encoding="utf-8")
    (input_dir / "good.json").write_text(
        json.dumps(
            {
                "case_id": "pm-green",
                "artifact_type": "pm_status_report",
                "canonical_output": {
                    "project_key": "AIP",
                    "project_name": "AI Platform",
                    "time_window": "Today",
                    "audience": "Team",
                    "health": "Green",
                    "executive_summary": "AI Platform is green and on track.",
                },
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "evaluate",
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert (output_dir / "pm-green.result.json").exists()
    assert (output_dir / "bad.result.json").exists()
    assert (output_dir / "summary.md").exists()
