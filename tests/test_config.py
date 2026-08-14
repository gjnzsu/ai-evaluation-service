from app.config import Settings, get_settings


def test_get_settings_uses_service_defaults():
    get_settings.cache_clear()

    settings = get_settings()

    assert isinstance(settings, Settings)
    assert settings.environment == "local"
    assert settings.database_url == "postgresql+psycopg://ai_eval:ai_eval@localhost:5432/ai_eval"
