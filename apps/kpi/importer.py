"""The CSV import pipeline, per `db_schema.txt` Part D.

    read the kpi= header      → load kpi_definition
    check template= header    → reject if older than the KPI's version
    read its kpi_input rows   → those ARE the expected columns
    validate each cell        → against data_type
    read each row's date      → the cadence decides which period it lands in
    write kpi_entry           → ONE PER ROW, never merged on the way in
    rebuild each period       → apps.kpi.records collapses and scores it
    log kpi_import_issue      → for anything rejected
    write audit_log           → one `imported` entry (the caller does this)

**An upload adds to a period, it does not replace it.** Rows are no longer
collapsed here before being written: each one is its own submission, and the
period is re-derived from every submission ever made against it. So a file
uploaded on the 7th and another on the 21st both count towards August, and the
month can be watched filling in. Cadence decides the period; it has never
decided how often you may upload.

**Nothing here is KPI-specific.** Adding a KPI adds zero lines to this file:
the columns come from the KPI's own `kpi_input` rows and the maths from its own
`expression`.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from . import periods, records, workbook
from .models import (
    REMARKS_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    KpiDefinition,
    KpiImportBatch,
    KpiImportIssue,
    KpiRecord,
)

HEADER_LINES = 3
MAX_BYTES = 5 * 1024 * 1024


def _remarks_error(text):
    """The message for an over-long note, or None when it fits.

    An over-long remark is a bad cell like any other, so the row is skipped and
    the issue names it. Quietly trimming what someone wrote would be worse: the
    upload would report success and the note would come back shorter.
    """
    if len(text) <= REMARKS_MAX_LENGTH:
        return None
    return (
        f'Remarks: {len(text)} characters is over the '
        f'{REMARKS_MAX_LENGTH} character limit. Shorten the note, then upload again.'
    )


# Joining a period's notes moved to `records._join_remarks`: a note now belongs
# to an ENTRY, and what the period's remarks say is decided when the period is
# collapsed, not when one file happens to be read.

# team/slug, or team/branch/slug for a branch KPI (see csv_template.scope_path).
_KPI_HEADER = re.compile(r'kpi\s*=\s*([\w-]+)/(?:([\w-]+)/)?([\w-]+)', re.IGNORECASE)
_TEMPLATE_HEADER = re.compile(r'template\s*=\s*(\d+)', re.IGNORECASE)
_GENERATED_HEADER = re.compile(r'generated\s*=\s*([0-9T:+\-\.]+)', re.IGNORECASE)


class ImportError_(ValueError):
    """The file as a whole cannot be processed. Per-ROW problems are issues."""


@dataclass
class Issue:
    row_number: int
    message: str
    column_key: str = ''
    raw_value: str = ''
    severity: str = KpiImportIssue.Severity.ERROR


@dataclass
class Result:
    batch: KpiImportBatch = None
    # PERIODS opened and PERIODS added to. A file reporting three weeks of one
    # month is one period, not three, which is what a reader expects the import
    # history to say.
    created: int = 0
    updated: int = 0
    # Submissions written. Different from the two above and worth its own
    # number now that a period is built from many: "3 periods, 42 entries".
    entries: int = 0
    rows: int = 0
    issues: list = field(default_factory=list)
    # True when a file with identical contents was already uploaded for this
    # KPI. Not an error — re-uploading is how a correction is made — but worth
    # saying, since it is usually a slip. This is what `file_hash` is for.
    duplicate_of: KpiImportBatch = None

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == KpiImportIssue.Severity.ERROR]


# --- reading the file ------------------------------------------------------


def _decode(raw: bytes) -> str:
    """Text from bytes, tolerating the BOM our own templates carry."""
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportError_('That file is not readable as text. Save it as CSV (UTF-8).')


def read_header(text: str) -> dict:
    """The three comment lines the template promises, parsed.

    Everything the importer needs to identify the file lives here, which is why
    the template's own first line tells the user not to remove them.
    """
    lines = text.splitlines()
    comments = [line for line in lines[:HEADER_LINES + 2] if line.lstrip().startswith('#')]
    joined = '\n'.join(comments)

    kpi_match = _KPI_HEADER.search(joined)
    if not kpi_match:
        raise ImportError_(
            'This file has no "kpi=" header, so there is no way to tell which '
            'KPI it belongs to. Download a fresh template and fill that in.'
        )

    template_match = _TEMPLATE_HEADER.search(joined)
    generated_match = _GENERATED_HEADER.search(joined)

    return {
        'team_slug': kpi_match.group(1),
        'branch_slug': kpi_match.group(2),
        'kpi_slug': kpi_match.group(3),
        'template_version': int(template_match.group(1)) if template_match else 0,
        'generated': generated_match.group(1) if generated_match else None,
        'comment_count': len(comments),
    }


def resolve_kpi(header, team, branch=None) -> KpiDefinition:
    """Find the KPI the file says it is for, and refuse someone else's."""
    if header['team_slug'] != team.slug:
        raise ImportError_(
            f'This template belongs to "{header["team_slug"]}", not {team.name}.'
        )

    # A slug is unique per (team, branch), so the branch is part of the KPI's
    # identity and not just a filter. Getting this wrong would file one Sales
    # branch's numbers under another branch's KPI of the same name.
    expected = branch.slug if branch is not None else None
    if header['branch_slug'] != expected:
        where = f'the {branch.name} branch' if branch is not None else f'{team.name} itself'
        belongs = (
            f'the "{header["branch_slug"]}" branch'
            if header['branch_slug']
            else f'{team.name} itself'
        )
        raise ImportError_(
            f'This template belongs to {belongs}, not {where}. '
            'Upload it on that page instead.'
        )

    kpi = KpiDefinition.objects.filter(
        team=team, branch=branch, slug=header['kpi_slug'], is_active=True
    ).first()
    if kpi is None:
        raise ImportError_(
            f'No active KPI called "{header["kpi_slug"]}" in {team.name}. '
            'It may have been retired or renamed.'
        )

    # §A.6 rule 3: an old template's columns no longer match the current
    # operands, so accepting it would write the wrong numbers into the wrong
    # inputs. Silence is the dangerous option here.
    if header['template_version'] < kpi.template_version:
        raise ImportError_(
            f'This template is out of date (v{header["template_version"]}; '
            f'{kpi.name} is now v{kpi.template_version}). Download a fresh one '
            'from KPI Management and re-enter the figures.'
        )

    return kpi


