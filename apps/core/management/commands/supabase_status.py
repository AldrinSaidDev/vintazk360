"""
Report how Supabase is wired in the current environment.

    docker compose exec web python manage.py supabase_status
    docker compose exec web python manage.py supabase_status --ping

Shows which project the settings point at, whether a client can be built, and
— with ``--ping`` — whether the Supabase API answers. It reads no table data.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.supabase import (
    SupabaseNotConfigured,
    get_client,
    has_service_role,
    is_configured,
)


def _mask(value):
    """Show enough of a key to identify it, never enough to use it."""
    if not value:
        return '(not set)'
    return f'{value[:8]}…{value[-4:]} ({len(value)} chars)'


class Command(BaseCommand):
    help = 'Show the Supabase configuration and optionally ping the API.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ping',
            action='store_true',
            help='Make one request to the Supabase Auth health endpoint.',
        )

    def handle(self, *args, **options):
        ok = self.style.SUCCESS
        warn = self.style.WARNING
        err = self.style.ERROR

        self.stdout.write(self.style.MIGRATE_HEADING('Supabase configuration'))
        self.stdout.write(f'  settings module   : {settings.SETTINGS_MODULE}')
        self.stdout.write(f'  SUPABASE_URL      : {settings.SUPABASE_URL or "(not set)"}')
        self.stdout.write(f'  anon key          : {_mask(settings.SUPABASE_ANON_KEY)}')
        self.stdout.write(f'  service-role key  : {_mask(settings.SUPABASE_SERVICE_ROLE_KEY)}')
        self.stdout.write(f'  schema / timeout  : {settings.SUPABASE_SCHEMA} / {settings.SUPABASE_TIMEOUT}s')

        # The ORM is a separate channel — say so plainly, it is the usual mix-up.
        db = settings.DATABASES['default']
        host = db.get('HOST') or '(default)'
        self.stdout.write(self.style.MIGRATE_HEADING('Django ORM database (separate channel)'))
        self.stdout.write(f'  host              : {host}:{db.get("PORT") or ""}')
        self.stdout.write(f'  name / ssl        : {db.get("NAME")} / {"required" if settings.DATABASE_SSL_REQUIRED else "disabled"}')
        if 'supabase' in str(host):
            self.stdout.write(ok('  → ORM is pointed at Supabase Postgres.'))
        else:
            self.stdout.write('  → ORM is pointed at the local development Postgres.')

        self.stdout.write(self.style.MIGRATE_HEADING('Client'))
        if not is_configured():
            self.stdout.write(warn('  Supabase is DISABLED (URL and/or anon key missing).'))
            self.stdout.write('  Set SUPABASE_URL and SUPABASE_ANON_KEY in .env to enable it.')
            return

        try:
            get_client()
        except SupabaseNotConfigured as exc:
            self.stdout.write(err(f'  Could not build client: {exc}'))
            return
        self.stdout.write(ok('  anon client       : built OK'))
        self.stdout.write(
            ok('  service client    : available')
            if has_service_role()
            else '  service client    : unavailable (no service-role key)'
        )

        if not options['ping']:
            self.stdout.write('\nRun with --ping to check that the API is reachable.')
            return

        self.stdout.write(self.style.MIGRATE_HEADING('Ping'))
        import httpx

        url = f'{settings.SUPABASE_URL}/auth/v1/health'
        try:
            response = httpx.get(
                url,
                headers={'apikey': settings.SUPABASE_ANON_KEY},
                timeout=settings.SUPABASE_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            self.stdout.write(err(f'  {url} → unreachable: {exc}'))
            return

        if response.is_success:
            self.stdout.write(ok(f'  {url} → {response.status_code} reachable'))
        else:
            self.stdout.write(err(f'  {url} → HTTP {response.status_code}: {response.text[:200]}'))
