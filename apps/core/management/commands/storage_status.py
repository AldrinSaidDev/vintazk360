"""
Report how object storage and the database are wired in this environment.

    docker compose exec web python manage.py storage_status
    docker compose exec web python manage.py storage_status --ping

Shows which Cloudflare R2 bucket the settings point at, whether a client can be
built, which database the ORM is on, and — with ``--ping`` — whether the bucket
actually answers. It reads no objects and no table data.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.storage import R2NotConfigured, get_client, is_configured


def _mask(value):
    """Show enough of a key to identify it, never enough to use it."""
    if not value:
        return '(not set)'
    return f'{value[:6]}…{value[-4:]} ({len(value)} chars)'


class Command(BaseCommand):
    help = 'Show the Cloudflare R2 / database configuration and optionally ping the bucket.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ping',
            action='store_true',
            help='Make one request to the R2 bucket to prove the credentials work.',
        )

    def handle(self, *args, **options):
        ok = self.style.SUCCESS
        warn = self.style.WARNING
        err = self.style.ERROR

        self.stdout.write(self.style.MIGRATE_HEADING('Cloudflare R2 (object storage)'))
        self.stdout.write(f'  settings module   : {settings.SETTINGS_MODULE}')
        self.stdout.write(f'  endpoint          : {settings.R2_ENDPOINT_URL or "(not set)"}')
        self.stdout.write(f'  bucket            : {settings.R2_BUCKET or "(not set)"}')
        self.stdout.write(f'  access key id     : {_mask(settings.R2_ACCESS_KEY_ID)}')
        self.stdout.write(f'  secret access key : {_mask(settings.R2_SECRET_ACCESS_KEY)}')
        self.stdout.write(f'  region / timeout  : {settings.R2_REGION} / {settings.R2_TIMEOUT}s')
        self.stdout.write(f'  signed URL TTL    : {settings.R2_SIGNED_URL_TTL}s')

        # The ORM is a separate channel — say so plainly, it is the usual mix-up.
        db = settings.DATABASES['default']
        host = db.get('HOST') or '(default)'
        self.stdout.write(self.style.MIGRATE_HEADING('Django ORM database (separate channel)'))
        self.stdout.write(f'  host              : {host}:{db.get("PORT") or ""}')
        self.stdout.write(
            f'  name / ssl        : {db.get("NAME")} / '
            f'{"required" if settings.DATABASE_SSL_REQUIRED else "disabled"}'
        )
        if 'render.com' in str(host) or str(host).endswith('-a'):
            self.stdout.write(ok('  → ORM is pointed at Render Postgres.'))
        elif str(host) in {'db', 'localhost', '127.0.0.1'}:
            self.stdout.write('  → ORM is pointed at the local development Postgres.')
        else:
            self.stdout.write(warn('  → ORM is pointed at a remote database.'))

        self.stdout.write(self.style.MIGRATE_HEADING('Client'))
        if not is_configured():
            self.stdout.write(warn('  R2 is DISABLED (endpoint, bucket and/or keys missing).'))
            self.stdout.write(
                '  Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and '
                'R2_BUCKET in .env to enable it.'
            )
            return

        try:
            client = get_client()
        except R2NotConfigured as exc:
            self.stdout.write(err(f'  Could not build client: {exc}'))
            return
        self.stdout.write(ok('  s3 client         : built OK'))

        if not options['ping']:
            self.stdout.write('\nRun with --ping to check that the bucket is reachable.')
            return

        self.stdout.write(self.style.MIGRATE_HEADING('Ping'))
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            client.head_bucket(Bucket=settings.R2_BUCKET)
        except ClientError as exc:
            code = exc.response.get('Error', {}).get('Code', '?')
            self.stdout.write(err(f'  {settings.R2_BUCKET} → HTTP {code}: {exc}'))
            if code in {'403', 'AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch'}:
                self.stdout.write(
                    '  Check the API token has Object Read & Write on this bucket.'
                )
            elif code in {'404', 'NoSuchBucket'}:
                self.stdout.write('  The bucket does not exist in this R2 account.')
            return
        except BotoCoreError as exc:
            self.stdout.write(err(f'  {settings.R2_ENDPOINT_URL} → unreachable: {exc}'))
            return

        self.stdout.write(ok(f'  {settings.R2_BUCKET} → reachable, credentials accepted'))
