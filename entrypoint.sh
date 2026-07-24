#!/usr/bin/env bash
# Container entrypoint for the `web` service.
# Applies database migrations, then starts the Django dev server.
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Starting development server on 0.0.0.0:8000..."
exec python manage.py runserver 0.0.0.0:8000
