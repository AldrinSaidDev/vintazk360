"""The CSV import pipeline, exactly as `db_schema.txt` Part D specifies it.

    read the kpi= header      → load kpi_definition
    check template= header    → reject if older than the KPI's version
    read its kpi_input rows   → those ARE the expected columns
    validate each cell        → against data_type
    group rows                → by reporting period
    collapse each column      → per kpi_input.aggregation
    evaluate expression       → apps.kpi.formula
    apply accumulation        → apps.kpi.records
    score against the band    → apps.core.kpi, unchanged
    upsert kpi_record         → on (kpi, period_start)
    write kpi_record_input    → one row per operand
    log kpi_import_issue      → for anything rejected
    write audit_log           → one `imported` entry (the caller does this)

**Nothing here is KPI-specific.** Adding a KPI adds zero lines to this file:
the columns come from the KPI's own `kpi_input` rows and the maths from its own
`expression`.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import statistics
import uuid
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from . import periods, records
from .models import (
    Aggregation,
    KpiDefinition,
    KpiImportBatch,
    KpiImportIssue,
    KpiRecord,
)

HEADER_LINES = 3
MAX_BYTES = 5 * 1024 * 1024

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
    created: int = 0
    updated: int = 0
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


# --- collapsing a period's rows into one set of operands -------------------


def aggregate(kpi_input, cells):
    """Collapse one column across a period's rows, per its `aggregation`."""
    if kpi_input.aggregation == Aggregation.COUNT:
        return len(cells)

    present = [c for c in cells if c is not None]
    if not present:
        return 0

    if kpi_input.aggregation == Aggregation.SUM:
        return sum(present)
    if kpi_input.aggregation == Aggregation.AVG:
        return statistics.mean(present)
    if kpi_input.aggregation == Aggregation.MIN:
        return min(present)
    if kpi_input.aggregation == Aggregation.MAX:
        return max(present)
    if kpi_input.aggregation == Aggregation.LAST:
        return present[-1]

    # NONE: exactly one row per period, and more than one is an error.
    if len(present) > 1:
        raise records.RecordError(
            f'{kpi_input.label} expects one row per period, but this period has '
            f'{len(present)}. Set its aggregation to Sum or Average if several '
            'rows are intended.',
            kpi_input.key,
        )
    return present[0]


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
    buckets = {}

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

        try:
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

        bucket = buckets.setdefault(period_start, {'rows': [], 'lines': [], 'remarks': []})
        bucket['rows'].append(values)
        bucket['lines'].append(line_number)
        if (row.get('remarks') or '').strip():
            bucket['remarks'].append(row['remarks'].strip())

    if not buckets and not result.issues:
        raise ImportError_('That file has no data rows to import.')

    result.duplicate_of = (
        KpiImportBatch.objects.filter(kpi=kpi, file_hash=hashlib.sha256(raw).hexdigest())
        .order_by('-uploaded_at')
        .first()
    )

    # The file is stored and the batch written before the records, so a failure
    # part-way through still leaves a trace of what was uploaded.
    batch = _store(raw, kpi=kpi, team=team, branch=branch, user=user, file_name=file_name,
                   content_type=content_type, header=header)
    result.batch = batch

    for period_start in sorted(buckets):
        bucket = buckets[period_start]
        try:
            collapsed = {
                kpi_input.key: aggregate(
                    kpi_input, [row[kpi_input.key] for row in bucket['rows']]
                )
                for kpi_input in inputs
            }
            _, created = records.save_record(
                kpi,
                period_start,
                collapsed,
                source=KpiRecord.Source.IMPORT,
                user=user,
                batch=batch,
                remarks=' · '.join(bucket['remarks'])[:2000],
            )
        except records.RecordError as error:
            result.issues.append(
                Issue(bucket['lines'][0], str(error), error.field or '')
            )
            continue

        result.created += 1 if created else 0
        result.updated += 0 if created else 1

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
    key = f'{team.slug}/{stamp:%Y/%m}/{kpi.slug}-{uuid.uuid4()}.csv'

    if storage.is_configured():
        storage.upload_fileobj(io.BytesIO(raw), key, content_type='text/csv')
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
        template_version=header['template_version'],
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
