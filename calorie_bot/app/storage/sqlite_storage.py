"""SQLite deployment for ``DATABASE_URL=sqlite+aiosqlite:///...``.

Local MVP shares ``SqlAlchemyStorage`` with Postgres — only connection URL differs.
"""

from calorie_bot.app.storage.sqlalchemy_backend import SqlAlchemyStorage as SQLiteStorage

__all__ = ["SQLiteStorage"]
