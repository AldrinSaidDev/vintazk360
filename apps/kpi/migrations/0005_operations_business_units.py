"""Create Operations' seven business units.

Operations became a branch team (`apps/operations/branches.py`), so its four
screens live under `/operations/<unit>/`. Without these rows every one of those
URLs is a 404 and the sidebar shows a department with nothing under it.

**Branch rows only. No KPIs, and no records.** The units track the same metrics,
but a KPI belongs to exactly one branch, so "the same KPI" across seven units is
seven rows and that is a decision about the data rather than about the schema.
Seeding them here would also write a description of figures the business may
have already edited.

Idempotent by `(team, slug)`, which is the model's own unique constraint, so it
is safe on a database where somebody has already made some of them by hand. The
reverse removes only units that never had a KPI filed against them: once one is
in use, unmigrating must not quietly take its data out of reach.
"""
from django.db import migrations

# Slug, display name. Kept in step with apps/operations/branches.NAV_BRANCHES —
# that list drives the sidebar and the breadcrumb, these rows drive the URLs and
# the KPI scoping, and a slug in one and not the other is a dead link.
UNITS = [
    ('moxxi-jade', 'Moxxi & Jade'),
    ('hermes', 'Hermes'),
    ('pddl', 'PDDL'),
    ('adparlor', 'AdParlor'),
    ('csteam', 'CSTeam'),
    ('jac-media', 'JAC & Media'),
    ('adops', 'AdOps'),
]

TEAM_SLUG = 'operations'


def create_units(apps, schema_editor):
    Team = apps.get_model('core', 'Team')
    KpiBranch = apps.get_model('kpi', 'KpiBranch')

    team = Team.objects.filter(slug=TEAM_SLUG).first()
    if team is None:
        # A database that has not seeded its teams yet. Nothing to attach to,
        # and core.0002 will not come back round to add these.
        return

    for order, (slug, name) in enumerate(UNITS):
        KpiBranch.objects.get_or_create(
            team=team,
            slug=slug,
            defaults={'name': name, 'order': order, 'is_active': True},
        )


def remove_units(apps, schema_editor):
    Team = apps.get_model('core', 'Team')
    KpiBranch = apps.get_model('kpi', 'KpiBranch')

    team = Team.objects.filter(slug=TEAM_SLUG).first()
    if team is None:
        return

    # `kpis` is PROTECTed, so a unit somebody has started using would raise
    # here anyway. Skipping it explicitly makes the reverse a no-op on the
    # rows that matter rather than a crash halfway through.
    KpiBranch.objects.filter(
        team=team, slug__in=[slug for slug, _ in UNITS], kpis__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('kpi', '0004_kpiimportbatch_is_active'),
        ('core', '0002_seed_teams_and_profiles'),
    ]

    operations = [
        migrations.RunPython(create_units, remove_units),
    ]
