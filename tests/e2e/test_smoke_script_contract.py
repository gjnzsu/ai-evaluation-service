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
