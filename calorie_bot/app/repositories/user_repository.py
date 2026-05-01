from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import User


class UserRepository:
    """Persist and load Telegram users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Return a user by Telegram id."""
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def upsert_telegram_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
    ) -> User:
        """Create or update a Telegram user."""
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id, username=username, first_name=first_name)
            self._session.add(user)
            await self._session.flush()
        else:
            user.username = username
            user.first_name = first_name
        return user

    async def mark_onboarding_completed(self, user: User) -> User:
        """Mark onboarding as completed for a user."""
        user.onboarding_completed = True
        user.onboarding_status = "completed"
        return user

    async def soft_delete_user(self, user: User, deleted_at: datetime) -> User:
        """Mark a user as deleted while retaining referential integrity."""
        user.deleted_at = deleted_at
        user.onboarding_status = "deleted"
        return user

    async def anonymize_user(self, user: User) -> User:
        """Remove optional Telegram profile data while preserving internal id."""
        user.username = None
        user.first_name = None
        return user
