#!/bin/sh
set -e
case "$1" in
  api)
    python -m pendar_api.cli migrate
    python -m pendar_api.cli seed-pricing
    if [ "$PENDAR_ENV" = "dev" ]; then python -m pendar_api.cli seed-demo-user; fi
    exec uvicorn pendar_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' \
      --workers "${API_WORKERS:-2}" --no-access-log
    ;;
  worker)
    exec celery -A pendar_worker.tasks worker --loglevel=INFO --concurrency "${WORKER_CONCURRENCY:-2}"
    ;;
  beat)
    exec celery -A pendar_worker.tasks beat --loglevel=INFO --schedule /app/var/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
