from calorie_bot.app.ai.schemas import MealAnalysis
from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource


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
        return MealDraft(
            items=items,
            total_calories=analysis.total_calories,
            source=source,
            confidence=analysis.confidence,
            notes=analysis.notes,
        )
