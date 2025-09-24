"""Utility script to reset the configured database."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from sirep.infra.config import settings
from sirep.infra.db import get_engine, is_sqlite_url


SQLITE_PREFIX: Final[str] = "sqlite:///"


def sqlite_path_from_url(url: str) -> Path | None:
    """Return the local filesystem path for SQLite URLs."""

    if not is_sqlite_url(url):
        return None

    return Path(url.removeprefix(SQLITE_PREFIX)).expanduser().resolve()


def remove_sqlite_file(path: Path) -> None:
    """Remove the SQLite file if it exists, logging the action to stdout."""

    try:
        path.unlink()
    except FileNotFoundError:
        print(f"[reset-db] arquivo SQLite já não existe: {path}")
    else:
        print(f"[reset-db] removido arquivo SQLite: {path}")


def recreate_relational_schema() -> None:
    """Drop and recreate all ORM metadata objects for non-SQLite databases."""

    from sirep.domain.models import Base

    engine = get_engine()
    with engine.begin() as conn:
        Base.metadata.drop_all(bind=conn)
        Base.metadata.create_all(bind=conn)

    print("[reset-db] schema recriado no banco configurado.")


def main() -> None:
    """Reset the configured database depending on the configured URL."""

    sqlite_path = sqlite_path_from_url(settings.DB_URL)
    if sqlite_path is not None:
        remove_sqlite_file(sqlite_path)
        return

    recreate_relational_schema()


if __name__ == "__main__":
    main()
