from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone

from apps.core.audit import log_action
from apps.core.models import AuditLog, Team
from apps.kpi import csv_template, importer
from apps.kpi import periods as kpi_periods
from apps.kpi import records as kpi_records
from apps.kpi.models import (
    Frequency,
    KpiCategory,
    KpiDefinition,
    KpiImportBatch,
    KpiRecord,
)
from .forms import AddRecordForm, CreateKpiForm, EditKpiForm, ImportRecordsForm

from django.contrib import messages
# Glyph cluster behind the banner header (FA4 names, largest first).
BANNER_ICONS = ['cogs', 'tasks', 'line-chart']


# --- SEED DATA ---------------------------------------------------------------
# No screen reads these any more: all four Operations pages are DB-backed. They
# survive as the input to `manage.py seed_operations_kpis`, which turns them
# into real KpiDefinition rows. Delete them once the six KPIs exist everywhere
# they need to, and delete the command with them.
#
# direction:
#   'up'   → higher is better; attainment = actual / target * 100
#   'down' → lower is better (e.g. attrition threshold); attainment = target / actual * 100
_OPERATIONS_KPIS = [
    {'name': 'Attrition Rate',            'category': 'People',        'target': 3.5,  'actual': 3.1,  'direction': 'down', 'target_display': 'Threshold 3.5%', 'actual_display': '3.1%',
     'frequency': 'Monthly',   'formula': 'Total exits ÷ Average headcount × 100',
     'description': 'Percentage of employees who leave during the reporting period.'},
    {'name': 'Client Retention Rate',     'category': 'Financial',     'target': 100,  'actual': 96,   'direction': 'up',   'target_display': '100%',           'actual_display': '96%',
     'frequency': 'Monthly',   'formula': 'Clients retained ÷ Total existing clients × 100',
     'description': 'Percentage of clients retained over the period, excluding clients acquired within the last month.'},
    {'name': 'Billable Hours Achievement','category': 'Financial',     'target': 95,   'actual': 92,   'direction': 'up',   'target_display': '≥95%',           'actual_display': '92%',
     'frequency': 'Monthly',   'formula': 'Actual billable hours ÷ Required billable hours × 100',
     'description': 'Percentage of required client-billable hours successfully delivered.'},
    {'name': 'CSAT',                      'category': 'Client Impact', 'target': 90,   'actual': 93,   'direction': 'up',   'target_display': '≥90%',           'actual_display': '93%',
     'frequency': 'Quarterly', 'formula': 'Positive responses ÷ Total survey responses × 100',
     'description': 'Percentage of customers who give a positive satisfaction rating.'},
    {'name': 'EBR Completion',            'category': 'Operational',   'target': 100,  'actual': 100,  'direction': 'up',   'target_display': '100%',           'actual_display': '100%',
     'frequency': 'Quarterly', 'formula': 'Completed compliant reviews ÷ Scheduled reviews × 100',
     'description': 'Percentage of scheduled business reviews completed accurately and on time.'},
    {'name': 'Seat Expansion',            'category': 'Financial',     'target': 100,  'actual': 78,   'direction': 'up',   'target_display': '30% of target',  'actual_display': '78% of goal',
     'frequency': 'Monthly',   'formula': 'Actual billable headcount ÷ Target headcount (500) × 100',
     'description': 'Progress toward the 500-headcount target through billable seat growth.'},
]


# Formula inputs for the Add-Record modal. Each KPI's value is computed from a
# numerator ÷ denominator × 100, so the user enters the two RAW numbers (not a
# pre-computed %) and we do the math — matching each KPI's real formula.
# `computed_display` controls how the resulting value reads (e.g. "3.5%").
_MODAL_KPIS = [
    {'name': 'Attrition Rate',             'numerator': 'Total exits',            'denominator': 'Average headcount'},
    {'name': 'Client Retention Rate',      'numerator': 'Clients retained',       'denominator': 'Total existing clients'},
    {'name': 'Billable Hours Achievement', 'numerator': 'Actual billable hours',  'denominator': 'Required billable hours'},
    {'name': 'CSAT',                       'numerator': 'Positive responses',     'denominator': 'Total survey responses'},
    {'name': 'EBR Completion',             'numerator': 'Completed compliant reviews', 'denominator': 'Scheduled reviews'},
    {'name': 'Seat Expansion',             'numerator': 'Actual billable headcount',   'denominator': 'Target headcount (500)'},
]

