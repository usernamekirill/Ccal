"""AI-first structured parser for free-text meals. No database access."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from calorie_bot.app.ai.prompts import TEXT_FOOD_STRUCTURED_PROMPT
from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.domain import GramsSource, PortionUnitType
from calorie_bot.app.services.calorie_service import CalorieService, normalize_food_name
from calorie_bot.app.services.nutrition_calculator import (
    calories_from_per_100g,
    has_quantified_portion_mass,
    macro_g_from_per_100g,
)
from calorie_bot.app.utils.openai_errors import translate_openai_exception

_log = logging.getLogger(__name__)

_MEAL_TYPES: frozenset[str] = frozenset({"breakfast", "lunch", "dinner", "snack"})


class ParsedMealDraft(BaseModel):
    """Validated output of the structured text meal LLM step (no persistence)."""

    model_config = ConfigDict(extra="ignore")

    recognized: bool = True
    food_result: FoodRecognitionResult
    user_message_normalized: str | None = None
    reasoning_summary: str | None = None
    raw_parse_failed: bool = False


class _TotalsPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    calories: float | int = 0
    protein: float = 0.0
    fat: float = 0.0
    carbs: float = 0.0


class StructuredTextMealItem(BaseModel):
    """One line from the OpenAI structured JSON."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    canonical_name: str | None = None
    quantity: float | None = Field(default=1.0, ge=0)
    unit: str | None = None
    weight_grams: float | None = Field(default=None, ge=0)
    estimated_grams: float | None = Field(default=None, ge=0)
    portion_description: str | None = None
    calories_per_100g: float | None = Field(default=None, ge=0, le=5000)
    protein_per_100g: float | None = Field(default=None, ge=0)
    fat_per_100g: float | None = Field(default=None, ge=0)
    carbs_per_100g: float | None = Field(default=None, ge=0)
    calories: float | int | None = Field(default=None, ge=0)
    protein: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)
    carbs: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_estimated: bool = True


class StructuredTextMealResponse(BaseModel):
    """Top-level JSON from the text-food LLM."""

    model_config = ConfigDict(extra="ignore")

    recognized: bool = True
    needs_clarification: bool = False
    clarification_question: str | None = None
    meal_type: str | None = "unknown"
    items: list[StructuredTextMealItem] = Field(default_factory=list)
    totals: _TotalsPayload | None = None
    user_message_normalized: str | None = None
    reasoning_summary: str | None = None

    @field_validator("items", mode="before")
    @classmethod
    def _items_must_be_list(cls, v: Any) -> Any:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("items_must_be_a_list")
        return v


def _normalize_llm_unit(unit: str | None) -> Literal["g", "piece", "other"]:
    if unit is None:
        return "g"
    u = unit.strip().lower()
    if u in ("g", "gram", "grams", "г", "gr"):
        return "g"
    if u in ("piece", "pcs", "pc", "шт", "штука", "штуки", "штук", "x"):
        return "piece"
    return "other"


def _item_to_food_recognition(
    raw: StructuredTextMealItem,
    *,
    user_text_has_gram_token: bool,
) -> FoodItemRecognition:
    """Map one structured item to :class:`FoodItemRecognition`."""
    g = raw.weight_grams if raw.weight_grams is not None else raw.estimated_grams
    ukind = _normalize_llm_unit(raw.unit)
    name_src = raw.canonical_name or raw.name
    name = normalize_food_name(name_src)
    portion = (raw.portion_description or "").strip()
    if not portion and g is not None:
        portion = f"{g:.0f} г"
    if not portion:
        portion = "порция"

    per_c = raw.calories_per_100g
    per_p = raw.protein_per_100g
    per_f = raw.fat_per_100g
    per_cb = raw.carbs_per_100g

    if raw.calories is not None:
        line_cal = int(round(float(raw.calories)))
    elif per_c is not None and g is not None:
        line_cal = calories_from_per_100g(per_c, float(g))
    else:
        line_cal = None

    protein_g = raw.protein
    fat_g = raw.fat
    carbs_g = raw.carbs
    if g is not None and protein_g is None and per_p is not None:
        protein_g = macro_g_from_per_100g(per_p, float(g))
    if g is not None and fat_g is None and per_f is not None:
        fat_g = macro_g_from_per_100g(per_f, float(g))
    if g is not None and carbs_g is None and per_cb is not None:
        carbs_g = macro_g_from_per_100g(per_cb, float(g))

    if ukind == "piece" and g is not None:
        grams_source = GramsSource.USER_QUANTITY.value
    elif g is not None and (user_text_has_gram_token or raw.weight_grams is not None):
        grams_source = GramsSource.USER.value
    elif g is not None:
        grams_source = GramsSource.AI_PHOTO.value
    else:
        grams_source = GramsSource.UNKNOWN.value

    fc = float(raw.confidence) if raw.confidence is not None else 0.72
    pc = 0.88 if g is not None else 0.45
    conf = min(fc, pc)

    qty_out: float | None = None
    u_type: str | None = None
    if ukind == "piece":
        qty_out = float(raw.quantity) if raw.quantity is not None else 1.0
        u_type = PortionUnitType.PIECE.value
    elif ukind == "other":
        u_type = PortionUnitType.UNKNOWN.value

    needs_portion = not has_quantified_portion_mass(g, None, None)

    return FoodItemRecognition(
        name=name,
        portion_description=portion,
        estimated_grams=g,
        grams_min=None,
        grams_max=None,
        calories=line_cal,
        calories_per_100g=per_c,
        protein_per_100g=per_p,
        fat_per_100g=per_f,
        carbs_per_100g=per_cb,
        protein=protein_g,
        fat=fat_g,
        carbs=carbs_g,
        food_confidence=fc,
        portion_confidence=pc,
        grams_source=grams_source,
        needs_portion_clarification=needs_portion,
        is_estimated=bool(raw.is_estimated or needs_portion),
        confidence=conf,
        quantity=qty_out,
        unit_type=u_type,
    )


