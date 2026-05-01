"""Tests for onboarding gates on meal logging."""

from types import SimpleNamespace

from calorie_bot.app.services.onboarding_gate import food_logging_blocked_message


def test_food_logging_blocked_when_onboarding_incomplete() -> None:
    """Users mid-onboarding should see a hint, not invoke food AI."""
    user = SimpleNamespace(onboarding_completed=False)
    msg = food_logging_blocked_message(user)
    assert msg is not None
    assert "настройку" in msg.casefold()


def test_food_logging_allowed_after_onboarding() -> None:
    """Completed onboarding should not block meal logging."""
    user = SimpleNamespace(onboarding_completed=True)
    assert food_logging_blocked_message(user) is None
