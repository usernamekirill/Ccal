#!/usr/bin/env bash
# Первый push на GitHub через GitHub CLI (после: gh auth login).
# Использование из корня репозитория:
#   gh auth login
#   ./scripts/first_push_github.sh
#
# Имя репозитория (по умолчанию calorie-bot):
#   GITHUB_REPO_NAME=my-calorie-bot ./scripts/first_push_github.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v gh >/dev/null 2>&1; then
  echo "Установите GitHub CLI: brew install gh"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Сначала войдите в GitHub (один раз на этом компьютере):"
  echo ""
  echo "  gh auth login"
  echo ""
  echo "Выберите: GitHub.com → HTTPS → «Login with a web browser»."
  exit 1
fi

REPO_NAME="${GITHUB_REPO_NAME:-calorie-bot}"
LOGIN="$(gh api user -q .login)"
echo "Аккаунт GitHub: $LOGIN"
echo "Имя репозитория: $REPO_NAME"

if git remote get-url origin >/dev/null 2>&1; then
  echo "Remote origin уже есть. Выполняю: git push -u origin main"
  git push -u origin main
  echo "Готово: https://github.com/$LOGIN/$REPO_NAME"
  exit 0
fi

echo "Создаю репозиторий на GitHub и пушу main..."
gh repo create "$REPO_NAME" \
  --private \
  --source=. \
  --remote=origin \
  --description="CalorieBot — Telegram-бот учёта калорий" \
  --push

echo "Готово: https://github.com/$LOGIN/$REPO_NAME"
