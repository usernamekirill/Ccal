"""Native Telegram food input: photo, voice, and text are handled by dedicated routers.

There is no separate “mode” FSM: users send content directly. Draft-aware text/voice
routing uses ``MealStates.photo_review`` plus ``input_router_service`` helpers.

See: ``photo``, ``voice``, ``text_food`` handlers and ``edit_interpreter_service``.
"""
