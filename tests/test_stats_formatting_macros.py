"""Stats formatting: KBJU progress block."""

from calorie_bot.app.domain import StatsTodayView
from calorie_bot.app.stats.formatting import format_today_macro_dashboard, format_today_stats


def test_format_today_macro_dashboard_shows_bars() -> None:
    view = StatsTodayView(
        total_calories=800,
        calorie_target=2000,
        remaining_kcal=1200,
        progress_percent=40.0,
        meals_count=2,
        food_sections=[],
        total_protein_g=40.0,
        total_fat_g=30.0,
        total_carbs_g=60.0,
        protein_target_g=120,
        fat_target_g=70,
        carbs_target_g=200,
    )
    text = format_today_macro_dashboard(view)
    assert text
    assert "КБЖУ за день" in text
    assert "Белки" in text and "Жиры" in text and "Углеводы" in text


def test_format_today_stats_appends_macro_block() -> None:
    view = StatsTodayView(
        total_calories=500,
        calorie_target=2000,
        remaining_kcal=1500,
        progress_percent=25.0,
        meals_count=1,
        food_sections=["• 10:00 — 500 ккал"],
        total_protein_g=20.0,
        total_fat_g=15.0,
        total_carbs_g=50.0,
        protein_target_g=100,
        fat_target_g=60,
        carbs_target_g=150,
    )
    out = format_today_stats(view)
    assert "Съедено" in out
    assert "КБЖУ за день" in out
