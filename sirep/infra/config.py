"""Application configuration loaded from environment variables."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Runtime configuration used across the project."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SIREP_", extra="ignore")
    DB_URL: str = "sqlite:///./sirep.db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int | None = Field(default=None, ge=1)
    DB_MAX_OVERFLOW: int | None = Field(default=None, ge=0)
    DB_POOL_TIMEOUT: int | None = Field(default=None, ge=1)
    DB_POOL_RECYCLE: int | None = Field(default=None, ge=1)
    RUNTIME_ENV: Literal["dev", "prod", "test"] = "dev"
    DRY_RUN: bool = True  # evita efeitos colaterais em stubs
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_DIR: str = "logs"
    LOG_FILENAME: str = "sirep.log"
    TIMEZONE: str = "America/Sao_Paulo"
    TIMEZONE_FALLBACK_OFFSET_MINUTES: int = -180
    DATE_FORMAT: str = "%d/%m/%Y"
    DATETIME_FORMAT: str = "%d/%m/%Y %H:%M:%S"

settings = Settings()
