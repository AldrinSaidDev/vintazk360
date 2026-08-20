"""Writing one actual: the single path from raw operands to a scored record.

Manual entry and CSV import both come through `add_entry()`, so a number typed
into the modal and the same number uploaded in a file are stored, collapsed and
scored identically. Anything that differs between the two (where the file went,
which rows were rejected) belongs to the importer, not here.

**Cadence defines the reporting period, not the upload frequency.** A monthly
KPI can be reported into every day of the month. Each report is a `kpi_entry`
with its own date; the period's `kpi_record` is DERIVED from all of them, so the
month can be watched filling in rather than only being readable once it ends.

The shape of the work:

    raw operand values  →  coerce per kpi_input.data_type
                        →  evaluate, for this entry's own figure
                        →  insert kpi_entry + kpi_entry_input        (add_entry)
                        ─────────────────────────────────────────────
                        →  collapse every entry's operands   (rebuild_period)
                        →  run the formula ONCE over them
                        →  apply accumulation, if the KPI is cumulative
                        →  score against the target band (apps.core.kpi)
                        →  upsert kpi_record on (kpi, period_start)

**There is ONE way a period is resolved: aggregate the inputs, then calculate.**
Every entry's operands collapse per `kpi_input.aggregation` and the formula runs
once over the totals (`collapse` / `collapsed_values`). That is what a rate, a
ratio or a share means: a month's attrition is all the exits over the headcount
they left from.

A second mode used to sit beside it — run the formula per entry, then combine
the answers — and it is gone. Nothing ever used it, it asked the KPI's author a
question about arithmetic that the per-input aggregation already answers, and
two modes that disagree by design is one more way for a figure to be wrong than
this needs. The per-input picker (`kpi_input.aggregation`) is the whole of the
configuration now.

Accumulation therefore happens on the OPERANDS and never on the finished
figure: 3% attrition plus 4% attrition is not 7%. It is also why a divisor is
not accumulated just because it is in the formula — see `collapse()`.

Design principle 2 is what makes the operand tables matter: the record keeps
`3.1%`, these keep `12` and `380`. Correct a formula later and history can be
recomputed.
"""

from __future__ import annotations

import datetime as dt
import statistics
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.core import kpi as scoring

from . import formula as formula_engine
from . import periods
from .models import (
    REMARKS_MAX_LENGTH,
    Accumulation,
    Aggregation,
    DataType,
    DisplayFormat,
    KpiEntry,
    KpiEntryInput,
    KpiRecord,
    KpiRecordInput,
)


class RecordError(ValueError):
    """A value that cannot be stored. The message is user-facing.

    `field` names the input key it belongs to, so a caller can attach it to the
    right form field or CSV column.
    """

    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


# --- reading what the user typed -------------------------------------------


def coerce(value, kpi_input):
    """Turn one raw cell into the Python value its `data_type` promises."""
    text = ('' if value is None else str(value)).strip()

    if not text:
        if kpi_input.is_required:
            raise RecordError(f'{kpi_input.label} is required.', kpi_input.key)
        # A blank optional cell counts as 0, or as "no date" for a date input.
        return None if kpi_input.data_type == DataType.DATE else Decimal(0)

    if kpi_input.data_type == DataType.DATE:
        try:
            return dt.date.fromisoformat(text)
        except ValueError:
            raise RecordError(
                f'{kpi_input.label}: "{text}" is not a date (use YYYY-MM-DD).',
                kpi_input.key,
            )

    # Spreadsheets cheerfully export "1,234" and "₱1,234" — read them anyway
    # rather than rejecting a row a human would call obviously fine.
    cleaned = text.replace(',', '').replace('₱', '').replace('%', '').strip()
    try:
        number = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise RecordError(f'{kpi_input.label}: "{text}" is not a number.', kpi_input.key)

    if kpi_input.data_type == DataType.INTEGER and number != number.to_integral_value():
        raise RecordError(
            f'{kpi_input.label}: "{text}" must be a whole number.', kpi_input.key
        )
    return number


