"""Factory for concrete ``StorageInterface`` implementations."""

from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.storage.external_api_storage import ExternalAPIStorage
from calorie_bot.app.storage.interface import StorageInterface
from calorie_bot.app.storage.sqlalchemy_backend import SqlAlchemyStorage


def create_storage(settings: Settings, session: AsyncSession | None) -> StorageInterface:
    """Return storage for ``DATABASE_TYPE`` (relational needs an open ``AsyncSession``)."""
    mode = settings.database_type.strip().lower()
    if mode == "external":
        return ExternalAPIStorage(settings)
    if session is None:
        raise ValueError("AsyncSession is required when DATABASE_TYPE is not 'external'")
    return SqlAlchemyStorage(session)


def create_sqlalchemy_storage(session: AsyncSession) -> SqlAlchemyStorage:
    """Shortcut used by the Telegram bot middleware (SQLite / Postgres URLs)."""
    return SqlAlchemyStorage(session)
