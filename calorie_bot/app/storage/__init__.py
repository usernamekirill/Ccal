"""Pluggable persistence: DTOs, protocol, SQLAlchemy + HTTP backends."""

from calorie_bot.app.storage.dto import DailyAggregateDTO, MealDTO, MealItemDTO, UserSettingsDTO
from calorie_bot.app.storage.factory import create_sqlalchemy_storage, create_storage
from calorie_bot.app.storage.interface import StorageInterface
from calorie_bot.app.storage.sqlalchemy_backend import SqlAlchemyStorage

__all__ = [
    "DailyAggregateDTO",
    "MealDTO",
    "MealItemDTO",
    "SqlAlchemyStorage",
    "StorageInterface",
    "UserSettingsDTO",
    "create_sqlalchemy_storage",
    "create_storage",
]
