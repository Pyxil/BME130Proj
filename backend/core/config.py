"""Backend settings, read from environment variables or a ``.env`` file.

See ``.env.example`` for every variable with a description.  Separate
configurations for development / testing / production are selected with
``APP_ENV``; production refuses to start with insecure defaults.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEV_SECRET = "dev-only-insecure-secret-change-me-before-deploying"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field("development", description="development | testing | production")
    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'app.db').as_posix()}"
    secret_key: str = _DEV_SECRET
    access_token_expire_minutes: int = 60 * 24 * 7
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    max_upload_bytes: int = 2_000_000
    max_concurrent_analyses: int = 2
    recordings_dir: Path = REPO_ROOT / "data" / "recordings"
    words_file: Path = REPO_ROOT / "data" / "words.json"
    auto_migrate: bool = True
    warmup_on_start: bool = True
    default_session_size: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    def check_production(self) -> None:
        if self.app_env == "production":
            if self.secret_key == _DEV_SECRET or len(self.secret_key) < 32:
                raise RuntimeError("SECRET_KEY must be set to a random value of at least 32 characters in production")
            if self.database_url.startswith("sqlite"):
                raise RuntimeError("Use PostgreSQL (DATABASE_URL) in production")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.check_production()
    return s
