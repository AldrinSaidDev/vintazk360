from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds the flag that asks a newly created account to set itself up.

    Default False, unlike `is_new_user`: every account that already exists was
    created with its name, email and password typed in by hand, so there is
    nothing to ask any of them for. Only accounts made from the Users screen
    after this point carry it, and `CreateUserForm` is what turns it on.
    """

    dependencies = [
        ('core', '0010_drop_django_cache_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='needs_setup',
            field=models.BooleanField(
                default=False,
                verbose_name='needs account setup',
                help_text=(
                    'Asks this user for their name, email and a password of '
                    'their own the next time they open the dashboard. Cleared '
                    'once they finish.'
                ),
            ),
        ),
    ]
