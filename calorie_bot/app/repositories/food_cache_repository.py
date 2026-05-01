from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import FoodCache


class FoodCacheRepository:
    """Read and write cached nutrition estimates for normalized foods."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_normalized_name(self, normalized_name: str) -> FoodCache | None:
        """Return cached nutrition data by normalized food name."""
        result = await self._session.execute(
            select(FoodCache).where(FoodCache.normalized_name == normalized_name)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        normalized_name: str,
        display_name: str,
        calories_per_100g: float,
        protein_per_100g: float | None,
        fat_per_100g: float | None,
        carbs_per_100g: float | None,
        confidence: float,
        source: str = "ai",
        is_estimated: bool = True,
    ) -> FoodCache:
        """Create or update cached nutrition data."""
        cached = await self.get_by_normalized_name(normalized_name)
        if cached is None:
            cached = FoodCache(normalized_name=normalized_name, display_name=display_name)
            self._session.add(cached)

        cached.display_name = display_name
        cached.calories_per_100g = calories_per_100g
        cached.protein_per_100g = protein_per_100g
        cached.fat_per_100g = fat_per_100g
        cached.carbs_per_100g = carbs_per_100g
        cached.confidence = confidence
        cached.source = source
        cached.is_estimated = is_estimated
        await self._session.flush()
        return cached
