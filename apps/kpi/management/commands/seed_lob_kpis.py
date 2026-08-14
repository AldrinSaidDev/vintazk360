"""Create real KPI rows from a LOB's static `kpis.py`.

    docker compose exec web python manage.py seed_lob_kpis          # every LOB
    docker compose exec web python manage.py seed_lob_kpis hr vct   # just these
    docker compose exec web python manage.py seed_lob_kpis --dry-run

A command rather than a data migration, for the same reason `seed_operations_kpis`
was one: this inserts BUSINESS data. A migration would force it on every
environment forever, including ones that have since edited or retired a KPI.

Idempotent by slug: a KPI whose slug already exists in the same scope is
skipped, so re-running after adding one entry to a `kpis.py` creates only that
one. It never updates an existing row, because by then the row is whatever the
business edited it to be and this file is only what it started as.

**Sales and Operations are branch teams.** Their data lives in
`apps/<slug>/branches.py` as `BRANCHES` rather than a flat `KPIS`/`MODAL_SPECS`
pair, and each branch seeds a `kpi_branch` row plus its own KPIs. Slugs are
unique per `(team, branch)`, so two branches may each own the same KPI name.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.module_loading import import_string
from django.utils.text import slugify

from apps.core.models import Team
from apps.kpi import seeding
from apps.kpi.models import KpiBranch, KpiDefinition

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
    'sales',
]

# Branch teams keep their KPIs under `apps.<slug>.branches.BRANCHES` instead of a
# flat KPIS/MODAL_SPECS pair, because each branch is its own scope.
BRANCHED = {'sales', 'operations'}


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
            if slug in BRANCHED:
                totals_for_lob = self.seed_branched_lob(
                    slug, dry_run=options['dry_run']
                )
            else:
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
            self.seed_one(
                team, kpi, by_name.get(kpi['name']), existing, counts,
                sort_order=position, dry_run=dry_run,
            )

        return counts

    # --- branch teams ------------------------------------------------------

    def seed_branched_lob(self, slug, *, dry_run):
        """Seed a team whose KPIs hang off branches (Sales).

        The `kpi_branch` rows are created here too: they are the scope every KPI
        below is keyed to, so seeding one without the other would put the whole
        team's KPIs at team level where no screen looks for them.
        """
        counts = {'created': 0, 'skipped': 0, 'failed': 0}

        try:
            team = Team.objects.get(slug=slug)
        except Team.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'{slug}: no Team row, skipped.'))
            return counts

        try:
            branches = import_string(f'apps.{slug}.branches.BRANCHES')
        except ImportError as error:
            self.stdout.write(self.style.ERROR(f'{slug}: {error}'))
            return counts

        self.stdout.write(self.style.MIGRATE_HEADING(f'{team.name} ({slug})'))

        for order, (branch_slug, spec) in enumerate(branches.items(), start=1):
            if dry_run:
                branch = KpiBranch.objects.filter(team=team, slug=branch_slug).first()
            else:
                branch, made = KpiBranch.objects.get_or_create(
                    team=team,
                    slug=branch_slug,
                    defaults={'name': spec['name'], 'order': order},
                )
                if made:
                    self.stdout.write(self.style.SUCCESS(f'  branch + {branch.name}'))

            self.stdout.write(f'  {spec["name"]}')

            by_name = {m['name']: m for m in spec['modal_kpis']}
            existing = set(
                KpiDefinition.objects.filter(team=team, branch=branch)
                .values_list('slug', flat=True)
            ) if branch else set()

            for position, kpi in enumerate(spec['kpis'], start=1):
                self.seed_one(
                    team, kpi, by_name.get(kpi['name']), existing, counts,
                    branch=branch, sort_order=position, dry_run=dry_run,
                    indent='    ',
                )

        return counts

    def seed_one(self, team, kpi, spec, existing, counts, *,
                 branch=None, sort_order=0, dry_run=False, indent='  '):
        """Create one KPI, or report why it was skipped. Updates `counts`."""
        name = kpi['name']

        if spec is None:
            # Without the operand labels there is nothing to build inputs from,
            # and a KPI with no inputs has no CSV columns (§6).
            counts['failed'] += 1
            self.stdout.write(
                self.style.ERROR(f'{indent}! {name}: no modal spec, skipped.')
            )
            return

        # Matching on the slug the seeder would generate, so a KPI the business
        # has since renamed is not created a second time.
        if slugify(name)[:110] in existing:
            counts['skipped'] += 1
            self.stdout.write(f'{indent}= {name}')
            return

        if dry_run:
            counts['created'] += 1
            self.stdout.write(self.style.SUCCESS(f'{indent}+ {name}'))
            return

        try:
            with transaction.atomic():
                definition = seeding.seed_kpi(
                    team, kpi, spec, branch=branch, sort_order=sort_order
                )
        except seeding.SeedError as error:
            counts['failed'] += 1
            self.stdout.write(self.style.ERROR(f'{indent}! {error}'))
        except Exception as error:  # noqa: BLE001 - report and keep going
            counts['failed'] += 1
            self.stdout.write(self.style.ERROR(f'{indent}! {name}: {error}'))
        else:
            counts['created'] += 1
            self.stdout.write(
                self.style.SUCCESS(f'{indent}+ {name}  →  {definition.formula_text}')
            )
