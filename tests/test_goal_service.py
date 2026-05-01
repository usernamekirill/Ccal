import pytest

from calorie_bot.app.domain import ActivityLevel, FitnessGoal, GoalInput, Sex
from calorie_bot.app.services.goal_service import GoalService


def test_calculates_weight_loss_targets_with_conservative_deficit() -> None:
    """Weight loss target should stay below estimated TDEE."""
    service = GoalService()
    goal_input = GoalInput(
        sex=Sex.MALE,
        age=30,
        height_cm=180,
        weight_kg=90,
        activity_level=ActivityLevel.MODERATE,
        goal=FitnessGoal.LOSE_WEIGHT,
    )

    targets = service.calculate_daily_targets(goal_input)

    assert targets.bmr_calories == 1880
    assert targets.tdee_calories == 2914
    assert targets.daily_calorie_target == 2477
    assert targets.daily_protein_target_g == 162
    assert targets.daily_fat_target_g == 72
    assert targets.daily_carbs_target_g == 295


def test_calculates_weight_gain_targets_with_moderate_surplus() -> None:
    """Weight gain target should stay above estimated TDEE."""
    service = GoalService()
    goal_input = GoalInput(
        sex=Sex.FEMALE,
        age=28,
        height_cm=165,
        weight_kg=60,
        activity_level=ActivityLevel.LIGHT,
        goal=FitnessGoal.GAIN_WEIGHT,
    )

    targets = service.calculate_daily_targets(goal_input)

    assert targets.bmr_calories == 1330
    assert targets.tdee_calories == 1829
    assert targets.daily_calorie_target == 2012
    assert targets.daily_protein_target_g == 102
    assert targets.daily_fat_target_g == 48
    assert targets.daily_carbs_target_g == 293


def test_rejects_out_of_range_age() -> None:
    """MVP goal calculations should reject unsupported ages."""
    service = GoalService()
    goal_input = GoalInput(
        sex=Sex.MALE,
        age=12,
        height_cm=170,
        weight_kg=70,
        activity_level=ActivityLevel.SEDENTARY,
        goal=FitnessGoal.MAINTAIN_WEIGHT,
    )

    with pytest.raises(ValueError, match="Age must be between"):
        service.calculate_daily_targets(goal_input)
