from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds the flag that decides whether the guided tour plays by itself.

    Existing profiles get True along with new ones. Nobody has seen the tour
    yet, so "has this account been shown around?" is False for everybody, and
    the flag clears itself the first time each of them finishes or skips it.
    """

    dependencies = [
        ('core', '0008_userprofile_viewer_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='is_new_user',
            field=models.BooleanField(
                default=True,
                verbose_name='new user',
                help_text=(
                    'Plays the guided tour automatically the next time this '
                    'user opens the dashboard. Cleared once they finish or '
                    'skip it.'
                ),
            ),
        ),
    ]
