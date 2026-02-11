#!/usr/bin/env sh
set -eu

if [ "${MIGRATE_ON_START:-0}" = "1" ]; then
  python -m app.infra.db.sqlite_legacy_repair
  echo "Running Alembic migrations..."
  alembic upgrade head
fi

exec "$@"
