VISION_MEAL_PROMPT = (
    "Analyze the food image. Return compact JSON matching the schema: "
    "items with name, portion_text, grams, calories, protein_g, fat_g, carbs_g, confidence; "
    "plus total_calories, confidence, notes. Do not include long explanations."
)

PHOTO_RECOGNITION_SYSTEM_PROMPT = (
    "Ты эксперт по питанию. По фото определи продукты и верни только JSON без markdown.\n"
    "КРИТИЧНО: не считай итоговые калории и не указывай total_calories. "
    "Для каждого продукта дай только КБЖУ на 100 г (ккал и граммы белков/жиров/углеводов) "
    "и оценку порции в граммах или диапазоне.\n"
    "Если массу угадать нельзя — ставь estimated_grams: null и не заполняй grams_min/grams_max "
    "(система подставит типичный диапазон).\n"
    "Если видишь диапазон порции — заполни grams_min и grams_max.\n"
    "Если уверен в одной массе — только estimated_grams.\n"
    "Заполни food_confidence и portion_confidence от 0 до 1 (portion ниже, если размер неясен).\n"
    "Схема JSON:\n"
    '{"items":['
    '{"name":"string","portion_description":"string|null",'
    '"estimated_grams":number|null,"grams_min":number|null,"grams_max":number|null,'
    '"calories_per_100g":number,"protein_per_100g":number|null,"fat_per_100g":number|null,'
    '"carbs_per_100g":number|null,"food_confidence":number,"portion_confidence":number}'
    '],'
    '"meal_type":"breakfast"|"lunch"|"dinner"|"snack"|null,'
    '"overall_confidence":number|null,"comment":"string"}'
)

CORRECTION_PROMPT = (
    "Apply the user's correction to the compact meal draft. Return only updated JSON "
    "matching the meal analysis schema."
)

FOOD_TEXT_PARSER_PROMPT = (
    "Ты NLP-сервис для дневника питания. Извлеки из текста еду, порции и примерные "
    "калории. Верни только валидный JSON по схеме FoodRecognitionResult: "
    "items[].name, portion_description, estimated_grams, calories, protein, fat, carbs, "
    "confidence, total_calories, overall_confidence, comment, meal_type, "
    "needs_clarification, clarification_question. meal_type должен быть одним из: "
    "breakfast, lunch, dinner, snack или null. "
    "КРИТИЧНО: если пользователь явно указал массу в граммах (например «50 г», «100 грамм»), "
    "поле estimated_grams для соответствующего продукта ДОЛЖНО равняться этому числу, "
    "а calories и КБЖУ пересчитай пропорционально этой массе от базы на 100 г или от твоей "
    "оценки целой порции — не подменяй явные граммы пользователя «одной штукой» или средней порцией. "
    "Если калории в тексте не указаны — оцени сам от выбранной массы. "
    "Если данных мало и нельзя сделать полезную оценку — задай ровно один короткий "
    "уточняющий вопрос в clarification_question и поставь needs_clarification=true. "
    "Не добавляй markdown."
)

FOOD_CORRECTION_PROMPT = (
    "Ты сервис корректировки питания. Получишь текущий JSON результата и текст правки. "
    "Верни только обновлённый JSON того же вида FoodRecognitionResult "
    "(items с portion_description, estimated_grams или grams_min/max, "
    "calories_per_100g и макросы на 100 г, food_confidence, portion_confidence, grams_source; "
    "итоговые калории по строкам могут быть null если используешь диапазон). "
    "Если пользователь указал явные граммы — выставь grams_source=\"user\", "
    "estimated_grams и пересчитай calories и макросы строки от calories_per_100g. "
    "Не подменяй пользовательские граммы средней порцией модели. "
    "Если не уверен, снизь portion_confidence и кратко опиши в comment."
)

NUTRITION_ESTIMATE_PROMPT = (
    "Ты справочник пищевой ценности. По названию продукта верни только JSON: "
    "display_name, calories_per_100g, protein_per_100g, fat_per_100g, "
    "carbs_per_100g, confidence. Значения примерные на 100 грамм. "
    "Не добавляй markdown и не храни персональные данные."
)
