"""Generate a KPI's CSV template — entirely from the KPI's own definition.

`db_schema.txt` Part D. Nothing here is KPI-specific: the columns are the KPI's
`kpi_input` rows in `position` order, because a key is simultaneously the
expression variable, the CSV header and the form field name. **Adding a KPI
adds zero lines of this file.**

The file is built ON DEMAND, never stored. §A.6 requires a freshly downloaded
template to carry the *current* `template_version`; a file saved at creation
time would silently go stale the first time anyone edited the formula, and the
importer would then reject the very template the screen was handing out.

    # Vintazk 360 KPI template. Do not edit or remove these three lines.
    # kpi=operations/attrition-rate | template=1 | frequency=monthly | generated=…
    # Formula: Total exits ÷ Average headcount × 100  ·  Target: Threshold 3.5% (lower is better)
    period,total_exits,average_headcount,remarks
    2026-08,,,
"""

from __future__ import annotations

import csv
import io

from django.utils import timezone

from .models import Direction, Frequency

HEADER_NOTE = 'Vintazk 360 KPI template. Do not edit or remove these three lines.'

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


def filename(kpi) -> str:
    return f'{kpi.team.slug}-{kpi.slug}-template-v{kpi.template_version}.csv'


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
        f'# kpi={kpi.team.slug}/{kpi.slug} | template={kpi.template_version} '
        f'| frequency={kpi.frequency} | generated={generated}\n'
    )
    buffer.write(
        f'# Formula: {formula}  ·  Target: {target}'
        + (f' ({direction})' if direction else '')
        + '\n'
    )

    header = columns(kpi)
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(header)
    # One blank row for the current period, so the person filling it in can see
    # the period format without a fake number they might upload as if it were real.
    writer.writerow([period_label(kpi.frequency, when), *[''] * (len(header) - 1)])

    return buffer.getvalue()


def build_bytes(kpi, when=None) -> bytes:
    """The file as bytes, BOM-first — this is what a view should serve.

    Excel does not sniff UTF-8: double-clicking a plain UTF-8 CSV on Windows
    decodes it as the ANSI code page, which turns the formula's ÷ × · — into
    Ã· Ã— Â· â€". A leading BOM is the one signal Excel does honour, and every
    other CSV reader skips it (Python's own `utf-8-sig` included).
    """
    return build(kpi, when).encode('utf-8-sig')
