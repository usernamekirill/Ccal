"""Guards for flows that should run only after profile onboarding."""

from calorie_bot.app.database.models import User
from calorie_bot.app.texts.onboarding import FOOD_AFTER_ONBOARDING_HINT


def food_logging_blocked_message(user: User) -> str | None:
    """Return a user hint if meal logging should wait until onboarding is done."""
    if user.onboarding_completed:
        return None
    return FOOD_AFTER_ONBOARDING_HINT
