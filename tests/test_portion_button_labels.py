"""Unit tests for portion quick-pick button label formatting."""

from calorie_bot.app.keyboards.meal import (
    PORTION_QUICK_PICK_CUSTOM_LABEL,
    format_portion_preset_button_label,
)


def test_label_no_duplicate_when_description_equals_value() -> None:
    assert format_portion_preset_button_label(10, "10 г") == "10 г"


def test_label_value_only_when_description_empty() -> None:
    assert format_portion_preset_button_label(20, "") == "20 г"
    assert format_portion_preset_button_label(20, "   ") == "20 г"


def test_label_combined_when_description_differs() -> None:
    assert format_portion_preset_button_label(150, "средняя порция") == "150 г · средняя порция"


def test_custom_quick_pick_label_constant() -> None:
    assert PORTION_QUICK_PICK_CUSTOM_LABEL == "✍️ Свой вариант"
