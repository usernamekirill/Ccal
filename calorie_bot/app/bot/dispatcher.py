from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from calorie_bot.app.bot.middleware import AppContextMiddleware
from calorie_bot.app.config import Settings
from calorie_bot.app.handlers import (
    errors,
    meal_confirmation,
    meal_portion_pick,
    navigation,
    onboarding,
    photo,
    settings_handler,
    start,
    stats_handler,
    text_food,
    today,
    trend_handler,
    voice,
)
from calorie_bot.app.middleware.errors import ErrorHandlerMiddleware
from calorie_bot.app.middleware.rate_limit import AIRateLimitMiddleware
from calorie_bot.app.ratelimit.sliding_window import SlidingWindowRateLimiter


def create_dispatcher(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> Dispatcher:
    """Create and configure aiogram dispatcher."""
    dispatcher = Dispatcher()

    limiter = SlidingWindowRateLimiter(
        max_events=settings.ai_rate_limit_per_minute,
        window_sec=60.0,
    )
    ai_rate = AIRateLimitMiddleware(limiter)

    dispatcher.update.middleware(AppContextMiddleware(settings, session_factory))
    dispatcher.update.middleware(ErrorHandlerMiddleware())

    dispatcher.include_router(start.router)
    dispatcher.include_router(onboarding.router)
    dispatcher.include_router(meal_confirmation.router)
    photo.router.message.middleware(ai_rate)
    dispatcher.include_router(photo.router)
    voice.router.message.middleware(ai_rate)
    dispatcher.include_router(voice.router)
    dispatcher.include_router(stats_handler.router)
    dispatcher.include_router(trend_handler.router)
    dispatcher.include_router(settings_handler.router)
    dispatcher.include_router(navigation.router)
    dispatcher.include_router(today.router)
    text_food.router.message.middleware(ai_rate)
    dispatcher.include_router(text_food.router)
    dispatcher.include_router(meal_portion_pick.router)
    dispatcher.include_router(errors.router)
    return dispatcher
