"""Re-derive aggregations after `formula.divisors()` learned about both sides.

`kpi.0007` called any operand under a `/` a divisor and put it on `last`. That
is wrong when the SAME operand is also a numerator:

    (total_payroll_transactions - payroll_errors) / total_payroll_transactions * 100

`total_payroll_transactions` is a count of events. 100 transactions on Monday
and 100 on Tuesday is 200, and `last` made the denominator 100 while the
numerator correctly used 200 — so Payroll Accuracy read 195% instead of 97.5%.
A wrong figure on the dashboard, not merely a wrong suggestion.

Four KPIs have that shape: Payroll Accuracy, Invoice Accuracy, Budget Variance
and Cash Flow Forecast Accuracy, all Finance. `divisors()` now excludes an
operand that appears outside the denominator too, so re-running the same
derivation corrects them.

Deliberately re-derives EVERY input rather than patching those four by name: the
derivation is the rule, and running it is what keeps this migration true if the
KPI set has moved on. It only touches rows the rule now disagrees with, and it
cannot clobber a considered override, because there are none to clobber — the
picker that makes overriding possible ships alongside this.
"""

from django.db import migrations


def redderive(apps, schema_editor):
    from apps.kpi import formula
    from apps.kpi.models import Aggregation, DataType

    KpiDefinition = apps.get_model('kpi', 'KpiDefinition')
    KpiInput = apps.get_model('kpi', 'KpiInput')
    changed = []

    for kpi in KpiDefinition.objects.prefetch_related('inputs'):
        try:
            denominators = formula.divisors(kpi.expression or '')
        except formula.FormulaError:
            continue

        for kpi_input in kpi.inputs.all():
            if kpi_input.data_type == DataType.DATE:
                wanted = Aggregation.LAST
            elif kpi_input.key in denominators:
                wanted = Aggregation.LAST
            else:
                wanted = Aggregation.SUM

            if kpi_input.aggregation != wanted:
                kpi_input.aggregation = wanted
                changed.append(kpi_input)

    KpiInput.objects.bulk_update(changed, ['aggregation'], batch_size=200)


def noop(apps, schema_editor):
    """No reverse.

    Putting the four back on `last` would restore a arithmetic bug, and there is
    nothing else to undo: `kpi.0007`'s reverse already resets every aggregation.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('kpi', '0007_backfill_entries'),
    ]

    operations = [
        migrations.RunPython(redderive, noop),
    ]
