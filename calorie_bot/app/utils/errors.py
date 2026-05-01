class CalorieBotError(Exception):
    """Base exception for expected application errors."""


class ExternalAIError(CalorieBotError):
    """Raised when an external AI provider fails."""


class UserInputError(CalorieBotError):
    """Raised when user input cannot be processed."""
