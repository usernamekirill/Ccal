from calorie_bot.app.ai.schemas import MealAnalysis
from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource
from calorie_bot.app.services.calorie_service import meal_draft_calorie_totals


class NutritionParser:
    """Convert AI schemas into domain meal drafts."""

    def to_meal_draft(self, analysis: MealAnalysis, source: MealSource) -> MealDraft:
        """Convert a validated AI meal analysis into a domain draft."""
        items = [
            MealItemDraft(
                name=item.name,
                portion_text=item.portion_text,
                grams=item.grams,
                calories=item.calories,
                protein_g=item.protein_g,
                fat_g=item.fat_g,
                carbs_g=item.carbs_g,
                confidence=item.confidence,
            )
            for item in analysis.items
        ]
        total_calories, t_min, t_max = meal_draft_calorie_totals(items)
        return MealDraft(
            items=items,
            total_calories=total_calories,
            total_calories_min=t_min,
            total_calories_max=t_max,
            has_estimated_items=any(i.is_estimated for i in items),
            source=source,
            confidence=analysis.confidence,
            notes=analysis.notes,
        )
