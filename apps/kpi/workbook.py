"""One workbook per team: every KPI a sheet, instead of a CSV per KPI.

The per-KPI CSV (`apps/kpi/csv_template.py`) asks someone reporting six KPIs to
download six files, fill six files and upload six files. This is the same
contract in one file: one download, one sheet per live KPI, one upload.

    operations-kpi-template-v2026-08-07.xlsx
      ├─ Attrition Rate            period | total_exits | average_headcount | remarks
      ├─ Client Retention Rate     period | clients_retained | …
      └─ …

Adding a KPI adds a sheet and deleting one removes it, with no action from
anybody: the workbook is built on demand from `kpi_definition`, exactly as the
CSV is, and for the same §A.6 reason — a stored file goes stale the moment a
formula changes.

**The sheet name is decoration; the `kpi=` cell is the identity.** Excel caps a
sheet name at 31 characters and forbids `[]:*?/\\`, so names get truncated and
deduplicated, and a user can rename a tab freely. Every sheet therefore carries
the same `kpi=team/[branch/]slug | template=N` header the CSV does, and that is
what the importer reads.

Rows 1-3 of each sheet are the header block, row 4 the column names, row 5 a
worked example, row 6 the blank row to fill. The example's first cell starts
with `#`, the same "this row is a note" convention the CSV uses, so one rule
covers both formats.
"""

from __future__ import annotations

import io
import re

from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import csv_template
from .models import DataType

# Excel forbids these in a sheet name, and caps it at 31 characters.
_ILLEGAL_SHEET = re.compile(r'[\[\]:*?/\\]')
SHEET_NAME_LIMIT = 31

# A row whose first cell starts with this is a note, not data. Same convention
# as the CSV template, so `importer` strips both the same way.
COMMENT = '#'

HEADER_ROWS = 3       # the three note rows at the top of every sheet
COLUMN_ROW = 4        # where the real column names live
FIRST_DATA_ROW = 5    # the example, then the blank row

# Brand ink, brand purple, and a light tint. The note rows are INK, not grey:
# they carry the KPI's identity, its formula and its target, which is the first
# thing anyone opening the sheet needs to read. Greying them said "skip this".
_INK = 'FF040404'
_BRAND = 'FF4F3D67'
_TINT = 'FFF1F5F9'
_BLUSH = 'FFDFADB6'


def sheet_name(kpi, taken):
    """A legal, unique Excel sheet name for this KPI.

    Truncation and deduplication are why the name cannot be the identity: two
    KPIs called "Time-to-Fill (Support/Leadership)" and "Time-to-Fill (Support
    Staff)" collapse to the same 31 characters.
    """
    base = _ILLEGAL_SHEET.sub(' ', kpi.name).strip()[:SHEET_NAME_LIMIT] or 'KPI'
    candidate, counter = base, 2
    while candidate in taken:
        suffix = f' ({counter})'
        candidate = base[: SHEET_NAME_LIMIT - len(suffix)] + suffix
        counter += 1
    taken.add(candidate)
    return candidate


def filename(team, branch=None) -> str:
    stem = f'{team.slug}-{branch.slug}' if branch is not None else team.slug
    return f'{stem}-kpi-template-{timezone.localdate():%Y-%m-%d}.xlsx'


