import asyncio
import contextlib
import logging

from aiogram import Bot

from calorie_bot.app.bot.dispatcher import create_dispatcher
from calorie_bot.app.config import get_settings
from calorie_bot.app.database.session import create_session_factory
from calorie_bot.app.health.server import run_health_server
from calorie_bot.app.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the Telegram bot in polling mode."""
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.telegram_bot_token.get_secret_value():
        raise RuntimeError("BOT_TOKEN or TELEGRAM_BOT_TOKEN is required to start the bot.")
    if not settings.openai_api_key.get_secret_value():
        logger.warning(
            "OPENAI_API_KEY is empty: vision, voice, and text meal parsing will fail "
            "until set in .env",
        )

    bot = Bot(token=settings.telegram_bot_token.get_secret_value())
    session_factory = create_session_factory(settings)
    dispatcher = create_dispatcher(settings, session_factory)

    health_task: asyncio.Task[None] | None = None
    if settings.health_check_port > 0:
        health_task = asyncio.create_task(
            run_health_server(settings.health_check_host, settings.health_check_port),
            name="health_check",
        )

    logger.info("Starting calorie bot polling")
    try:
        await dispatcher.start_polling(bot)
    finally:
        if health_task is not None:
            health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await health_task


if __name__ == "__main__":
    asyncio.run(main())
