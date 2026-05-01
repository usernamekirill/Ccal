from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import User
from calorie_bot.app.repositories.user_repository import UserRepository


class UserService:
    """Coordinate Telegram user persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = UserRepository(session)

    async def ensure_user(self, telegram_user: TelegramUser) -> User:
        """Create or update a user from Telegram profile data."""
        return await self._repository.upsert_telegram_user(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
        )