def _write_sheet(sheet, kpi, team, generated, when=None):
    """One KPI's sheet: three note rows, the columns, an example, a blank row."""
    columns = csv_template.columns(kpi)
    target = kpi.target_display or 'No target'
    direction = csv_template.DIRECTION_NOTE.get(kpi.direction, '')
    dates = any(row.data_type == DataType.DATE for row in kpi.inputs.all())
    owner = kpi.branch.name if kpi.branch_id else team.name

    notes = [
        # The masthead: whose file this is and which KPI this tab measures.
        # Excel lets a long A1 overflow across the empty cells beside it, so
        # this reads as a title bar without merging anything.
        f'{COMMENT} VINTAZK 360   ·   {owner}   ·   {kpi.name}',
        f'{COMMENT} kpi={csv_template.scope_path(kpi)} '
        f'| template={kpi.template_version} | frequency={kpi.frequency} '
        f'| generated={generated}',
        f'{COMMENT} Formula: {kpi.formula_text or kpi.expression}  ·  Target: {target}'
        + (f' ({direction})' if direction else '')
        + '  ·  '
        + csv_template.PERIOD_NOTE.format(
            cadence=csv_template.CADENCE_WORD.get(kpi.frequency, 'reporting')
        )
        + (f'  ·  {csv_template.DATE_NOTE}' if dates else '')
        + '  ·  Rows starting with # are notes. Leave them; they are ignored on upload.',
    ]
    for index, note in enumerate(notes, start=1):
        cell = sheet.cell(row=index, column=1, value=note)
        # Black, at three weights. The masthead leads, the identity line is
        # plain, the formula line is the one to read before typing.
        cell.font = Font(
            name='Calibri',
            size=13 if index == 1 else 10,
            bold=index == 1,
            color=_INK,
        )
    sheet.row_dimensions[1].height = 22
    sheet.row_dimensions[3].height = 16

    for index, name in enumerate(columns, start=1):
        cell = sheet.cell(row=COLUMN_ROW, column=index, value=name)
        cell.font = Font(bold=True, color='FFFFFFFF', size=10)
        cell.fill = PatternFill('solid', fgColor=_BRAND)
        cell.alignment = Alignment(horizontal='left')

    # The worked example. Its own row is a comment so it can never be read as
    # data; the tint and the trailing label are what say so to a human. The
    # TEXT stays ink, so the numbers can be read at a glance and copied.
    example = [
        f'{COMMENT} {csv_template.previous_period(kpi, when)}',
        *csv_template.example_values(kpi),
        'Optional note',
        # Sits one column past `remarks`. `read_sheets` zips cells against the
        # column names, so a trailing extra is dropped; the row is skipped as a
        # comment anyway.
        '←  example, ignored on upload',
    ]
    for index, value in enumerate(example, start=1):
        cell = sheet.cell(row=FIRST_DATA_ROW, column=index, value=value)
        cell.font = Font(size=10, color=_INK, italic=index == len(example))
        if index <= len(columns):
            cell.fill = PatternFill('solid', fgColor=_TINT)

    # The row to actually fill: the current period, everything else empty. A
    # blush underline marks where to type without shouting about it.
    for index in range(1, len(columns) + 1):
        cell = sheet.cell(row=FIRST_DATA_ROW + 1, column=index)
        cell.font = Font(size=11, color=_INK)
        cell.fill = PatternFill('solid', fgColor=_BLUSH if index == 1 else 'FFFFFFFF')
    # Today's DATE, not the period label. The column carries the date the
    # figures are for and the cadence decides which period that lands in, which
    # is what lets a month be topped up on the 7th and again on the 21st.
    sheet.cell(row=FIRST_DATA_ROW + 1, column=1,
               value=(when or timezone.localdate()).isoformat())

    # Wide enough to read the column names without dragging every border.
    for index, name in enumerate(columns, start=1):
        width = max(len(name) + 4, 14)
        sheet.column_dimensions[get_column_letter(index)].width = min(width, 42)
    sheet.freeze_panes = sheet.cell(row=FIRST_DATA_ROW, column=1)


def build(kpis, team, branch=None, when=None) -> bytes:
    """The whole workbook as bytes. `kpis` is already ordered and scoped."""
    generated = timezone.now().isoformat(timespec='seconds')

    book = Workbook()
    book.remove(book.active)

    taken = set()
    for kpi in kpis:
        _write_sheet(
            book.create_sheet(sheet_name(kpi, taken)), kpi, team, generated, when
        )

    if not book.sheetnames:
        # openpyxl cannot save a workbook with no sheets, and a team with no
        # KPIs still deserves a file that explains itself rather than a 500.
        sheet = book.create_sheet('No KPIs yet')
        sheet['A1'] = (
            f'{COMMENT} {team.name} has no active KPIs. '
            'Define one on KPI Management, then download this again.'
        )

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


# --- reading one back -------------------------------------------------------


def _cell_text(value):
    """A cell as the importer wants it: text, with Excel's quirks flattened."""
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        # Excel hands back a datetime for anything it decided was a date. The
        # importer parses ISO, and a date typed into a date-formatted cell would
        # otherwise arrive as "2026-08-06 00:00:00" and be rejected.
        text = value.isoformat()
        return text[:10] if text.endswith('00:00:00') else text
    if isinstance(value, float) and value.is_integer():
        # 17.0 came from a whole number; keep it whole so an integer input
        # ("must be a whole number") is not rejected by its own spreadsheet.
        return str(int(value))
    return str(value).strip()


def read_sheets(raw: bytes):
    """Yield `(sheet_name, header_text, column_names, rows)` per sheet.

    `rows` are `(excel_row_number, {column: text})`, comment and blank rows
    already dropped. Nothing here knows about KPIs; `importer` resolves those.
    """
    try:
        book = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    except Exception as error:  # openpyxl raises a zoo of exception types
        raise ValueError(
            'That file could not be read as an Excel workbook. '
            'Download a fresh template and fill that in.'
        ) from error

    for sheet in book.worksheets:
        grid = [
            [_cell_text(cell) for cell in row]
            for row in sheet.iter_rows(values_only=True)
        ]
        notes = [
            row[0] for row in grid
            if row and row[0].startswith(COMMENT)
        ]
        header_text = '\n'.join(notes)

        columns, rows = [], []
        for number, row in enumerate(grid, start=1):
            first = row[0] if row else ''
            if first.startswith(COMMENT):
                continue
            if not any(cell for cell in row):
                continue
            if not columns:
                columns = [cell for cell in row]
                continue
            rows.append((number, dict(zip(columns, row))))

        yield sheet.title, header_text, columns, rows

    book.close()
