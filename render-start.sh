#!/usr/bin/env bash
# Start command for the Render web service (see render.yaml).
#
# Migrations and collectstatic run here rather than in the Docker build because
# the build has no DATABASE_URL and no SECRET_KEY — the environment variables
# only exist at run time.
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting gunicorn on 0.0.0.0:${PORT:-8000}..."
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
