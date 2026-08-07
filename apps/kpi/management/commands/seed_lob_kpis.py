"""Create real KPI rows from a LOB's static `kpis.py`.

    docker compose exec web python manage.py seed_lob_kpis          # every LOB
    docker compose exec web python manage.py seed_lob_kpis hr vct   # just these
    docker compose exec web python manage.py seed_lob_kpis --dry-run

A command rather than a data migration, for the same reason `seed_operations_kpis`
was one: this inserts BUSINESS data. A migration would force it on every
environment forever, including ones that have since edited or retired a KPI.

Idempotent by slug: a KPI whose slug already exists on the team is skipped, so
re-running after adding one entry to a `kpis.py` creates only that one. It never
updates an existing row, because by then the row is whatever the business edited
it to be and this file is only what it started as.

Sales is deliberately absent. Its KPIs are per branch and `kpi_definition.branch`
is not modelled by these flat `kpis.py` modules.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.module_loading import import_string

from apps.core.models import Team
from apps.kpi import seeding
from apps.kpi.models import KpiDefinition

# team slug → the module holding KPIS / MODAL_SPECS. The team slug is also the
# app label everywhere except where the two were named differently.
LOBS = [
    'operations',
    'nexzys',
    'hr',
    'academy',
    'finance',
    'sitelead',
    'vct',
    'smm',
    'content',
]


class Command(BaseCommand):
    help = "Create KpiDefinition rows from each LOB's static kpis.py."

    def add_arguments(self, parser):
        parser.add_argument('lobs', nargs='*', help='Team slugs; default is all.')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be created without writing anything.',
        )

    def handle(self, *args, **options):
        chosen = options['lobs'] or LOBS
        unknown = [slug for slug in chosen if slug not in LOBS]
        if unknown:
            raise CommandError(
                f'Not seedable: {", ".join(unknown)}. Known: {", ".join(LOBS)}.'
            )

        totals = {'created': 0, 'skipped': 0, 'failed': 0}

        for slug in chosen:
            totals_for_lob = self.seed_lob(slug, dry_run=options['dry_run'])
            for key, value in totals_for_lob.items():
                totals[key] += value

        self.stdout.write('')
        summary = (
            f'{totals["created"]} created, {totals["skipped"]} already existed, '
            f'{totals["failed"]} failed'
        )
        if options['dry_run']:
            self.stdout.write(self.style.WARNING(f'Dry run: {summary}. Nothing written.'))
        elif totals['failed']:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    def seed_lob(self, slug, *, dry_run):
        counts = {'created': 0, 'skipped': 0, 'failed': 0}

        try:
            team = Team.objects.get(slug=slug)
        except Team.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'{slug}: no Team row, skipped.'))
            return counts

        try:
            kpis = import_string(f'apps.{slug}.kpis.KPIS')
            specs = import_string(f'apps.{slug}.kpis.MODAL_SPECS')
        except ImportError as error:
            self.stdout.write(self.style.ERROR(f'{slug}: {error}'))
            return counts

        by_name = {spec['name']: spec for spec in specs}
        existing = set(
            KpiDefinition.objects.filter(team=team).values_list('slug', flat=True)
        )

        self.stdout.write(self.style.MIGRATE_HEADING(f'{team.name} ({slug})'))

        for position, kpi in enumerate(kpis, start=1):
            name = kpi['name']
            spec = by_name.get(name)

            if spec is None:
                # Without the operand labels there is nothing to build inputs
                # from, and a KPI with no inputs has no CSV columns (§6).
                counts['failed'] += 1
                self.stdout.write(
                    self.style.ERROR(f'  ! {name}: no MODAL_SPECS entry, skipped.')
                )
                continue

            # Matching on the slug the seeder would generate, so a KPI the
            # business has since renamed is not created a second time.
            from django.utils.text import slugify

            if slugify(name)[:110] in existing:
                counts['skipped'] += 1
                self.stdout.write(f'  = {name}')
                continue

            if dry_run:
                counts['created'] += 1
                self.stdout.write(self.style.SUCCESS(f'  + {name}'))
                continue

            try:
                with transaction.atomic():
                    definition = seeding.seed_kpi(
                        team, kpi, spec, sort_order=position
                    )
            except seeding.SeedError as error:
                counts['failed'] += 1
                self.stdout.write(self.style.ERROR(f'  ! {error}'))
            except Exception as error:  # noqa: BLE001 - report and keep going
                counts['failed'] += 1
                self.stdout.write(self.style.ERROR(f'  ! {name}: {error}'))
            else:
                counts['created'] += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  + {name}  →  {definition.formula_text}')
                )

        return counts
