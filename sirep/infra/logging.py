from __future__ import annotations

import logging
import logging.handlers
import sys

from sirep.shared.config import LOG_DIRECTORY_PATH, LOG_FILE_PATH, LOG_LEVEL


def setup_logging(level: str | None = None) -> None:
    resolved_level = (level or LOG_LEVEL).upper()
    LOG_DIRECTORY_PATH.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(resolved_level)

    # Console handler (formato compacto)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(resolved_level)
    ch.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    ))

    # File handler com rotação
    fh = logging.handlers.RotatingFileHandler(
        str(LOG_FILE_PATH), maxBytes=10_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(resolved_level)
    fh.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Limpa handlers anteriores para evitar duplicação ao reload
    root.handlers.clear()
    root.addHandler(ch)
    root.addHandler(fh)

    # Integra loggers conhecidos
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "asyncio"):
        logging.getLogger(name).setLevel(resolved_level)
