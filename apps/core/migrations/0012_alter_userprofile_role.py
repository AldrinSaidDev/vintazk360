"""Adds the Finance and HR roles.

They are what replaced the named-person allowlist that used to decide who
reaches the Finance and Human Resources departments. Nothing is renamed and no
profile has to move: every existing role keeps its value, and the two new ones
start unused until somebody is assigned one.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_userprofile_needs_setup'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(choices=[('superadmin', 'Super Admin'), ('admin', 'Admin'), ('finance', 'Finance'), ('hr', 'HR'), ('manager', 'Manager'), ('user', 'User'), ('viewer', 'Viewer')], default='user', max_length=20),
        ),
    ]