# Merge in target/direction/target_display/formula from the master KPI list so
# the modal has everything it needs in one structure.
_MODAL_KPIS = [
    {**m, **{k: src[k] for k in ('target', 'direction', 'target_display', 'formula')}}
    for m in _MODAL_KPIS
    for src in _OPERATIONS_KPIS if src['name'] == m['name']
]


def _latest_records(team):
    """The most recent `kpi_record` per KPI, keyed by KPI id.

    One query. Records arrive newest first, so the first row seen for a KPI is
    its latest period and every later one is skipped.
    """
    latest = {}
    for record in (
        KpiRecord.objects.filter(kpi__team=team, kpi__is_active=True)
        .order_by('kpi_id', '-period_start')
        .only('kpi_id', 'period_start', 'value', 'score', 'value_display', 'source')
    ):
        latest.setdefault(record.kpi_id, record)
    return latest


def _scorecard_rows(team):
    """One dashboard card per live KPI, from its latest recorded period.

    Two states exist beyond the three scored ones, and they are not the same
    thing: `monitored` means the KPI has a number but no target to judge it
    against, `no_data` means nobody has entered a figure yet. Collapsing them
    would report an untracked KPI as if it were merely untargeted.

    Attainment is RECOMPUTED here rather than read from `kpi_record.attainment`.
    The cached score is a snapshot of the target in force when the row was
    written, so moving a target would otherwise leave the dashboard showing the
    old verdict until every record happened to be re-saved. Design principle 6:
    scores are cached, never authoritative.
    """
    latest = _latest_records(team)
    rows = []

    for kpi in _kpi_queryset(team):
        row = _kpi_row(kpi)
        record = latest.get(kpi.pk)

        if record is None:
            rows.append({
                **row,
                'status': 'no_data',
                'status_label': 'No Data',
                'attainment': None,
                'bar_pct': 0,
                'actual_display': '',
                'period': '',
            })
            continue

        # `score` holds the graded number only when it differs from the shown
        # one (a signed variance displays −3.2% but is graded as 3.2).
        graded = record.score if record.score is not None else record.value
        attainment, status = kpi_records.score(kpi, float(graded))

        rows.append({
            **row,
            'status': status,
            'status_label': KpiRecord.Status(status).label,
            'attainment': attainment,
            # Bar fill is capped at 100 so an overachiever shows full; the label
            # beside it still reads the true figure (e.g. 112.9%).
            'bar_pct': 0 if attainment is None else min(round(attainment), 100),
            'actual_display': record.value_display or record.value,
            'period': kpi_periods.label(record.period_start, kpi.frequency),
        })

    return rows


@login_required
@team_required('operations')
def index(request):
    """Operations — team dashboard (KPI scorecard: actual vs target + status)."""
    operations_team = get_object_or_404(Team, slug='operations')
    kpis = _scorecard_rows(operations_team)
    today = timezone.localdate()

    def count(status):
        return sum(1 for k in kpis if k['status'] == status)

    # Only KPIs that were actually scored can be plotted against a target line.
    charted = [k for k in kpis if k['attainment'] is not None]

    return render(
        request,
        'operations/dashboard.html',
        {
            'banner_icons': BANNER_ICONS,
            'kpis': kpis,
            'on_track_count': count('on_track'),
            'at_risk_count': count('at_risk'),
            'below_count': count('below'),
            'monitored_count': count('monitored'),
            'no_data_count': count('no_data'),
            'kpi_count': len(kpis),
            'period': f'{today:%B %Y}',
            'import_url': reverse('operations:import_data'),
            'manage_url': reverse('operations:kpi_management'),
            # Compact payload the bar chart reads via json_script.
            'chart_data': [
                {
                    'name': k['name'],
                    'attainment': k['attainment'],
                    'status': k['status'],
                    'actual_display': k['actual_display'],
                    'target_display': k['target_display'],
                    'period': k['period'],
                }
                for k in charted
            ],
        },
    )


