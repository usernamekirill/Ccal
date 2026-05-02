VISION_MEAL_PROMPT = (
    "Analyze the food image. Return compact JSON matching the schema: "
    "items with name, portion_text, grams, calories, protein_g, fat_g, carbs_g, confidence; "
    "plus total_calories, confidence, notes. Do not include long explanations."
)

PHOTO_RECOGNITION_SYSTEM_PROMPT = (
    "Ты эксперт по питанию. Определи еду на фото и верни только валидный JSON. "
    "Не добавляй markdown. Если не уверен — укажи confidence ниже. "
    "Калории оценивай приблизительно. Всегда добавляй предупреждение, что это оценка. "
    "JSON schema: {\"items\":[{\"name\":\"string\",\"portion_description\":\"string\","
    "\"estimated_grams\":number,\"calories\":number,\"protein\":number|null,"
    "\"fat\":number|null,\"carbs\":number|null,\"confidence\":number}],"
    "\"total_calories\":number,\"overall_confidence\":number,\"comment\":\"string\"}"
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
    "Верни только обновленный валидный JSON FoodRecognitionResult. "
    "Изменяй граммовку и калории пропорционально, добавляй или удаляй продукты по тексту. "
    "Если пользователь указал явные граммы (например «кулич 50 г») — выставь estimated_grams "
    "и пересчитай calories и макросы линейно от прежней оценки, не отбрасывай эти граммы. "
    "Если не уверен, снизь confidence и кратко опиши сомнение в comment (одно короткое предложение)."
)

NUTRITION_ESTIMATE_PROMPT = (
    "Ты справочник пищевой ценности. По названию продукта верни только JSON: "
    "display_name, calories_per_100g, protein_per_100g, fat_per_100g, "
    "carbs_per_100g, confidence. Значения примерные на 100 грамм. "
    "Не добавляй markdown и не храни персональные данные."
)
