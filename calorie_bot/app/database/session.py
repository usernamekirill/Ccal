from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from calorie_bot.app.config import Settings


def create_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    """Create an async SQLAlchemy session factory from application settings."""
    if settings.database_type.strip().lower() == "external":
        raise RuntimeError(
            "DATABASE_TYPE=external is for HTTP storage workers only; "
            "the Telegram bot expects sqlite or postgres DATABASE_URL.",
        )
    _ensure_sqlite_parent(settings.database_url)
    engine_kwargs: dict = {"pool_pre_ping": True}
    url = settings.database_url
    if url.startswith("postgresql"):
        engine_kwargs["pool_size"] = settings.postgres_pool_size
        engine_kwargs["max_overflow"] = settings.postgres_max_overflow
    engine = create_async_engine(url, **engine_kwargs)
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield an async session and commit or rollback around the caller."""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite"):
        return
    database = make_url(database_url).database
    if database in {None, "", ":memory:"}:
        return
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