@login_required
@team_required('operations')
def kpi_reference(request):
    """Operations — KPI definitions reference (North Star + formulas/targets).

    DB-backed, sharing `_kpi_row` with the management table so the two screens
    can never disagree about what a KPI's target or formula is.
    """
    operations_team = get_object_or_404(Team, slug='operations')
    rows = [_kpi_row(kpi) for kpi in _kpi_queryset(operations_team)]

    context = {
        'banner_icons': BANNER_ICONS,
        'lob_name': 'Operations',
        'kpis': rows,
        'kpi_count': len(rows),
        'manage_url': reverse('operations:kpi_management'),
    }
    return render(request, 'operations/index.html', context)


def _import_stats(team):
    """The four Import Data stat cards, counted from the database.

    Everything here reads `kpi_record` / `kpi_import_batch`, so until the
    importer and the Add-Record modal actually write rows these read 0 and
    "No imports yet". That is the honest state, and it is what makes the first
    real import visibly land.
    """
    records = KpiRecord.objects.filter(kpi__team=team)
    today = timezone.localdate()

    last_batch = (
        KpiImportBatch.objects.filter(team=team).order_by('-uploaded_at').first()
    )

    return {
        'total_records': records.count(),
        # Records ENTERED this month, not records whose period is this month —
        # this tile sits next to Total Records and is about data-entry activity.
        # `__date` compares in the project timezone; handing a plain date to a
        # DateTimeField would compare a naive value and slip a row either side
        # of the month boundary.
        'added_this_month': records.filter(
            created_at__date__gte=today.replace(day=1)
        ).count(),
        'period': f'{today:%B %Y}',
        'last_import': (
            f'{timezone.localtime(last_batch.uploaded_at):%d %b %Y}'
            if last_batch
            else 'No imports yet'
        ),
    }


RECORDS_PAGE_SIZE = 10

# Successful POSTs land on the records table. It must be a REAL anchor: see the
# note on _TABLE_ANCHOR — a fragment-less redirect inherits the modal's own
# fragment and re-opens it.
_RECORDS_ANCHOR = 'kpi-records'


def _record_rows(records_qs):
    """KPI Records table rows, from `kpi_record`."""
    return [
        {
            'kpi': record.kpi.name,
            'category': record.kpi.category.name if record.kpi.category_id else '—',
            'actual': record.value_display or record.value,
            'target': record.kpi.target_display or 'No Target',
            'period': kpi_periods.label(record.period_start, record.kpi.frequency),
            'status': record.status,
            'status_label': record.get_status_display(),
            'attainment': record.attainment,
            'source': record.get_source_display(),
            'remarks': record.remarks,
        }
        for record in records_qs
    ]


def _import_rows(batches):
    """Recent Import History rows, from `kpi_import_batch`."""
    return [
        {
            'file_name': batch.file_name,
            'kpi': batch.kpi.name if batch.kpi_id else 'Multiple',
            'records': batch.created_count + batch.updated_count,
            'errors': batch.error_count,
            'status': batch.status,
            'status_label': batch.get_status_display(),
            'uploaded_by': (
                batch.uploaded_by.get_full_name() or batch.uploaded_by.get_username()
                if batch.uploaded_by_id
                else 'System'
            ),
            'uploaded_at': batch.uploaded_at,
        }
        for batch in batches
    ]


