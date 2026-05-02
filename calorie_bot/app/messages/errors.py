"""Centralized, safe user-facing error copy (no technical details)."""

from calorie_bot.app.exceptions import AppError, ErrorCode

# Primary texts keyed by ``ErrorCode`` value.
USER_ERROR_TEXT: dict[str, str] = {
    ErrorCode.RATE_LIMIT_AI.value: (
        "Слишком много запросов к анализу еды за короткое время. "
        "Подождите минуту или внесите приём вручную текстом с калориями."
    ),
    ErrorCode.FILE_TOO_LARGE.value: (
        "Файл слишком большой для бота. Отправьте фото поменьше или со сжатием."
    ),
    ErrorCode.UNSUPPORTED_IMAGE_FORMAT.value: (
        "Формат изображения не подходит. Используйте JPEG, PNG или WEBP."
    ),
    ErrorCode.TEXT_TOO_LONG.value: (
        "Текст слишком длинный. Сократите описание еды и попробуйте снова "
        "(или укажите блюда и калории вручную)."
    ),
    ErrorCode.AUDIO_TOO_LONG.value: (
        "Аудио слишком длинное. Запишите сообщение короче или опишите еду текстом."
    ),
    ErrorCode.OPENAI_UNAVAILABLE.value: (
        "Не получилось уверенно распознать.\n\n"
        "Попробуйте проще: «гречка 200 г и курица 150 г» или отправьте другое фото."
    ),
    ErrorCode.OPENAI_RATE_LIMIT.value: (
        "Сейчас высокая нагрузка на ИИ. Повторите через минуту или добавьте еду вручную."
    ),
    ErrorCode.TELEGRAM_NETWORK.value: (
        "Не удалось связаться с Telegram. Проверьте сеть и отправьте ещё раз."
    ),
    ErrorCode.TELEGRAM_BAD_REQUEST.value: (
        "Запрос не принят Telegram. Попробуйте другое вложение или чуть позже."
    ),
    ErrorCode.TELEGRAM_SERVER.value: (
        "На стороне Telegram сбой. Подождите немного и попробуйте снова."
    ),
    ErrorCode.DATABASE_ERROR.value: (
        "Не удалось сохранить данные. Повторите действие через минуту."
    ),
    ErrorCode.UNKNOWN.value: "Что-то пошло не так. Попробуйте ещё раз чуть позже.",
}

DEFAULT_USER_ERROR = USER_ERROR_TEXT[ErrorCode.UNKNOWN.value]


def text_for_code(code: str) -> str:
    """Return a friendly line for an ``ErrorCode`` value."""
    return USER_ERROR_TEXT.get(code, DEFAULT_USER_ERROR)


def text_for_app_error(exc: AppError) -> str:
    """Map a raised ``AppError`` to user-visible text."""
    return text_for_code(exc.code.value)