def _rows(text: str, header):
    """The data rows, as dicts, with their 1-based line numbers as seen in Excel."""
    lines = text.splitlines()
    body = [line for line in lines if not line.lstrip().startswith('#')]
    reader = csv.DictReader(io.StringIO('\n'.join(body)))

    if reader.fieldnames is None:
        raise ImportError_('That file has no column headings.')

    fieldnames = [(name or '').strip() for name in reader.fieldnames]
    reader.fieldnames = fieldnames

    # +1 for the heading row, + the comment lines, so the number matches what
    # the user sees in the spreadsheet.
    offset = header['comment_count'] + 1
    for index, row in enumerate(reader, start=1):
        yield offset + index, {(k or '').strip(): v for k, v in row.items()}, fieldnames


# --- turning read rows into entries ----------------------------------------
#
# `aggregate()` used to live here, collapsing a period's rows into one set of
# operands before writing. It moved to `records.collapse()`, because collapsing
# is no longer something the importer does to a file: it is what a period does
# to every entry ever made against it, whether they arrived in one upload, in
# six uploads a week apart, or by hand through the modal. Keeping a copy here
# would be a second answer to "what is August's figure?".


def _write_entries(kpi, rows, batch, result, user, label=''):
    """Write one KPI's rows as entries, then re-derive each period they touch.

    Every row is its own entry, so uploading the same month twice adds to it
    instead of replacing it. The rebuild is deferred and done once per period
    rather than once per row: a 400-row file otherwise re-collapses the same
    month 400 times to reach the answer it reaches once.
    """
    touched = set()

    for row in rows:
        try:
            records.add_entry(
                kpi,
                row['entry_date'],
                row['values'],
                source=KpiRecord.Source.IMPORT,
                user=user,
                batch=batch,
                remarks=row['remarks'],
                rebuild=False,
            )
        except records.RecordError as error:
            result.issues.append(
                Issue(row['line'], f'{label}{error}' if label else str(error),
                      error.field or '')
            )
            continue
        touched.add(row['period_start'])
        result.entries += 1

    for period_start in sorted(touched):
        try:
            existed = KpiRecord.objects.filter(
                kpi=kpi, period_start=period_start, is_active=True
            ).exists()
            records.rebuild_period(kpi, period_start)
        except records.RecordError as error:
            # The entries are written and will collapse correctly the next time
            # this period is rebuilt, so this is an issue on the period, not a
            # reason to throw the upload away.
            result.issues.append(
                Issue(0, f'{label}{error}' if label else str(error), error.field or '')
            )
            continue
        # "Created" and "updated" count PERIODS, which is what the import
        # history has always reported and what a reader recognises. How many
        # submissions went into them is `entries`.
        if existed:
            result.updated += 1
        else:
            result.created += 1


