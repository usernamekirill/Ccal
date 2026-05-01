#!/usr/bin/env bash
# Восстановление из .sql.gz (контейнер postgres должен быть запущен; бот будет остановлен).
# Использование: ./scripts/restore_postgres.sh path/to/calorie_pg_*.sql.gz
# Или без аргумента — последний файл в backups/
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BACKUP="${1:-}"
if [[ -z "$BACKUP" ]]; then
  BACKUP="$(ls -t "${ROOT_DIR}"/backups/calorie_pg_*.sql.gz 2>/dev/null | head -1 || true)"
fi

if [[ -z "$BACKUP" || ! -f "$BACKUP" ]]; then
  echo "usage: $0 [backups/calorie_pg_YYYYMMDD_HHMMSS.sql.gz]" >&2
  exit 1
fi

echo "Stopping bot..."
docker compose stop bot

echo "Restoring from $BACKUP (ON_ERROR_STOP)..."
gunzip -c "$BACKUP" | docker compose exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'

echo "Starting bot..."
docker compose start bot
echo "restore_ok"
