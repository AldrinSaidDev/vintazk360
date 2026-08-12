"""
Staging settings.

Select with ``DJANGO_SETTINGS_MODULE=config.settings.staging``.

Staging is the deployed environment: a **Render** web service, a **Render
Postgres** database (``DATABASE_URL``) and a **Cloudflare R2** bucket for
uploaded files (``R2_*``). Development stays on the local Docker Postgres and is
unaffected by this module.

It inherits production's hardening so staging exercises the same code paths,
with two deliberate relaxations noted below.
"""

import os

from .prod import *  # noqa: F401,F403
from .base import R2_ENABLED

# HSTS is a browser-sticky promise: once sent, browsers refuse plain HTTP to
# that host for the whole max-age. That is right for the production domain and
# a nuisance on a throwaway staging one, so it is off unless explicitly set.
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = False

# Staging exists to exercise the deployed wiring, so missing storage
# credentials are a misconfiguration worth failing fast on rather than
# discovering at the first CSV upload.
if not R2_ENABLED:
    raise RuntimeError(
        'Cloudflare R2 is required in staging: set R2_ACCOUNT_ID, '
        'R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET. See .env.example.'
    )
