from __future__ import annotations
import logging
import logging.handlers
import os
import sys

DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_PATH = os.path.join(LOG_DIR, "sirep.log")

def setup_logging(level: str | None = None) -> None:
    level = level or DEFAULT_LEVEL
    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler (formato compacto)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    ))

    # File handler com rotação
    fh = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(level)
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
        logging.getLogger(name).setLevel(level)

    logging.getLogger(__name__).info("logging configurado em %s (arquivo: %s)", level, LOG_PATH)