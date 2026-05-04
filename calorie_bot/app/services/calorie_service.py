import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.schemas import (
    FoodItemRecognition,
    FoodRecognitionResult,
    VisionPhotoAnalysisItem,
    VisionPhotoAnalysisResult,
)
from calorie_bot.app.domain import (
    GramsSource,
    MealDraft,
    MealItemDraft,
    MealSource,
    MealType,
    PortionUnitType,
)
from calorie_bot.app.repositories.food_cache_repository import FoodCacheRepository
from calorie_bot.app.services.nutrition_normalizer import (
    atwater_calories_from_line_macros,
    should_align_line_calories_with_macros,
)
from calorie_bot.app.services import portion_estimator
from calorie_bot.app.services.nutrition_calculator import calories_from_per_100g, has_quantified_portion_mass
from calorie_bot.app.utils import ux_formatter

if TYPE_CHECKING:
    from calorie_bot.app.config import Settings

LOW_CONFIDENCE_THRESHOLD = 0.65
MAX_ITEM_CALORIES = 5000
MAX_ITEM_GRAMS = 5000

# Short product names that usually need weight or type (rule-based clarification).
_AMBIGUOUS_FOOD_KEYS = frozenset(
    {
        "сыр",
        "колбаса",
        "мясо",
        "рыба",
        "салат",
        "суп",
        "каша",
        "творог",
        "пармезан",
        "макароны",
    }
)
_MAX_CLARIFICATION_CHARS = 3500

# Higher wins when deciding whether to replace grams (user/correction beats AI).
_GRAMS_SOURCE_RANK: dict[str, int] = {
    GramsSource.UNKNOWN.value: 1,
    GramsSource.DEFAULT_PORTION.value: 2,
    GramsSource.AI_PHOTO.value: 3,
    GramsSource.TEXT_CORRECTION.value: 5,
    GramsSource.VOICE_CORRECTION.value: 5,
    GramsSource.USER.value: 5,
    GramsSource.USER_QUANTITY.value: 5,
}


@dataclass(frozen=True)
class NutritionEstimate:
    """Nutrition values for a food per 100 grams."""

    display_name: str
    calories_per_100g: float
    protein_per_100g: float | None
    fat_per_100g: float | None
    carbs_per_100g: float | None
    confidence: float
    is_estimated: bool = True


class FoodNutritionEstimator(Protocol):
    """Protocol for AI-backed nutrition estimation."""

    async def estimate_food(self, food_name: str) -> NutritionEstimate:
        """Return nutrition estimate for a normalized food name."""


def draft_item_effective_calories(item: MealItemDraft) -> int:
    """Single-number calories for rollups when a line uses a range."""
    if item.calories is not None:
        return item.calories
    if item.calories_min is not None and item.calories_max is not None:
        return (item.calories_min + item.calories_max) // 2
    return 0


def meal_draft_calorie_totals(items: list[MealItemDraft]) -> tuple[int, int | None, int | None]:
    """Return (midpoint total, optional sum of mins, optional sum of maxes) for a draft."""
    mid = 0
    lo = 0
    hi = 0
    any_range = False
    for it in items:
        if it.calories is not None:
            mid += it.calories
            lo += it.calories
            hi += it.calories
        elif it.calories_min is not None and it.calories_max is not None:
            any_range = True
            mid_d = (it.calories_min + it.calories_max) // 2
            mid += mid_d
            lo += it.calories_min
            hi += it.calories_max
    return mid, (lo if any_range else None), (hi if any_range else None)


def recognition_item_mid_calories(item: FoodItemRecognition) -> int:
    """Midpoint calories for one recognition line."""
    if item.calories is not None:
        return item.calories
    if item.calories_min is not None and item.calories_max is not None:
        return (item.calories_min + item.calories_max) // 2
    return 0


