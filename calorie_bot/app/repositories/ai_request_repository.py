from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import AIRequest


class AIRequestRepository:
    """Persist AI request metadata without sensitive payloads."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        request_type: str,
        status: str,
        meal_id: int | None = None,
        model: str | None = None,
    ) -> AIRequest:
        """Create an AI request metadata record."""
        request = AIRequest(
            user_id=user_id,
            meal_id=meal_id,
            request_type=request_type,
            model=model,
            status=status,
        )
        self._session.add(request)
        await self._session.flush()
        return request

    async def mark_succeeded(
        self,
        request: AIRequest,
        input_units: int | None = None,
        output_units: int | None = None,
        estimated_cost: float | None = None,
    ) -> AIRequest:
        """Mark an AI request as successful."""
        request.status = "succeeded"
        request.input_units = input_units
        request.output_units = output_units
        request.estimated_cost = estimated_cost
        return request

    async def mark_failed(self, request: AIRequest, error_message: str) -> AIRequest:
        """Mark an AI request as failed without storing sensitive payloads."""
        request.status = "failed"
        request.error_message = error_message[:500]
        return request

    async def count_for_user_since(self, user_id: int, since: datetime) -> int:
        """Count AI requests for a user since a datetime."""
        result = await self._session.execute(
            select(func.count(AIRequest.id)).where(
                AIRequest.user_id == user_id,
                AIRequest.created_at >= since,
            )
        )
        return int(result.scalar_one())
