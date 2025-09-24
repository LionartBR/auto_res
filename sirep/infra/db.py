"""Database helpers and SQLAlchemy session configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from sirep.infra.config import settings


SQLITE_SCHEME_PREFIX = "sqlite:///"


def _build_engine_options() -> dict[str, Any]:
    options: dict[str, Any] = {"future": True, "pool_pre_ping": True}

    if settings.DB_ECHO:
        options["echo"] = True

    if settings.DB_POOL_SIZE is not None:
        options["pool_size"] = settings.DB_POOL_SIZE

    if settings.DB_MAX_OVERFLOW is not None:
        options["max_overflow"] = settings.DB_MAX_OVERFLOW

    if settings.DB_POOL_TIMEOUT is not None:
        options["pool_timeout"] = settings.DB_POOL_TIMEOUT

    if settings.DB_POOL_RECYCLE is not None:
        options["pool_recycle"] = settings.DB_POOL_RECYCLE

    if is_sqlite_url(settings.DB_URL):
        connect_args: dict[str, Any]
        existing = options.get("connect_args")
        if isinstance(existing, Mapping):
            connect_args = dict(existing)
        else:
            connect_args = {}
        connect_args.setdefault("check_same_thread", False)
        options["connect_args"] = connect_args

    return options


def is_sqlite_url(url: str) -> bool:
    """Return ``True`` if the database URL points to a SQLite database."""

    return url.startswith(SQLITE_SCHEME_PREFIX)


def get_engine() -> Engine:
    """Create a SQLAlchemy engine configured with the application settings."""

    return create_engine(settings.DB_URL, **_build_engine_options())


_engine = get_engine()

SessionLocal = sessionmaker(
    bind=_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    """Create database tables and apply legacy migrations when needed."""

    # importa Base aqui para evitar import circular
    from sirep.domain.models import Base

    Base.metadata.create_all(bind=_engine)
    _apply_legacy_plan_patches()


def _apply_legacy_plan_patches() -> None:
    legacy_columns = {
        "razao_social": "ALTER TABLE plans ADD COLUMN razao_social VARCHAR(255)",
        "data_rescisao": "ALTER TABLE plans ADD COLUMN data_rescisao DATE",
        "data_comunicacao": "ALTER TABLE plans ADD COLUMN data_comunicacao DATE",
        "metodo_comunicacao": "ALTER TABLE plans ADD COLUMN metodo_comunicacao VARCHAR(16)",
        "referencia_comunicacao": "ALTER TABLE plans ADD COLUMN referencia_comunicacao VARCHAR(128)",
        "dt_proposta": "ALTER TABLE plans ADD COLUMN dt_proposta DATE",
        "resolucao": "ALTER TABLE plans ADD COLUMN resolucao VARCHAR(32)",
        "numero_inscricao": "ALTER TABLE plans ADD COLUMN numero_inscricao VARCHAR(32)",
    }

    columns_to_drop = ("tipo_parcelamento", "saldo_total")

    with _engine.begin() as conn:
        inspector = inspect(conn)
        if not inspector.has_table("plans"):
            return

        existing = {column["name"] for column in inspector.get_columns("plans")}

        for column, ddl in legacy_columns.items():
            if column not in existing:
                conn.execute(text(ddl))

        for column in columns_to_drop:
            if column in existing:
                try:
                    conn.execute(text(f"ALTER TABLE plans DROP COLUMN {column}"))
                except OperationalError as exc:  # pragma: no cover - sqlite compat
                    if is_sqlite_url(settings.DB_URL):
                        continue
                    raise exc
