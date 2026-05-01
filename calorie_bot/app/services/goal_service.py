from calorie_bot.app.domain import GoalInput, NutritionTargets
from calorie_bot.app.utils.nutrition_targets import calculate_targets


class GoalService:
    """Calculate and validate user nutrition goals."""

    def calculate_daily_targets(self, goal_input: GoalInput) -> NutritionTargets:
        """Return conservative calorie and macro targets for a user goal."""
        self._validate_goal_input(goal_input)
        return calculate_targets(goal_input)

    def _validate_goal_input(self, goal_input: GoalInput) -> None:
        if goal_input.age < 16 or goal_input.age > 100:
            raise ValueError("Age must be between 16 and 100 for MVP calculations.")
        if goal_input.height_cm < 120 or goal_input.height_cm > 230:
            raise ValueError("Height must be between 120 and 230 cm.")
        if goal_input.weight_kg < 35 or goal_input.weight_kg > 250:
            raise ValueError("Weight must be between 35 and 250 kg.")
