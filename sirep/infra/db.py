"""Database helpers and SQLAlchemy session configuration."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from sirep.infra.config import settings


def get_engine() -> Engine:
    """Create a SQLAlchemy engine configured with the application settings."""

    return create_engine(settings.DB_URL, future=True)


_engine = get_engine()

SessionLocal = sessionmaker(
    bind=_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    """Create database tables and backfill missing columns for legacy databases."""

    # importa Base aqui para evitar import circular
    from sirep.domain.models import Base

    Base.metadata.create_all(bind=_engine)

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
        info = conn.execute(text("PRAGMA table_info(plans)")).fetchall()
        existing = {row[1] for row in info}

        for column, ddl in legacy_columns.items():
            if column not in existing:
                conn.execute(text(ddl))

        for column in columns_to_drop:
            if column in existing:
                try:
                    conn.execute(text(f"ALTER TABLE plans DROP COLUMN {column}"))
                except OperationalError:
                    pass
