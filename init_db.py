"""Apply Alembic migrations so the SQLite (or other) database schema exists.

Run from the project root (same folder as ``alembic.ini``):

    python init_db.py

Uses ``DATABASE_URL`` from ``.env`` if present (Alembic ``env.py`` loads settings).
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations() -> None:
    """Upgrade to ``head`` using the repo ``alembic.ini``."""
    root = Path(__file__).resolve().parent
    ini_path = root / "alembic.ini"
    if not ini_path.is_file():
        print(f"Missing {ini_path}", file=sys.stderr)
        sys.exit(1)
    cfg = Config(str(ini_path))
    command.upgrade(cfg, "head")
    print("Database migrations applied (alembic upgrade head).")


if __name__ == "__main__":
    run_migrations()
