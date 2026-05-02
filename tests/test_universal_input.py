"""Tests for native input classification helpers."""

from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext

from calorie_bot.app.handlers.universal_input import (
    NativeInputKind,
    classify_native_message,
    should_refinement_apply_to_photo_draft,
)


def test_classify_native_message_photo_text_voice() -> None:
    """``classify_native_message`` should mirror Telegram content priority."""
    photo_msg = SimpleNamespace(photo=[1], voice=None, audio=None, text=None)
    assert classify_native_message(photo_msg) == NativeInputKind.PHOTO

    voice_msg = SimpleNamespace(photo=None, voice=object(), audio=None, text="ignored")
    assert classify_native_message(voice_msg) == NativeInputKind.VOICE_OR_AUDIO

    audio_msg = SimpleNamespace(photo=None, voice=None, audio=object(), text=None)
    assert classify_native_message(audio_msg) == NativeInputKind.VOICE_OR_AUDIO

    text_msg = SimpleNamespace(photo=None, voice=None, audio=None, text="  рис 100 г  ")
    assert classify_native_message(text_msg) == NativeInputKind.TEXT

    empty = SimpleNamespace(photo=None, voice=None, audio=None, text="   ")
    assert classify_native_message(empty) == NativeInputKind.OTHER


@pytest.mark.asyncio
async def test_should_refinement_delegates_to_input_router(monkeypatch: pytest.MonkeyPatch) -> None:
    """Draft-edit gate should use ``input_router_service`` logic."""
    calls: list[bool] = []

    async def fake_should(_state: FSMContext) -> bool:
        calls.append(True)
        return True

    monkeypatch.setattr(
        "calorie_bot.app.handlers.universal_input.should_treat_native_message_as_draft_edit",
        fake_should,
    )
    state = SimpleNamespace()  # unused by fake
    assert await should_refinement_apply_to_photo_draft(state) is True  # type: ignore[arg-type]
    assert calls == [True]
