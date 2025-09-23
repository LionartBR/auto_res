"""Centralized runtime configuration helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta, timezone, tzinfo
from functools import cached_property, lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sirep.infra.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _resolve_timezone(name: str, fallback_offset_minutes: int) -> tzinfo:
    """Return a timezone instance for ``name`` with graceful fallback."""

    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        offset = timedelta(minutes=fallback_offset_minutes)
        fallback = timezone(offset, name=name or "UTC")
        sign = "+" if fallback_offset_minutes >= 0 else "-"
        minutes = abs(fallback_offset_minutes)
        hours, minutes = divmod(minutes, 60)
        logger.warning(
            "Fuso horário '%s' não encontrado; usando offset UTC%s%02d:%02d como fallback",
            name,
            sign,
            hours,
            minutes,
        )
        return fallback


@dataclass(frozen=True)
class AppConfig:
    """Expose derived configuration used across the application."""

    timezone_name: str
    timezone_fallback_offset_minutes: int
    date_display_format: str
    datetime_display_format: str

    @cached_property
    def display_timezone(self) -> tzinfo:
        """Timezone used to present datetimes to the user."""

        return _resolve_timezone(self.timezone_name, self.timezone_fallback_offset_minutes)


@dataclass(frozen=True)
class LoggingConfig:
    """Expose logging related configuration."""

    directory: str
    filename: str
    level: str

    @cached_property
    def directory_path(self) -> Path:
        return Path(self.directory)

    @cached_property
    def file_path(self) -> Path:
        return self.directory_path / self.filename


app_config = AppConfig(
    timezone_name=settings.TIMEZONE,
    timezone_fallback_offset_minutes=settings.TIMEZONE_FALLBACK_OFFSET_MINUTES,
    date_display_format=settings.DATE_FORMAT,
    datetime_display_format=settings.DATETIME_FORMAT,
)


DISPLAY_TIMEZONE: tzinfo = app_config.display_timezone
DATE_DISPLAY_FORMAT: str = app_config.date_display_format
DATETIME_DISPLAY_FORMAT: str = app_config.datetime_display_format


logging_config = LoggingConfig(
    directory=settings.LOG_DIR,
    filename=settings.LOG_FILENAME,
    level=settings.LOG_LEVEL,
)


LOGGING_CONFIG = logging_config
LOG_DIRECTORY: str = logging_config.directory
LOG_DIRECTORY_PATH: Path = logging_config.directory_path
LOG_FILE_NAME: str = logging_config.filename
LOG_FILE_PATH: Path = logging_config.file_path
LOG_LEVEL: str = logging_config.level