def _user_text_suggests_explicit_grams(user_text: str) -> bool:
    from calorie_bot.app.services.food_parser_service import extract_ordered_gram_values

    return bool(extract_ordered_gram_values(user_text))


def structured_meal_to_food_result(
    data: StructuredTextMealResponse,
    *,
    user_text: str,
    default_meal_type: str | None,
    calorie_service: CalorieService | None = None,
) -> FoodRecognitionResult:
    """Convert validated LLM payload into :class:`FoodRecognitionResult`."""
    svc = calorie_service or CalorieService()
    gram_hint = _user_text_suggests_explicit_grams(user_text)

    items_out: list[FoodItemRecognition] = []
    for raw in data.items:
        items_out.append(_item_to_food_recognition(raw, user_text_has_gram_token=gram_hint))

    mt = (data.meal_type or "").strip().lower()
    meal_type: str | None = None
    if mt in _MEAL_TYPES:
        meal_type = mt
    elif default_meal_type and default_meal_type in _MEAL_TYPES:
        meal_type = default_meal_type

    needs_clar = bool(data.needs_clarification)
    clar_q = (data.clarification_question or "").strip() or None

    if not data.recognized:
        needs_clar = True
        clar_q = clar_q or "Не получилось разобрать текст. Уточните блюдо и вес, например «гречка 200 г»."
    elif (
        items_out
        and all(has_quantified_portion_mass(i.estimated_grams, i.grams_min, i.grams_max) for i in items_out)
        and needs_clar
        and clar_q
    ):
        lowered = clar_q.lower()
        weight_only_followup = any(
            w in lowered for w in ("грамм", " г ", "вес", "масс", "сколько грамм", "уточните вес")
        )
        product_detail = any(
            w in lowered for w in ("какой", "вид", "что за", "состав", "начинк", "рецепт")
        )
        if weight_only_followup and not product_detail:
            needs_clar = False
            clar_q = None

    comment = (data.reasoning_summary or "").strip() or "Оценка приёма пищи"
    raw_fr = FoodRecognitionResult(
        items=items_out,
        total_calories=0,
        overall_confidence=0.7,
        comment=comment,
        meal_type=meal_type,
        needs_clarification=needs_clar,
        clarification_question=clar_q,
    )
    return svc.validate_food_result(raw_fr)


def _empty_parse_result() -> FoodRecognitionResult:
    """Placeholder when the LLM response cannot be parsed."""
    return FoodRecognitionResult(
        items=[],
        total_calories=0,
        overall_confidence=0.0,
        comment="Пустой разбор текста",
    )


class TextFoodParser:
    """OpenAI-backed structured text meal parser."""

    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None) -> None:
        self._settings = settings
        self._client = client or AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def parse_food_text(self, user_text: str, context: dict | None = None) -> ParsedMealDraft:
        """Call OpenAI, validate JSON, map to :class:`FoodRecognitionResult`."""
        ctx = context or {}
        raw_dmt = ctx.get("default_meal_type")
        dmt: str | None = raw_dmt.strip().lower() if isinstance(raw_dmt, str) else None

        default_hint = f"\nЕсли тип приёма пищи не указан, используй meal_type={dmt}." if dmt else ""
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_correction_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": TEXT_FOOD_STRUCTURED_PROMPT},
                    {"role": "user", "content": user_text + default_hint},
                ],
            )
            content = response.choices[0].message.content or "{}"
            payload = json.loads(content)
            data = StructuredTextMealResponse.model_validate(payload)
            fr = structured_meal_to_food_result(
                data,
                user_text=user_text,
                default_meal_type=dmt,
            )
            return ParsedMealDraft(
                recognized=bool(data.recognized),
                food_result=fr,
                user_message_normalized=data.user_message_normalized,
                reasoning_summary=data.reasoning_summary,
                raw_parse_failed=False,
            )
        except (json.JSONDecodeError, ValidationError, KeyError, IndexError, TypeError) as exc:
            _log.warning("text_food_structured_parse_failed", extra={"error": str(exc)})
            return ParsedMealDraft(
                recognized=False,
                food_result=_empty_parse_result(),
                raw_parse_failed=True,
            )
        except Exception as exc:
            _log.warning(
                "text_food_openai_failed",
                extra={"error": str(translate_openai_exception(exc))},
            )
            return ParsedMealDraft(
                recognized=False,
                food_result=_empty_parse_result(),
                raw_parse_failed=True,
            )
