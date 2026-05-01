from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import MotivationEvent


class MotivationEventRepository:
    """Persist motivational product events and rate-limit queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_event(
        self,
        user_id: int,
        event_type: str,
        event_date: datetime,
        payload: dict | None = None,
    ) -> MotivationEvent:
        """Create a motivation event for a user."""
        event = MotivationEvent(
            user_id=user_id,
            event_type=event_type,
            event_date=event_date,
            payload=payload,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_recent(self, user_id: int, limit: int = 20) -> list[MotivationEvent]:
        """Return recent motivation events for a user."""
        result = await self._session.execute(
            select(MotivationEvent)
            .where(MotivationEvent.user_id == user_id)
            .order_by(MotivationEvent.event_date.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def count_since(self, user_id: int, since: datetime) -> int:
        """Count events with ``event_date >= since``."""
        result = await self._session.execute(
            select(func.count())
            .select_from(MotivationEvent)
            .where(
                MotivationEvent.user_id == user_id,
                MotivationEvent.event_date >= since,
            )
        )
        return int(result.scalar_one())

    async def last_event_of_type(
        self,
        user_id: int,
        event_type: str,
    ) -> MotivationEvent | None:
        """Return the most recent event of a given type, if any."""
        result = await self._session.execute(
            select(MotivationEvent)
            .where(
                MotivationEvent.user_id == user_id,
                MotivationEvent.event_type == event_type,
            )
            .order_by(MotivationEvent.event_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def has_ever_event_type(self, user_id: int, event_type: str) -> bool:
        """Return whether an event type was ever recorded for the user."""
        row = await self.last_event_of_type(user_id, event_type)
        return row is not None
