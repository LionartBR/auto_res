from __future__ import annotations

import os
from sirep.infra.config import settings
from sirep.infra.db import get_engine

def is_sqlite_file(url: str) -> str | None:
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1)
        return os.path.abspath(path)
    return None

def main():
    sqlite_path = is_sqlite_file(settings.DB_URL)
    if sqlite_path:
        if os.path.exists(sqlite_path):
            os.remove(sqlite_path)
            print(f"[reset-db] removido arquivo SQLite: {sqlite_path}")
        else:
            print(f"[reset-db] arquivo SQLite já não existe: {sqlite_path}")


from pathlib import Path
from typing import Final

from sirep.infra.config import settings
from sirep.infra.db import get_engine


SQLITE_PREFIX: Final[str] = "sqlite:///"


def sqlite_path_from_url(url: str) -> Path | None:
    """Return the path for SQLite URLs (``sqlite:///``) or ``None`` otherwise."""

    if not url.startswith(SQLITE_PREFIX):
        return None
    return Path(url.removeprefix(SQLITE_PREFIX)).expanduser().resolve()


def recreate_relational_schema() -> None:
    """Drop and create all ORM metadata objects for non-SQLite databases."""

    from sirep.domain.models import Base

    engine = get_engine()
    with engine.begin() as conn:
        Base.metadata.drop_all(bind=conn)
        Base.metadata.create_all(bind=conn)
    print("[reset-db] schema recriado no banco configurado.")


def remove_sqlite_file(path: Path) -> None:
    """Remove the SQLite file if it exists, reporting the action to stdout."""

    try:
        path.unlink()
    except FileNotFoundError:
        print(f"[reset-db] arquivo SQLite já não existe: {path}")

    else:
        print(f"[reset-db] removido arquivo SQLite: {path}")


def main() -> None:
    """Reset the configured database, handling SQLite files and other engines."""

    sqlite_path = sqlite_path_from_url(settings.DB_URL)
    if sqlite_path is not None:
        remove_sqlite_file(sqlite_path)
        return

    recreate_relational_schema()


if __name__ == "__main__":
    main()