# --- the whole run ---------------------------------------------------------


def parse_and_apply(raw: bytes, *, team, user, file_name, content_type='', branch=None):
    """Import one uploaded file. Returns a `Result`; raises `ImportError_` only
    for whole-file problems, never for a single bad row."""
    if not raw:
        raise ImportError_('That file is empty.')
    if len(raw) > MAX_BYTES:
        raise ImportError_('That file is larger than 5 MB.')

    text = _decode(raw)
    header = read_header(text)
    kpi = resolve_kpi(header, team, branch)

    inputs = list(kpi.inputs.all())
    expected = [row.key for row in inputs]

    result = Result()
    entry_rows = []
    # Rows that carry at least one figure. The template ships with its period
    # cell already filled, so an untouched file is not "empty" — see below.
    filled_rows = 0

    for line_number, row, fieldnames in _rows(text, header):
        missing = [key for key in expected if key not in fieldnames]
        if missing:
            raise ImportError_(
                'This file is missing the column(s) ' + ', '.join(missing) +
                '. Download a fresh template for this KPI.'
            )

        if not any((value or '').strip() for value in row.values()):
            continue  # a blank spacer row, not an error

        result.rows += 1
        if any((row.get(key) or '').strip() for key in expected):
            filled_rows += 1

        try:
            # The cell holds the DATE this row is for. The KPI's cadence then
            # decides which period that lands in — a full date is kept as
            # written so the history log can say when each figure arrived, and
            # a bare period label still works for reporting a whole month at once.
            entry_date = periods.parse_entry_date(row.get('period'), kpi.frequency)
            period_start, _ = periods.parse(row.get('period'), kpi.frequency)
        except periods.PeriodError as error:
            result.issues.append(
                Issue(line_number, str(error), 'period', (row.get('period') or '')[:255])
            )
            continue

        try:
            values = {}
            for kpi_input in inputs:
                values[kpi_input.key] = records.coerce(row.get(kpi_input.key), kpi_input)
        except records.RecordError as error:
            result.issues.append(
                Issue(
                    line_number,
                    str(error),
                    error.field or '',
                    (row.get(error.field) or '')[:255] if error.field else '',
                )
            )
            continue

        remarks = (row.get('remarks') or '').strip()
        too_long = _remarks_error(remarks)
        if too_long:
            result.issues.append(Issue(line_number, too_long, 'remarks', remarks[:255]))
            continue

        entry_rows.append({
            'line': line_number,
            'entry_date': entry_date,
            'period_start': period_start,
            'values': values,
            'remarks': remarks,
        })

    if not entry_rows and not result.issues:
        raise ImportError_('That file has no data rows to import.')

    # A downloaded template arrives with its period cell already filled and the
    # rest blank, so uploading it untouched used to produce one "X is required"
    # per row: a whole-file mistake reported as a cell-level one, complete with
    # a batch in the import history recording that nothing happened. It is the
    # likeliest slip of all now that the file also carries a worked example.
    if result.rows and not filled_rows:
        raise ImportError_(
            'This template has not been filled in yet. Every row has a date '
            'but no figures. Enter the numbers under '
            + ', '.join(expected)
            + ', then upload it again.'
        )

    result.duplicate_of = (
        # Live batches only: after an import is deleted, uploading the same file
        # again is how you undo that, not an accidental repeat.
        KpiImportBatch.objects.filter(
            kpi=kpi, file_hash=hashlib.sha256(raw).hexdigest(), is_active=True
        )
        .order_by('-uploaded_at')
        .first()
    )

    # The file is stored and the batch written before the records, so a failure
    # part-way through still leaves a trace of what was uploaded.
    batch = _store(raw, kpi=kpi, team=team, branch=branch, user=user, file_name=file_name,
                   content_type=content_type, header=header)
    result.batch = batch

    _write_entries(kpi, entry_rows, batch, result, user)

    _finish(batch, result)
    return result


