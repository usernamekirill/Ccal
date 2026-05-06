"""Integration: text_ai / photo / manual meal save → DB totals → daily_stats (no OpenAI)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.database.base import Base
from calorie_bot.app.database.models import DailyStats, Meal, MealItem, User, UserProfile
from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource, MealStatus, MealType
from calorie_bot.app.repositories.meal_repository import MealRepository
from calorie_bot.app.services.calorie_service import (
    CalorieService,
    MealDraftSaveError,
    ensure_meal_draft_persistable,
    meal_draft_calorie_totals,
)
from calorie_bot.app.services.daily_stats_sync import (
    on_confirmed_meal_edited,
    on_meal_confirmed,
    on_meal_soft_deleted,
)
from calorie_bot.app.services.meal_service import MealService
from calorie_bot.app.services.stats_service import StatsService, _day_bounds
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.repositories.profile_repository import ProfileRepository


async def _engine_factory(tmp_path):
    db_path = tmp_path / "meal_pipe.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_user(session: AsyncSession) -> int:
    session.add(User(telegram_id=900001, onboarding_completed=True))
    await session.flush()
    uid = (await session.execute(select(User.id).where(User.telegram_id == 900001))).scalar_one()
    session.add(UserProfile(user_id=uid, timezone="Europe/Moscow"))
    await session.commit()
    return int(uid)


def _settings_tz():
    s = MagicMock()
    s.timezone = "Europe/Moscow"
    return s


def _item(
    name: str,
    grams: float,
    cal: int,
    p: float,
    f: float,
    c: float,
    *,
    per_c: float = 100.0,
    per_p: float = 10.0,
    per_f: float = 5.0,
    per_cb: float = 15.0,
) -> FoodItemRecognition:
    return FoodItemRecognition(
        name=name,
        portion_description=f"{grams:.0f} г",
        estimated_grams=grams,
        calories=cal,
        calories_per_100g=per_c,
        protein_per_100g=per_p,
        fat_per_100g=per_f,
        carbs_per_100g=per_cb,
        protein=p,
        fat=f,
        carbs=c,
        food_confidence=0.9,
        portion_confidence=0.88,
        grams_source="user",
        needs_portion_clarification=False,
        is_estimated=False,
    )


@pytest.mark.asyncio
async def test_meal_repository_totals_from_items_not_from_draft_field(tmp_path) -> None:
    """DB meal calories must follow line items even if MealDraft.total_calories was wrong."""
    engine, factory = await _engine_factory(tmp_path)
    async with factory() as session:
        uid = await _seed_user(session)
        cs = CalorieService()
        r = cs.validate_food_result(
            FoodRecognitionResult(
                items=[_item("а", 100, 100, 10, 0, 5), _item("б", 100, 150, 15, 5, 10)],
                total_calories=0,
                overall_confidence=0.9,
                comment="x",
                meal_type="lunch",
            )
        )
        d = cs.to_meal_draft(r, source=MealSource.TEXT_AI)
        d_corrupt = MealDraft(
            items=d.items,
            total_calories=99999,
            total_calories_min=d.total_calories_min,
            total_calories_max=d.total_calories_max,
            has_estimated_items=d.has_estimated_items,
            source=d.source,
            meal_type=d.meal_type,
            confidence=d.confidence,
            notes=d.notes,
        )
        exp_cal, _, _ = meal_draft_calorie_totals(d_corrupt.items)
        exp_prot = sum(it.protein_g or 0 for it in d_corrupt.items)
        meal = await MealRepository(session).create_draft(
            uid,
            d_corrupt,
            datetime.now(UTC),
        )
        await session.commit()
        assert meal.total_calories == exp_cal
        assert meal.total_calories != 99999
        assert meal.total_protein_g == pytest.approx(exp_prot)
    await engine.dispose()


@pytest.mark.asyncio
async def test_multi_item_text_ai_confirm_syncs_daily_stats(tmp_path) -> None:
    engine, factory = await _engine_factory(tmp_path)
    tz = ZoneInfo("Europe/Moscow")
    day = datetime(2026, 4, 30, 8, 0, tzinfo=tz)
    async with factory() as session:
        uid = await _seed_user(session)
        cs = CalorieService()

        async def save_at(when: datetime, items: list, mtype: str | None) -> None:
            r = cs.validate_food_result(
                FoodRecognitionResult(
                    items=items,
                    total_calories=0,
                    overall_confidence=0.88,
                    comment="x",
                    meal_type=mtype,
                )
            )
            d = cs.to_meal_draft(r, source=MealSource.TEXT_AI)
            meal = await MealRepository(session).create_draft(uid, d, when)
            await MealRepository(session).confirm(meal)
            await on_meal_confirmed(session, _settings_tz(), user_sql_id=uid, meal=meal)

        await save_at(
            day.replace(hour=8),
            [
                _item("яйцо", 150, 220, 20, 15, 2),
            ],
            "breakfast",
        )
        await save_at(
            day.replace(hour=13),
            [
                _item("гречка", 200, 240, 8, 4, 45),
                _item("курица", 150, 250, 40, 8, 0),
            ],
            "lunch",
        )
        await save_at(
            day.replace(hour=16),
            [_item("яблоко", 100, 52, 0.3, 0.2, 14)],
            "snack",
        )
        await session.commit()

    async with factory() as session:
        profile = await ProfileRepository(session).get_by_user_id(uid)
        start, end = _day_bounds(day.date(), tz)
        meals = await StatsRepository(session).list_confirmed_meals_between(uid, start, end)
        view = await StatsService(
            StatsRepository(session),
            ProfileRepository(session),
            default_timezone="Europe/Moscow",
            now_factory=lambda _: day.replace(hour=20),
        ).today_view(uid)

        assert len(meals) == 3
        assert sum(len(m.items) for m in meals) == 4
        assert view.meals_count == 3
        assert view.total_calories == sum(m.total_calories for m in meals)
        assert view.total_protein_g == pytest.approx(sum(float(m.total_protein_g or 0) for m in meals), rel=1e-3)
        rows = (
            await session.execute(select(DailyStats).where(DailyStats.user_id == uid))
        ).scalars().all()
        assert len(rows) == 1
        ds = rows[0]
        assert ds.meals_count == 3
        assert ds.total_calories == view.total_calories

    await engine.dispose()


@pytest.mark.asyncio
async def test_mixed_sources_all_counted_in_rollups(tmp_path) -> None:
    engine, factory = await _engine_factory(tmp_path)
    tz = ZoneInfo("Europe/Moscow")
    when = datetime(2026, 5, 1, 12, 0, tzinfo=tz)
    async with factory() as session:
        uid = await _seed_user(session)
        cs = CalorieService()

        def draft_from_items(items: list, source: MealSource) -> MealDraft:
            r = cs.validate_food_result(
                FoodRecognitionResult(
                    items=items,
                    total_calories=0,
                    overall_confidence=0.85,
                    comment="x",
                    meal_type="lunch",
                )
            )
            return cs.to_meal_draft(r, source=source)

        expected_cals = 0
        for src, it in (
            (MealSource.TEXT_AI, [_item("текст", 100, 100, 10, 0, 0)]),
            (MealSource.PHOTO, [_item("фото", 80, 120, 8, 5, 10)]),
            (MealSource.MANUAL, [_item("ручной", 50, 75, 5, 3, 5)]),
        ):
            d = draft_from_items(it, src)
            expected_cals += meal_draft_calorie_totals(d.items)[0]
            m = await MealRepository(session).create_draft(uid, d, when)
            await MealRepository(session).confirm(m)
            await on_meal_confirmed(session, _settings_tz(), user_sql_id=uid, meal=m)
        await session.commit()

    async with factory() as session:
        start, end = _day_bounds(when.date(), tz)
        meals = await StatsRepository(session).list_confirmed_meals_between(uid, start, end)
        assert {m.source for m in meals} == {
            MealSource.TEXT_AI.value,
            MealSource.PHOTO.value,
            MealSource.MANUAL.value,
        }
        assert sum(m.total_calories for m in meals) == expected_cals
    await engine.dispose()


@pytest.mark.asyncio
async def test_edit_confirmed_meal_updates_totals_and_daily_stats(tmp_path) -> None:
    engine, factory = await _engine_factory(tmp_path)
    tz = ZoneInfo("Europe/Moscow")
    when = datetime(2026, 5, 2, 14, 0, tzinfo=tz)
    async with factory() as session:
        uid = await _seed_user(session)
        cs = CalorieService()
        r = cs.validate_food_result(
            FoodRecognitionResult(
                items=[_item("курица", 150, 300, 30, 10, 0)],
                total_calories=0,
                overall_confidence=0.9,
                comment="x",
                meal_type="lunch",
            )
        )
        d0 = cs.to_meal_draft(r, source=MealSource.TEXT_AI)
        meal = await MealRepository(session).create_draft(uid, d0, when)
        await MealRepository(session).confirm(meal)
        await on_meal_confirmed(session, _settings_tz(), user_sql_id=uid, meal=meal)
        await session.commit()
        mid = meal.id

    async with factory() as session:
        meal_before = await MealRepository(session).get_user_meal(uid, mid)
        cs = CalorieService()
        r2 = cs.validate_food_result(
            FoodRecognitionResult(
                items=[_item("курица", 200, 400, 40, 12, 0)],
                total_calories=0,
                overall_confidence=0.9,
                comment="x",
                meal_type="lunch",
            )
        )
        d1 = cs.to_meal_draft(r2, source=MealSource.TEXT_AI)
        exp_after_cal, _, _ = meal_draft_calorie_totals(d1.items)
        ms = MealService(MealRepository(session), None)
        updated = await ms.update_saved_meal(uid, mid, d1)
        await session.commit()
        assert updated is not None
        assert updated.items[0].grams == 200
        assert updated.total_calories == exp_after_cal

        await on_confirmed_meal_edited(
            session,
            _settings_tz(),
            user_sql_id=uid,
            before_eaten_at=meal_before.eaten_at,
            before_calories=meal_before.total_calories,
            before_protein_g=float(meal_before.total_protein_g or 0),
            before_fat_g=float(meal_before.total_fat_g or 0),
            before_carbs_g=float(meal_before.total_carbs_g or 0),
            before_status=MealStatus.CONFIRMED.value,
            after_meal=updated,
        )
        await session.commit()

    async with factory() as session:
        row = (
            await session.execute(select(DailyStats).where(DailyStats.user_id == uid))
        ).scalar_one()
        assert row.total_calories == exp_after_cal
    await engine.dispose()


@pytest.mark.asyncio
async def test_soft_delete_meal_reverts_daily_stats(tmp_path) -> None:
    engine, factory = await _engine_factory(tmp_path)
    tz = ZoneInfo("Europe/Moscow")
    when = datetime(2026, 5, 3, 9, 0, tzinfo=tz)
    async with factory() as session:
        uid = await _seed_user(session)
        cs = CalorieService()
        d = cs.to_meal_draft(
            cs.validate_food_result(
                FoodRecognitionResult(
                    items=[_item("x", 100, 100, 10, 0, 0)],
                    total_calories=0,
                    overall_confidence=0.9,
                    comment="x",
                )
            ),
            source=MealSource.TEXT_AI,
        )
        meal = await MealRepository(session).create_draft(uid, d, when)
        await MealRepository(session).confirm(meal)
        await on_meal_confirmed(session, _settings_tz(), user_sql_id=uid, meal=meal)
        await session.commit()
        mid = meal.id

    async with factory() as session:
        m = await MealRepository(session).get_user_meal(uid, mid)
        await on_meal_soft_deleted(session, _settings_tz(), user_sql_id=uid, meal=m)
        await MealRepository(session).soft_delete(m, datetime.now(UTC))
        await session.commit()

    async with factory() as session:
        n_meals = (
            await session.execute(
                select(func.count()).select_from(Meal).where(Meal.user_id == uid, Meal.deleted_at.is_(None))
            )
        ).scalar_one()
        assert int(n_meals) == 0
        row = (
            await session.execute(select(DailyStats).where(DailyStats.user_id == uid))
        ).scalar_one()
        assert row.total_calories == 0
        assert row.meals_count == 0
    await engine.dispose()


def test_ensure_meal_draft_persistable_rejects_empty() -> None:
    d = MealDraft(
        items=[],
        total_calories=0,
        source=MealSource.TEXT_AI,
    )
    with pytest.raises(MealDraftSaveError):
        ensure_meal_draft_persistable(d)


def test_meal_draft_calorie_totals_matches_sum() -> None:
    it = MealItemDraft(
        name="a",
        grams=100,
        calories=200,
        protein_g=10,
        fat_g=5,
        carbs_g=20,
    )
    mid, _, _ = meal_draft_calorie_totals([it])
    assert mid == 200