class CalorieService:
    """Format, recalculate, and edit food recognition results."""

    def from_vision_photo_analysis(self, raw: VisionPhotoAnalysisResult) -> FoodRecognitionResult:
        """Build a normalized recognition result from vision JSON (per-100g only, no AI calories)."""
        items = [self._food_item_from_vision_row(vi) for vi in raw.items]
        comment = (raw.comment or "").strip() or "Оценка по фото — уточните порцию, если нужно точнее."
        ov = raw.overall_confidence
        if ov is None and items:
            ov = min(it.confidence for it in items)
        elif ov is None:
            ov = 0.6
        base = FoodRecognitionResult(
            items=items,
            total_calories=0,
            overall_confidence=ov,
            comment=comment,
            meal_type=raw.meal_type,
        )
        return self.validate_food_result(base)

    def _food_item_from_vision_row(self, vi: VisionPhotoAnalysisItem) -> FoodItemRecognition:
        """Map one vision row to FoodItemRecognition with honest ranges when needed."""
        name = normalize_food_name(vi.name)
        portion_desc = (vi.portion_description or "").strip() or "порция"
        food_c = vi.food_confidence if vi.food_confidence is not None else 0.72
        portion_c = vi.portion_confidence if vi.portion_confidence is not None else 0.55

        per_c = vi.calories_per_100g
        if per_c is None:
            per_c = 200.0
            food_c = min(food_c, 0.5)

        g_point = vi.estimated_grams
        g_lo = vi.grams_min
        g_hi = vi.grams_max
        src = GramsSource.AI_PHOTO.value

        if g_point is not None:
            return self._finalize_single_gram_item(
                name=name,
                grams=float(g_point),
                per_c=float(per_c),
                vi=vi,
                portion_desc=portion_desc,
                grams_source=src,
                food_c=food_c,
                portion_c=portion_c,
            )

        if g_lo is not None and g_hi is not None:
            return self._finalize_range_item(
                name=name,
                g_lo=float(g_lo),
                g_hi=float(g_hi),
                per_c=float(per_c),
                vi=vi,
                portion_desc=portion_desc,
                grams_source=src,
                food_c=food_c,
                portion_c=portion_c,
            )

        rng = portion_estimator.estimate_default_portion_grams(name)
        portion_c = min(portion_c, 0.55)
        return self._finalize_range_item(
            name=name,
            g_lo=float(rng.grams_min),
            g_hi=float(rng.grams_max),
            per_c=float(per_c),
            vi=vi,
            portion_desc=portion_desc,
            grams_source=GramsSource.DEFAULT_PORTION.value,
            food_c=food_c,
            portion_c=portion_c,
        )

    def _finalize_single_gram_item(
        self,
        *,
        name: str,
        grams: float,
        per_c: float,
        vi: VisionPhotoAnalysisItem,
        portion_desc: str,
        grams_source: str,
        food_c: float,
        portion_c: float,
    ) -> FoodItemRecognition:
        """Single mass; KBJU from per 100g × grams."""
        self.validate_grams(grams)
        cal = self.calculate_item_calories(per_c, grams)
        p = _from_per_100g(vi.protein_per_100g, grams)
        f = _from_per_100g(vi.fat_per_100g, grams)
        c = _from_per_100g(vi.carbs_per_100g, grams)
        est = grams_source not in (
            GramsSource.USER.value,
            GramsSource.TEXT_CORRECTION.value,
            GramsSource.VOICE_CORRECTION.value,
        )
        item = FoodItemRecognition(
            name=name,
            portion_description=portion_desc,
            estimated_grams=grams,
            grams_min=None,
            grams_max=None,
            calories=cal,
            calories_min=None,
            calories_max=None,
            calories_per_100g=per_c,
            protein_per_100g=vi.protein_per_100g,
            fat_per_100g=vi.fat_per_100g,
            carbs_per_100g=vi.carbs_per_100g,
            protein=p,
            fat=f,
            carbs=c,
            protein_min=None,
            protein_max=None,
            fat_min=None,
            fat_max=None,
            carbs_min=None,
            carbs_max=None,
            food_confidence=food_c,
            portion_confidence=portion_c,
            grams_source=grams_source,
            needs_portion_clarification=False,
            is_estimated=est,
        )
        return self._apply_portion_clarification_rules(item)

    def _finalize_range_item(
        self,
        *,
        name: str,
        g_lo: float,
        g_hi: float,
        per_c: float,
        vi: VisionPhotoAnalysisItem,
        portion_desc: str,
        grams_source: str,
        food_c: float,
        portion_c: float,
    ) -> FoodItemRecognition:
        """Mass range; calories + macros ranges from per 100g."""
        self.validate_grams(g_lo)
        self.validate_grams(g_hi)
        if g_hi < g_lo:
            g_lo, g_hi = g_hi, g_lo
        c_lo = self.calculate_item_calories(per_c, g_lo)
        c_hi = self.calculate_item_calories(per_c, g_hi)
        item = FoodItemRecognition(
            name=name,
            portion_description=portion_desc,
            estimated_grams=None,
            grams_min=g_lo,
            grams_max=g_hi,
            calories=None,
            calories_min=c_lo,
            calories_max=c_hi,
            calories_per_100g=per_c,
            protein_per_100g=vi.protein_per_100g,
            fat_per_100g=vi.fat_per_100g,
            carbs_per_100g=vi.carbs_per_100g,
            protein=None,
            fat=None,
            carbs=None,
            protein_min=_from_per_100g(vi.protein_per_100g, g_lo),
            protein_max=_from_per_100g(vi.protein_per_100g, g_hi),
            fat_min=_from_per_100g(vi.fat_per_100g, g_lo),
            fat_max=_from_per_100g(vi.fat_per_100g, g_hi),
            carbs_min=_from_per_100g(vi.carbs_per_100g, g_lo),
            carbs_max=_from_per_100g(vi.carbs_per_100g, g_hi),
            food_confidence=food_c,
            portion_confidence=portion_c,
            grams_source=grams_source,
            needs_portion_clarification=False,
            is_estimated=True,
        )
        return self._apply_portion_clarification_rules(item)

    def _apply_portion_clarification_rules(self, item: FoodItemRecognition) -> FoodItemRecognition:
        """Set needs_portion_clarification: low portion confidence or calorie-dense foods."""
        if item.grams_source in (
            GramsSource.USER.value,
            GramsSource.USER_QUANTITY.value,
            GramsSource.TEXT_CORRECTION.value,
            GramsSource.VOICE_CORRECTION.value,
        ):
            return item.model_copy(update={"needs_portion_clarification": False})
        dense = portion_estimator.is_calorie_dense_food(item.name)
        weak_portion = item.portion_confidence < 0.6
        from_default_or_unknown = item.grams_source in (
            GramsSource.DEFAULT_PORTION.value,
            GramsSource.UNKNOWN.value,
        )
        need = weak_portion or (dense and (from_default_or_unknown or item.portion_confidence < 0.75))
        return item.model_copy(update={"needs_portion_clarification": need})

    def merge_ai_grams_if_weaker_source(
        self,
        current: FoodItemRecognition,
        ai_grams: float | None,
        ai_grams_min: float | None,
        ai_grams_max: float | None,
    ) -> FoodItemRecognition:
        """Replace grams only if current source is weaker than AI photo."""
        rank_curr = _GRAMS_SOURCE_RANK.get(current.grams_source, 0)
        if rank_curr >= _GRAMS_SOURCE_RANK[GramsSource.AI_PHOTO.value]:
            return current
        if ai_grams is not None:
            return self._finalize_single_gram_item(
                name=current.name,
                grams=float(ai_grams),
                per_c=float(current.calories_per_100g or 200),
                vi=VisionPhotoAnalysisItem(
                    name=current.name,
                    calories_per_100g=current.calories_per_100g,
                    protein_per_100g=current.protein_per_100g,
                    fat_per_100g=current.fat_per_100g,
                    carbs_per_100g=current.carbs_per_100g,
                ),
                portion_desc=current.portion_description,
                grams_source=GramsSource.AI_PHOTO.value,
                food_c=current.food_confidence,
                portion_c=current.portion_confidence,
            )
        if ai_grams_min is not None and ai_grams_max is not None:
            return self._finalize_range_item(
                name=current.name,
                g_lo=float(ai_grams_min),
                g_hi=float(ai_grams_max),
                per_c=float(current.calories_per_100g or 200),
                vi=VisionPhotoAnalysisItem(
                    name=current.name,
                    calories_per_100g=current.calories_per_100g,
                    protein_per_100g=current.protein_per_100g,
                    fat_per_100g=current.fat_per_100g,
                    carbs_per_100g=current.carbs_per_100g,
                ),
                portion_desc=current.portion_description,
                grams_source=GramsSource.AI_PHOTO.value,
                food_c=current.food_confidence,
                portion_c=current.portion_confidence,
            )
        return current

    def to_meal_draft(
        self,
        result: FoodRecognitionResult,
        source: MealSource = MealSource.PHOTO,
    ) -> MealDraft:
        """Convert food recognition result into a confirmable meal draft."""
        items: list[MealItemDraft] = []
        for item in result.items:
            items.append(
                MealItemDraft(
                    name=item.name,
                    portion_text=item.portion_description,
                    grams=item.estimated_grams,
                    grams_min=item.grams_min,
                    grams_max=item.grams_max,
                    grams_source=_grams_source_from_str(item.grams_source),
                    calories=item.calories,
                    calories_min=item.calories_min,
                    calories_max=item.calories_max,
                    calories_per_100g=item.calories_per_100g,
                    protein_per_100g=item.protein_per_100g,
                    fat_per_100g=item.fat_per_100g,
                    carbs_per_100g=item.carbs_per_100g,
                    protein_g=item.protein,
                    fat_g=item.fat,
                    carbs_g=item.carbs,
                    protein_g_min=item.protein_min,
                    protein_g_max=item.protein_max,
                    fat_g_min=item.fat_min,
                    fat_g_max=item.fat_max,
                    carbs_g_min=item.carbs_min,
                    carbs_g_max=item.carbs_max,
                    food_confidence=item.food_confidence,
                    portion_confidence=item.portion_confidence,
                    needs_portion_clarification=item.needs_portion_clarification,
                    is_estimated=item.is_estimated,
                    confidence=item.confidence,
                    quantity=item.quantity,
                    unit_type=item.unit_type,
                    unit_weight_grams=item.unit_weight_grams,
                    size_modifier=item.size_modifier,
                )
            )
        normalized_items = [self.validate_item(item) for item in items]
        total, t_min, t_max = meal_draft_calorie_totals(normalized_items)
        has_est = any(i.is_estimated for i in normalized_items)
        return MealDraft(
            items=normalized_items,
            total_calories=total,
            total_calories_min=t_min,
            total_calories_max=t_max,
            has_estimated_items=has_est,
            source=source,
            meal_type=MealType(result.meal_type) if result.meal_type else None,
            confidence=result.overall_confidence,
            notes=result.comment,
        )

    def draft_to_result(self, draft: MealDraft) -> FoodRecognitionResult:
        """Convert a stored meal draft into a reviewable recognition result."""
        items = [
            FoodItemRecognition(
                name=item.name,
                portion_description=item.portion_text or _portion_text(item.grams),
                estimated_grams=item.grams,
                grams_min=item.grams_min,
                grams_max=item.grams_max,
                calories=item.calories,
                calories_min=item.calories_min,
                calories_max=item.calories_max,
                calories_per_100g=item.calories_per_100g,
                protein_per_100g=item.protein_per_100g,
                fat_per_100g=item.fat_per_100g,
                carbs_per_100g=item.carbs_per_100g,
                protein=item.protein_g,
                fat=item.fat_g,
                carbs=item.carbs_g,
                protein_min=item.protein_g_min,
                protein_max=item.protein_g_max,
                fat_min=item.fat_g_min,
                fat_max=item.fat_g_max,
                carbs_min=item.carbs_g_min,
                carbs_max=item.carbs_g_max,
                food_confidence=item.food_confidence or 1,
                portion_confidence=item.portion_confidence or 1,
                grams_source=(item.grams_source or GramsSource.UNKNOWN).value,
                needs_portion_clarification=item.needs_portion_clarification,
                is_estimated=item.is_estimated,
                confidence=item.confidence or 1,
                quantity=item.quantity,
                unit_type=item.unit_type,
                unit_weight_grams=item.unit_weight_grams,
                size_modifier=item.size_modifier,
            )
            for item in draft.items
        ]
        return self.validate_food_result(
            FoodRecognitionResult(
                items=items,
                total_calories=draft.total_calories,
                total_calories_min=draft.total_calories_min,
                total_calories_max=draft.total_calories_max,
                overall_confidence=draft.confidence or 1,
                comment=draft.notes or "Сохраненный прием пищи",
                meal_type=draft.meal_type.value if draft.meal_type else None,
                has_estimated_items=draft.has_estimated_items,
            )
        )

    def result_to_dict(self, result: FoodRecognitionResult) -> dict:
        """Serialize a recognition result for FSM storage."""
        return result.model_dump(mode="json")

    def result_from_dict(self, data: dict) -> FoodRecognitionResult:
        """Deserialize a recognition result from FSM storage."""
        merged = self._backfill_legacy_result(FoodRecognitionResult.model_validate(data))
        return self.validate_food_result(merged)

    def _backfill_legacy_result(self, result: FoodRecognitionResult) -> FoodRecognitionResult:
        """Derive per-100g and ranges from legacy totals when needed."""
        new_items: list[FoodItemRecognition] = []
        for it in result.items:
            new_items.append(self._backfill_legacy_item(it))
        return result.model_copy(update={"items": new_items})

    def _backfill_legacy_item(self, item: FoodItemRecognition) -> FoodItemRecognition:
        """Infer calories_per_100g from legacy calories/grams if missing; then derive line kcal/macros."""
        item_work = item
        if item_work.calories_per_100g is None:
            grams = item_work.estimated_grams
            if grams and item_work.calories is not None and float(grams) > 0:
                per = float(item_work.calories) * 100.0 / float(grams)
                item_work = item_work.model_copy(
                    update={
                        "calories_per_100g": round(per, 2),
                        "grams_source": item_work.grams_source
                        if item_work.grams_source != GramsSource.UNKNOWN.value
                        else GramsSource.AI_PHOTO.value,
                    }
                )
            elif item_work.calories is not None and item_work.calories_min is None:
                item_work = item_work.model_copy(update={"calories_per_100g": 200.0})
        return self._recompute_point_mass_totals_from_per_100g(item_work)

    def _recompute_point_mass_totals_from_per_100g(self, item: FoodItemRecognition) -> FoodItemRecognition:
        """Derive line calories and macros from ``calories_per_100g`` × ``estimated_grams`` when absent."""
        if item.calories_per_100g is None:
            return item
        g = item.estimated_grams
        if g is None or float(g) <= 0:
            return item
        if item.grams_min is not None or item.grams_max is not None:
            return item
        g_float = float(g)
        per = float(item.calories_per_100g)
        updates: dict[str, object] = {}
        if item.calories is None:
            updates["calories"] = self.calculate_item_calories(per, g_float)
        if item.protein is None and item.protein_per_100g is not None:
            updates["protein"] = _from_per_100g(item.protein_per_100g, g_float)
        if item.fat is None and item.fat_per_100g is not None:
            updates["fat"] = _from_per_100g(item.fat_per_100g, g_float)
        if item.carbs is None and item.carbs_per_100g is not None:
            updates["carbs"] = _from_per_100g(item.carbs_per_100g, g_float)
        if not updates:
            return item
        return item.model_copy(update=updates)

    def _reconcile_point_mass_atwater(self, item: FoodItemRecognition) -> FoodItemRecognition:
        """When Б, Ж, У are known for a point mass, align line kcal with Atwater (4/9/4) if density disagrees."""
        if item.grams_min is not None or item.grams_max is not None:
            return item
        g = item.estimated_grams
        if g is None or float(g) <= 0:
            return item
        if not should_align_line_calories_with_macros(
            item.protein,
            item.fat,
            item.carbs,
            item.calories,
        ):
            return item
        atw = atwater_calories_from_line_macros(item.protein, item.fat, item.carbs)
        if atw is None:
            return item
        g_float = float(g)
        new_per = round(atw * 100.0 / g_float, 2) if g_float > 0 else item.calories_per_100g
        return item.model_copy(update={"calories": atw, "calories_per_100g": new_per})

    async def hydrate_items_missing_nutrition_density(
        self,
        result: FoodRecognitionResult,
        session: AsyncSession,
        settings: "Settings",
    ) -> FoodRecognitionResult:
        """Fill missing ``calories_per_100g`` using food cache + AI estimate, then recompute line totals."""
        from calorie_bot.app.ai.nutrition_estimator_service import AINutritionEstimatorService

        cache = FoodCacheRepository(session)
        estimator = AINutritionEstimatorService(settings)
        new_items: list[FoodItemRecognition] = []
        for item in result.items:
            it = self._backfill_legacy_item(item)
            g = it.estimated_grams
            need_density = (
                it.calories_per_100g is None
                and g is not None
                and float(g) > 0
                and it.grams_min is None
                and it.grams_max is None
                and has_quantified_portion_mass(it.estimated_grams, it.grams_min, it.grams_max)
            )
            if need_density:
                rich_name = normalize_food_name(item.name)
                est_line = await self.get_or_estimate_food(rich_name, float(g), cache, estimator)
                preserve_source = it.grams_source in (
                    GramsSource.USER.value,
                    GramsSource.TEXT_CORRECTION.value,
                    GramsSource.VOICE_CORRECTION.value,
                    GramsSource.USER_QUANTITY.value,
                )
                it = est_line.model_copy(
                    update={
                        "name": rich_name,
                        "portion_description": item.portion_description or est_line.portion_description,
                        "grams_source": it.grams_source if preserve_source else est_line.grams_source,
                        "quantity": item.quantity,
                        "unit_type": item.unit_type,
                        "unit_weight_grams": item.unit_weight_grams,
                        "size_modifier": item.size_modifier,
                    }
                )
            it = self._recompute_point_mass_totals_from_per_100g(it)
            new_items.append(it)
        out = result.model_copy(update={"items": new_items})
        return self.validate_food_result(out)

    def separate_uncounted_quantified_items(self, result: FoodRecognitionResult) -> FoodRecognitionResult:
        """Remove lines that have a known mass but no countable calories; ask the user to clarify.

        Avoids showing products as logged when they are not included in meal energy totals.
        """
        dropped_names: list[str] = []
        kept: list[FoodItemRecognition] = []
        for item in result.items:
            if not has_quantified_portion_mass(item.estimated_grams, item.grams_min, item.grams_max):
                kept.append(item)
                continue
            if recognition_item_mid_calories(item) > 0:
                kept.append(item)
                continue
            dropped_names.append(item.name)

        if not dropped_names:
            return result

        msg = (
            "Не смог точно посчитать: "
            + ", ".join(dropped_names)
            + ". Укажите вес, калории или уточните описание."
        )
        prev_q = (result.clarification_question or "").strip()
        new_q = f"{prev_q}\n{msg}".strip() if prev_q else msg
        out = result.model_copy(
            update={
                "items": kept,
                "needs_clarification": True,
                "clarification_question": new_q,
            }
        )
        return out

    async def enrich_after_text_processing(
        self,
        result: FoodRecognitionResult,
        user_text: str | None,
        session: AsyncSession,
        settings: "Settings",
    ) -> FoodRecognitionResult:
        """Run food-cache + AI density fill for text flows, then drop uncounted mass-only lines.

        Call after ``apply_user_text_gram_priority`` (and quantity rules). ``user_text`` is reserved
        for future heuristics; hydration uses each item's name and grams.
        """
        _ = user_text
        merged = await self.hydrate_items_missing_nutrition_density(result, session, settings)
        merged = self.validate_food_result(merged)
        merged = self.separate_uncounted_quantified_items(merged)
        return self.validate_food_result(merged)

    def apply_user_text_gram_priority(
        self,
        user_text: str | None,
        result: FoodRecognitionResult,
        *,
        grams_source: str | None = None,
    ) -> FoodRecognitionResult:
        """Honor explicit ``X г`` in user text over model portion grams (linear rescale)."""
        from calorie_bot.app.services.food_parser_service import apply_user_gram_priority

        return apply_user_gram_priority(user_text, result, self, grams_source=grams_source)

    def apply_user_quantity_resolution(
        self,
        user_text: str | None,
        result: FoodRecognitionResult,
    ) -> FoodRecognitionResult:
        """Apply countable-portion parsing (штуки / ломтики / «половина») when no explicit grams."""
        from calorie_bot.app.services.food_parser_service import apply_user_quantity_from_text

        out, _ = apply_user_quantity_from_text(user_text, result, self)
        return out

    async def get_or_estimate_food(
        self,
        food_name: str,
        grams: float,
        cache_repository: FoodCacheRepository,
        estimator: FoodNutritionEstimator,
    ) -> FoodItemRecognition:
        """Return food item using cache first, AI estimator second."""
        self.validate_grams(grams)
        normalized_name = normalize_food_name(food_name)
        cached = await cache_repository.get_by_normalized_name(normalized_name)
        if cached is None:
            estimate = await estimator.estimate_food(food_name)
            self.validate_calories(estimate.calories_per_100g)
            cached = await cache_repository.upsert(
                normalized_name=normalized_name,
                display_name=estimate.display_name,
                calories_per_100g=estimate.calories_per_100g,
                protein_per_100g=estimate.protein_per_100g,
                fat_per_100g=estimate.fat_per_100g,
                carbs_per_100g=estimate.carbs_per_100g,
                confidence=estimate.confidence,
                is_estimated=estimate.is_estimated,
            )

        calories = self.calculate_item_calories(cached.calories_per_100g, grams)
        return FoodItemRecognition(
            name=cached.display_name,
            portion_description=f"{grams:.0f} г",
            estimated_grams=grams,
            calories=calories,
            protein=_from_per_100g(cached.protein_per_100g, grams),
            fat=_from_per_100g(cached.fat_per_100g, grams),
            carbs=_from_per_100g(cached.carbs_per_100g, grams),
            calories_per_100g=cached.calories_per_100g,
            protein_per_100g=cached.protein_per_100g,
            fat_per_100g=cached.fat_per_100g,
            carbs_per_100g=cached.carbs_per_100g,
            food_confidence=cached.confidence,
            portion_confidence=cached.confidence,
            grams_source=GramsSource.AI_PHOTO.value,
            is_estimated=True,
            needs_portion_clarification=False,
        )

    def calculate_item_calories(self, calories_per_100g: float, grams: float) -> int:
        """Calculate calories for an item from per-100g value and grams."""
        self.validate_calories(calories_per_100g)
        self.validate_grams(grams)
        calories = calories_from_per_100g(calories_per_100g, grams)
        self.validate_calories(calories)
        return calories

    def calculate_meal_calories(self, items: list[MealItemDraft]) -> int:
        """Calculate total meal calories from items."""
        for item in items:
            self.validate_item(item)
        return sum(draft_item_effective_calories(item) for item in items)

    def validate_item(self, item: MealItemDraft) -> MealItemDraft:
        """Validate item calories, grams, macros, and confidence."""
        if item.calories is not None:
            self.validate_calories(item.calories)
        if item.calories_min is not None:
            self.validate_calories(item.calories_min)
        if item.calories_max is not None:
            self.validate_calories(item.calories_max)
        if item.grams is not None:
            self.validate_grams(item.grams)
        if item.grams_min is not None:
            self.validate_grams(item.grams_min)
        if item.grams_max is not None:
            self.validate_grams(item.grams_max)
        if item.calories_per_100g is not None:
            self.validate_calories(item.calories_per_100g)
        _validate_optional_non_negative(item.protein_g, "protein")
        _validate_optional_non_negative(item.fat_g, "fat")
        _validate_optional_non_negative(item.carbs_g, "carbs")
        if item.confidence is not None and not 0 <= item.confidence <= 1:
            raise ValueError("confidence_must_be_between_0_and_1")
        return item

    def validate_food_result(self, result: FoodRecognitionResult) -> FoodRecognitionResult:
        """Validate and normalize a recognition result."""
        patched_items: list[FoodItemRecognition] = []
        for item in result.items:
            item = self._backfill_legacy_item(item)
            if not has_quantified_portion_mass(item.estimated_grams, item.grams_min, item.grams_max):
                item = item.model_copy(
                    update={
                        "calories": None,
                        "calories_min": None,
                        "calories_max": None,
                        "protein": None,
                        "fat": None,
                        "carbs": None,
                        "protein_min": None,
                        "protein_max": None,
                        "fat_min": None,
                        "fat_max": None,
                        "carbs_min": None,
                        "carbs_max": None,
                        "needs_portion_clarification": True,
                    }
                )
            if item.estimated_grams is not None:
                self.validate_grams(item.estimated_grams)
            if item.grams_min is not None:
                self.validate_grams(item.grams_min)
            if item.grams_max is not None:
                self.validate_grams(item.grams_max)
            item = item.model_copy(update={"name": normalize_food_name(item.name)})
            _validate_optional_non_negative(item.protein, "protein")
            _validate_optional_non_negative(item.fat, "fat")
            _validate_optional_non_negative(item.carbs, "carbs")
            item = self._reconcile_point_mass_atwater(item)
            if item.calories is not None:
                self.validate_calories(item.calories)
            if item.calories_min is not None:
                self.validate_calories(item.calories_min)
            if item.calories_max is not None:
                self.validate_calories(item.calories_max)
            patched_items.append(item)

        total_mid = sum(recognition_item_mid_calories(i) for i in patched_items)
        any_ranges = any(i.calories_min is not None and i.calories_max is not None for i in patched_items)
        t_min = (
            sum(
                (i.calories_min if i.calories_min is not None else recognition_item_mid_calories(i))
                for i in patched_items
            )
            if any_ranges
            else None
        )
        t_max = (
            sum(
                (i.calories_max if i.calories_max is not None else recognition_item_mid_calories(i))
                for i in patched_items
            )
            if any_ranges
            else None
        )
        need_portion = any(i.needs_portion_clarification for i in patched_items)
        has_est = any(i.is_estimated for i in patched_items)
        ov = result.overall_confidence
        if patched_items:
            ov = min(i.confidence for i in patched_items)

        out = FoodRecognitionResult(
            items=patched_items,
            total_calories=total_mid,
            total_calories_min=t_min if any_ranges else None,
            total_calories_max=t_max if any_ranges else None,
            overall_confidence=ov,
            comment=(result.comment or "").strip() or "Оценка приёма пищи",
            meal_type=result.meal_type,
            needs_clarification=result.needs_clarification,
            clarification_question=result.clarification_question,
            needs_portion_clarification=need_portion,
            has_estimated_items=has_est,
        )
        return FoodRecognitionResult.model_validate(out.model_dump())

    def with_default_meal_type(
        self,
        result: FoodRecognitionResult,
        meal_type: MealType,
    ) -> FoodRecognitionResult:
        """Set meal type when parser did not detect it."""
        if result.meal_type is None:
            result = result.model_copy(update={"meal_type": meal_type.value})
        return self.validate_food_result(result)

    def update_meal_type(
        self,
        result: FoodRecognitionResult,
        meal_type: MealType,
    ) -> FoodRecognitionResult:
        """Update meal type selected by the user."""
        return self.validate_food_result(result.model_copy(update={"meal_type": meal_type.value}))

    def format_saved_meal_brief(self, result: FoodRecognitionResult) -> str:
        """Compact summary after the user saved a meal (no edit-mode hints)."""
        result = self.validate_food_result(result)
        return ux_formatter.format_saved_brief(result)

    def format_result(self, result: FoodRecognitionResult) -> str:
        """Return a user-facing recognition summary."""
        result = self.validate_food_result(result)
        return ux_formatter.format_meal_review(
            result,
            show_low_confidence_hint=self.is_low_confidence(result),
        )

    def is_low_confidence(self, result: FoodRecognitionResult) -> bool:
        """Return whether recognition confidence is low."""
        return result.overall_confidence < LOW_CONFIDENCE_THRESHOLD or any(
            item.confidence < LOW_CONFIDENCE_THRESHOLD for item in result.items
        )

    def _ambiguous_name_requires_detail(self, item: FoodItemRecognition) -> bool:
        """True for very generic names when the user did not pin grams via explicit input signals."""
        key = normalize_food_name(item.name)
        if key not in _AMBIGUOUS_FOOD_KEYS:
            return False
        if item.grams_source in (
            GramsSource.USER.value,
            GramsSource.TEXT_CORRECTION.value,
            GramsSource.VOICE_CORRECTION.value,
            GramsSource.USER_QUANTITY.value,
        ):
            return False
        if item.needs_portion_clarification:
            return True
        if item.portion_confidence < LOW_CONFIDENCE_THRESHOLD:
            return True
        if item.grams_source in (
            GramsSource.UNKNOWN.value,
            GramsSource.DEFAULT_PORTION.value,
        ):
            return True
        return False

    def apply_clarification_guards(self, result: FoodRecognitionResult) -> FoodRecognitionResult:
        """Append rule-based clarification prompts; set ``needs_clarification`` when needed."""
        if not result.items:
            return result
        extras: list[str] = []
        prev_q = (result.clarification_question or "").strip().lower()

        if self.is_low_confidence(result) and "неточн" not in prev_q and "уверен" not in prev_q:
            extras.append("Оценка неточная — уточните состав или вес в граммах.")

        for it in result.items:
            if self._ambiguous_name_requires_detail(it):
                extras.append(
                    f"Уточните «{it.name}»: вес и вид продукта "
                    f"(например «пармезан 50 г» или «макароны 200 г и твёрдый сыр 30 г»)."
                )
            elif it.needs_portion_clarification:
                needle = f"«{it.name}»"
                if needle.lower() not in prev_q:
                    extras.append(
                        f"Укажите вес или количество для «{it.name}» (например 150 г или 2 шт.)."
                    )

        if not extras:
            return result

        deduped: list[str] = []
        seen: set[str] = set()
        for line in extras:
            low = line.lower()
            if low not in seen:
                seen.add(low)
                deduped.append(line)

        block = "\n".join(f"• {e}" for e in deduped)
        prior = (result.clarification_question or "").strip()
        new_q = f"{prior}\n{block}".strip() if prior else block
        new_q = new_q[:_MAX_CLARIFICATION_CHARS]
        return result.model_copy(update={"needs_clarification": True, "clarification_question": new_q})

    def requires_blocking_clarification(self, result: FoodRecognitionResult) -> bool:
        """True when the user should answer follow-up questions before the preview step."""
        q = (result.clarification_question or "").strip()
        return bool(result.needs_clarification and q)

    def update_name(
        self,
        result: FoodRecognitionResult,
        index: int,
        name: str,
    ) -> FoodRecognitionResult:
        """Update a recognized item name."""
        self._item_at(result, index)
        items = list(result.items)
        items[index - 1] = items[index - 1].model_copy(update={"name": normalize_food_name(name)})
        return self._rebuild(result.model_copy(update={"items": items}))

    def update_grams(
        self,
        result: FoodRecognitionResult,
        index: int,
        grams: float,
        *,
        grams_source: str = GramsSource.USER.value,
    ) -> FoodRecognitionResult:
        """Update grams; recalculate from per-100g when available."""
        self.validate_grams(grams)
        item = self._item_at(result, index)
        per = item.calories_per_100g
        if per is not None:
            cal = self.calculate_item_calories(per, grams)
            new_item = item.model_copy(
                update={
                    "estimated_grams": grams,
                    "grams_min": None,
                    "grams_max": None,
                    "calories": cal,
                    "calories_min": None,
                    "calories_max": None,
                    "protein": _from_per_100g(item.protein_per_100g, grams),
                    "fat": _from_per_100g(item.fat_per_100g, grams),
                    "carbs": _from_per_100g(item.carbs_per_100g, grams),
                    "protein_min": None,
                    "protein_max": None,
                    "fat_min": None,
                    "fat_max": None,
                    "carbs_min": None,
                    "carbs_max": None,
                    "portion_description": f"{grams:.0f} г",
                    "grams_source": grams_source,
                    "needs_portion_clarification": False,
                    "quantity": None,
                    "unit_type": None,
                    "unit_weight_grams": None,
                    "size_modifier": None,
                    "is_estimated": grams_source
                    not in (
                        GramsSource.USER.value,
                        GramsSource.TEXT_CORRECTION.value,
                        GramsSource.VOICE_CORRECTION.value,
                    ),
                }
            )
        else:
            base_g = item.estimated_grams or item.grams_max or item.grams_min or 1
            ratio = grams / float(base_g) if base_g else 1.0
            mid_cal = recognition_item_mid_calories(item)
            new_cal = max(0, round(mid_cal * ratio))
            new_item = item.model_copy(
                update={
                    "estimated_grams": grams,
                    "grams_min": None,
                    "grams_max": None,
                    "calories": new_cal,
                    "calories_min": None,
                    "calories_max": None,
                    "protein": _scale_optional(item.protein, ratio),
                    "fat": _scale_optional(item.fat, ratio),
                    "carbs": _scale_optional(item.carbs, ratio),
                    "portion_description": f"{grams:.0f} г",
                    "grams_source": grams_source,
                    "needs_portion_clarification": False,
                    "quantity": None,
                    "unit_type": None,
                    "unit_weight_grams": None,
                    "size_modifier": None,
                }
            )
        items = list(result.items)
        items[index - 1] = self._apply_portion_clarification_rules(new_item)
        return self._rebuild(result.model_copy(update={"items": items}))

    def apply_quantity_to_item(
        self,
        result: FoodRecognitionResult,
        index: int,
        *,
        quantity: float,
        unit_type: str,
        unit_weight_grams: float,
        total_grams: float,
        size_modifier: str | None,
        grams_source: str = GramsSource.USER_QUANTITY.value,
    ) -> FoodRecognitionResult:
        """Recalculate macros from per-100g using a count-based portion (reference unit mass)."""
        self.validate_grams(total_grams)
        if quantity <= 0:
            raise ValueError("quantity_must_be_positive")
        item = self._item_at(result, index)
        per = item.calories_per_100g
        portion_text = _format_quantity_portion_description(quantity, unit_type, total_grams)
        if per is not None:
            cal = self.calculate_item_calories(per, total_grams)
            new_item = item.model_copy(
                update={
                    "estimated_grams": total_grams,
                    "grams_min": None,
                    "grams_max": None,
                    "calories": cal,
                    "calories_min": None,
                    "calories_max": None,
                    "protein": _from_per_100g(item.protein_per_100g, total_grams),
                    "fat": _from_per_100g(item.fat_per_100g, total_grams),
                    "carbs": _from_per_100g(item.carbs_per_100g, total_grams),
                    "protein_min": None,
                    "protein_max": None,
                    "fat_min": None,
                    "fat_max": None,
                    "carbs_min": None,
                    "carbs_max": None,
                    "portion_description": portion_text,
                    "grams_source": grams_source,
                    "needs_portion_clarification": False,
                    "is_estimated": True,
                    "quantity": quantity,
                    "unit_type": unit_type,
                    "unit_weight_grams": unit_weight_grams,
                    "size_modifier": size_modifier,
                    "portion_confidence": 0.9,
                }
            )
        else:
            base_g = item.estimated_grams or item.grams_max or item.grams_min or 1
            ratio = total_grams / float(base_g) if base_g else 1.0
            mid_cal = recognition_item_mid_calories(item)
            new_cal = max(0, round(mid_cal * ratio))
            new_item = item.model_copy(
                update={
                    "estimated_grams": total_grams,
                    "grams_min": None,
                    "grams_max": None,
                    "calories": new_cal,
                    "calories_min": None,
                    "calories_max": None,
                    "protein": _scale_optional(item.protein, ratio),
                    "fat": _scale_optional(item.fat, ratio),
                    "carbs": _scale_optional(item.carbs, ratio),
                    "portion_description": portion_text,
                    "grams_source": grams_source,
                    "needs_portion_clarification": False,
                    "is_estimated": True,
                    "quantity": quantity,
                    "unit_type": unit_type,
                    "unit_weight_grams": unit_weight_grams,
                    "size_modifier": size_modifier,
                    "portion_confidence": 0.9,
                }
            )
        items = list(result.items)
        items[index - 1] = self._apply_portion_clarification_rules(new_item)
        return self._rebuild(result.model_copy(update={"items": items}))

    def update_calories(
        self,
        result: FoodRecognitionResult,
        index: int,
        calories: int,
    ) -> FoodRecognitionResult:
        """Update calories for a recognized item."""
        self.validate_calories(calories)
        items = list(result.items)
        items[index - 1] = items[index - 1].model_copy(update={"calories": calories})
        return self._rebuild(result.model_copy(update={"items": items}))

    def add_item(
        self,
        result: FoodRecognitionResult,
        name: str,
        grams: float,
        calories: int,
    ) -> FoodRecognitionResult:
        """Add a manual item to a recognition result."""
        self.validate_grams(grams)
        self.validate_calories(calories)
        per = round(calories * 100.0 / grams, 2) if grams > 0 else None
        new_line = FoodItemRecognition(
            name=normalize_food_name(name),
            portion_description=f"{grams:.0f} г",
            estimated_grams=grams,
            calories=calories,
            calories_per_100g=per,
            food_confidence=1,
            portion_confidence=1,
            grams_source=GramsSource.USER.value,
            is_estimated=False,
            needs_portion_clarification=False,
        )
        return self._rebuild(result.model_copy(update={"items": list(result.items) + [new_line]}))

    def delete_item(self, result: FoodRecognitionResult, index: int) -> FoodRecognitionResult:
        """Delete a recognized item."""
        self._item_at(result, index)
        new_items = list(result.items)
        del new_items[index - 1]
        return self.validate_food_result(result.model_copy(update={"items": new_items}))

    def recalculate_total(self, items: list[MealItemDraft]) -> int:
        """Recalculate total calories from items."""
        return self.calculate_meal_calories(items)

    def validate_calories(self, calories: float) -> None:
        """Validate calories against realistic per-item bounds."""
        if calories < 0:
            raise ValueError("calories_cannot_be_negative")
        if calories > MAX_ITEM_CALORIES:
            raise ValueError("item_calories_too_high")

    def validate_grams(self, grams: float) -> None:
        """Validate grams against realistic per-item bounds."""
        if grams < 0:
            raise ValueError("grams_cannot_be_negative")
        if grams > MAX_ITEM_GRAMS:
            raise ValueError("item_grams_too_high")

    def _rebuild(self, result: FoodRecognitionResult) -> FoodRecognitionResult:
        tmp = FoodRecognitionResult.model_validate(result.model_dump())
        return self.validate_food_result(tmp)

    def _item_at(self, result: FoodRecognitionResult, index: int) -> FoodItemRecognition:
        if index < 1 or index > len(result.items):
            raise ValueError("item_index_out_of_range")
        return result.items[index - 1]