def coerce_all(kpi, raw):
    """Coerce a whole row, keyed by input key. Raises on the first bad cell."""
    return {row.key: coerce(raw.get(row.key), row) for row in kpi.inputs.all()}


# --- turning operands into a scored value ----------------------------------


def evaluate(kpi, values):
    """The expression's result, as a float."""
    numeric = {
        key: (value if isinstance(value, dt.date) else float(value or 0))
        for key, value in values.items()
    }
    try:
        return float(formula_engine.evaluate(kpi.expression, numeric))
    except formula_engine.FormulaError as error:
        raise RecordError(str(error))


def format_value(kpi, value):
    """How the number prints: the same sum reads "93%", "8.6 days" or "₱1,240"."""
    precision = kpi.precision or 0
    unit = kpi.unit or ''

    if kpi.display_format == DisplayFormat.PERCENT:
        return f'{value:.{precision}f}%'
    if kpi.display_format == DisplayFormat.INTEGER:
        return f'{round(value):,}{unit}'
    if kpi.display_format == DisplayFormat.CURRENCY:
        return f'{unit or "₱"}{value:,.{precision}f}'
    if kpi.display_format == DisplayFormat.RATIO:
        return f'{value:.{precision}f}{unit or "×"}'
    if kpi.display_format == DisplayFormat.DAYS:
        return f'{value:.{precision}f}{unit or " days"}'
    return f'{value:,.{precision}f}{unit}'


def score(kpi, value):
    """Attainment and status for a value, or `(None, 'monitored')` when unscored.

    Delegates to `apps.core.kpi`, which is the band math already in production
    across seven LOBs — a second implementation here would be one more place
    for the two to disagree.
    """
    row = {
        'target_min': float(kpi.target_min) if kpi.target_min is not None else None,
        'target_max': float(kpi.target_max) if kpi.target_max is not None else None,
        'direction': kpi.direction,
        'actual': value,
    }
    attainment = scoring.attainment(row)
    if attainment is None:
        return None, KpiRecord.Status.MONITORED
    # Bucket on the UNROUNDED value so 99.96% is not rounded up into "On Track".
    return round(scoring.shown(attainment), 2), scoring.status(attainment)


# --- collapsing a period's entries -----------------------------------------


def collapse(kpi_input, cells):
    """Collapse ONE input across every entry in a period, per its `aggregation`.

    This is where "accumulate, don't overwrite" actually happens, and it happens
    on the operand rather than on the finished figure. Summing results would be
    wrong at almost every KPI shape: 3% attrition in week one and 4% in week two
    is not 7% attrition. Summing the operands and re-running the formula is
    right at all of them, which is why the aggregation lives per input.

    It also means a DIVISOR is not accumulated just because it is in the
    formula. `average_headcount` is on `last`, so three uploads describe a
    population of 380, not 1,140.

    Three options and no more. COUNT, MIN and MAX were dropped: the first
    ignored the number in the cell entirely and the other two described the
    entries rather than the period. Anything not SUM or AVG therefore falls
    through to LAST, which is also what an aggregation lost from an older
    database collapses as.
    """
    present = [cell for cell in cells if cell is not None]
    if not present:
        return 0

    if kpi_input.aggregation == Aggregation.SUM:
        return sum(present)
    if kpi_input.aggregation == Aggregation.AVG:
        return statistics.mean(present)

    # LAST: the newest entry wins. It used to have a twin called "replace" that
    # raised on a second row, which is exactly the overwrite-or-fail behaviour
    # the entry model removes — an upload arriving whenever new data exists must
    # never be an error just because it is the second one.
    return present[-1]


