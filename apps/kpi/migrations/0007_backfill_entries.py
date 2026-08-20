"""Turn every existing record into its first entry, and choose an aggregation.

Two jobs, both one-way-ish and both explained here because neither is obvious
from the schema alone.

1. AGGREGATION. Every `kpi_input` in the database is on the old `none` default,
   which used to mean "one row per period and a second is an error". Under the
   entry model a second submission is the normal case, so `none` would now mean
   "silently replace", which is the behaviour this whole change removes. The
   right setting is per input and the formula can half derive it: an operand
   under a `/` is a denominator and must NOT be auto-summed, a date operand
   cannot be summed at all, and everything else is an additive event. That is a
   DEFAULT — `kpi_input.aggregation` is editable on KPI Management, which is
   where a numerator that is really a snapshot gets corrected.

2. BACKFILL. Each existing `kpi_record` becomes one `kpi_entry` carrying its
   operands, so the history log is not empty for figures entered before this
   migration and so `rebuild_period()` re-derives exactly the value already on
   screen rather than zero. `entry_date` is the period start: the real date the
   figure was reported is not recorded anywhere, and inventing one from
   `created_at` would read as fact rather than as a backfill.

The reverse drops the entries and puts every input back on `none`, so the
migration can be unapplied without leaving half a model behind.
"""

from django.db import migrations


def _aggregation_for(kpi_input, denominators):
    from apps.kpi.models import Aggregation, DataType

    if kpi_input.data_type == DataType.DATE:
        # days_between(day_zero, ready_date): adding two dates is meaningless,
        # and the latest pair is the one that describes the period.
        return Aggregation.LAST
    if kpi_input.key in denominators:
        return Aggregation.LAST
    return Aggregation.SUM


def set_aggregations(apps, schema_editor):
    from apps.kpi import formula

    KpiDefinition = apps.get_model('kpi', 'KpiDefinition')
    updated = []

    for kpi in KpiDefinition.objects.prefetch_related('inputs'):
        try:
            denominators = formula.divisors(kpi.expression or '')
        except formula.FormulaError:
            # A formula that no longer parses must not stop the migration. Its
            # inputs stay additive, which is the safer of the two mistakes: a
            # wrong sum is visible on the dashboard, a silent replace is not.
            denominators = set()

        for kpi_input in kpi.inputs.all():
            wanted = _aggregation_for(kpi_input, denominators)
            if kpi_input.aggregation != wanted:
                kpi_input.aggregation = wanted
                updated.append(kpi_input)

    KpiInput = apps.get_model('kpi', 'KpiInput')
    KpiInput.objects.bulk_update(updated, ['aggregation'], batch_size=200)


def unset_aggregations(apps, schema_editor):
    KpiInput = apps.get_model('kpi', 'KpiInput')
    KpiInput.objects.update(aggregation='none')


def backfill_entries(apps, schema_editor):
    KpiRecord = apps.get_model('kpi', 'KpiRecord')
    KpiEntry = apps.get_model('kpi', 'KpiEntry')
    KpiEntryInput = apps.get_model('kpi', 'KpiEntryInput')

    records = list(
        KpiRecord.objects.prefetch_related('input_values').select_related('kpi')
    )
    if not records:
        return

    entries = KpiEntry.objects.bulk_create(
        [
            KpiEntry(
                kpi_id=record.kpi_id,
                # Not created_at: the date this figure was FOR is unrecorded, and
                # the day the row happened to be written is a different fact.
                entry_date=record.period_start,
                period_start=record.period_start,
                period_end=record.period_end,
                value=record.value,
                value_display=record.value_display,
                source=record.source,
                import_batch_id=record.import_batch_id,
                remarks=record.remarks,
                entered_by_id=record.entered_by_id,
                is_active=record.is_active,
            )
            for record in records
        ],
        batch_size=200,
    )

    KpiEntryInput.objects.bulk_create(
        [
            KpiEntryInput(
                entry_id=entry.pk,
                input_id=operand.input_id,
                value_number=operand.value_number,
                value_date=operand.value_date,
            )
            for entry, record in zip(entries, records)
            for operand in record.input_values.all()
        ],
        batch_size=500,
    )

    # `created_at` is auto_now_add, so bulk_create stamped all of these with the
    # migration's own timestamp. The history log is ordered by it, so put the
    # record's real one back rather than showing a month of figures as having
    # been entered in the same second.
    for entry, record in zip(entries, records):
        entry.created_at = record.created_at
        entry.updated_at = record.updated_at
    KpiEntry.objects.bulk_update(entries, ['created_at', 'updated_at'], batch_size=200)

    # One entry each, and a closed period until something says otherwise.
    KpiRecord.objects.update(entry_count=1)


def drop_entries(apps, schema_editor):
    apps.get_model('kpi', 'KpiEntryInput').objects.all().delete()
    apps.get_model('kpi', 'KpiEntry').objects.all().delete()
    apps.get_model('kpi', 'KpiRecord').objects.update(entry_count=0)


class Migration(migrations.Migration):

    dependencies = [
        ('kpi', '0006_entries'),
    ]

    operations = [
        migrations.RunPython(set_aggregations, unset_aggregations),
        migrations.RunPython(backfill_entries, drop_entries),
    ]
