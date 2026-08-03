"""
Supabase client wiring.

This module builds and caches a configured `supabase.Client`. It deliberately
does **no** reading or writing — no tables, no buckets, no auth calls. Its only
job is to be the single place that knows how to construct a client, so feature
code can later do::

    from apps.core.supabase import get_client

    rows = get_client().table('kpi_records').select('*').execute()

Which Supabase project it talks to comes from `SUPABASE_URL` /
`SUPABASE_ANON_KEY` in the environment (see .env.example). Development leaves
the Django ORM on the local Docker Postgres regardless — these settings drive
the HTTP API only, and are aimed at staging.

Nothing here runs at import time or at startup: the client is built lazily on
first use, so an unconfigured or unreachable Supabase project can never stop
the app from booting.
"""

from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

__all__ = [
    'SupabaseNotConfigured',
    'is_configured',
    'has_service_role',
    'get_client',
    'reset_clients',
]


class SupabaseNotConfigured(ImproperlyConfigured):
    """Raised when a client is requested but the credentials are missing."""


def is_configured():
    """True when a URL and the anon key are both present."""
    return bool(settings.SUPABASE_ENABLED)


def has_service_role():
    """True when the privileged service-role key is available."""
    return bool(settings.SUPABASE_SERVICE_ROLE_KEY)


@lru_cache(maxsize=2)
def get_client(service_role=False):
    """
    Return a cached Supabase client.

    ``service_role=True`` uses the service-role key, which BYPASSES Row Level
    Security — only for trusted server-side work (imports, admin jobs), never
    behind an end-user request whose access should be scoped by RLS.

    Raises ``SupabaseNotConfigured`` if the required settings are missing, so
    callers get a clear message instead of a confusing HTTP 401 later.
    """
    if not is_configured():
        raise SupabaseNotConfigured(
            'Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY '
            'in your environment (.env) — see .env.example.'
        )

    if service_role and not has_service_role():
        raise SupabaseNotConfigured(
            'SUPABASE_SERVICE_ROLE_KEY is not set, so no privileged client can '
            'be built. Set it in the server environment only — it bypasses Row '
            'Level Security and must never reach a browser.'
        )

    try:
        from supabase import Client, ClientOptions, create_client
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImproperlyConfigured(
            'The `supabase` package is not installed. It is pinned in '
            'requirements/base.txt — rebuild the image with '
            '`docker compose up --build`.'
        ) from exc

    key = settings.SUPABASE_SERVICE_ROLE_KEY if service_role else settings.SUPABASE_ANON_KEY

    client: Client = create_client(
        settings.SUPABASE_URL,
        key,
        options=ClientOptions(
            schema=settings.SUPABASE_SCHEMA,
            postgrest_client_timeout=settings.SUPABASE_TIMEOUT,
            storage_client_timeout=settings.SUPABASE_TIMEOUT,
            # This is a server process, not a browser: there is no session to
            # persist or refresh between requests.
            auto_refresh_token=False,
            persist_session=False,
        ),
    )
    return client


def reset_clients():
    """Drop the cached clients — for tests, or after changing settings."""
    get_client.cache_clear()
