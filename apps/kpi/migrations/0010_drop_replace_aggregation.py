"""Drop the "Replace (one figure per period)" aggregation.

It collapsed exactly as `last` does — the newest entry wins — so it was one
label for a behaviour that already had one, and it was the label that described
the OLD upsert model rather than this one. Nothing overwrites a period any more,
so an option promising to is worse than no option.

The rows move to `last`, which is what they were already doing. Nothing on this
database holds it (every input is sum, avg or last), but a database seeded
before the entry model does, and the two are the same collapse either way.
"""

from django.db import migrations, models


def to_last(apps, schema_editor):
    apps.get_model('kpi', 'KpiInput').objects.filter(aggregation='none').update(
        aggregation='last'
    )
    apps.get_model('kpi', 'KpiPresetInput').objects.filter(aggregation='none').update(
        aggregation='last'
    )


def noop(apps, schema_editor):
    """Irreversible in name only: `last` is what "replace" already did."""


class Migration(migrations.Migration):

    dependencies = [
        ('kpi', '0009_approved_aggregations'),
    ]

    operations = [
        migrations.RunPython(to_last, noop),
        migrations.AlterField(
            model_name='kpiinput',
            name='aggregation',
            field=models.CharField(choices=[('sum', 'Add them up'), ('last', 'Most recent wins'), ('avg', 'Average'), ('count', 'Count the entries'), ('min', 'Lowest'), ('max', 'Highest')], default='sum', help_text='How this figure collapses when a period has several entries. Additive events add up. A snapshot or a divisor should not.', max_length=8),
        ),
        migrations.AlterField(
            model_name='kpipresetinput',
            name='aggregation',
            field=models.CharField(choices=[('sum', 'Add them up'), ('last', 'Most recent wins'), ('avg', 'Average'), ('count', 'Count the entries'), ('min', 'Lowest'), ('max', 'Highest')], default='sum', max_length=8),
        ),
    ]
