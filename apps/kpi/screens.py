"""The four KPI screens, once, for every LOB.

Operations was the reference implementation: dashboard, KPI Definitions, Import
Data and KPI Management, all reading `kpi_definition` / `kpi_record` rather than
a Python dict. This is that implementation with the word "operations" taken out
of it.

A LOB app now supplies three things and gets four working screens::

    screens = KpiScreens(team_slug='hr', namespace='hr', scope=SCOPE)
    index           = screens.dashboard
    kpi_reference   = screens.definitions
    import_data     = screens.import_data
    kpi_management  = screens.management
    kpi_template    = screens.template

`scope` is the banner copy (title, badge, blurb, north_star, icons) and nothing
else. Everything a screen shows about a KPI comes from the database.

Why a class rather than four functions taking a slug: the views are wired into
`urlpatterns` by reference, so each has to be a ready-made callable with its
`@login_required` and `@team_required` already applied. Building them in
`__init__` is what lets a LOB's urls.py stay a plain list of `path()` calls.

A BRANCH team (Sales) passes `branched=True`. Its views then take the branch
slug from the URL, every query is filtered on `kpi_definition.branch`, and a
sixth screen appears: `overview`, the team-level rollup across all branches.
The four screen templates are unchanged, because they never name a URL: the
branch-aware URLs are resolved in `_urls()` and handed over as context.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core import kpi as scoring
from apps.core.access import team_required
from apps.core.audit import log_action
from apps.core.models import AuditLog, Team

from . import csv_template, importer
from . import periods as kpi_periods
from . import records as kpi_records
from .forms import (
    AddRecordForm,
    CreateKpiForm,
    EditKpiForm,
    ImportRecordsForm,
)
from .models import (
    Frequency,
    KpiBranch,
    KpiCategory,
    KpiDefinition,
    KpiImportBatch,
    KpiRecord,
)

# Rows per page: KPI Management's table, and Import Data's records table.
PAGE_SIZE = 10
RECORDS_PAGE_SIZE = 10

# How each KPI's direction reads on the definitions and management screens.
DIRECTION_LABEL = {'up': 'Higher is better', 'down': 'Lower is better'}

# Where a successful POST lands. Both have to be REAL anchors on the page:
# modals open via CSS :target, and a browser reattaches the original request's
# fragment to a redirect whose Location carries none of its own (RFC 7231
# §7.1.2). Without this, saving from #kpiEdit-<slug> would redirect to a
# fragment-less URL, the browser would put #kpiEdit-<slug> back, and the modal
# would spring open again on the fresh page looking like the save had failed.
TABLE_ANCHOR = 'kpi-definitions'
RECORDS_ANCHOR = 'kpi-records'


def _query_without_page(request):
    """The current query string minus `page`, for pagination links."""
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()


def _params_without_page(request):
    """The same, as key/value pairs, for the pagination form's hidden inputs."""
    return [
        {'key': key, 'value': value}
        for key, values in request.GET.lists()
        if key != 'page'
        for value in values
        if value
    ]


