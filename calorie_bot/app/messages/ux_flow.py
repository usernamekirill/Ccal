"""User-facing copy for post-action and navigation loops."""

MAIN_MENU_TITLE = "Главное меню"

READY_TO_LOG_BLURB = (
    "Я готов записать еду 👌\n\n"
    "Можно просто отправить:\n"
    "📸 фото тарелки\n"
    "🎙 голосовое: «творог 200 г и кофе»\n"
    "✍️ текст: «рис 150 г, курица 120 г»\n\n"
    "А я сам разберу и покажу результат перед сохранением."
)

HOW_TO_ADD_EXPLANATION = (
    "Чтобы добавить еду, просто отправьте фото, голосовое или текст в этот чат — "
    "я сам пойму формат. Кнопки для выбора способа не нужны 🙂"
)

POST_SAVE_CONFIRMED_HEAD = "✅ Добавил"

POST_SAVE_WHAT_NEXT = (
    "Можно сразу отправить следующую еду фото, голосом или текстом — как удобнее."
)

MEAL_CANCEL_FOLLOWUP = (
    "Ок, не сохраняю.\n\n"
    "Можно отправить новую еду:\n"
    "📸 фото • 🎙 голосовое • ✍️ текст"
)

# Legacy names kept for navigation.py until fully migrated
ADD_FOOD_GATEWAY_TEXT = HOW_TO_ADD_EXPLANATION
ADD_VOICE_GATEWAY_TEXT = HOW_TO_ADD_EXPLANATION
ADD_TEXT_GATEWAY_TEXT = HOW_TO_ADD_EXPLANATION
