# CalorieBot — секреты только через env / env_file при запуске контейнера.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN chmod +x docker/entrypoint.sh \
    scripts/backup_postgres.sh \
    scripts/restore_postgres.sh \
    scripts/deploy.sh \
    scripts/restart.sh \
    scripts/logs.sh

HEALTHCHECK --interval=45s --timeout=15s --start-period=90s --retries=3 \
    CMD python scripts/healthcheck.py || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
