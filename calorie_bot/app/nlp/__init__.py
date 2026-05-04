"""NLP utilities for meal text (normalization, offline heuristics)."""

from calorie_bot.app.nlp.meal_text_preprocess import (
    normalize_meal_input_text,
    try_parse_plaintext_meal_line,
)

__all__ = ["normalize_meal_input_text", "try_parse_plaintext_meal_line"]
