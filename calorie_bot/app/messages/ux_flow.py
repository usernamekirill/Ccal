"""User-facing copy for post-action and navigation loops."""

MAIN_MENU_TITLE = "Главное меню"

READY_TO_LOG_BLURB = (
    "Я помогу посчитать калории 👌\n\n"
    "Просто отправьте:\n"
    "📸 фото еды\n"
    "🎙 голосовое\n"
    "✍️ или напишите текстом\n\n"
    "Например:\n"
    "«рис 150 г и курица 120 г»"
)

HOW_TO_ADD_EXPLANATION = (
    "Чтобы добавить еду, просто отправьте фото, голосовое или текст в этот чат — "
    "я сам пойму формат. Кнопки для выбора способа не нужны 🙂"
)

POST_SAVE_CONFIRMED_HEAD = "✅ Добавлено"

POST_SAVE_WHAT_NEXT = "Можно отправить следующую еду."

MEAL_CANCEL_FOLLOWUP = (
    "Ок, не сохраняю.\n\n"
    "Можно отправить новую еду:\n"
    "📸 фото • 🎙 голосовое • ✍️ текст"
)

# Legacy names kept for navigation.py until fully migrated
ADD_FOOD_GATEWAY_TEXT = HOW_TO_ADD_EXPLANATION
ADD_VOICE_GATEWAY_TEXT = HOW_TO_ADD_EXPLANATION
ADD_TEXT_GATEWAY_TEXT = HOW_TO_ADD_EXPLANATION
