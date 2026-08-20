"""Cut the input aggregations down to SUM, AVG and LAST.

A figure somebody types into a template is either something that accumulates,
something measured repeatedly, or a snapshot. Those are the three.

`count` ignored the number in the cell and counted rows instead, so the column
the uploader had just filled in stopped mattering; `min` and `max` answered a
question about the entries rather than about the period. No input on this
database held any of the three (173 sum, 49 last, 10 avg), so the data pass
below is for a database seeded before this, not for ours.

Where they do exist, `count` becomes `sum` (both read the column as "how many",
and summing at least uses what was typed) and `min`/`max` become `last`, the
option that likewise picks one entry's reading rather than combining them.
"""

from django.db import migrations, models

CHOICES = [
    ('sum', 'Add them up'),
    ('avg', 'Average'),
    ('last', 'Most recent wins'),
]

MOVES = {'count': 'sum', 'min': 'last', 'max': 'last'}


def narrow(apps, schema_editor):
    for model in ('KpiInput', 'KpiPresetInput'):
        rows = apps.get_model('kpi', model).objects
        for old, new in MOVES.items():
            rows.filter(aggregation=old).update(aggregation=new)


def noop(apps, schema_editor):
    """Irreversible in name only: nothing can say which rows were which."""


class Migration(migrations.Migration):

    dependencies = [
        ('kpi', '0010_drop_replace_aggregation'),
    ]

    operations = [
        migrations.RunPython(narrow, noop),
        migrations.AlterField(
            model_name='kpiinput',
            name='aggregation',
            field=models.CharField(
                choices=CHOICES,
                default='sum',
                help_text='How this figure collapses when a period has several entries. Additive events add up. A snapshot or a divisor should not.',
                max_length=8,
            ),
        ),
        migrations.AlterField(
            model_name='kpipresetinput',
            name='aggregation',
            field=models.CharField(choices=CHOICES, default='sum', max_length=8),
        ),
    ]
