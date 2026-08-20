"""Generate a KPI's CSV template — entirely from the KPI's own definition.

`db_schema.txt` Part D. Nothing here is KPI-specific: the columns are the KPI's
`kpi_input` rows in `position` order, because a key is simultaneously the
expression variable, the CSV header and the form field name. **Adding a KPI
adds zero lines of this file.**

The file is built ON DEMAND, never stored. §A.6 requires a freshly downloaded
template to carry the *current* `template_version`; a file saved at creation
time would silently go stale the first time anyone edited the formula, and the
importer would then reject the very template the screen was handing out.

    # Vintazk 360 KPI template. Lines starting with # are notes and are ignored…
    # kpi=operations/attrition-rate | template=1 | frequency=monthly | generated=…
    # Formula: Total exits ÷ Average headcount × 100  ·  Target: Threshold 3.5% (lower is better)
    period,total_exits,average_headcount,remarks
    # Example (ignored on upload): 2026-07,12,380,Optional note  →  3.2%
    2026-08,,,

The example row is COMMENTED. It shows the shape of a filled row column by
column and what those operands work out to, which is also the answer to "where
does the formula happen?" — the file carries RAW inputs and the value is
computed on upload. Being a comment, it can never be uploaded as real data.
"""

from __future__ import annotations

import csv
import datetime as dt
import io

from django.utils import timezone

from .models import DataType, Direction, Frequency

# Every '#' line is stripped on upload, so this note also covers the example
# row further down: it can be left in place, edited, or deleted freely.
HEADER_NOTE = (
    'Vintazk 360 KPI template. Lines starting with # are notes and are ignored '
    'on upload. Do not edit or remove the first three.'
)

# `records.coerce()` reads dates with `date.fromisoformat` only, so a cell of
# "8/6/2026" is rejected. The rejection message says so, but only AFTER an
# upload that has already been filled in and sent. Saying it on the template is
# the difference between a rule and an ambush. Numbers need no equivalent note:
# `coerce()` already tolerates "1,234", "₱1,234" and stray spaces.
DATE_NOTE = 'Dates as YYYY-MM-DD'

# The `period` column changed meaning: it carries the DATE a row is for, and the
# KPI's cadence decides which reporting period that lands in. Saying so on the
# file matters more than most notes here, because the behaviour it describes is
# the one people will not expect: uploading twice in a month ADDS to that month
# rather than replacing it. A bare period label (2026-08) still works, so every
# template downloaded before this change keeps importing.
PERIOD_NOTE = (
    'The period column takes the date the figures are for (2026-08-21). '
    'Rows falling in the same {cadence} are combined, and uploading again '
    'later adds to that {cadence} rather than replacing it.'
)

CADENCE_WORD = {
    Frequency.DAILY: 'day',
    Frequency.WEEKLY: 'week',
    Frequency.MONTHLY: 'month',
    Frequency.QUARTERLY: 'quarter',
    Frequency.ANNUALLY: 'year',
}

DIRECTION_NOTE = {
    Direction.UP: 'higher is better',
    Direction.DOWN: 'lower is better',
}


def period_label(frequency: str, when=None) -> str:
    """How the `period` cell reads for this cadence (§D).

    monthly `2026-07` · quarterly `2026-Q3` · daily `2026-07-15` ·
    weekly `2026-W32` · annually `2026`.
    """
    when = when or timezone.localdate()

    if frequency == Frequency.DAILY:
        return when.isoformat()
    if frequency == Frequency.WEEKLY:
        return f'{when.isocalendar().year}-W{when.isocalendar().week:02d}'
    if frequency == Frequency.QUARTERLY:
        return f'{when.year}-Q{(when.month - 1) // 3 + 1}'
    if frequency == Frequency.ANNUALLY:
        return str(when.year)
    return f'{when.year}-{when.month:02d}'


def columns(kpi) -> list[str]:
    """The data columns: `period`, one per input in order, then `remarks`."""
    keys = list(kpi.inputs.order_by('position').values_list('key', flat=True))
    return ['period', *keys, 'remarks']


def scope_path(kpi) -> str:
    """The KPI's address inside the org: `team/slug`, or `team/branch/slug`.

    A slug is unique per `(team, branch)`, NOT per team, so two Sales branches
    can both own "qualified-leads-generated". Without the branch segment the
    importer would resolve a file to whichever of the two it happened to find
    first and write the numbers into the wrong branch.
    """
    if kpi.branch_id:
        return f'{kpi.team.slug}/{kpi.branch.slug}/{kpi.slug}'
    return f'{kpi.team.slug}/{kpi.slug}'


def filename(kpi) -> str:
    stem = scope_path(kpi).replace('/', '-')
    return f'{stem}-template-v{kpi.template_version}.csv'


