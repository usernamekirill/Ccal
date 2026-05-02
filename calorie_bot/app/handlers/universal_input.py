"""Classification and draft rules for native Telegram food input (no mode buttons).

Photo, voice, and text are bound to separate Aiogram routers; this module is the
single place for **what kind of payload** arrived and **whether it should refine
the current photo draft** instead of starting a new meal.

Flow:

- ``PHOTO`` → photo pipeline
- ``VOICE_OR_AUDIO`` → voice pipeline
- ``TEXT`` → text food parser **or** draft edit when ``should_refinement_apply_to_photo_draft``

See ``photo``, ``voice``, ``audio``, ``text_food`` handlers and
``edit_interpreter_service.apply_instruction_to_food_result``.
"""

from __future__ import annotations

from enum import Enum

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from calorie_bot.app.services.input_router_service import should_treat_native_message_as_draft_edit


class NativeInputKind(str, Enum):
    """High-level content type for a user message."""

    PHOTO = "photo"
    VOICE_OR_AUDIO = "voice"
    TEXT = "text"
    OTHER = "other"


def classify_native_message(message: Message) -> NativeInputKind:
    """Return the primary input channel for this update (used by tests and future middleware)."""
    if message.photo:
        return NativeInputKind.PHOTO
    if message.voice or message.audio:
        return NativeInputKind.VOICE_OR_AUDIO
    if message.text and message.text.strip():
        return NativeInputKind.TEXT
    return NativeInputKind.OTHER


async def should_refinement_apply_to_photo_draft(state: FSMContext) -> bool:
    """True when text/voice should edit ``photo_food_result`` in ``photo_review`` state."""
    return await should_treat_native_message_as_draft_edit(state)
