"""
Staging settings.

Select with ``DJANGO_SETTINGS_MODULE=config.settings.staging``.

Staging is the environment that runs against **Supabase** — both the Django ORM
(``DATABASE_URL`` pointed at Supabase Postgres) and the Supabase HTTP API
(``SUPABASE_URL`` / ``SUPABASE_ANON_KEY``). Development stays on the local
Docker Postgres and is unaffected by this module.

It inherits production's hardening so staging exercises the same code paths,
with two deliberate relaxations noted below.
"""

import os

from .prod import *  # noqa: F401,F403
from .base import SUPABASE_ENABLED

# HSTS is a browser-sticky promise: once sent, browsers refuse plain HTTP to
# that host for the whole max-age. That is right for the production domain and
# a nuisance on a throwaway staging one, so it is off unless explicitly set.
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = False

# Staging exists to exercise the Supabase wiring, so missing credentials are a
# misconfiguration worth failing fast on rather than discovering at first use.
if not SUPABASE_ENABLED:
    raise RuntimeError(
        'SUPABASE_URL and SUPABASE_ANON_KEY are required in staging. '
        'See .env.example.'
    )