def _store(raw, *, kpi, team, user, file_name, content_type, header, branch=None):
    """Put the file in object storage and record the pointer.

    Dev has no R2 credentials, so the file lands on local disk and
    `storage_provider` says so. The three `storage_*` columns exist precisely so
    the row records WHICH vendor holds the object.
    """
    from django.conf import settings
    from apps.core import storage

    digest = hashlib.sha256(raw).hexdigest()
    stamp = timezone.now()
    # A UUID, not the content hash: re-uploading a corrected file is a
    # SUPPORTED action (§F idempotency), and every upload has to be its own
    # object. `file_hash` below is what spots an accidental duplicate; the path
    # must never collide, which a timestamp plus a content hash does the moment
    # the same file is sent twice in one second.
    # A workbook covers every KPI, so it has no single slug to be named after.
    stem = kpi.slug if kpi is not None else 'workbook'
    suffix = 'xlsx' if file_name.lower().endswith('.xlsx') else 'csv'
    key = f'{team.slug}/{stamp:%Y/%m}/{stem}-{uuid.uuid4()}.{suffix}'

    if storage.is_configured():
        storage.upload_fileobj(io.BytesIO(raw), key, content_type=content_type or 'text/csv')
        provider = KpiImportBatch.Provider.R2
        bucket = storage.bucket_name()
    else:
        destination = settings.MEDIA_ROOT / 'kpi-imports' / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        provider = KpiImportBatch.Provider.LOCAL
        bucket = 'kpi-imports'

    generated = None
    if header.get('generated'):
        generated = timezone.datetime.fromisoformat(header['generated'])
        if timezone.is_naive(generated):
            generated = timezone.make_aware(generated)

    return KpiImportBatch.objects.create(
        team=team,
        branch=branch,
        kpi=kpi,
        file_name=file_name[:255],
        storage_provider=provider,
        storage_bucket=bucket[:100],
        storage_path=key[:500],
        file_size=len(raw),
        file_hash=digest,
        content_type=(content_type or 'text/csv')[:60],
        template_version=header.get('template_version') or 0,
        template_generated_at=generated,
        uploaded_at=stamp,
        status=KpiImportBatch.Status.PENDING,
        uploaded_by=user if user and user.is_authenticated else None,
    )


@transaction.atomic
def _finish(batch, result):
    """Write the per-row issues and the batch's summary line."""
    KpiImportIssue.objects.bulk_create(
        KpiImportIssue(
            batch=batch,
            row_number=issue.row_number,
            column_key=issue.column_key[:60],
            raw_value=issue.raw_value[:255],
            severity=issue.severity,
            message=issue.message[:255],
        )
        for issue in result.issues
    )

    errors = len(result.errors)
    applied = result.created + result.updated

    batch.row_count = result.rows
    batch.created_count = result.created
    batch.updated_count = result.updated
    batch.error_count = errors
    batch.status = (
        KpiImportBatch.Status.APPLIED if applied and not errors
        else KpiImportBatch.Status.PARTIAL if applied
        else KpiImportBatch.Status.FAILED
    )
    batch.completed_at = timezone.now()
    batch.save()


# --- one workbook, one sheet per KPI ---------------------------------------


def _collect(kpi, rows, result, label=''):
    """Turn a sheet's rows into entry rows, logging bad cells as it goes.

    One spreadsheet row is one entry. It is no longer collapsed here: rows for
    the same month are not merged on the way in, they are written as separate
    submissions and collapsed by the period when it is rebuilt. That is what
    makes uploading week two add to week one instead of replacing it.

    `label` prefixes an issue message with the KPI it came from, which is what
    makes a many-sheet upload readable — `kpi_import_issue` has no sheet column.
    """
    inputs = list(kpi.inputs.all())
    expected = [row.key for row in inputs]
    entry_rows = []
    filled = 0

    def note(row_number, message, column='', raw=''):
        result.issues.append(
            Issue(row_number, f'{label}{message}' if label else message,
                  column, str(raw)[:255])
        )

    for line_number, row in rows:
        # A row carrying only its period is the template's own blank row, not
        # data. Skipping it silently is what makes one workbook usable: most
        # months you have figures for some KPIs and not others, and being told
        # "Actual billable hours is required" about every sheet you deliberately
        # left alone would make the format unusable.
        if not any((row.get(key) or '').strip() for key in expected):
            continue

        result.rows += 1
        filled += 1

        try:
            # See the CSV path: the cell is the DATE, the cadence picks the period.
            entry_date = periods.parse_entry_date(row.get('period'), kpi.frequency)
            period_start, _ = periods.parse(row.get('period'), kpi.frequency)
        except periods.PeriodError as error:
            note(line_number, str(error), 'period', row.get('period') or '')
            continue

        try:
            values = {}
            for kpi_input in inputs:
                values[kpi_input.key] = records.coerce(row.get(kpi_input.key), kpi_input)
        except records.RecordError as error:
            note(line_number, str(error), error.field or '',
                 (row.get(error.field) or '') if error.field else '')
            continue

        remarks = (row.get('remarks') or '').strip()
        too_long = _remarks_error(remarks)
        if too_long:
            note(line_number, too_long, 'remarks', remarks[:255])
            continue

        entry_rows.append({
            'line': line_number,
            'entry_date': entry_date,
            'period_start': period_start,
            'values': values,
            'remarks': remarks,
        })

    return entry_rows, filled


