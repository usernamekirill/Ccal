"""Stable callback_data values for navigation and post-action UX."""

from enum import StrEnum


class NavCallback(StrEnum):
    """Inline callbacks that only prompt the next user action (no business writes)."""

    ADD_FOOD = "nav:add_food"
    ADD_VOICE_HINT = "nav:add_voice"
    ADD_TEXT_HINT = "nav:add_text"
    MAIN_MENU = "nav:main_menu"
