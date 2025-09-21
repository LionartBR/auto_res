from __future__ import annotations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sirep.infra.config import settings

def get_engine():
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
    # importa Base aqui para evitar import circular
    from sirep.domain.models import Base

    Base.metadata.create_all(bind=_engine)

    # Ajusta colunas novas em execuções antigas do sqlite.
    with _engine.begin() as conn:
        info = conn.execute(text("PRAGMA table_info(plans)")).fetchall()
        existing = {row[1] for row in info}
        alter_statements = []
        if "razao_social" not in existing:
            alter_statements.append("ALTER TABLE plans ADD COLUMN razao_social VARCHAR(255)")
        if "data_rescisao" not in existing:
            alter_statements.append("ALTER TABLE plans ADD COLUMN data_rescisao DATE")
        if "data_comunicacao" not in existing:
            alter_statements.append("ALTER TABLE plans ADD COLUMN data_comunicacao DATE")
        if "metodo_comunicacao" not in existing:
            alter_statements.append("ALTER TABLE plans ADD COLUMN metodo_comunicacao VARCHAR(16)")
        if "referencia_comunicacao" not in existing:
            alter_statements.append(
                "ALTER TABLE plans ADD COLUMN referencia_comunicacao VARCHAR(128)"
            )
        for ddl in alter_statements:
            conn.execute(text(ddl))