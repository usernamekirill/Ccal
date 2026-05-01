from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import ErrorLog


class ErrorLogRepository:
    """Persist safe technical errors without sensitive payloads."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_safe_log(
        self,
        error_type: str,
        user_id: int | None = None,
        handler: str | None = None,
        safe_message: str | None = None,
        request_id: str | None = None,
    ) -> ErrorLog:
        """Create a redacted error log record."""
        log = ErrorLog(
            user_id=user_id,
            error_type=error_type,
            handler=handler,
            safe_message=safe_message,
            request_id=request_id,
        )
        self._session.add(log)
        await self._session.flush()
        return log
