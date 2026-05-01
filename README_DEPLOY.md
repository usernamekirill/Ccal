# CalorieBot — деплой на VPS (Docker + PostgreSQL)

Цель: **push в GitHub → clone на сервер → `.env` → `docker compose up -d --build` → бот 24/7**, PostgreSQL только во внутренней сети Docker (порт наружу не публикуется), бэкапы в `./backups/`.

Стек: **Python 3.11**, **aiogram 3.x**, **SQLAlchemy async**, драйвер **asyncpg**, миграции **Alembic** (`init_db.py` при каждом старте контейнера).

---

## Часть 1 — GitHub (локально)

```bash
cd /path/to/CB
git init
git add .
git commit -m "init: CalorieBot"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

В репозитории **нет** `.env`, `logs/`, `backups/`, `*.db` (см. `.gitignore`).

---

## Часть 2 — Сервер (SSH, Docker, Git)

```bash
ssh root@YOUR_VPS_IP
```

Установка Docker (Ubuntu, пример):

```bash
apt-get update && apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

Проверка: `docker compose version`

---

## Часть 3 — Запуск

```bash
mkdir -p /srv/caloriebot && cd /srv/caloriebot
git clone https://github.com/YOUR_USER/YOUR_REPO.git .
cp .env.example .env
nano .env   # BOT_TOKEN, OPENAI_API_KEY, POSTGRES_PASSWORD, DATABASE_URL (пароль как в POSTGRES_PASSWORD)
mkdir -p logs tmp backups
chmod +x scripts/*.sh
docker compose up -d --build
docker compose ps
docker compose logs -f bot
```

Переменная **`BOT_TOKEN`** читается приложением (алиас к `TELEGRAM_BOT_TOKEN`). Пароль в `DATABASE_URL` должен совпадать с `POSTGRES_PASSWORD`.

---

## Часть 4 — Обновление кода

```bash
cd /srv/caloriebot
./scripts/deploy.sh
```

Вручную: `git pull && docker compose up -d --build`

---

## Часть 5 — Логи

```bash
./scripts/logs.sh
# или
docker compose logs -f bot
```

---

## Часть 6 — Бэкапы

Ручной дамп:

```bash
./scripts/backup_postgres.sh
```

Файлы: `backups/calorie_pg_YYYYMMDD_HHMMSS.sql.gz`, удаление старше **14 дней**.

**Cron (ежедневно в 03:00):**

```cron
0 3 * * * cd /srv/caloriebot && /usr/bin/env bash ./scripts/backup_postgres.sh >> /srv/caloriebot/logs/backup.log 2>&1
```

---

## Часть 7 — Восстановление

```bash
cd /srv/caloriebot
./scripts/restore_postgres.sh backups/calorie_pg_XXXXXX.sql.gz
# или последний автоматически:
./scripts/restore_postgres.sh
```

Скрипт останавливает **bot**, заливает дамп в БД через `psql`, снова запускает **bot**. При конфликтах объектов сначала восстановите на пустую БД (см. документацию PostgreSQL / `pg_dump --clean` при создании дампа).

---

## Управление

| Действие | Команда |
|----------|---------|
| Деплой | `./scripts/deploy.sh` |
| Перезапуск | `./scripts/restart.sh` |
| Логи | `./scripts/logs.sh` |
| Health | `docker compose exec bot python scripts/healthcheck.py` |
| Остановка | `docker compose down` |
| Удалить и данные БД | `docker compose down -v` (осторожно) |

---

## Безопасность (чеклист)

- Секреты только в `.env`, не в образе.
- Postgres **без** секции `ports:` — доступ только контейнерам сети compose.
- Токены в логи чатов не попадают по штатной обработке ошибок.
- Фото/аудио — временные файлы (`TEMP_MEDIA_DIR`, volume `./tmp`).
- Удаление данных пользователя — через сценарии приложения (настройки / purge).

---

## Проверка проекта

| Пункт | Статус |
|-------|--------|
| `main.py` | Корневая точка входа |
| `requirements.txt` | aiogram 3.x, SQLAlchemy[asyncio], asyncpg |
| Storage | `DATABASE_TYPE` sqlite / postgres / external (монолит: не external) |
| SQLite | Не обязателен для продакшена |
| Токены в коде | Нет |
| Индексы | `user_id`, `eaten_at` / `daily_stats` по дате — в миграциях Alembic |

---

## Команды «с нуля» (шпаргалка)

**Локально**

```text
git init && git add . && git commit -m "init" && git remote add origin ... && git push -u origin main
```

**Сервер**

```text
ssh root@IP
git clone ... /srv/caloriebot && cd /srv/caloriebot
cp .env.example .env && nano .env
mkdir -p logs tmp backups && chmod +x scripts/*.sh
docker compose up -d --build
```

**Обновление**

```text
git pull && docker compose up -d --build
```