class KpiScreens:
    """The four KPI screens plus the CSV template download, for one team."""

    def __init__(self, *, team_slug, namespace=None, scope=None, branched=False):
        self.team_slug = team_slug
        self.namespace = namespace or team_slug
        self.scope = scope or {}
        self.branched = branched

        guard = [login_required, team_required(team_slug)]

        def wrap(view):
            for decorator in reversed(guard):
                view = decorator(view)
            return view

        self.dashboard = wrap(self._dashboard)
        self.definitions = wrap(self._definitions)
        self.import_data = wrap(self._import_data)
        self.management = wrap(self._management)
        self.template = wrap(self._template)
        # Only a branch team has anything to roll up.
        self.overview = wrap(self._overview) if branched else None

    # --- shared plumbing ---------------------------------------------------

    def team(self):
        return get_object_or_404(Team, slug=self.team_slug)

    def branch_or_404(self, team, slug):
        """Resolve a branch slug from the URL. 404 rather than a silent None.

        A typo'd branch must not fall through to the team-level KPIs: those are
        a different set of rows, and showing them would look like data loss.
        """
        return get_object_or_404(KpiBranch, team=team, slug=slug, is_active=True)

    def url(self, name, *args, branch=None):
        """Reverse one of this LOB's URLs, branch prefix included when needed.

        A branch team's routes are `branch_index` / `branch_kpis` / … and every
        one takes the branch slug first, so the name and the args both change.
        """
        if self.branched and branch is not None:
            return reverse(f'{self.namespace}:branch_{name}', args=[branch.slug, *args])
        return reverse(f'{self.namespace}:{name}', args=args)

    def _urls(self, branch=None):
        """Every cross-screen link, pre-resolved.

        The templates are shared, so they cannot name a namespace or know
        whether this LOB has branches. Both differences are absorbed here.
        """
        context = {
            'scope': self.scope_for(branch),
            'branch': branch,
            'dashboard_url': self.url('index', branch=branch),
            'definitions_url': self.url('kpis', branch=branch),
            'import_url': self.url('import_data', branch=branch),
            'manage_url': self.url('kpi_management', branch=branch),
        }
        if self.branched:
            # The way back up to the team-level rollup.
            context['overview_url'] = reverse(f'{self.namespace}:index')
        return context

    def scope_for(self, branch):
        """Banner copy for the page being rendered.

        A branch page is titled with the BRANCH, not the team: on `/sales/seo/`
        the heading that matters is "SEO & Google Ads". The team name still sits
        in the badge, so the hierarchy stays legible.
        """
        if branch is None:
            return self.scope
        return {
            **self.scope,
            **(self.scope.get('branches', {}).get(branch.slug) or {}),
            'title': branch.name,
            'badge': f'{self.scope.get("badge", "")} · {branch.name}'.strip(' ·'),
        }

    def queryset(self, team, branch=None):
        """Every live KPI in scope, ready for any of the four screens.

        For a branch team `branch=None` would mean the TEAM-LEVEL KPIs, which is
        not the same as "all of them" — the overview asks for those separately.
        """
        return (
            KpiDefinition.objects.filter(team=team, branch=branch, is_active=True)
            .select_related('category')
            .prefetch_related('inputs')
            .order_by('sort_order', 'name')
        )

    def row(self, kpi):
        """One KPI as the templates want it.

        Shared by all four screens, so they can never disagree about what a
        KPI's target or formula is.
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
            'direction_label': DIRECTION_LABEL[kpi.direction],
            'frequency': kpi.get_frequency_display(),
            'formula': kpi.formula_text or kpi.expression,
            'template_version': kpi.template_version,
            # The operands, in CSV column order. These ARE the columns of this
            # KPI's template and the fields of its Add-Record form.
            'inputs': [row.label for row in kpi.inputs.all()],
            'input_count': len(kpi.inputs.all()),
        }

    # --- dashboard ---------------------------------------------------------

    def _latest_records(self, team, branch=None):
        """The most recent `kpi_record` per KPI, keyed by KPI id.

        One query. Records arrive newest first, so the first row seen for a KPI
        is its latest period and every later one is skipped.
        """
        latest = {}
        for record in (
            KpiRecord.objects.filter(
                kpi__team=team, kpi__branch=branch, kpi__is_active=True
            )
            .order_by('kpi_id', '-period_start')
            .only('kpi_id', 'period_start', 'value', 'score', 'value_display')
        ):
            latest.setdefault(record.kpi_id, record)
        return latest

    def scorecard_rows(self, team, branch=None):
        """One dashboard card per live KPI, from its latest recorded period.

        Two states exist beyond the three scored ones, and they are not the
        same thing: `monitored` means the KPI has a number but no target to
        judge it against, `no_data` means nobody has entered a figure yet.
        Collapsing them would report an untracked KPI as merely untargeted.

        Attainment is RECOMPUTED rather than read from `kpi_record.attainment`.
        The cached score is a snapshot of the target in force when the row was
        written, so moving a target would otherwise leave the dashboard showing
        the old verdict until every record happened to be re-saved. Design
        principle 6: scores are cached, never authoritative.
        """
        latest = self._latest_records(team, branch)
        rows = []

        for kpi in self.queryset(team, branch):
            row = self.row(kpi)
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

            # `score` holds the graded number only when it differs from the
            # shown one (a signed variance displays −3.2%, grades as 3.2).
            graded = record.score if record.score is not None else record.value
            attainment, status = kpi_records.score(kpi, float(graded))

            rows.append({
                **row,
                'status': status,
                'status_label': KpiRecord.Status(status).label,
                'attainment': attainment,
                # Capped at 100 so an overachiever shows a full bar; the label
                # beside it still reads the true figure (e.g. 112.9%).
                'bar_pct': 0 if attainment is None else min(round(attainment), 100),
                'actual_display': record.value_display or record.value,
                'period': kpi_periods.label(record.period_start, kpi.frequency),
            })

        return rows

    def _dashboard(self, request, branch=None):
        """Team (or branch) dashboard: the KPI scorecard and its chart."""
        team = self.team()
        branch = self.branch_or_404(team, branch) if branch else None
        kpis = self.scorecard_rows(team, branch)
        today = timezone.localdate()

        def count(status):
            return sum(1 for k in kpis if k['status'] == status)

        return render(request, 'kpi/dashboard.html', {
            **self._urls(branch),
            'kpis': kpis,
            'on_track_count': count('on_track'),
            'at_risk_count': count('at_risk'),
            'below_count': count('below'),
            'monitored_count': count('monitored'),
            'no_data_count': count('no_data'),
            'kpi_count': len(kpis),
            'period': f'{today:%B %Y}',
            # Only KPIs that were actually scored can be plotted against a
            # target line.
            'chart_data': [
                {
                    'name': k['name'],
                    'attainment': k['attainment'],
                    'status': k['status'],
                    'actual_display': k['actual_display'],
                    'target_display': k['target_display'],
                    'period': k['period'],
                }
                for k in kpis
                if k['attainment'] is not None
            ],
        })

    # --- KPI definitions ---------------------------------------------------

    def _definitions(self, request, branch=None):
        """KPI definitions reference: targets, cadence, formulas, inputs."""
        team = self.team()
        branch = self.branch_or_404(team, branch) if branch else None
        rows = [self.row(kpi) for kpi in self.queryset(team, branch)]

        return render(request, 'kpi/kpi_definitions.html', {
            **self._urls(branch),
            'kpis': rows,
            'kpi_count': len(rows),
        })

    # --- import data -------------------------------------------------------

    def import_stats(self, team, branch=None):
        """The four Import Data stat cards, counted from the database."""
        records = KpiRecord.objects.filter(kpi__team=team, kpi__branch=branch)
        today = timezone.localdate()
        last_batch = (
            KpiImportBatch.objects.filter(team=team, branch=branch)
            .order_by('-uploaded_at')
            .first()
        )

        return {
            'total_records': records.count(),
            # Records ENTERED this month, not records whose period is this
            # month: this tile sits beside Total Records and is about
            # data-entry activity. `__date` compares in the project timezone;
            # handing a plain date to a DateTimeField would compare a naive
            # value and slip a row either side of the month boundary.
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

    def record_rows(self, records_qs):
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

    def import_rows(self, batches):
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

    def _report_import(self, request, result):
        """One flash message that says what the file actually did."""
        errors = len(result.errors)
        applied = result.created + result.updated
        summary = (
            f'{result.batch.file_name}: {result.created} created, '
            f'{result.updated} updated'
        )

        # Re-uploading identical contents is legitimate (it is how a correction
        # is re-applied), so this is a note rather than a rejection.
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

    def _import_data(self, request, branch=None):
        """Import Data: manual entry and CSV upload both write records."""
        team = self.team()
        branch = self.branch_or_404(team, branch) if branch else None

        add_form = AddRecordForm(team=team, branch=branch)
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
                            team=team,
                            user=request.user,
                            file_name=upload.name,
                            content_type=upload.content_type or 'text/csv',
                            branch=branch,
                        )
                    except importer.ImportError_ as error:
                        # A whole-file problem: nothing was written, so it
                        # belongs on the form rather than in import history.
                        import_form.add_error('file', str(error))
                        open_import_modal = True
                    else:
                        log_action(
                            request,
                            action=AuditLog.Action.IMPORTED,
                            entity=result.batch,
                            entity_type='kpi_import_batch',
                            team=team,
                            new_values={
                                'file_name': result.batch.file_name,
                                'rows': result.rows,
                                'created': result.created,
                                'updated': result.updated,
                                'errors': len(result.errors),
                            },
                        )
                        self._report_import(request, result)
                        return redirect(f'{request.path}#{RECORDS_ANCHOR}')
                else:
                    open_import_modal = True

            else:
                add_form = AddRecordForm(request.POST, team=team, branch=branch)

                if add_form.is_valid():
                    record, created = add_form.save(user=request.user)

                    log_action(
                        request,
                        action=(
                            AuditLog.Action.CREATED if created
                            else AuditLog.Action.UPDATED
                        ),
                        entity=record,
                        entity_type='kpi_record',
                        team=team,
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
                    return redirect(f'{request.path}#{RECORDS_ANCHOR}')

                open_add_modal = True

        records_qs = (
            KpiRecord.objects.filter(kpi__team=team, kpi__branch=branch)
            .select_related('kpi', 'kpi__category')
            .order_by('-period_start', 'kpi__sort_order')
        )
        paginator = Paginator(records_qs, RECORDS_PAGE_SIZE)
        page = paginator.get_page(request.GET.get('page'))
        # Records accumulate every period, so the page list is elided rather
        # than printing one pill per page once a few years of history exist.
        # list(), not the generator: it is single-use, so anything reading it
        # after the template has rendered would find it empty.
        page_numbers = list(
            paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
        )

        batches = (
            KpiImportBatch.objects.filter(team=team, branch=branch)
            .select_related('kpi', 'uploaded_by')
            .order_by('-uploaded_at')[:10]
        )

        return render(request, 'kpi/import_data.html', {
            **self._urls(branch),
            'add_form': add_form,
            'import_form': import_form,
            'open_add_modal': open_add_modal,
            'open_import_modal': open_import_modal,
            'records': self.record_rows(page.object_list),
            'record_count': paginator.count,
            'page_obj': page,
            'page_numbers': page_numbers,
            'extra_query': _query_without_page(request),
            'extra_params': _params_without_page(request),
            'imports': self.import_rows(batches),
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
                for kpi in self.queryset(team, branch)
            ],
            **self.import_stats(team, branch),
        })

    # --- KPI management ----------------------------------------------------

    def management_rows(self, kpis, team, edit_forms=None, branch=None):
        """`row()` plus what only the management table needs.

        Each row carries its own bound-or-fresh `EditKpiForm`, so the Edit
        modal renders real fields with real validation messages rather than a
        mockup. Only the CURRENT PAGE gets forms built.
        """
        edit_forms = edit_forms or {}

        return [
            {
                **self.row(kpi),
                # Generated on demand: see apps/kpi/csv_template.py for why it
                # is not a stored file.
                'csv_url': self.url('kpi_template', kpi.slug, branch=branch),
                'form': (
                    edit_forms.get(kpi.slug)
                    or EditKpiForm(instance=kpi, team=team, branch=branch)
                ),
            }
            for kpi in kpis
        ]

    def _back_to_page(self, request, branch=None):
        """Return to the view the change was made from, every modal closed.

        A form with no `action` posts to the current URL, query string
        included, so `request.GET` still holds whatever filters were applied.
        Carrying them back is the difference between saving a KPI and having
        the filtered list you were working through reset itself underneath you.
        """
        params = request.GET.copy()
        page = request.POST.get('_page')
        if page and page.isdigit():
            params['page'] = page
        else:
            params.pop('page', None)

        query = params.urlencode()
        url = self.url('kpi_management', branch=branch)
        return f'{url}{"?" + query if query else ""}#{TABLE_ANCHOR}'

    def _management(self, request, branch=None):
        """KPI Management: create, edit, soft-delete, search, filter."""
        team = self.team()
        branch = self.branch_or_404(team, branch) if branch else None

        # All three modals open via CSS :target. On a validation failure the
        # re-rendered page has no fragment, so the modal would land CLOSED with
        # its errors unseen. These two force the right one back open instead.
        open_create_modal = False
        open_edit_slug = None

        form = CreateKpiForm(team=team, branch=branch)
        edit_forms = {}

        if request.method == 'POST':
            # One view, three modals: each form identifies itself so the create
            # form isn't bound to an edit's POST data, and vice versa.
            if request.POST.get('_action') == 'delete':
                kpi = get_object_or_404(
                    KpiDefinition,
                    team=team,
                    branch=branch,
                    slug=request.POST.get('_slug', ''),
                    is_active=True,
                )

                # SOFT delete: nothing is destroyed (design principle 7). The
                # KPI drops off the scorecard and its CSV template stops
                # downloading, but its records, history and audit trail stay
                # intact and it can be brought back by flipping this one flag.
                kpi.is_active = False
                kpi.save(update_fields=['is_active', 'updated_at'])

                log_action(
                    request,
                    action=AuditLog.Action.DELETED,
                    entity=kpi,
                    entity_type='kpi_definition',
                    team=kpi.team,
                    old_values={'is_active': True},
                    new_values={'is_active': False},
                )

                messages.success(request, f'KPI "{kpi.name}" has been deleted.')
                return redirect(self._back_to_page(request, branch))

            if request.POST.get('_action') == 'edit':
                kpi = get_object_or_404(
                    KpiDefinition,
                    team=team,
                    branch=branch,
                    slug=request.POST.get('_slug', ''),
                    is_active=True,
                )
                edit_form = EditKpiForm(
                    request.POST, instance=kpi, team=team, branch=branch
                )

                if edit_form.is_valid():
                    targets_changed = edit_form.targets_changed
                    formula_changed = edit_form.formula_changed
                    kpi = edit_form.save(user=request.user)

                    if edit_form.changes:
                        # Moving a target and rewriting a formula are each their
                        # own action: both re-read every past period, so neither
                        # should hide inside a generic "updated". One edit can
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
                                entity_type='kpi_definition',
                                team=kpi.team,
                                old_values={
                                    f: c['from'] for f, c in edit_form.changes.items()
                                },
                                new_values={
                                    f: c['to'] for f, c in edit_form.changes.items()
                                },
                            )

                        if formula_changed:
                            messages.success(
                                request,
                                f'KPI "{kpi.name}" updated. Its CSV template is now '
                                f'v{kpi.template_version}, so download a fresh one '
                                'before the next upload.',
                            )
                        else:
                            messages.success(request, f'KPI "{kpi.name}" updated.')
                    else:
                        messages.info(request, 'Nothing changed.')

                    return redirect(self._back_to_page(request, branch))

                edit_forms[kpi.slug] = edit_form
                open_edit_slug = kpi.slug

            else:
                form = CreateKpiForm(request.POST, team=team, branch=branch)

                if form.is_valid():
                    kpi = form.save(user=request.user)

                    log_action(
                        request,
                        action=AuditLog.Action.CREATED,
                        entity=kpi,
                        entity_type='kpi_definition',
                        team=kpi.team,
                        new_values={
                            'name': kpi.name,
                            'slug': kpi.slug,
                            'expression': kpi.expression,
                            'formula_text': kpi.formula_text,
                            'target_display': kpi.target_display,
                            'inputs': [i.key for i in kpi.inputs.all()],
                        },
                    )

                    messages.success(request, f'KPI "{kpi.name}" has been created.')
                    return redirect(self._back_to_page(request, branch))

                open_create_modal = True

        # Every category the team HAS, not just the ones currently in use, so
        # the filter still offers a category whose last KPI was deleted.
        categories = sorted(
            KpiCategory.objects.filter(team=team).values_list('name', flat=True)
        )

        search = request.GET.get('q', '').strip()
        chosen_categories = [c for c in request.GET.getlist('category') if c]
        chosen_frequencies = [f for f in request.GET.getlist('frequency') if f]

        kpis = self.queryset(team, branch)
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
        page = paginator.get_page(request.GET.get('page'))

        return render(request, 'kpi/kpi_management.html', {
            **self._urls(branch),
            'form': form,
            'open_create_modal': open_create_modal,
            'open_edit_slug': open_edit_slug,
            'kpis': self.management_rows(page.object_list, team, edit_forms, branch),
            'page_obj': page,
            # The count of what the filters MATCHED. The stat card above the
            # table keeps counting the whole scorecard.
            'result_count': paginator.count,
            'kpi_count': self.queryset(team, branch).count(),
            'categories': categories,
            # One popover replaces the two inert dropdowns. Each option carries
            # its own checked flag so the template holds no lookup logic.
            'category_options': [
                {'value': name, 'label': name, 'checked': name in chosen_categories}
                for name in categories
            ],
            'frequency_options': [
                {'value': value, 'label': label, 'checked': value in chosen_frequencies}
                for value, label in Frequency.choices
            ],
            'search': search,
            # Drives the button's active styling and its count badge. Search
            # has its own visible box, so it is not counted here.
            'active_filter_count': len(chosen_categories) + len(chosen_frequencies),
            'has_any_filter': bool(search or chosen_categories or chosen_frequencies),
            'clear_url': self.url('kpi_management', branch=branch),
            # Pagination has to carry the filters, or page 2 silently drops them.
            'page_query': _query_without_page(request),
            'page_params': _params_without_page(request),
        })

    # --- branch overview ---------------------------------------------------

    def _overview(self, request):
        """A branch team's own Dashboard: every branch rolled up.

        It IS the team dashboard, not a table of contents above one. The tiles
        tally every branch's KPIs together, and the chart carries one bar per
        BRANCH rather than per KPI, because the per-KPI breakdown already lives
        on each branch's own dashboard and repeating all of them here would just
        be the same chart three times over.
        """
        team = self.team()
        branches = KpiBranch.objects.filter(team=team, is_active=True)

        cards = []
        everything = []

        for branch in branches:
            rows = self.scorecard_rows(team, branch)
            everything += rows

            # A branch's headline number is the mean attainment of its SCORED
            # KPIs. 'No Target' and 'No Data' KPIs have nothing to average, so
            # they are left out rather than dragged in as zero, which would
            # report an unmeasured branch as a failing one.
            scored = [r['attainment'] for r in rows if r['attainment'] is not None]
            average = round(sum(scored) / len(scored), 1) if scored else None
            status = 'monitored' if average is None else scoring.status(average)

            cards.append({
                'slug': branch.slug,
                'name': branch.name,
                'url': self.url('index', branch=branch),
                'kpi_count': len(rows),
                'scored_count': len(scored),
                'on_track_count': sum(1 for r in rows if r['status'] == 'on_track'),
                'at_risk_count': sum(1 for r in rows if r['status'] == 'at_risk'),
                'below_count': sum(1 for r in rows if r['status'] == 'below'),
                'monitored_count': sum(1 for r in rows if r['status'] == 'monitored'),
                'no_data_count': sum(1 for r in rows if r['status'] == 'no_data'),
                'attainment': average,
                'bar_pct': 0 if average is None else min(int(average), 100),
                'status': status,
                'status_label': (
                    'No Data' if average is None
                    else KpiRecord.Status(status).label
                ),
            })

        def count(status):
            return sum(1 for r in everything if r['status'] == status)

        today = timezone.localdate()

        return render(request, 'kpi/branch_overview.html', {
            'scope': self.scope,
            'branches': cards,
            'branch_count': len(cards),
            'manage_url': None,
            # Tiles tally every KPI across every branch, not just scored ones.
            'kpi_count': len(everything),
            'on_track_count': count('on_track'),
            'at_risk_count': count('at_risk'),
            'below_count': count('below'),
            'monitored_count': count('monitored'),
            'no_data_count': count('no_data'),
            'period': f'{today:%B %Y}',
            'chart_data': [
                {
                    'name': card['name'],
                    'attainment': card['attainment'],
                    'status': card['status'],
                    'actual_display': (
                        f'{card["on_track_count"]} of {card["scored_count"]} KPIs on target'
                    ),
                    'target_display': '100%',
                    'period': '',
                }
                for card in cards
                if card['attainment'] is not None
            ],
        })

    # --- CSV template ------------------------------------------------------

    def _template(self, request, slug, branch=None):
        """Download one KPI's CSV template, built from its own inputs (§D)."""
        team = self.team()
        branch = self.branch_or_404(team, branch) if branch else None
        kpi = get_object_or_404(
            KpiDefinition, team=team, branch=branch, slug=slug, is_active=True
        )

        response = HttpResponse(
            csv_template.build_bytes(kpi), content_type='text/csv; charset=utf-8'
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{csv_template.filename(kpi)}"'
        )
        return response
