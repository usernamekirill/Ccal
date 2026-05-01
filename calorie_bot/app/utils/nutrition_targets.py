from calorie_bot.app.domain import ActivityLevel, FitnessGoal, GoalInput, NutritionTargets, Sex

ACTIVITY_MULTIPLIERS: dict[ActivityLevel, float] = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.55,
    ActivityLevel.ACTIVE: 1.725,
    ActivityLevel.VERY_ACTIVE: 1.9,
}


def calculate_bmr(goal_input: GoalInput) -> int:
    """Estimate BMR using the Mifflin-St Jeor equation."""
    sex_modifier = 5 if goal_input.sex == Sex.MALE else -161
    bmr = (
        10 * goal_input.weight_kg
        + 6.25 * goal_input.height_cm
        - 5 * goal_input.age
        + sex_modifier
    )
    return round(bmr)


def calculate_tdee(bmr_calories: int, activity_level: ActivityLevel) -> int:
    """Estimate total daily energy expenditure from BMR and activity level."""
    return round(bmr_calories * ACTIVITY_MULTIPLIERS[activity_level])


def calculate_targets(goal_input: GoalInput) -> NutritionTargets:
    """Calculate conservative daily calorie and macro targets."""
    bmr_calories = calculate_bmr(goal_input)
    tdee_calories = calculate_tdee(bmr_calories, goal_input.activity_level)
    daily_calorie_target = _calorie_target_for_goal(tdee_calories, goal_input.goal)
    protein_g = _protein_target_for_goal(goal_input.weight_kg, goal_input.goal)
    fat_g = _fat_target(goal_input.weight_kg)
    carbs_g = _remaining_carbs(daily_calorie_target, protein_g, fat_g)

    return NutritionTargets(
        bmr_calories=bmr_calories,
        tdee_calories=tdee_calories,
        daily_calorie_target=daily_calorie_target,
        daily_protein_target_g=protein_g,
        daily_fat_target_g=fat_g,
        daily_carbs_target_g=carbs_g,
    )


def _calorie_target_for_goal(tdee_calories: int, goal: FitnessGoal) -> int:
    if goal == FitnessGoal.LOSE_WEIGHT:
        return round(tdee_calories * 0.85)
    if goal == FitnessGoal.GAIN_WEIGHT:
        return round(tdee_calories * 1.1)
    return tdee_calories


def _protein_target_for_goal(weight_kg: float, goal: FitnessGoal) -> int:
    if goal == FitnessGoal.LOSE_WEIGHT:
        grams_per_kg = 1.8
    elif goal == FitnessGoal.GAIN_WEIGHT:
        grams_per_kg = 1.7
    else:
        grams_per_kg = 1.5
    return round(weight_kg * grams_per_kg)


def _fat_target(weight_kg: float) -> int:
    return round(weight_kg * 0.8)


def _remaining_carbs(calories: int, protein_g: int, fat_g: int) -> int:
    calories_after_protein_and_fat = calories - protein_g * 4 - fat_g * 9
    return max(round(calories_after_protein_and_fat / 4), 0)
