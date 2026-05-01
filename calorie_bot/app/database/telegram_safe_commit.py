"""Helpers to align DB transaction boundaries with Telegram side effects."""

from sqlalchemy.ext.asyncio import AsyncSession


async def commit_db_work_before_telegram(session: AsyncSession) -> None:
    """Commit pending ORM writes before sending or editing Telegram messages.

    If a later step (edit_text, motivation, etc.) fails, the meal row and related
    rollups stay persisted; only a new transaction is rolled back by middleware.
    """
    await session.commit()
