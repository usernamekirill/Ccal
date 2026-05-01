"""PostgreSQL deployment (Supabase, Yandex Managed PG, Railway, $5 VPS).

Recommended URL: ``postgresql+asyncpg://user:pass@host:5432/db`` (install ``asyncpg``).

Pooling is configured in ``database.session.create_session_factory`` via
``POSTGRES_POOL_SIZE`` / ``POSTGRES_MAX_OVERFLOW``.
"""

from calorie_bot.app.storage.sqlalchemy_backend import SqlAlchemyStorage as PostgresStorage

__all__ = ["PostgresStorage"]