def example_values(kpi):
    """One example value per input, in column order.

    `kpi_input.placeholder` is the source, because it is already the example
    the business wrote for that field. Where it is blank, a neutral stand-in
    keeps the row readable: the point of the line is the SHAPE of a filled row,
    and a column showing nothing teaches nothing.
    """
    values = []
    for index, row in enumerate(kpi.inputs.all()):
        if row.placeholder:
            values.append(row.placeholder)
        elif row.data_type == DataType.DATE:
            # Distinct dates, EARLIEST LAST. `days` KPIs are seeded as
            # `days_between(second, first)`, so the first column is the end
            # date; putting the later date first is what makes the worked
            # result read "+5 days" rather than "-5 days".
            values.append(f'2026-07-{15 - index * 5:02d}')
        else:
            # 100 rather than 0: a zero denominator would make the worked
            # result below a division by zero on half the KPIs.
            values.append('100')
    return values


def previous_period(kpi, when=None):
    """The example row's date: a day inside the period BEFORE this one.

    A DATE now, matching what the column means and what the blank row below it
    carries. It stays in an earlier period rather than sharing this one, but the
    reason has changed: two rows for a period used to be rejected outright, and
    now they simply add together. So uncommenting this line is no longer a trap,
    it just contributes an example figure. Keeping it in the previous period
    means doing that does not quietly move the current period's total.
    """
    from . import periods

    start, _ = periods.parse(period_label(kpi.frequency, when), kpi.frequency)
    return (start - dt.timedelta(days=1)).isoformat()


def example_line(kpi, when=None) -> str:
    """The commented example row, with what those numbers work out to.

    The arrow is the answer to "where does the formula happen?": the file holds
    RAW operands, and the KPI's value is computed on upload. Showing the inputs
    beside their result makes that visible without anyone having to upload
    something first to find out.
    """
    from . import formula as formula_engine
    from . import records

    values = example_values(kpi)
    period = previous_period(kpi, when)

    buffer = io.StringIO()
    csv.writer(buffer, lineterminator='').writerow(
        [period, *values, 'Optional note']
    )
    row = buffer.getvalue()

    # Only claim a result if these particular values really produce one. A
    # stand-in operand can still divide by zero or be the wrong shape, and a
    # wrong worked example is worse than none.
    worked = ''
    try:
        numbers = {}
        for kpi_input, raw in zip(kpi.inputs.all(), values):
            numbers[kpi_input.key] = records.coerce(raw, kpi_input)
        value = records.evaluate(kpi, numbers)
        worked = f'  →  {records.format_value(kpi, value)}'
    except (records.RecordError, formula_engine.FormulaError, ZeroDivisionError, ValueError):
        worked = ''

    return f'# Example (ignored on upload): {row}{worked}\n'


def build(kpi, when=None) -> str:
    """Return the whole CSV file as text."""
    target = kpi.target_display or ('No target' if not kpi.is_scored else '')
    direction = DIRECTION_NOTE.get(kpi.direction, '')
    formula = kpi.formula_text or kpi.expression

    # The generated= stamp lands in `kpi_import_batch.template_generated_at`,
    # which is a timestamptz — so a full timestamp rather than §D's bare date,
    # which could not tell two downloads on the same day apart.
    generated = timezone.now().isoformat(timespec='seconds')

    buffer = io.StringIO()
    buffer.write(f'# {HEADER_NOTE}\n')
    buffer.write(
        f'# kpi={scope_path(kpi)} | template={kpi.template_version} '
        f'| frequency={kpi.frequency} | generated={generated}\n'
    )
    dates = any(row.data_type == DataType.DATE for row in kpi.inputs.all())
    # Still ONE line: line 1 promises exactly three comment lines, and the
    # importer counts comments to work out which spreadsheet row a bad cell was
    # on, so adding a fourth would misreport every error position in the file.
    buffer.write(
        f'# Formula: {formula}  ·  Target: {target}'
        + (f' ({direction})' if direction else '')
        + '  ·  '
        + PERIOD_NOTE.format(cadence=CADENCE_WORD.get(kpi.frequency, 'reporting'))
        + (f'  ·  {DATE_NOTE}' if dates else '')
        + '\n'
    )

    header = columns(kpi)
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(header)

    # A worked example, COMMENTED OUT. It shows the shape of a filled row
    # column by column, sitting directly above the row to fill, and the
    # importer strips every '#' line — so a demo number can never be uploaded
    # as if it were real performance. That was the objection to putting sample
    # values in the live row; commenting it answers both needs at once.
    buffer.write(example_line(kpi, when))

    # The row to actually fill: today's DATE, and nothing else. A date rather
    # than the period label it used to carry, because that is what the column
    # now means and because a filled-in date is the thing that makes the
    # accumulate-into-the-period behaviour visible rather than surprising.
    writer.writerow([
        (when or timezone.localdate()).isoformat(), *[''] * (len(header) - 1)
    ])

    return buffer.getvalue()


def build_bytes(kpi, when=None) -> bytes:
    """The file as bytes, BOM-first — this is what a view should serve.

    Excel does not sniff UTF-8: double-clicking a plain UTF-8 CSV on Windows
    decodes it as the ANSI code page, which turns the formula's ÷ × · — into
    Ã· Ã— Â· â€". A leading BOM is the one signal Excel does honour, and every
    other CSV reader skips it (Python's own `utf-8-sig` included).
    """
    return build(kpi, when).encode('utf-8-sig')
