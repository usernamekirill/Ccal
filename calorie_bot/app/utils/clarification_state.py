"""FSM update payloads for meal clarification flows (handlers only; no extra business rules)."""

from __future__ import annotations

from typing import Any

from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService


def fsm_data_blocking_text_clarification(
    calorie_service: CalorieService,
    result: FoodRecognitionResult,
    *,
    pending_text: str,
    default_meal_type: str,
    **extra: Any,
) -> dict[str, Any]:
    """Build ``FSMContext.update_data`` fields after blocking clarification from text/voice parse.

    When the model returned no lines yet, the follow-up must **re-parse** combined text
    (``clarification_mode`` unset). Non-empty drafts use ``text_draft`` + correction merge.

    For a single-item draft, ``pending_food`` holds minimal product context for weight follow-up.
    """
    pending_food: dict[str, object] | None = None
    if len(result.items) == 1:
        it = result.items[0]
        pending_food = {
            "name": it.name,
            "quantity": float(it.quantity) if it.quantity is not None else 1.0,
            "unit": it.unit_type or "piece",
        }
    data: dict[str, Any] = {
        "pending_text_food": pending_text,
        "default_meal_type": default_meal_type,
        "pending_food_result_draft": calorie_service.result_to_dict(result) if result.items else None,
        "clarification_mode": "text_draft" if result.items else None,
        "pending_food": pending_food,
    }
    data.update(extra)
    return data
