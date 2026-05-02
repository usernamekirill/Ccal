"""Tests for draft-vs-new-meal routing helpers."""

from unittest.mock import AsyncMock

import pytest

from calorie_bot.app.services.input_router_service import should_treat_native_message_as_draft_edit
from calorie_bot.app.states.meal import MealStates


@pytest.mark.asyncio
async def test_treat_as_draft_edit_in_photo_review_with_payload() -> None:
    """Text/voice should refine draft when user sees confirmation screen."""
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=MealStates.photo_review.state)
    state.get_data = AsyncMock(return_value={"photo_food_result": {"items": [{"name": "x"}]}})
    assert await should_treat_native_message_as_draft_edit(state) is True


@pytest.mark.asyncio
async def test_treat_as_draft_edit_in_photo_editing_with_payload() -> None:
    """After «Изменить», state is photo_editing but the review keyboard must still imply draft context."""
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=MealStates.photo_editing.state)
    state.get_data = AsyncMock(return_value={"photo_food_result": {"items": [{"name": "x"}]}})
    assert await should_treat_native_message_as_draft_edit(state) is True


@pytest.mark.asyncio
async def test_no_draft_edit_without_photo_food_result() -> None:
    """photo_review state without serialized result should not force edit path."""
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=MealStates.photo_review.state)
    state.get_data = AsyncMock(return_value={})
    assert await should_treat_native_message_as_draft_edit(state) is False


@pytest.mark.asyncio
async def test_no_draft_edit_when_fsm_idle() -> None:
    """No open draft → native text is a new meal."""
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.get_data = AsyncMock(return_value={})
    assert await should_treat_native_message_as_draft_edit(state) is False
