"""Split "Social Media & Marketing" into three standalone departments.

VCT turned out to BE the Visual and Content Team, with SMM and Content Writing as their own
departments rather than branches beneath it. So the old `marketing` team row is
repurposed as `vct` (keeping its PK, so any user assignments survive) and two new
rows are added.

Slugs must match each LOB app's URL namespace — the sidebar and the
``team_required`` guard both key off them.
"""
from django.db import migrations

OLD_SLUG = 'marketing'

# (slug, display name, sidebar order)
VCT = ('vct', 'VCT (Visual and Content Team)', 70)
NEW_TEAMS = [
    ('smm', 'Social Media Management', 72),
    ('content', 'Content Writing', 74),
]


def split(apps, schema_editor):
    Team = apps.get_model('core', 'Team')

    # Repurpose the existing row so team assignments and its PK carry over.
    slug, name, order = VCT
    updated = Team.objects.filter(slug=OLD_SLUG).update(slug=slug, name=name, order=order)
    if not updated:
        Team.objects.update_or_create(slug=slug, defaults={'name': name, 'order': order})

    for slug, name, order in NEW_TEAMS:
        Team.objects.update_or_create(slug=slug, defaults={'name': name, 'order': order})


def unsplit(apps, schema_editor):
    Team = apps.get_model('core', 'Team')
    Team.objects.filter(slug__in=[slug for slug, _, _ in NEW_TEAMS]).delete()
    Team.objects.filter(slug=VCT[0]).update(
        slug=OLD_SLUG, name='Social Media & Marketing', order=70,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_seed_teams_and_profiles'),
    ]

    operations = [
        migrations.RunPython(split, unsplit),
    ]
