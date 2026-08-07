"""Writing one actual: the single path from raw operands to a scored record.

Manual entry and CSV import both come through `save_record()`, so a number
typed into the modal and the same number uploaded in a file are stored and
scored identically. Anything that differs between the two (where the file went,
which rows were rejected) belongs to the importer, not here.

The shape of the work, per `db_schema.txt`:

    raw operand values  →  coerce per kpi_input.data_type
                        →  evaluate kpi_definition.expression (apps.kpi.formula)
                        →  apply accumulation, if the KPI is cumulative
                        →  score against the target band (apps.core.kpi)
                        →  upsert kpi_record on (kpi, period_start)
                        →  replace kpi_record_input, one row per operand

Design principle 2 is what makes the last step matter: the record keeps `3.1%`,
these keep `12` and `380`. Correct a formula later and history can be recomputed.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.core import kpi as scoring

from . import formula as formula_engine
from . import periods
from .models import DataType, Accumulation, DisplayFormat, KpiRecord, KpiRecordInput


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


# --- the write ------------------------------------------------------------


@transaction.atomic
def save_record(
    kpi,
    period_start,
    values,
    *,
    source=KpiRecord.Source.MANUAL,
    user=None,
    batch=None,
    remarks='',
):
    """Create or update this KPI's record for one period.

    `values` is already-coerced, keyed by `kpi_input.key`. Returns
    `(record, created)`.
    """
    _, period_end = periods.parse(periods.label(period_start, kpi.frequency), kpi.frequency)

    value = evaluate(kpi, values)

    if kpi.accumulation == Accumulation.CUMULATIVE:
        # A running total: this period's own figure plus everything before it.
        # NOTE: inserting an EARLIER period after a later one leaves the later
        # ones stale — they are recomputed only when re-saved.
        previous = (
            KpiRecord.objects.filter(kpi=kpi, period_start__lt=period_start)
            .order_by('-period_start')
            .first()
        )
        base = float(previous.value) if previous else float(kpi.baseline_value or 0)
        value += base

    graded = value
    if kpi.score_expression:
        # The graded number can differ from the shown one: a −3.2% variance
        # displays signed but is scored as 3.2 against a ±5 tolerance.
        try:
            graded = float(
                formula_engine.evaluate(
                    kpi.score_expression,
                    {**{k: float(v or 0) for k, v in values.items() if not isinstance(v, dt.date)}, 'value': value},
                )
            )
        except formula_engine.FormulaError as error:
            raise RecordError(str(error))

    attainment, status = score(kpi, graded)

    record, created = KpiRecord.objects.update_or_create(
        kpi=kpi,
        period_start=period_start,
        defaults={
            'period_end': period_end,
            'value': Decimal(str(round(value, 4))),
            'score': None if graded == value else Decimal(str(round(graded, 4))),
            'value_display': format_value(kpi, value),
            'attainment': None if attainment is None else Decimal(str(attainment)),
            'status': status,
            'source': source,
            'import_batch': batch,
            'remarks': remarks or '',
            'entered_by': user if user and user.is_authenticated else None,
        },
    )

    # Replace rather than merge: the operand set is whatever this save says it
    # is, so a re-upload with a corrected column cannot leave a stale value behind.
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

    return record, created
