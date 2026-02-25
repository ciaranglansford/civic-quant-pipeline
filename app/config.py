from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    database_url: str

    # Digest / publishing
    vip_digest_hours: int = 4
    tg_bot_token: str | None = None
    tg_vip_chat_id: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]

