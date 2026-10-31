#!/bin/sh
set -e
case "$1" in
  api)
    python -m finops_api.cli migrate
    python -m finops_api.cli seed-pricing
    if [ "$FINOPS_ENV" = "dev" ]; then python -m finops_api.cli seed-demo-user; fi
    exec uvicorn finops_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' \
      --workers "${API_WORKERS:-2}" --no-access-log
    ;;
  worker)
    exec celery -A finops_worker.tasks worker --loglevel=INFO --concurrency "${WORKER_CONCURRENCY:-2}"
    ;;
  beat)
    exec celery -A finops_worker.tasks beat --loglevel=INFO --schedule /app/var/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
