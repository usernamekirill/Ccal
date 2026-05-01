from datetime import datetime

from calorie_bot.app.domain import MealType


def infer_meal_type(moment: datetime) -> MealType:
    """Infer meal type from local time."""
    hour = moment.hour
    if 5 <= hour < 11:
        return MealType.BREAKFAST
    if 11 <= hour < 16:
        return MealType.LUNCH
    if 16 <= hour < 22:
        return MealType.DINNER
    return MealType.SNACK
