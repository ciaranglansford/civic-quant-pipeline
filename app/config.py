from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Telegram listener
    tg_api_id: int | None = None
    tg_api_hash: str | None = None
    tg_session_name: str | None = None
    tg_source_channel: str | None = None
    ingest_api_base_url: str | None = None

    # Database
    database_url: str = "sqlite+pysqlite:///./civicquant_dev.db"

    # Digest / publishing
    vip_digest_hours: int = 4
    tg_bot_token: str | None = None
    tg_vip_chat_id: str | None = None

    # Phase 2 extraction
    phase2_extraction_enabled: bool = False
    phase2_batch_size: int = 50
    phase2_lease_seconds: int = 600
    phase2_scheduler_lock_seconds: int = 540
    phase2_admin_token: str | None = None

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
