"""Atomic draft status transitions (no double-confirm under concurrent use)."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from calorie_bot.app.database.base import Base
from calorie_bot.app.database.models import Meal, User
from calorie_bot.app.domain import MealStatus
from calorie_bot.app.repositories.meal_repository import MealRepository


@pytest.mark.asyncio
async def test_transition_latest_draft_confirm_only_once_concurrent(tmp_path) -> None:
    """Two parallel confirms for the same draft: one succeeds, one gets None; meal stays confirmed once."""
    db_path = tmp_path / "atomic.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        s.add(User(telegram_id=424242, onboarding_completed=True))
        await s.flush()
        uid = (await s.execute(select(User.id).where(User.telegram_id == 424242))).scalar_one()
        s.add(
            Meal(
                user_id=uid,
                status=MealStatus.DRAFT.value,
                source="text",
                eaten_at=datetime.now(UTC),
                total_calories=100,
            )
        )
        await s.commit()

    async def confirm_once() -> bool:
        async with factory() as session:
            meal = await MealRepository(session).transition_latest_draft_status(
                uid,
                from_status=MealStatus.DRAFT.value,
                to_status=MealStatus.CONFIRMED.value,
            )
            await session.commit()
            return meal is not None

    wins = await asyncio.gather(confirm_once(), confirm_once())
    assert sum(1 for w in wins if w) == 1

    async with factory() as s:
        n_conf = (
            await s.execute(
                select(func.count())
                .select_from(Meal)
                .where(Meal.user_id == uid, Meal.status == MealStatus.CONFIRMED.value)
            )
        ).scalar_one()
        n_draft = (
            await s.execute(
                select(func.count())
                .select_from(Meal)
                .where(Meal.user_id == uid, Meal.status == MealStatus.DRAFT.value)
            )
        ).scalar_one()
    assert int(n_conf) == 1
    assert int(n_draft) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_transition_latest_draft_cancel_is_atomic(tmp_path) -> None:
    """Cancel uses the same atomic path; no draft left after one cancel."""
    db_path = tmp_path / "cancel.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        s.add(User(telegram_id=434343, onboarding_completed=True))
        await s.flush()
        uid = (await s.execute(select(User.id).where(User.telegram_id == 434343))).scalar_one()
        s.add(
            Meal(
                user_id=uid,
                status=MealStatus.DRAFT.value,
                source="text",
                eaten_at=datetime.now(UTC),
                total_calories=50,
            )
        )
        await s.commit()

    async def cancel_once() -> bool:
        async with factory() as session:
            meal = await MealRepository(session).transition_latest_draft_status(
                uid,
                from_status=MealStatus.DRAFT.value,
                to_status=MealStatus.CANCELLED.value,
            )
            await session.commit()
            return meal is not None

    wins = await asyncio.gather(cancel_once(), cancel_once())
    assert sum(1 for w in wins if w) == 1

    async with factory() as s:
        n_cancel = (
            await s.execute(
                select(func.count())
                .select_from(Meal)
                .where(Meal.user_id == uid, Meal.status == MealStatus.CANCELLED.value)
            )
        ).scalar_one()
    assert int(n_cancel) == 1

    await engine.dispose()
