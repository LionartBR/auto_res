from __future__ import annotations
from sqlalchemy import create_engine
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