def _scale_optional(value: float | None, ratio: float) -> float | None:
    return round(value * ratio, 1) if value is not None else None


def _portion_text(grams: float | None) -> str:
    return f"{grams:.0f} г" if grams is not None else "порция"


def _format_quantity_portion_description(quantity: float, unit_type: str, total_grams: float) -> str:
    """Stable portion line stored on the item (UX is rendered in ``nutrition_formatter``)."""
    q_display = int(quantity) if abs(quantity - round(quantity)) < 1e-9 else quantity
    if unit_type == PortionUnitType.SLICE.value:
        return f"{q_display} ломт. (~{total_grams:.0f} г)"
    if unit_type == PortionUnitType.PORTION.value:
        return f"{q_display} порц. (~{total_grams:.0f} г)"
    return f"{q_display} шт (~{total_grams:.0f} г)"


def _from_per_100g(value: float | None, grams: float) -> float | None:
    return round(value * grams / 100, 1) if value is not None else None


def _validate_optional_non_negative(value: float | None, field_name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{field_name}_cannot_be_negative")


def normalize_food_name(name: str) -> str:
    """Normalize food names for display and cache lookup."""
    normalized = name.strip().lower().replace("ё", "е")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^0-9a-zа-я\s-]", "", normalized)
    return normalized.strip()


def _grams_source_from_str(value: str | None) -> GramsSource | None:
    if not value:
        return None
    try:
        return GramsSource(value)
    except ValueError:
        return None
