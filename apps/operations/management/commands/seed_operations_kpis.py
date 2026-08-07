"""Turn the six hard-coded Operations KPIs into real `kpi_definition` rows.

Rollout step 2/3 of `db_schema.txt` Part E, for one team. Operations is the
exception the doc calls out: its KPIs are described with `numerator` /
`denominator` labels rather than a calculation type, so the mapping to an
expression is done here rather than derived from a `MODAL_SPECS` block.

A command rather than a data migration — this is business data, and a migration
that inserts it is awkward to undo. Idempotent: a KPI whose slug already exists
for Operations is left alone, so re-running is safe.

    docker compose exec web python manage.py seed_operations_kpis
"""

import re

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.core.models import Team
from apps.kpi import formula as formula_engine
from apps.kpi.models import (
    Direction,
    DisplayFormat,
    Frequency,
    KpiCategory,
    KpiDefinition,
    KpiFormulaHistory,
    KpiInput,
)
from apps.operations.views import _MODAL_KPIS, _OPERATIONS_KPIS

# _MODAL_KPIS carries the operand labels, _OPERATIONS_KPIS the rest of the
# definition; they are keyed on the KPI name.
_SPECS = [
    {**modal, **master}
    for modal in _MODAL_KPIS
    for master in _OPERATIONS_KPIS
    if master['name'] == modal['name']
]


def _key(label):
    """A label like "Target headcount (500)" becomes `target_headcount`.

    The parenthetical is context for the reader, not part of the column name,
    and the key has to survive as both a formula variable and a CSV header.
    """
    stripped = re.sub(r'\([^)]*\)', '', label)
    key = re.sub(r'[^a-z0-9]+', '_', stripped.strip().lower()).strip('_')
    return re.sub(r'^(?=\d)', 'n', key)


class Command(BaseCommand):
    help = 'Create the six standard Operations KPIs as database rows (idempotent).'

    @transaction.atomic
    def handle(self, *args, **options):
        team = Team.objects.filter(slug='operations').first()
        if team is None:
            self.stderr.write('No Operations team. Run migrations first.')
            return

        created = skipped = 0

        for order, spec in enumerate(_SPECS):
            slug = slugify(spec['name'])

            if KpiDefinition.objects.filter(team=team, branch=None, slug=slug).exists():
                skipped += 1
                self.stdout.write(f'  skip   {slug} (already exists)')
                continue

            category, _ = KpiCategory.objects.get_or_create(
                team=team, name=spec['category']
            )

            numerator, denominator = _key(spec['numerator']), _key(spec['denominator'])
            expression = f'{numerator} / {denominator} * 100'
            labels = {numerator: spec['numerator'], denominator: spec['denominator']}

            # Same validation the Create-KPI form applies, so a seeded KPI is
            # indistinguishable from a hand-built one.
            formula_engine.validate(expression, [numerator, denominator])

            kpi = KpiDefinition.objects.create(
                team=team,
                category=category,
                name=spec['name'],
                slug=slug,
                description=spec['description'],
                expression=expression,
                formula_text=formula_engine.render_text(expression, labels)[:255],
                display_format=DisplayFormat.PERCENT,
                direction=(
                    Direction.DOWN if spec['direction'] == 'down' else Direction.UP
                ),
                frequency=(
                    Frequency.QUARTERLY
                    if spec['frequency'] == 'Quarterly'
                    else Frequency.MONTHLY
                ),
                # A single figure is a band of width zero.
                target_min=spec['target'],
                target_max=spec['target'],
                target_display=spec['target_display'],
                template_version=1,
                sort_order=order,
            )

            KpiInput.objects.bulk_create([
                KpiInput(
                    kpi=kpi, key=numerator, label=spec['numerator'], position=1
                ),
                KpiInput(
                    kpi=kpi, key=denominator, label=spec['denominator'], position=2
                ),
            ])

            KpiFormulaHistory.objects.create(
                kpi=kpi,
                expression=kpi.expression,
                formula_text=kpi.formula_text,
                template_version=1,
                effective_from=kpi.created_at.date(),
                reason='Seeded from the original Operations KPI list',
            )

            created += 1
            self.stdout.write(f'  create {slug} · {kpi.formula_text}')

        self.stdout.write(
            self.style.SUCCESS(f'\n{created} created, {skipped} already present.')
        )
