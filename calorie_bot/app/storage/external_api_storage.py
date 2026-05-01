"""HTTP JSON storage for Supabase REST, Cloud Functions, or a custom backend."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any, cast

import httpx

from calorie_bot.app.config import Settings
from calorie_bot.app.storage.dto import DailyAggregateDTO, MealDTO, MealItemDTO, UserSettingsDTO


class ExternalAPIStorage:
    """Async REST client implementing the same operations as ``SqlAlchemyStorage``."""

    def __init__(self, settings: Settings) -> None:
        """Attach HTTP configuration; raises if ``EXTERNAL_STORAGE_BASE_URL`` is empty."""
        base = settings.external_storage_base_url.rstrip("/")
        if not base:
            raise ValueError("EXTERNAL_STORAGE_BASE_URL is required for DATABASE_TYPE=external")
        self._base = base
        self._headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        key = settings.external_storage_api_key.get_secret_value()
        if key:
            self._headers["Authorization"] = f"Bearer {key}"
        self._timeout = httpx.Timeout(settings.external_storage_timeout_seconds)
        self._retries = max(0, settings.external_storage_max_retries)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform HTTP request with bounded retries (Telegram-friendly latency)."""
        url = f"{self._base}{path}"
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(method, url, headers=self._headers, **kwargs)
                    resp.raise_for_status()
                    if resp.content:
                        return resp.json()
                    return None
            except (httpx.HTTPError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt >= self._retries:
                    break
                await asyncio.sleep(0.2 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def save_meal(self, meal: MealDTO) -> MealDTO:
        """POST /meals — response includes ``id``."""
        data = await self._request("POST", "/meals", json=_meal_to_json(meal))
        return _meal_from_json(cast(dict, data))

    async def save_meals_batch(self, meals: list[MealDTO]) -> list[MealDTO]:
        """POST /meals/batch — optional batch contract."""
        payload = {"meals": [_meal_to_json(m) for m in meals]}
        data = await self._request("POST", "/meals/batch", json=payload)
        body = cast(dict, data)
        rows = body.get("meals", body.get("items", []))
        return [_meal_from_json(cast(dict, r)) for r in cast(list, rows)]

    async def get_meals_by_day(self, user_id: int, day: date, *, tz_name: str) -> list[MealDTO]:
        """GET /meals filtered by local day."""
        path = f"/meals?user_id={user_id}&date={day.isoformat()}&tz={tz_name}"
        data = await self._request("GET", path)
        rows = data if isinstance(data, list) else cast(dict, data).get("items", [])
        return [_meal_from_json(cast(dict, r)) for r in cast(list, rows)]

    async def get_meals_range(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
    ) -> list[MealDTO]:
        """GET /meals/range."""
        data = await self._request(
            "GET",
            "/meals/range",
            params={"user_id": user_id, "start": start.isoformat(), "end": end.isoformat()},
        )
        rows = data if isinstance(data, list) else cast(dict, data).get("items", [])
        return [_meal_from_json(cast(dict, r)) for r in cast(list, rows)]

    async def delete_meal(self, meal_id: int, user_id: int) -> bool:
        """DELETE /meals/{id}."""
        await self._request("DELETE", f"/meals/{meal_id}", params={"user_id": user_id})
        return True

    async def get_user_settings(self, user_id: int) -> UserSettingsDTO | None:
        """GET /settings/{user_id}."""
        data = await self._request("GET", f"/settings/{user_id}")
        if not data:
            return None
        return _settings_from_json(user_id, cast(dict, data))

    async def save_user_settings(self, user_id: int, settings: UserSettingsDTO) -> None:
        """POST /settings."""
        await self._request(
            "POST",
            "/settings",
            json={**_settings_to_json(settings), "user_id": user_id},
        )

    async def get_daily_aggregates(self, user_id: int, day: date) -> DailyAggregateDTO | None:
        """GET /stats/daily."""
        data = await self._request(
            "GET",
            "/stats/daily",
            params={"user_id": user_id, "date": day.isoformat()},
        )
        if not data:
            return None
        return _aggregate_from_json(user_id, day, cast(dict, data))

    async def get_range_aggregates(
        self,
        user_id: int,
        start_day: date,
        end_day: date,
    ) -> list[DailyAggregateDTO]:
        """GET /stats/range."""
        data = await self._request(
            "GET",
            "/stats/range",
            params={
                "user_id": user_id,
                "start": start_day.isoformat(),
                "end": end_day.isoformat(),
            },
        )
        body = cast(dict, data) if isinstance(data, dict) else {}
        rows = data if isinstance(data, list) else body.get("days", body.get("items", []))
        out: list[DailyAggregateDTO] = []
        for r in cast(list, rows):
            rd = cast(dict, r)
            day_raw = rd.get("day", rd.get("date"))
            d = day_raw if isinstance(day_raw, date) else date.fromisoformat(str(day_raw))
            out.append(_aggregate_from_json(user_id, d, rd))
        return out


def _meal_to_json(meal: MealDTO) -> dict:
    return {
        "id": meal.id,
        "user_id": meal.user_id,
        "eaten_at": meal.eaten_at.isoformat(),
        "calories": meal.calories,
        "source": meal.source,
        "meal_type": meal.meal_type,
        "status": meal.status,
        "protein_g": meal.protein_g,
        "fat_g": meal.fat_g,
        "carbs_g": meal.carbs_g,
        "ai_confidence": meal.ai_confidence,
        "is_deleted": meal.is_deleted,
        "items": [
            {
                "name": i.name,
                "grams": i.grams,
                "calories": i.calories,
                "portion_text": i.portion_text,
                "protein_g": i.protein_g,
                "fat_g": i.fat_g,
                "carbs_g": i.carbs_g,
            }
            for i in meal.items
        ],
    }


def _meal_from_json(data: dict) -> MealDTO:
    eaten = datetime.fromisoformat(str(data["eaten_at"]))
    items = [
        MealItemDTO(
            name=str(x["name"]),
            grams=x.get("grams"),
            calories=int(x["calories"]),
            portion_text=x.get("portion_text"),
            protein_g=x.get("protein_g"),
            fat_g=x.get("fat_g"),
            carbs_g=x.get("carbs_g"),
        )
        for x in data.get("items", [])
    ]
    return MealDTO(
        id=data.get("id"),
        user_id=int(data["user_id"]),
        eaten_at=eaten,
        calories=int(data.get("calories", data.get("total_calories", 0))),
        source=str(data.get("source", "text")),
        meal_type=data.get("meal_type"),
        status=str(data.get("status", "confirmed")),
        protein_g=float(data.get("protein_g", 0)),
        fat_g=float(data.get("fat_g", 0)),
        carbs_g=float(data.get("carbs_g", 0)),
        ai_confidence=data.get("ai_confidence"),
        is_deleted=bool(data.get("is_deleted", False)),
        items=items,
    )


def _settings_from_json(user_id: int, data: dict) -> UserSettingsDTO:
    return UserSettingsDTO(
        user_id=user_id,
        timezone=str(data.get("timezone", "Europe/Moscow")),
        calorie_goal=data.get("calorie_goal"),
        language=str(data.get("language", "ru")),
        notifications_enabled=bool(data.get("notifications_enabled", True)),
        motivation_enabled=bool(data.get("motivation_enabled", True)),
        ai_analysis_enabled=bool(data.get("ai_analysis_enabled", True)),
        measurement_unit=str(data.get("measurement_unit", "metric")),
    )


def _settings_to_json(s: UserSettingsDTO) -> dict:
    return {
        "timezone": s.timezone,
        "calorie_goal": s.calorie_goal,
        "language": s.language,
        "notifications_enabled": s.notifications_enabled,
        "motivation_enabled": s.motivation_enabled,
        "ai_analysis_enabled": s.ai_analysis_enabled,
        "measurement_unit": s.measurement_unit,
    }


def _aggregate_from_json(user_id: int, day: date, data: dict) -> DailyAggregateDTO:
    return DailyAggregateDTO(
        user_id=user_id,
        day=day,
        total_calories=int(data.get("total_calories", 0)),
        meals_count=int(data.get("meals_count", 0)),
        calorie_goal=data.get("calorie_goal"),
        total_protein_g=float(data.get("total_protein_g", 0)),
        total_fat_g=float(data.get("total_fat_g", 0)),
        total_carbs_g=float(data.get("total_carbs_g", 0)),
    )
