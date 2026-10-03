from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_EVAL_", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+psycopg://ai_eval:ai_eval@localhost:5432/ai_eval"
    worker_poll_seconds: float = 0.5
    job_lease_seconds: int = 60
    job_max_attempts: int = 3
    decision_judge_provider: str = "disabled"
    decision_judge_model: str = ""
    decision_judge_projects: str = ""
    decision_judge_timeout_seconds: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
