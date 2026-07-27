"""Seed the 8 LOB teams and give every existing user a profile.

Slugs must match each LOB app's URL namespace (used by the sidebar and the
``team_required`` guard). Existing Django superusers become Super Admin;
everyone else defaults to the plain User role with no team (assign in admin).
"""
from django.db import migrations

# (slug, display name, sidebar order) — order follows the North Star wheel.
TEAMS = [
    ('operations', 'Operations', 10),
    ('sitelead', 'Site Lead', 20),
    ('sales', 'Sales', 30),
    ('hr', 'HR', 40),
    ('academy', 'VINTAZK Academy', 50),
    ('finance', 'Finance', 60),
    ('marketing', 'Social Media & Marketing', 70),
    ('nexzys', 'Nexzys', 80),
]


def seed(apps, schema_editor):
    Team = apps.get_model('core', 'Team')
    UserProfile = apps.get_model('core', 'UserProfile')
    User = apps.get_model('auth', 'User')

    for slug, name, order in TEAMS:
        Team.objects.update_or_create(
            slug=slug,
            defaults={'name': name, 'order': order},
        )

    # Give every existing user a profile so the app never hits a missing one.
    # Django superusers see everything anyway; mark them Super Admin for clarity.
    for user in User.objects.all():
        role = 'superadmin' if user.is_superuser else 'user'
        UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': role},
        )


def unseed(apps, schema_editor):
    Team = apps.get_model('core', 'Team')
    Team.objects.filter(slug__in=[slug for slug, _, _ in TEAMS]).delete()
    # UserProfiles are left in place; removing them would lose role/team data.


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