def collapsed_values(kpi, entries):
    """Every input collapsed across `entries`, keyed by input key.

    `entries` must carry their `input_values`, newest LAST — `last` means the
    most recent entry, so the order this is handed is part of the answer.
    """
    by_key = {row.key: [] for row in kpi.inputs.all()}
    for entry in entries:
        for operand in entry.input_values.all():
            key = operand.input.key
            if key in by_key:
                by_key[key].append(
                    operand.value_date
                    if operand.value_number is None
                    else operand.value_number
                )
    return {row.key: collapse(row, by_key[row.key]) for row in kpi.inputs.all()}


# --- the write ------------------------------------------------------------


def _period_of(kpi, day):
    """The `(start, end)` the KPI's cadence puts `day` in."""
    return periods.parse(periods.label(day, kpi.frequency), kpi.frequency)


@transaction.atomic
def add_entry(
    kpi,
    entry_date,
    values,
    *,
    source=KpiRecord.Source.MANUAL,
    user=None,
    batch=None,
    remarks='',
    rebuild=True,
):
    """Record one submission and re-derive the period it falls in.

    This is the ONLY way a figure gets in, for manual entry and for import
    alike, so a number typed into the modal and the same number uploaded in a
    file are stored, collapsed and scored identically.

    `entry_date` is the date the figures are FOR, not the reporting period: the
    KPI's cadence decides which period it lands in. That is the whole rule —
    cadence defines the period, never how often you may report into it.

    `values` is already coerced, keyed by `kpi_input.key`. Returns
    `(entry, record)`.

    `rebuild=False` writes the entry and leaves the record alone, for a caller
    inserting many entries at once. A 400-row upload otherwise re-collapses the
    same month 400 times to reach the answer it would have reached once. The
    importer is the only caller that does this, and it is then responsible for
    calling `rebuild_period()` for each period it touched — an entry whose
    period is never rebuilt is invisible on every dashboard.
    """
    period_start, period_end = _period_of(kpi, entry_date)

    # Evaluated per entry as well as per period, so the history log can show
    # what this one submission on its own came to. It is NOT what the period's
    # figure is built from — see rebuild_period.
    value = evaluate(kpi, values)

    entry = KpiEntry.objects.create(
        kpi=kpi,
        entry_date=entry_date,
        period_start=period_start,
        period_end=period_end,
        value=Decimal(str(round(value, 4))),
        value_display=format_value(kpi, value),
        source=source,
        import_batch=batch,
        # The callers validate the length and report it properly; this is the
        # backstop that keeps the invariant true whatever calls in, since
        # Postgres does not enforce a TextField's max_length.
        remarks=(remarks or '')[:REMARKS_MAX_LENGTH],
        entered_by=user if user and user.is_authenticated else None,
    )
    KpiEntryInput.objects.bulk_create(
        KpiEntryInput(
            entry=entry,
            input=row,
            value_number=None if isinstance(values.get(row.key), dt.date) else values.get(row.key),
            value_date=values.get(row.key) if isinstance(values.get(row.key), dt.date) else None,
        )
        for row in kpi.inputs.all()
        if values.get(row.key) is not None
    )

    record = rebuild_period(kpi, period_start) if rebuild else None
    return entry, record


