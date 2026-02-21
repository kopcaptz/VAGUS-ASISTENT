#!/bin/bash
# Применение Alembic миграций.
# Запускайте из корня проекта или из любой директории — скрипт перейдёт в корень.
# Требует: VAGUS_DATABASE_URL или POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_DB

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Поддержка POSTGRES_* если VAGUS_DATABASE_URL не задан
if [ -z "$VAGUS_DATABASE_URL" ] && [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_PASSWORD" ]; then
  export VAGUS_DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST:-localhost}:5432/${POSTGRES_DB:-vagus_db}"
fi

echo "Applying Alembic migrations..."
alembic upgrade head
echo "Migrations applied successfully!"
