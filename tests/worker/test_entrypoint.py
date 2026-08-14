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
