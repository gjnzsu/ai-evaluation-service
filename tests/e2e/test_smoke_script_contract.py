from pathlib import Path


def test_smoke_uses_compose_effective_local_configuration() -> None:
    script = Path("scripts/smoke-poc.ps1").read_text(encoding="utf-8")

    assert "http://localhost:8000" not in script
    assert "local-project-a-submit-read-review-key" not in script
    assert "local-project-b-submit-read-review-key" not in script
    assert "-U ai_eval" not in script
    assert "-d ai_eval" not in script
    assert '".env"' in script
    assert '".env.example"' in script
    assert "AI_EVAL_API_PORT" in script
    assert "AI_EVAL_DEMO_PROJECT_A_KEY" in script
    assert "AI_EVAL_DEMO_PROJECT_B_KEY" in script
    assert "POSTGRES_USER" in script
    assert "POSTGRES_DB" in script


def test_compose_keeps_jev_disabled_but_supports_explicit_worker_opt_in() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert (
        "AI_EVAL_DECISION_JUDGE_PROVIDER: ${AI_EVAL_DECISION_JUDGE_PROVIDER:-disabled}"
        in compose
    )
    assert "AI_EVAL_INSTALL_JEV:-false" in compose
    assert "TYPESAFE_API_KEY: ${TYPESAFE_API_KEY:-}" in compose
    assert "ARG INSTALL_JEV=false" in dockerfile
    assert "pip install '.[jev]'" in dockerfile
