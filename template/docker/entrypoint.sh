#!/bin/sh

set -eu

# One image runs three processes. The Dockerfile's CMD selects "web".
# Any other command runs as given, such as `python manage.py createsuperuser`.
case "${1:-web}" in
web)
    echo "Migrating database..."
    python manage.py migrate

    echo "Starting granian..."
    exec python manage.py serve
    ;;
worker)
    # db_worker fails on any task backend other than django_tasks_db's, the default.
    exec python manage.py db_worker
    ;;
scheduler)
    # The heartbeat serves Sentry cron monitors and otherwise adds a task every minute.
    exec python manage.py crontask --no-heartbeat
    ;;
*)
    exec "$@"
    ;;
esac
