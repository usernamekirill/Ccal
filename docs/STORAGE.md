# Хранение данных и статистика

## 1. Архитектура (три слоя)

```
Handlers  →  Services (StatsService, …)  →  Repositories (legacy SQLAlchemy)
                     ↘
               StorageInterface  ←→  SqlAlchemyStorage | ExternalAPIStorage
                     ↘
            DTO (MealDTO, DailyAggregateDTO, …)
```

- **Storage Adapter** — `calorie_bot/app/storage/`: протокол `StorageInterface`, реализации без логики продуктовых сценариев.
- **Repository** — существующие классы в `repositories/` остаются для пошаговой миграции; они по-прежнему используют `AsyncSession`.
- **Service** — `StatsService` не импортирует SQLAlchemy; агрегаты дня дополнительно ведутся в таблице `daily_stats` (денормализация).

Точка переключения бэкенда: `DATABASE_TYPE` + `DATABASE_URL` (или REST для `external`).

## 2. Файлы

| Модуль | Назначение |
|--------|------------|
| `storage/dto.py` | DTO без ORM |
| `storage/interface.py` | `StorageInterface` (Protocol) |
| `storage/sqlalchemy_backend.py` | SQLite + Postgres (один код) |
| `storage/sqlite_storage.py` / `postgres_storage.py` | Алиасы + заметки по деплою |
| `storage/external_api_storage.py` | `httpx`, retry, timeout |
| `storage/factory.py` | `create_storage` / `create_sqlalchemy_storage` |
| `storage/cache.py` | опциональный TTL-кэш для горячих чтений |
| `services/daily_stats_sync.py` | синхронизация `daily_stats` при confirm / редактировании / delete |
| `utils/stat_anchor.py` | локальная полночь для ключа дня |

В **middleware** в каждый запрос передаётся `data["storage"]` (`SqlAlchemyStorage`, опционально обёрнутый в `CachingStorageWrapper`).

## 3. Таблица `daily_stats`

Уже в моделях: уникальный ключ `(user_id, stat_date)`. При подтверждении приёма, при правке сохранённого приёма (подтверждение после «Сегодня» → редактирование) и при удалении из «Сегодня» вызываются `add_confirmed_meal_totals` / `subtract_confirmed_meal_totals` — меньше пересчётов для трендов и внешних API.

## 4. REST API (контракт для ExternalAPIStorage)

База URL: `EXTERNAL_STORAGE_BASE_URL`. Заголовок `Authorization: Bearer <EXTERNAL_STORAGE_API_KEY>` если ключ задан.

| Метод | Путь | Назначение |
|--------|------|------------|
| POST | `/meals` | создать приём (тело как JSON meal) |
| POST | `/meals/batch` | пакетное сохранение |
| GET | `/meals?user_id=&date=&tz=` | приёмы за локальный день |
| GET | `/meals/range` | `user_id`, `start`, `end` ISO |
| DELETE | `/meals/{id}?user_id=` | soft-delete на стороне API |
| GET | `/settings/{user_id}` | настройки |
| POST | `/settings` | upsert |
| GET | `/stats/daily` | `user_id`, `date` |
| GET | `/stats/range` | `user_id`, `start`, `end` даты |

Ответы — JSON, поля совместимы с `_meal_from_json` / `_aggregate_from_json` в `external_api_storage.py`.

## 5. Миграция SQLite → PostgreSQL

1. Остановить бота.
2. `sqlite3 data/calorie_bot.db .dump > dump.sql` (или alembic revision на пустой PG).
3. Создать БД Postgres, применить те же Alembic-миграции: `alembic upgrade head` с `DATABASE_URL=postgresql+asyncpg://...`.
4. Перенести данные (ETL: скрипт или `pgloader` со SQLite).
5. Выставить `DATABASE_URL` на Postgres, `DATABASE_TYPE=postgres` (опционально, для ясности).
6. Установить драйвер: `asyncpg` уже в `requirements.txt`; при установке из `pyproject.toml` зависимости тоже включают `asyncpg`.

## 6. Оптимизация под Telegram

- Асинхронные I/O, короткий timeout для внешнего API (`EXTERNAL_STORAGE_TIMEOUT_SECONDS`, по умолчанию 2 с).
- Один запрос на окно в `get_calorie_trend`.
- Пул соединений Postgres: `POSTGRES_POOL_SIZE`, `POSTGRES_MAX_OVERFLOW`.
- Кэш: `STATS_CACHE_TTL_SECONDS` > 0 включает процессный TTL только для `get_daily_aggregates` на обёртке.

## 7. Безопасность

- В БД не кладутся токены бота/OpenAI.
- Медиа не хранятся (временные файлы на диске).
- Soft delete для приёмов; полное удаление пользователя — через существующие purge-репозитории.

## 8. Ограничения MVP

- Монолитный бот при `DATABASE_TYPE=external` не стартует: нет SQL-сессии для текущих репозиториев — внешний режим рассчитан на отдельный HTTP-worker или постепенный перевод хендлеров на `data["storage"]`.

### Расхождение `daily_stats` с историческими данными

После старых версий бота или ручных правок в БД строки `daily_stats` могут не совпасть с суммой по `meals`. Исправление без массового рефакторинга: одноразовый SQL/скрипт пересчёта по `meals` за нужный период либо удаление строк `daily_stats` и ленивая пересборка при следующих событиях (если добавите job). Текущий код синхронизирует роллапы при confirm, редактировании сохранённого приёма (фото-флоу «Сегодня») и soft-delete.
