"""Spell the VCT team out in the sidebar: "Visual and Content Team".

The sidebar shows `Team.name`, and the abbreviation-plus-parenthetical form set
by 0003 read awkwardly there. Slug and PK are untouched, so URLs, the
``team_required`` guard, and user assignments are unaffected — this is a label
change only.
"""
from django.db import migrations

NAME = 'Visual and Content Team'
PREVIOUS_NAME = 'VCT (Visual and Content Team)'


def rename(apps, schema_editor):
    Team = apps.get_model('core', 'Team')
    Team.objects.filter(slug='vct').update(name=NAME)


def unrename(apps, schema_editor):
    Team = apps.get_model('core', 'Team')
    Team.objects.filter(slug='vct').update(name=PREVIOUS_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_split_marketing_into_departments'),
    ]

    operations = [
        migrations.RunPython(rename, unrename),
    ]
