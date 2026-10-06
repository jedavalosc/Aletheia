#!/bin/sh
# Web process: apply migrations (idempotent), optionally load seed data, then serve.
set -e
alembic upgrade head
# AUTO_SEED=demo loads the Brazil configuration and the fictional demo edition
# the first time (needed on hosts without a shell, such as Render's free plan).
if [ "$AUTO_SEED" = "demo" ] || [ "$AUTO_SEED" = "brasil" ]; then
  python -m app.cli seed-brasil
  [ "$AUTO_SEED" = "demo" ] && python -m app.cli seed-demo --se-ausente
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips='*'
