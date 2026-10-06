#!/bin/sh
# Scheduled Machine: weekly pipeline (idempotent; acts Saturday 00:00 to Monday 06:00 BRT).
set -e
exec python -m app.pipeline.weekly
