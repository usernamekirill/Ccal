from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from calorie_bot.app.config import Settings
from calorie_bot.app.exceptions import UserFacingHandledError
from calorie_bot.app.storage.cache import CachingStorageWrapper
from calorie_bot.app.storage.factory import create_sqlalchemy_storage


class AppContextMiddleware(BaseMiddleware):
    """Inject application settings and a database session into handlers."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Run a handler with shared app dependencies."""
        async with self._session_factory() as session:
            data["settings"] = self._settings
            data["session"] = session
            data["storage"] = create_sqlalchemy_storage(session)
            if self._settings.stats_cache_ttl_seconds > 0:
                data["storage"] = CachingStorageWrapper(
                    data["storage"],
                    self._settings.stats_cache_ttl_seconds,
                )
            data["_session_factory"] = self._session_factory
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except UserFacingHandledError:
                await session.rollback()
                return None
            except Exception:
                await session.rollback()
                raise
