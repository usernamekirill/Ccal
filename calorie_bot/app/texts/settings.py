"""Copy for the /settings flow (Russian)."""

from calorie_bot.app.domain import FitnessGoal, MeasurementUnit

GOAL_LABELS: dict[str, str] = {
    FitnessGoal.LOSE_WEIGHT.value: "Похудеть",
    FitnessGoal.MAINTAIN_WEIGHT.value: "Поддерживать вес",
    FitnessGoal.GAIN_WEIGHT.value: "Набрать массу",
    FitnessGoal.TRACK_CALORIES.value: "Только считать калории",
}

UNIT_LABELS: dict[str, str] = {
    MeasurementUnit.METRIC.value: "Кг, см, ккал",
    MeasurementUnit.IMPERIAL.value: "Фунты, дюймы, ккал",
}

SETTINGS_NO_PROFILE = (
    "Цель ещё не настроена. Отправьте /start, чтобы пройти первичную настройку."
)

CALORIE_GOAL_PROMPT = (
    "Введите дневную цель по калориям (целое число, ккал). "
    "Допустимый диапазон для этого бота: от 500 до 8000."
)

CALORIE_GOAL_SAVED = "Новая цель по калориям сохранена. Прогресс за дни в дневнике пересчитан."

INVALID_CALORIE_NUMBER = "Нужно целое число калорий. Пример: 2000"

CALORIE_OUT_OF_RANGE = "Число вне допустимого диапазона. Попробуйте другое значение."

TIMEZONE_SAVED = "Часовой пояс сохранён."

DATA_DELETE_WARN = (
    "Удалить все ваши данные в боте? Это действие необратимо: приёмы пищи, профиль "
    "и настройки будут стёрты. "
    "Связь с Telegram останется только для новой регистрации через /start."
)

DATA_DELETE_CONFIRM = "Подтвердить удаление"

DATA_DELETE_CANCEL = "Отмена"

DATA_DELETED_OK = (
    "Готово: ваши данные удалены из бота. Чтобы начать заново, отправьте /start."
)

DATA_DELETE_CANCELLED = "Удаление отменено."

RECALC_OK = "Норма КБЖУ пересчитана по данным анкеты, прогресс обновлён."

RECALC_NEEDS_FULL_PROFILE = (
    "Чтобы пересчитать норму автоматически, нужны пол, возраст, рост, вес и активность. "
    "Измените профиль через пункт ниже."
)


def main_screen_text(
    *,
    goal_key: str | None,
    daily_calorie_target: int | None,
    protein_g: int | None,
    fat_g: int | None,
    carbs_g: int | None,
    profile_timezone: str | None,
    settings_timezone: str | None,
    notifications_on: bool,
    motivation_on: bool,
    ai_on: bool,
    measurement_unit: str,
) -> str:
    """Build the primary settings overview without exposing secrets."""
    g = GOAL_LABELS.get(goal_key, goal_key or "—")
    kcal = daily_calorie_target if daily_calorie_target is not None else "—"
    p, f_, c = protein_g, fat_g, carbs_g
    macros = f"{p}/{f_}/{c}" if p is not None or f_ is not None or c is not None else "—/—/—"
    tz = profile_timezone or settings_timezone or "—"
    unit_label = UNIT_LABELS.get(measurement_unit, measurement_unit)
    return (
        "⚙️ Настройки\n\n"
        f"Цель: {g}\n"
        f"Калории в день: {kcal} ккал\n"
        f"БЖУ (г): {macros}\n"
        f"Часовой пояс (дневник): {tz}\n"
        f"Единицы: {unit_label}\n"
        f"Уведомления: {'вкл.' if notifications_on else 'выкл.'}\n"
        f"Мотивация: {'вкл.' if motivation_on else 'выкл.'}\n"
        f"AI-анализ (фото, голос, текст еды): {'вкл.' if ai_on else 'выкл.'}\n"
    )


TIMEZONE_HEADING = "Выберите часовой пояс для дневника:"

UNITS_HEADING = "Единицы измерения (для отображения):"

AI_DISABLED_HINT = (
    "AI-анализ выключен в настройках. Включите его здесь или ограничьтесь ручным вводом калорий."
)

PROFILE_EDIT_INTRO = (
    "Нажмите кнопку ниже, чтобы снова пройти вопросы профиля и целей анкеты."
)