def _apply(kpi, entry_rows, batch, result, user, label=''):
    """Write one sheet's entries and re-derive their periods."""
    _write_entries(kpi, entry_rows, batch, result, user, label)


def parse_and_apply_workbook(raw, *, team, user, file_name, content_type='', branch=None):
    """Import one filled-in team workbook. Returns a `Result`.

    Every sheet is independent. A sheet nobody filled in is SKIPPED silently,
    which is the whole point of the one-file design: on any given month you
    have numbers for some KPIs and not others, and being nagged about the
    sheets you left alone would make the format unusable. Only a workbook with
    nothing filled in anywhere is an error.

    A stale or unknown sheet is likewise an issue on that sheet rather than a
    rejection of the file: one KPI's formula changing must not block the other
    five from reporting.
    """
    if not raw:
        raise ImportError_('That file is empty.')
    if len(raw) > MAX_BYTES:
        raise ImportError_('That file is larger than 5 MB.')

    try:
        sheets = list(workbook.read_sheets(raw))
    except ValueError as error:
        raise ImportError_(str(error))

    if not sheets:
        raise ImportError_('That workbook has no sheets.')

    result = Result()
    plans = []          # (kpi, entry_rows, label)
    filled_total = 0
    recognised = 0      # sheets carrying a kpi= note
    resolved = 0        # …that also matched a live KPI on this team
    resolve_errors = []
    first_header = None

    for title, header_text, columns, rows in sheets:
        label = f'{title}: '

        try:
            header = read_header(header_text)
        except ImportError_:
            # A sheet somebody added by hand, or the "No KPIs yet" placeholder.
            # Not an error unless it holds data nobody can file anywhere.
            if rows:
                result.issues.append(Issue(
                    workbook.COLUMN_ROW,
                    f'{label}this sheet has no "kpi=" note, so there is no way '
                    'to tell which KPI it belongs to. It was skipped.',
                ))
            continue

        recognised += 1
        first_header = first_header or header

        try:
            kpi = resolve_kpi(header, team, branch)
        except ImportError_ as error:
            resolve_errors.append(str(error))
            result.issues.append(Issue(workbook.COLUMN_ROW, f'{label}{error}'))
            continue
        resolved += 1

        missing = [k.key for k in kpi.inputs.all() if k.key not in columns]
        if missing:
            result.issues.append(Issue(
                workbook.COLUMN_ROW,
                f'{label}missing the column(s) ' + ', '.join(missing) +
                '. Download a fresh workbook.',
            ))
            continue

        entry_rows, filled = _collect(kpi, rows, result, label)
        filled_total += filled
        if filled:
            plans.append((kpi, entry_rows, label))

    if not recognised:
        raise ImportError_(
            'None of the sheets in that workbook are KPI templates. '
            'Download a fresh one from KPI Management.'
        )

    # Every sheet failed to resolve, so this is not a per-sheet problem: the
    # workbook belongs to another team, or to a set of KPIs that no longer
    # exists. Reporting it once on the form beats the same message repeated
    # per sheet in an import-history row nobody asked for.
    if not resolved:
        raise ImportError_(resolve_errors[0])

    if not filled_total and not result.issues:
        raise ImportError_(
            'Nothing was filled in. Enter figures on at least one sheet, '
            'then upload it again.'
        )

    result.duplicate_of = (
        KpiImportBatch.objects.filter(
            team=team, kpi__isnull=True, file_hash=hashlib.sha256(raw).hexdigest(),
            is_active=True,
        )
        .order_by('-uploaded_at')
        .first()
    )

    # kpi=None: the batch covers the whole team, which is why that column is
    # nullable and why Recent Import History already reads "Multiple".
    batch = _store(
        raw, kpi=None, team=team, branch=branch, user=user, file_name=file_name,
        content_type=content_type or
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        header=first_header or {},
    )
    result.batch = batch

    for kpi, entry_rows, label in plans:
        _apply(kpi, entry_rows, batch, result, user, label)

    _finish(batch, result)
    return result