@transaction.atomic
def rebuild_period(kpi, period_start):
    """Re-derive one period's `kpi_record` from every entry inside it.

    The single writer of `kpi_record`. Called after an entry is added, edited or
    removed, so the figure on every dashboard is always the collapse of what is
    currently in `kpi_entry` and can never drift from it.

    A period whose entries have all been removed is SOFT-DELETED rather than
    left showing its last figure, and returns None.
    """
    _, period_end = _period_of(kpi, period_start)

    entries = list(
        KpiEntry.objects.filter(kpi=kpi, period_start=period_start, is_active=True)
        # Oldest first: `last` means the most recent entry wins, and that is
        # decided by the order collapse() is handed, not by the database's mood.
        .order_by('entry_date', 'created_at', 'pk')
        .prefetch_related('input_values__input')
    )

    if not entries:
        KpiRecord.objects.filter(kpi=kpi, period_start=period_start).update(
            is_active=False, entry_count=0
        )
        return None

    # Aggregate the inputs, then calculate. One collapse of the period's raw
    # operands, one run of the formula.
    values = collapsed_values(kpi, entries)
    value = evaluate(kpi, values)

    if kpi.accumulation == Accumulation.CUMULATIVE:
        # A running total: this period's own figure plus everything before it.
        # NOTE: inserting an EARLIER period after a later one leaves the later
        # ones stale — they are recomputed only when that period is next rebuilt.
        previous = (
            KpiRecord.objects.filter(
                kpi=kpi, period_start__lt=period_start, is_active=True
            )
            .order_by('-period_start')
            .first()
        )
        base = float(previous.value) if previous else float(kpi.baseline_value or 0)
        value += base

    # Grade AFTER the carry-forward: `score_expression` reads `value`, and for a
    # cumulative KPI the number being judged is the running total. Doing this
    # before the base was added would score the period's own slice.
    graded = _grade(kpi, values, value)

    attainment, status = score(kpi, graded)
    newest = entries[-1]

    record, _ = KpiRecord.objects.update_or_create(
        kpi=kpi,
        period_start=period_start,
        defaults={
            'period_end': period_end,
            'value': Decimal(str(round(value, 4))),
            'score': None if graded == value else Decimal(str(round(graded, 4))),
            'value_display': format_value(kpi, value),
            'attainment': None if attainment is None else Decimal(str(attainment)),
            'status': status,
            'entry_count': len(entries),
            # Scored against the FULL target even while the period is open, so
            # a month can be watched filling in. This flag is what stops that
            # part-filled figure reading as failure rather than as unfinished.
            'is_in_progress': period_end > timezone.localdate(),
            # The period's provenance is its most recent entry: a month topped
            # up by hand after an upload is now a manual figure.
            'source': newest.source,
            'import_batch': newest.import_batch,
            'remarks': _join_remarks(entries),
            'entered_by': newest.entered_by,
            # REVIVE a deleted row rather than leaving the new figure invisible.
            # The unique key is (kpi, period_start) and it counts deleted rows,
            # so this update lands on the soft-deleted one. Without this, typing
            # or uploading that period again would report success and show
            # nothing, which reads as data loss.
            'is_active': True,
        },
    )

    # Replace rather than merge: the collapsed operand set is whatever the
    # current entries say it is, so a removed entry cannot leave its number
    # behind in the "why is the month this figure?" panel.
    record.input_values.all().delete()
    KpiRecordInput.objects.bulk_create(
        KpiRecordInput(
            record=record,
            input=row,
            value_number=None if isinstance(values.get(row.key), dt.date) else values.get(row.key),
            value_date=values.get(row.key) if isinstance(values.get(row.key), dt.date) else None,
        )
        for row in kpi.inputs.all()
        if values.get(row.key) is not None
    )

    return record


def _grade(kpi, values, value):
    """The number the target is judged against, which is not always the shown one.

    A −3.2% budget variance displays signed and grades as 3.2 against a ±5
    tolerance. Most KPIs have no `score_expression` and grade on the value.
    """
    if not kpi.score_expression:
        return value
    try:
        return float(
            formula_engine.evaluate(
                kpi.score_expression,
                {
                    **{
                        key: float(item or 0)
                        for key, item in values.items()
                        if not isinstance(item, dt.date)
                    },
                    'value': value,
                },
            )
        )
    except formula_engine.FormulaError as error:
        raise RecordError(str(error))


def _join_remarks(entries):
    """One period's notes, newest first, inside the column's limit."""
    seen, out = set(), []
    for entry in reversed(entries):
        note = (entry.remarks or '').strip()
        if note and note not in seen:
            seen.add(note)
            out.append(note)
    joined = ' / '.join(out)
    return joined[:REMARKS_MAX_LENGTH]
