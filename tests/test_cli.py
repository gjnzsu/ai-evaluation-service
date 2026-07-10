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
            "--run-id",
            "single-smoke",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    run_dir = output_dir / "runs" / "single-smoke"
    result_file = run_dir / "cases" / "login-audit.result.json"
    assert result_file.exists()
    payload = json.loads(result_file.read_text(encoding="utf-8"))
    assert payload["case_id"] == "login-audit"
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["run_id"] == "single-smoke"
    assert run_payload["summary"]["total_cases"] == 1
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "summary.md").exists()


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
                    "progress": [{"summary": "Gateway integration complete"}],
                    "completed": [{"summary": "Batch eval MVP merged"}],
                    "risks": [{"summary": "No material risk"}],
                    "blockers": [{"summary": "No active blockers"}],
                    "decisions_needed": [{"summary": "Confirm dashboard timing"}],
                    "owner_gaps": [{"summary": "No owner gaps"}],
                    "next_actions": [{"summary": "Run SIT smoke tests"}],
                    "stakeholder_update": (
                        "AI Platform is green and ready for SIT smoke testing."
                    ),
                    "source_references": [{"source_type": "jira", "key": "AIP-1"}],
                    "confidence_notes": ["Jira and status notes reviewed."],
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
            "--run-id",
            "batch-smoke",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    run_dir = output_dir / "runs" / "batch-smoke"
    assert (run_dir / "cases" / "pm-green.result.json").exists()
    assert (run_dir / "cases" / "bad.result.json").exists()
    summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary_payload["total_cases"] == 2
    assert summary_payload["passed_cases"] == 1
    assert summary_payload["failed_cases"] == 1
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["input_path"] == str(input_dir)
    assert run_payload["summary"] == summary_payload
