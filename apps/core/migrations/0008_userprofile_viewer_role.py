"""Add the Viewer role (read-only across every team).

Five roles now, not four. Nothing is renamed or removed, so no data has to
move: this is the choices list plus the reworded ``teams`` help text, since
that field is now ignored for Super Admin and Viewer rather than for Super
Admin and Admin. Admin becomes team-scoped, which is an access rule in
``apps/core/access.py`` and not a column.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_alter_auditlog_action'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('superadmin', 'Super Admin'),
                    ('admin', 'Admin'),
                    ('manager', 'Manager'),
                    ('user', 'User'),
                    ('viewer', 'Viewer'),
                ],
                default='user',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='teams',
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    'Teams this user can access. Ignored for Super Admin and '
                    'Viewer (both reach every team). A plain User should have '
                    'exactly one.'
                ),
                related_name='members',
                to='core.team',
            ),
        ),
    ]
