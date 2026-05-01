"""Проверка BOT_TOKEN/TELEGRAM_BOT_TOKEN, типа storage и подключения к БД."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def _run_checks() -> None:
    """Проверка токена, режима хранения и SQL-подключения (без вывода секретов)."""
    from calorie_bot.app.config import get_settings

    settings = get_settings()
    if not settings.telegram_bot_token.get_secret_value().strip():
        raise RuntimeError("BOT_TOKEN or TELEGRAM_BOT_TOKEN is empty")

    db_type = settings.database_type.strip().lower()
    if db_type == "external":
        raise RuntimeError("DATABASE_TYPE=external: polling-бот используйте с sqlite или postgres")

    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


def main() -> None:
    """Запуск: ``python scripts/healthcheck.py`` или ``python -m scripts.healthcheck``."""
    try:
        asyncio.run(_run_checks())
    except Exception as exc:
        print(f"healthcheck_failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
