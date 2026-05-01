"""Friendly motivation copy — no guilt, no pressure."""

from calorie_bot.app.domain import MotivationEventType

MESSAGES: dict[MotivationEventType, str] = {
    MotivationEventType.FIRST_SAVED_MEAL: (
        "Отличное начало! Первый сохранённый приём пищи уже в дневнике — "
        "так удобнее смотреть динамику."
    ),
    MotivationEventType.STREAK_3_DAYS: (
        "Вы уже 3 дня подряд ведёте учёт — это сильный и спокойный шаг. Продолжайте в своём темпе."
    ),
    MotivationEventType.STREAK_7_DAYS: (
        "Целая неделя подряд с записями — ровный ритм. Если так комфортно, формат вам подходит."
    ),
    MotivationEventType.CLOSE_TO_GOAL: (
        "Сегодня вы близко к ориентиру по калориям — если так и планировали, "
        "хорошо совпало с целью."
    ),
    MotivationEventType.RETURNED_AFTER_BREAK: (
        "Вы снова в дневнике после перерыва — это нормально: можно продолжить "
        "с этого дня без спешки."
    ),
    MotivationEventType.PHOTO_ENTHUSIAST: (
        "Вы часто добавляете еду через фото — удобный способ быстро фиксировать приёмы."
    ),
    MotivationEventType.REGULARITY_IMPROVED: (
        "Регулярность записей в последние дни выше, чем чуть раньше — по дням стало нагляднее."
    ),
}

# Hours before the same event type may repeat (first_saved_meal is once-ever via separate check).
TYPE_COOLDOWN_HOURS: dict[MotivationEventType, int] = {
    MotivationEventType.STREAK_3_DAYS: 10 * 24,
    MotivationEventType.STREAK_7_DAYS: 14 * 24,
    MotivationEventType.CLOSE_TO_GOAL: 3 * 24,
    MotivationEventType.RETURNED_AFTER_BREAK: 30 * 24,
    MotivationEventType.PHOTO_ENTHUSIAST: 14 * 24,
    MotivationEventType.REGULARITY_IMPROVED: 14 * 24,
}

GLOBAL_MIN_HOURS_BETWEEN = 5
GLOBAL_MAX_PER_LOCAL_DAY = 2
