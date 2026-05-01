#!/usr/bin/env bash
# Дамп БД из контейнера postgres (порт наружу не нужен).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/backups}"
mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
OUT_GZ="${BACKUP_DIR}/calorie_pg_${TS}.sql.gz"

docker compose exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' \
  | gzip -c > "$OUT_GZ"

find "$BACKUP_DIR" -name 'calorie_pg_*.sql.gz' -type f -mtime +14 -delete

echo "backup_ok path=$OUT_GZ"
