import os
import subprocess
import sys


def test_worker_terminal_configuration_failure_is_sanitized() -> None:
    environment = os.environ.copy()
    secret = "terminal-password-secret"
    environment["AI_EVAL_JOB_LEASE_SECONDS"] = secret

    completed = subprocess.run(
        [sys.executable, "-m", "app.worker"],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=10,
    )

    rendered = completed.stdout + completed.stderr
    assert completed.returncode == 1
    assert '"event":"worker_terminal_failure"' in rendered
    assert '"error_code":"worker_startup_failed"' in rendered
    assert secret not in rendered
    assert "Traceback" not in rendered


def test_enabled_jev_without_credentials_fails_before_database_connection() -> None:
    environment = os.environ.copy()
    environment.pop("TYPESAFE_API_KEY", None)
    environment["AI_EVAL_DECISION_JUDGE_PROVIDER"] = "jev"
    environment["AI_EVAL_DECISION_JUDGE_MODEL"] = "jev-2026-09"
    environment["AI_EVAL_DECISION_JUDGE_PROJECTS"] = "project-a"
    environment["AI_EVAL_DATABASE_URL"] = "postgresql+psycopg://unavailable@127.0.0.1:1/no"

    completed = subprocess.run(
        [sys.executable, "-m", "app.worker"], capture_output=True,
        check=False, env=environment, text=True, timeout=10,
    )

    rendered = completed.stdout + completed.stderr
    assert completed.returncode == 1
    assert '"error_code":"decision_judge_configuration_invalid"' in rendered
    assert "Traceback" not in rendered