@login_required
@team_required('operations')
def import_data(request):
    """Operations — Import Data. Manual entry and CSV upload both write records."""
    operations_team = get_object_or_404(Team, slug='operations')

    add_form = AddRecordForm(team=operations_team)
    import_form = ImportRecordsForm()
    open_add_modal = open_import_modal = False

    if request.method == 'POST':
        if request.POST.get('_action') == 'import':
            import_form = ImportRecordsForm(request.POST, request.FILES)

            if import_form.is_valid():
                upload = import_form.cleaned_data['file']
                try:
                    result = importer.parse_and_apply(
                        upload.read(),
                        team=operations_team,
                        user=request.user,
                        file_name=upload.name,
                        content_type=upload.content_type or 'text/csv',
                    )
                except importer.ImportError_ as error:
                    # A whole-file problem: nothing was written, so it belongs
                    # on the form rather than in the import history.
                    import_form.add_error('file', str(error))
                    open_import_modal = True
                else:
                    log_action(
                        request,
                        action=AuditLog.Action.IMPORTED,
                        entity=result.batch,
                        entity_type='kpi_import_batch',
                        team=operations_team,
                        new_values={
                            'file_name': result.batch.file_name,
                            'rows': result.rows,
                            'created': result.created,
                            'updated': result.updated,
                            'errors': len(result.errors),
                        },
                    )
                    _report_import(request, result)
                    return redirect(f'{request.path}#{_RECORDS_ANCHOR}')
            else:
                open_import_modal = True

        else:
            add_form = AddRecordForm(request.POST, team=operations_team)

            if add_form.is_valid():
                record, created = add_form.save(user=request.user)

                log_action(
                    request,
                    action=(
                        AuditLog.Action.CREATED if created else AuditLog.Action.UPDATED
                    ),
                    entity=record,
                    entity_type='kpi_record',
                    team=operations_team,
                    new_values={
                        'kpi': record.kpi.name,
                        'period': str(record.period_start),
                        'value': record.value_display,
                        'status': record.status,
                    },
                )

                messages.success(
                    request,
                    f'{record.kpi.name} for '
                    f'{kpi_periods.label(record.period_start, record.kpi.frequency)} '
                    f'{"recorded" if created else "updated"}: '
                    f'{record.value_display} ({record.get_status_display()}).',
                )
                return redirect(f'{request.path}#{_RECORDS_ANCHOR}')

            open_add_modal = True

    records_qs = (
        KpiRecord.objects.filter(kpi__team=operations_team)
        .select_related('kpi', 'kpi__category')
        .order_by('-period_start', 'kpi__sort_order')
    )
    paginator = Paginator(records_qs, RECORDS_PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    # Records accumulate every period, so the page list is elided rather than
    # printing one pill per page once a few years of history exist.
    # list(), not the generator itself: it is single-use, so anything that reads
    # it after the template has rendered would find it empty.
    page_numbers = list(
        paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    )

    batches = (
        KpiImportBatch.objects.filter(team=operations_team)
        .select_related('kpi', 'uploaded_by')
        .order_by('-uploaded_at')[:10]
    )

    return render(
        request,
        'operations/import_data.html',
        {
            'add_form': add_form,
            'import_form': import_form,
            'open_add_modal': open_add_modal,
            'open_import_modal': open_import_modal,
            'records': _record_rows(page.object_list),
            'record_count': paginator.count,
            'page_obj': page,
            'page_numbers': page_numbers,
            'extra_query': _query_without_page(request),
            'extra_params': _params_without_page(request),
            'imports': _import_rows(batches),
            # The Add-Record modal renders one field group per KPI; only the
            # selected one is enabled, so only its operands are submitted.
            'record_kpis': [
                {
                    'pk': kpi.pk,
                    'name': kpi.name,
                    'formula': kpi.formula_text or kpi.expression,
                    'target_display': kpi.target_display or 'No Target',
                    'frequency': kpi.get_frequency_display(),
                    'period_hint': kpi_periods.FORMAT_HINT.get(kpi.frequency, ''),
                    'period_example': kpi_periods.label(
                        timezone.localdate(), kpi.frequency
                    ),
                    'inputs': list(kpi.inputs.all()),
                }
                for kpi in _kpi_queryset(operations_team)
            ],
            **_import_stats(operations_team),
        },
    )


def _report_import(request, result):
    """One flash message that says what the file actually did."""
    errors = len(result.errors)
    applied = result.created + result.updated
    summary = (
        f'{result.batch.file_name}: {result.created} created, '
        f'{result.updated} updated'
    )

    # Re-uploading identical contents is legitimate (it is how a correction is
    # re-applied), so this is a note rather than a rejection.
    repeat = (
        ' This file was already uploaded once; the records were re-applied.'
        if result.duplicate_of
        else ''
    )

    if errors and applied:
        messages.warning(
            request,
            f'{summary}, {errors} row(s) rejected. See Recent Import History.{repeat}',
        )
    elif errors:
        messages.error(
            request,
            f'{result.batch.file_name}: nothing imported, {errors} row(s) rejected.',
        )
    else:
        messages.success(request, f'{summary}.{repeat}')


# How each KPI's direction reads on the management screen.
_DIRECTION_LABEL = {'up': 'Higher is better', 'down': 'Lower is better'}

# Rows per page on the KPI Management table.
PAGE_SIZE = 10


def _kpi_queryset(team):
    """Every live KPI this team owns, ready for either KPI screen."""
    return (
        KpiDefinition.objects.filter(team=team, is_active=True)
        .select_related('category')
        .prefetch_related('inputs')
        .order_by('sort_order', 'name')
    )


def _kpi_row(kpi):
    """One KPI as the templates want it, from the database.

    Deliberately the SAME shape the static `_OPERATIONS_KPIS` dicts produced,
    so the templates did not have to change around the switch (rollout step 5).
    Shared by KPI Definitions and KPI Management; management layers its own
    extras on top.
    """
    return {
        'pk': kpi.pk,
        'slug': kpi.slug,
        'name': kpi.name,
        'description': kpi.description,
        'category': kpi.category.name if kpi.category else 'Uncategorised',
        'target_display': kpi.target_display or 'No Target',
        'target_min': kpi.target_min,
        'target_max': kpi.target_max,
        'direction': kpi.direction,
        'direction_label': _DIRECTION_LABEL[kpi.direction],
        'frequency': kpi.get_frequency_display(),
        'formula': kpi.formula_text or kpi.expression,
        'template_version': kpi.template_version,
        # The operands, in CSV column order. These ARE the columns of this
        # KPI's template and the fields of its Add-Record form.
        'inputs': [row.label for row in kpi.inputs.all()],
        'input_count': len(kpi.inputs.all()),
    }


def _management_rows(kpis, team, edit_forms=None):
    """`_kpi_row` plus what only the management table needs.

    Each row carries its own bound-or-fresh `EditKpiForm`, so the Edit modal
    renders real fields with real validation messages rather than a mockup.
    Only the CURRENT PAGE gets forms built — that is what keeps this to ten.
    """
    edit_forms = edit_forms or {}

    return [
        {
            **_kpi_row(kpi),
            # Generated on demand — see apps/kpi/csv_template.py for why it is
            # not a stored file.
            'csv_url': reverse('operations:kpi_template', args=[kpi.slug]),
            'form': edit_forms.get(kpi.slug) or EditKpiForm(instance=kpi, team=team),
        }
        for kpi in kpis
    ]


@login_required
@team_required('operations')
def kpi_template(request, slug):
    """Download one KPI's CSV template, built from its own inputs (§D)."""
    kpi = get_object_or_404(
        KpiDefinition, team__slug='operations', slug=slug, is_active=True
    )

    response = HttpResponse(
        csv_template.build_bytes(kpi), content_type='text/csv; charset=utf-8'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{csv_template.filename(kpi)}"'
    )
    return response


@login_required
@team_required("operations")
def kpi_management(request):
    operations_team = get_object_or_404(Team, slug="operations")

    # Both modals open via CSS :target. On a validation failure the re-rendered
    # page has no fragment, so the modal would land CLOSED with its errors
    # unseen — these two force the right one back open instead.
    open_create_modal = False
    open_edit_slug = None

    form = CreateKpiForm(team=operations_team)
    edit_forms = {}

    if request.method == "POST":
        # One view, three modals: each form identifies itself so the create
        # form isn't bound to an edit's POST data (and vice versa).
        if request.POST.get("_action") == "delete":
            kpi = get_object_or_404(
                KpiDefinition,
                team=operations_team,
                slug=request.POST.get("_slug", ""),
                is_active=True,
            )

            # SOFT delete: nothing is destroyed (design principle 7). The KPI
            # drops off the scorecard and its CSV template stops downloading,
            # but its records, history and audit trail stay intact and it can
            # be brought back by flipping this one flag.
            kpi.is_active = False
            kpi.save(update_fields=["is_active", "updated_at"])

            log_action(
                request,
                action=AuditLog.Action.DELETED,
                entity=kpi,
                entity_type="kpi_definition",
                team=kpi.team,
                old_values={"is_active": True},
                new_values={"is_active": False},
            )

            messages.success(
                request,
                f'KPI "{kpi.name}" has been deleted.',
            )
            return redirect(_back_to_page(request))

        if request.POST.get("_action") == "edit":
            kpi = get_object_or_404(
                KpiDefinition,
                team=operations_team,
                slug=request.POST.get("_slug", ""),
                is_active=True,
            )
            edit_form = EditKpiForm(request.POST, instance=kpi, team=operations_team)

            if edit_form.is_valid():
                targets_changed = edit_form.targets_changed
                formula_changed = edit_form.formula_changed
                kpi = edit_form.save(user=request.user)

                if edit_form.changes:
                    # Moving a target and rewriting a formula are each their
                    # own action — both re-read every past period, so neither
                    # should hide inside a generic "updated". A single edit can
                    # legitimately do both, so both are logged.
                    actions = []
                    if formula_changed:
                        actions.append(AuditLog.Action.FORMULA_CHANGED)
                    if targets_changed:
                        actions.append(AuditLog.Action.TARGET_CHANGED)
                    if not actions:
                        actions.append(AuditLog.Action.UPDATED)

                    for action in actions:
                        log_action(
                            request,
                            action=action,
                            entity=kpi,
                            entity_type="kpi_definition",
                            team=kpi.team,
                            old_values={
                                f: c["from"] for f, c in edit_form.changes.items()
                            },
                            new_values={
                                f: c["to"] for f, c in edit_form.changes.items()
                            },
                        )

                    if formula_changed:
                        messages.success(
                            request,
                            f'KPI "{kpi.name}" updated. Its CSV template is now '
                            f"v{kpi.template_version}, so download a fresh one "
                            "before the next upload.",
                        )
                    else:
                        messages.success(request, f'KPI "{kpi.name}" updated.')
                else:
                    messages.info(request, "Nothing changed.")

                return redirect(_back_to_page(request))

            edit_forms[kpi.slug] = edit_form
            open_edit_slug = kpi.slug

        else:
            form = CreateKpiForm(request.POST, team=operations_team)

            if form.is_valid():
                kpi = form.save(user=request.user)

                log_action(
                    request,
                    action=AuditLog.Action.CREATED,
                    entity=kpi,
                    entity_type="kpi_definition",
                    team=kpi.team,
                    new_values={
                        "name": kpi.name,
                        "slug": kpi.slug,
                        "expression": kpi.expression,
                        "formula_text": kpi.formula_text,
                        "target_display": kpi.target_display,
                        "inputs": [i.key for i in kpi.inputs.all()],
                    },
                )

                messages.success(request, f'KPI "{kpi.name}" has been created.')

                return redirect(_back_to_page(request))

            open_create_modal = True

    # Every category the team HAS, not just the ones currently in use, so the
    # filter still offers a category whose last KPI was deleted.
    categories = sorted(
        KpiCategory.objects.filter(team=operations_team).values_list("name", flat=True)
    )

    search = request.GET.get("q", "").strip()
    chosen_categories = [c for c in request.GET.getlist("category") if c]
    chosen_frequencies = [f for f in request.GET.getlist("frequency") if f]

    kpis = _kpi_queryset(operations_team)
    if search:
        kpis = kpis.filter(
            Q(name__icontains=search)
            | Q(formula_text__icontains=search)
            | Q(expression__icontains=search)
        )
    if chosen_categories:
        kpis = kpis.filter(category__name__in=chosen_categories)
    if chosen_frequencies:
        kpis = kpis.filter(frequency__in=chosen_frequencies)

    paginator = Paginator(kpis, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    rows = _management_rows(page.object_list, operations_team, edit_forms)

    return render(
        request,
        "operations/kpi_management.html",
        {
            "form": form,
            "open_create_modal": open_create_modal,
            "open_edit_slug": open_edit_slug,
            "kpis": rows,
            "page_obj": page,
            # The count of what the filters MATCHED. The stat card above the
            # table keeps counting the whole scorecard.
            "result_count": paginator.count,
            "kpi_count": _kpi_queryset(operations_team).count(),
            "categories": categories,
            # One popover replaces the two inert dropdowns. Each option carries
            # its own checked flag so the template holds no lookup logic.
            "category_options": [
                {"value": name, "label": name, "checked": name in chosen_categories}
                for name in categories
            ],
            "frequency_options": [
                {"value": value, "label": label, "checked": value in chosen_frequencies}
                for value, label in Frequency.choices
            ],
            "search": search,
            # Drives the button's active styling and its count badge. Search has
            # its own visible box, so it is not counted here.
            "active_filter_count": len(chosen_categories) + len(chosen_frequencies),
            "has_any_filter": bool(search or chosen_categories or chosen_frequencies),
            "clear_url": reverse("operations:kpi_management"),
            # Pagination has to carry the filters, or page 2 silently drops them.
            "page_query": _query_without_page(request),
            "page_params": _params_without_page(request),
        },
    )


def _query_without_page(request):
    """The current query string minus `page`, for pagination links."""
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def _params_without_page(request):
    """The same, as key/value pairs, for the pagination form's hidden inputs."""
    return [
        {"key": key, "value": value}
        for key, values in request.GET.lists()
        if key != "page"
        for value in values
        if value
    ]


# Where a successful POST lands. It is an anchor on the table, and it has to be
# a real one: modals open via CSS :target, and a browser REATTACHES the original
# request's fragment to a redirect whose Location carries none of its own
# (RFC 7231 §7.1.2). Without this, saving from #kpiEdit-<slug> would redirect to
# a fragment-less URL, the browser would put #kpiEdit-<slug> back, and the modal
# would spring open again on the fresh page.
_TABLE_ANCHOR = "kpi-definitions"


def _back_to_page(request):
    """Return to the view the change was made from, with every modal closed.

    A form with no `action` posts to the current URL, query string included, so
    `request.GET` still holds whatever filters were applied. Carrying them back
    is the difference between saving a KPI and having the filtered list you were
    working through reset itself underneath you.
    """
    params = request.GET.copy()
    page = request.POST.get("_page")
    if page and page.isdigit():
        params["page"] = page
    else:
        params.pop("page", None)

    query = params.urlencode()
    url = reverse("operations:kpi_management")
    return f"{url}{'?' + query if query else ''}#{_TABLE_ANCHOR}"