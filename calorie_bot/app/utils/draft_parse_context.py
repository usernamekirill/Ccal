"""FSM + OpenAI envelope helpers for meal draft reconciliation."""

from __future__ import annotations

from typing import Any


def meal_parse_context(state_data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Attach vision baseline from FSM and caller overrides for draft reconciliation."""
    ctx: dict[str, Any] = {k: v for k, v in kwargs.items() if v is not None}
    vb = state_data.get("vision_baseline_snapshot")
    if vb is not None:
        ctx.setdefault("vision_baseline", vb)
    return ctx


def unresolved_clarifications_from_recognition(fr) -> list[str] | None:
    """Single open question string from a recognition draft, if any."""
    q = (fr.clarification_question or "").strip() if fr else ""
    return [q] if q else None
