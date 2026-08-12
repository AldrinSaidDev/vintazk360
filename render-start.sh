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

# First-login bootstrap. Render's free instance types have no Shell, so without
# this a successful deploy lands on a login screen nobody can get past. Both
# steps are idempotent and safe to run on every boot.
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    # The username is read from the environment inside Python rather than
    # interpolated into the snippet, so it is never parsed as code.
    if python manage.py shell -c "
import os, sys
from django.contrib.auth import get_user_model
sys.exit(0 if get_user_model().objects.filter(
    username=os.environ['DJANGO_SUPERUSER_USERNAME']).exists() else 1)
"; then
        echo "Superuser '${DJANGO_SUPERUSER_USERNAME}' already exists, skipping."
    else
        echo "Creating superuser '${DJANGO_SUPERUSER_USERNAME}'..."
        # createsuperuser --noinput reads DJANGO_SUPERUSER_{USERNAME,EMAIL,PASSWORD}.
        # EMAIL is required because it is in the User model's REQUIRED_FIELDS.
        DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" \
            python manage.py createsuperuser --noinput
    fi
else
    echo "DJANGO_SUPERUSER_USERNAME / _PASSWORD not set, skipping superuser bootstrap."
fi

# Idempotent by slug: an existing KPI is skipped and never updated, so this
# cannot overwrite anything the business has since edited or deleted.
if [ "${SEED_KPIS:-true}" = "true" ]; then
    echo "Seeding LOB KPIs..."
    python manage.py seed_lob_kpis
else
    echo "SEED_KPIS is not 'true', skipping KPI seeding."
fi

echo "Starting gunicorn on 0.0.0.0:${PORT:-8000}..."
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
