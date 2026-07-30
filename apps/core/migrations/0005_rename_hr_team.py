"""Spell HR out in the sidebar: "Human Resources".

The sidebar renders `Team.name`, so the abbreviation had to change here — the
banner and badge are template-side. Slug and PK are untouched, so URLs, the
``team_required`` guard, and user assignments are unaffected.
"""
from django.db import migrations

NAME = 'Human Resources'
PREVIOUS_NAME = 'HR'


def rename(apps, schema_editor):
    Team = apps.get_model('core', 'Team')
    Team.objects.filter(slug='hr').update(name=NAME)


def unrename(apps, schema_editor):
    Team = apps.get_model('core', 'Team')
    Team.objects.filter(slug='hr').update(name=PREVIOUS_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_rename_vct_team'),
    ]

    operations = [
        migrations.RunPython(rename, unrename),
    ]
