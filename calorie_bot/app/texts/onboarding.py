from calorie_bot.app.messages.ux_flow import MAIN_MENU_TITLE

WELCOME = (
    "Привет! Я помогу спокойно считать калории 🙂\n\n"
    "Просто отправь фото еды, голосовое или напиши текстом. "
    "Я соберу черновик, а ты сможешь проверить и поправить."
)

CONTINUE_PROMPT = "Похоже, мы уже начали настройку. Продолжим с того места? 🙂"
FOOD_AFTER_ONBOARDING_HINT = (
    "Сначала закончи короткую настройку — ответь на вопросы выше или нажми нужные кнопки. "
    "После этого сможешь отправлять еду текстом, фото или голосом."
)
COMPLETED_WELCOME = (
    "Ты уже настроил базовые параметры. Можно отправлять еду фото, голосом или текстом."
)
GOAL_PROMPT = "Какая цель сейчас ближе?"
CALORIE_STRATEGY_PROMPT = (
    "Хочешь указать дневную цель калорий сам или рассчитать примерный ориентир?"
)
MANUAL_CALORIES_PROMPT = "Напиши дневную цель калорий одним числом. Например: 1800"
SEX_PROMPT = "Для расчета нужен пол. Можно пропустить, если не хочешь отвечать."
AGE_PROMPT = "Сколько тебе лет? Напиши число или нажми «Пропустить»."
HEIGHT_PROMPT = "Какой рост в сантиметрах? Можно пропустить."
WEIGHT_PROMPT = "Какой сейчас вес в кг? Можно пропустить."
ACTIVITY_PROMPT = "Выбери примерный уровень активности."
INVALID_NUMBER = "Не смог разобрать число. Напиши только цифры, пожалуйста."
CALCULATION_NEEDS_DATA = (
    "Для аккуратного расчета нужны пол, возраст, рост, вес и активность. "
    "Пока сохраню цель без расчета, а позже можно будет вернуться в настройки."
)
CONFIRM_TARGETS = "Вот мягкий ориентир на день. Сохраняем?"
FINISHED = (
    "Готово! Настройки сохранены ✅\n\n"
    "Отправьте в этот чат фото еды, голосовое или текст — отдельно ничего включать не нужно."
)
RESTARTED = "Ок, начнем заново. Какая цель сейчас ближе?"
SKIPPED = "Без проблем, пропускаем. Это можно заполнить позже."


def render_targets(
    calories: int | None,
    protein_g: int | None = None,
    fat_g: int | None = None,
    carbs_g: int | None = None,
) -> str:
    """Render a short target confirmation text."""
    if calories is None:
        return "Сохраним цель без дневного лимита калорий. Его можно добавить позже."

    lines = [f"Калории: {calories} ккал"]
    if protein_g is not None and fat_g is not None and carbs_g is not None:
        lines.append(f"БЖУ: {protein_g}/{fat_g}/{carbs_g} г")
    return CONFIRM_TARGETS + "\n\n" + "\n".join(lines)


def render_main_menu() -> str:
    """Render onboarding completion main menu text."""
    return MAIN_MENU_TITLE
