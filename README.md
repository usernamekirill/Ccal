# Calorie Telegram Bot (MVP)

Бот для учёта калорий: фото еды, текст, голос и голосовые правки к черновику. Команды **статистики**, **трендов** и **настроек** подключены. Секреты задаются **только через `.env`**, в коде токенов нет.

## Что уже собрано

- Точка входа: `main.py` (корень) или `python -m calorie_bot.app.main`
- Роутеры зарегистрированы в `calorie_bot/app/bot/dispatcher.py`
- БД: SQLAlchemy async + Alembic; инициализация: `init_db.py`
- Ошибки и лимиты ИИ: middleware в `calorie_bot/app/middleware/`

## Быстрый старт (macOS / Linux)

```bash
cd "/path/to/CB"   # корень репозитория, где лежат main.py и alembic.ini

python3 -m venv .venv
source .venv/bin/activate

# Вариант A — установка как пакет (удобно для разработки)
pip install -e ".[dev]"

# Вариант B — только зависимости из файла
# pip install -r requirements.txt
# pip install -e . --no-deps

cp .env.example .env
# Откройте .env и подставьте реальные TELEGRAM_BOT_TOKEN и OPENAI_API_KEY

python init_db.py
python main.py
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
# Заполните .env
python init_db.py
python main.py
```

## Структура проекта (финальная, логические блоки)

```text
CB/
├── main.py                 # Запуск бота из корня
├── init_db.py              # alembic upgrade head
├── alembic.ini
├── requirements.txt        # pip-зависимости
├── pyproject.toml          # пакет + dev-зависимости
├── .env.example
├── calorie_bot/
│   └── app/
│       ├── main.py         # async main, polling, опционально health
│       ├── config.py       # настройки из env
│       ├── bot/
│       │   ├── dispatcher.py   # все routers + middleware
│       │   └── middleware.py   # сессия БД
│       ├── middleware/     # ошибки, rate limit
│       ├── health/         # GET /health (опционально)
│       ├── handlers/       # только Telegram-слой → сервисы
│       ├── services/       # бизнес-логика
│       ├── repositories/   # доступ к БД
│       ├── ai/             # OpenAI-клиенты
│       ├── database/       # модели, миграции
│       ├── messages/       # тексты ошибок и шаблоны
│       ├── texts/          # онбординг / настройки
│       ├── keyboards/
│       ├── states/
│       ├── stats/          # форматирование статистики
│       ├── trends/         # форматирование трендов
│       └── utils/
└── tests/
```

## Команды

| Действие | Команда |
|----------|---------|
| Создать/обновить таблицы БД | `python init_db.py` |
| Запустить бота | `python main.py` или `python -m calorie_bot.app.main` |
| Тесты | `pytest` |
| Линтер | `ruff check calorie_bot tests` |

## Как пользоваться боту (MVP-сценарии)

Проверьте по чеклисту ниже в реальном Telegram:

1. **Новый пользователь** — `/start`, приветствие, создание записи пользователя.
2. **Онбординг** — выбор цели, калорий (ручной/расчёт/пропуск), подтверждение; после этого доступны еда и меню.
3. **Фото еды** — отправить фото → черновик с КБЖУ → экран подтверждения.
4. **Подтверждение** — подтвердить или отменить черновик (`meal_confirmation`, клавиатуры фото).
5. **Голосовое добавление** — голос/аудио без активного черновика → текст → разбор еды (ИИ).
6. **Голосовая корректировка** — сначала фото/черновик, затем голос → правка черновика.
7. **Текстовое добавление** — описание еды текстом (не команда) → черновик.
8. **Статистика** — команды из `stats_handler` (см. бота: обычно `/stats` или кнопки меню, если добавлены в `start`).
9. **Тренд** — команды из `trend_handler` (окна 7/14/30 дней).
10. **Настройки** — `/settings` (цель ккал, часовой пояс, уведомления, мотивация, ИИ, единицы, профиль, удаление данных).

Точные тексты команд смотрите в `calorie_bot/app/handlers/stats_handler.py`, `trend_handler.py`, `start.py` (меню).

## Принципы MVP

- Результат ИИ — **черновик**, пока пользователь не подтвердил.
- Фото и аудио хранятся **временно** на диске, долгосрочно не сохраняются.
- **Handlers** вызывают **services**; **services** — **repositories** и AI-клиенты.
- Основные пользовательские тексты — в `calorie_bot/app/messages/` и `calorie_bot/app/texts/`.

## Checklist готовности MVP

- [ ] Python 3.11+ установлен
- [ ] Виртуальное окружение создано и активировано
- [ ] Выполнено `pip install -e ".[dev]"` или `pip install -r requirements.txt` + `pip install -e .`
- [ ] Файл `.env` скопирован из `.env.example`, заполнены **только** `TELEGRAM_BOT_TOKEN` и `OPENAI_API_KEY` (остальное можно по умолчанию)
- [ ] Выполнено `python init_db.py` без ошибок
- [ ] `python main.py` запускается, в логах нет падения на старте
- [ ] Пройден онбординг под тестовым аккаунтом
- [ ] Фото → черновик → подтверждение
- [ ] Голос и текст еды
- [ ] Статистика и тренд открываются
- [ ] `/settings` открывается после завершённого онбординга
- [ ] (Опционально) `HEALTH_CHECK_PORT>0` — `curl http://127.0.0.1:<port>/health` отвечает `ok`

## Проблемы

- **`TELEGRAM_BOT_TOKEN is required`** — в `.env` пустой токен или файл не в корне проекта.
- **Ошибки миграций** — запускайте `init_db.py` из корня, где лежит `alembic.ini`.
- **ИИ не отвечает** — проверьте `OPENAI_API_KEY`, лимиты и что в настройках бота не отключён «AI-анализ».
