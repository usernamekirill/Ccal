from typing import Any

WELCOME_TEXT = (
    "Привет! Я помогу считать калории по фото, тексту и голосу. "
    "Сначала настроим цель и ориентиры по КБЖУ."
)

NUTRITION_DISCLAIMER_TEXT = (
    "Расчет КБЖУ является ориентиром и не заменяет консультацию врача или нутрициолога, "
    "особенно при медицинских ограничениях."
)

PHOTO_PROCESSING_TEXT = "Смотрю, что на тарелке 🔍"
PHOTO_FORMAT_ERROR_TEXT = "Не смог открыть фото. Поддерживаются JPEG, PNG и WEBP."
PHOTO_EDIT_FLEX_TEXT = (
    "Одной фразой, что поменять. Примеры:\n"
    "• кулич 50 г\n"
    "• убери соус\n"
    "• добавь яблоко 100 г, 50 ккал"
)
PHOTO_EDIT_ERROR_TEXT = "Не смог применить правку. Переформулируй короче или попробуй ещё раз."
PHOTO_QUICK_ADD_TEXT = (
    "Через запятую: название, граммы, калории.\n"
    "Пример: кофе с молоком, 250, 120"
)
PHOTO_QUICK_DELETE_TEXT = "Напиши номер строки продукта (1, 2…)."
RECOGNITION_UNCERTAIN_TEXT = (
    "Не получилось уверенно распознать.\n\n"
    "Попробуйте проще, например:\n"
    "✍️ «гречка 200 г и курица 150 г»\n"
    "или отправьте фото блюда / голосовое описание."
)
TEXT_FOOD_PROCESSING_TEXT = "Разбираю, что добавить в дневник ✍️"
TEXT_FOOD_CLARIFICATION_PREFIX = "Уточню один момент:"

GENERIC_ERROR_TEXT = "Что-то пошло не так. Попробуй еще раз чуть позже."

GOAL_PROMPT_TEXT = "Какая у тебя сейчас главная цель?"
SEX_PROMPT_TEXT = "Укажи пол для расчета базового обмена."
AGE_PROMPT_TEXT = "Сколько тебе лет? Напиши число."
HEIGHT_PROMPT_TEXT = "Какой у тебя рост в сантиметрах?"
WEIGHT_PROMPT_TEXT = "Какой сейчас вес в килограммах?"
ACTIVITY_PROMPT_TEXT = "Выбери примерный уровень активности."
TARGETS_CONFIRMED_TEXT = (
    "Готово, цель сохранена. Дальше просто отправляйте в чат фото, голос или текст с едой."
)
INVALID_NUMBER_TEXT = "Не смог разобрать число. Напиши, пожалуйста, только значение."
MEAL_NOT_FOUND_TEXT = "Не нашел активный черновик приема пищи. Отправь фото или текст с едой."
MEAL_CONFIRMED_TEXT = "Сохранил прием пищи. Вот обновленный итог:"
MEAL_CANCELLED_TEXT = "Ок, отменил этот черновик."
MEAL_DELETED_TEXT = "Удалил прием пищи из дневника."
TODAY_EMPTY_TEXT = "За сегодня пока нет сохраненных приемов пищи."
TODAY_HEADER_TEXT = "Сегодня в дневнике:"
AI_UNAVAILABLE_TEXT = (
    "Сейчас не получилось распознать автоматически. "
    "Можно попробовать еще раз или написать еду текстом."
)
FILE_TOO_LARGE_TEXT = (
    "Файл слишком большой для MVP. Попробуй отправить фото или аудио меньшего размера."
)


def render_targets_text(
    calories: int,
    protein_g: int,
    fat_g: int,
    carbs_g: int,
    bmr_calories: int,
    tdee_calories: int,
) -> str:
    """Render daily nutrition targets for onboarding confirmation."""
    return (
        "Твои ориентиры на день:\n"
        f"Калории: {calories} ккал\n"
        f"Белки: {protein_g} г\n"
        f"Жиры: {fat_g} г\n"
        f"Углеводы: {carbs_g} г\n\n"
        f"BMR: {bmr_calories} ккал, TDEE: {tdee_calories} ккал.\n"
        f"{NUTRITION_DISCLAIMER_TEXT}"
    )


def render_meal_draft_text(
    items: list[str],
    total_calories: int,
    confidence: float | None,
    notes: str | None,
) -> str:
    """Render a meal draft before user confirmation."""
    confidence_text = f"\nУверенность: {confidence:.0%}" if confidence is not None else ""
    notes_text = f"\nЗаметка: {notes}" if notes else ""
    return (
        "Я оценил прием пищи. Проверь перед сохранением:\n\n"
        + "\n".join(items)
        + f"\n\nИтого: {total_calories} ккал"
        + confidence_text
        + notes_text
    )


def render_today_meals_text(meals: list[Any]) -> str:
    """Render today's saved meals with item summaries."""
    if not meals:
        return TODAY_EMPTY_TEXT
    lines = [TODAY_HEADER_TEXT]
    for meal in meals:
        item_names = ", ".join(item.name for item in meal.items)
        lines.append(
            f"#{meal.id} — {meal.total_calories} ккал"
            f" ({item_names or 'без продуктов'})"
        )
    lines.append("\nМожно изменить или удалить любой прием пищи.")
    return "\n".join(lines)
