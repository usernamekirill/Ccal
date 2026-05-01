#!/usr/bin/env bash
# Обновить код и пересобрать стек.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull
docker compose up -d --build
