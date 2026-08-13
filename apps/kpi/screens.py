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

from apps.core import async_content
from apps.core import cache
from apps.core import kpi as scoring
from apps.core.access import require_edit, team_required
from apps.core.audit import log_action
from apps.core.models import AuditLog, Team

from . import csv_template, importer, workbook
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
IMPORTS_PAGE_SIZE = 10

# The history pager's own query key. NOT `page`: both tables live on one screen
# now, and sharing a key would move them together.
IMPORTS_PAGE_PARAM = 'ipage'

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

# Import Data's two panels share one card and one anchor. Records is the
# default, so `?tab=` only ever appears when the other one is showing.
RECORDS_TAB = 'records'
IMPORTS_TAB = 'imports'


def _link_params(request):
    """`request.GET` as the basis for a link the USER is going to click.

    Stage 2's `partial=1` must never survive into one. These screens render in
    two stages (`apps/core/async_content.py`), so on the fetch that builds the
    content `request.GET` carries that flag, and a pager pill or a tab link
    built from it would hand the visitor the FRAGMENT: no sidebar, no header,
    no page frame at all. Every link and redirect below starts here.
    """
    params = request.GET.copy()
    params.pop(async_content.PARTIAL_PARAM, None)
    return params


def _query_without_page(request, key='page'):
    """The current query string minus one pager's own key, for its links.

    `key` because Import Data now has TWO pagers on one page, and each has to
    drop only its own parameter: a records link that stripped `ipage` would
    quietly send the history back to page 1.
    """
    params = _link_params(request)
    params.pop(key, None)
    return params.urlencode()


def _tab_url(request, tab):
    """The current URL with one of Import Data's two tabs selected.

    A real link, not a JS-only control: with the script the panels swap
    instantly, without it the tab still works as a page load. It also means the
    choice lives in the query string, so a form posting to the current URL
    carries it and a redirect can land back on the tab it was submitted from.
    Records is the default, so it drops the parameter rather than spelling it
    out.
    """
    params = _link_params(request)
    if tab == RECORDS_TAB:
        params.pop('tab', None)
    else:
        params['tab'] = tab
    query = params.urlencode()
    return f'{request.path}{"?" + query if query else ""}#{RECORDS_ANCHOR}'


def _posted_pk(request, field):
    """The row id a modal's hidden field posted, or 0 for anything that isn't one.

    A hand-made POST can carry '' or 'abc', and a non-numeric value reaching a
    pk lookup raises ValueError rather than turning into a not-found — a 500
    where a 404 belongs. 0 never matches, so the caller's `get_object_or_404`
    gives the right answer.
    """
    value = request.POST.get(field, '')
    return int(value) if value.isdigit() else 0


def _params_without_page(request, key='page'):
    """The same, as key/value pairs, for the pagination form's hidden inputs."""
    return [
        {'key': name, 'value': value}
        for name, values in _link_params(request).lists()
        if name != key
        for value in values
        if value
    ]


class KpiScreens:
    """The four KPI screens plus the CSV template download, for one team."""

    def __init__(self, *, team_slug, namespace=None, scope=None, branched=False,
                 workbook_template=False):
        self.team_slug = team_slug
        self.namespace = namespace or team_slug
        self.scope = scope or {}
        self.branched = branched
        # ONE workbook for the whole team, a sheet per KPI, instead of a CSV
        # per KPI. Operations is the pilot; the rest keep per-KPI CSVs until
        # this shape is signed off, which is why it is a flag and not a
        # replacement.
        self.workbook_template = workbook_template

        guard = [login_required, team_required(team_slug)]

        def wrap(view, shell_title=None):
            # The shell wrapper goes on FIRST so the guards end up outside it.
            # Reversed, an anonymous visitor would be handed a page frame before
            # anything checked whether they may see the team at all.
            if shell_title is not None:
                view = self._shell_first(view, shell_title)
            for decorator in reversed(guard):
                view = decorator(view)
            return view

        # A shell_title means the screen renders in two stages: frame and
        # skeleton now, data on the follow-up fetch. The downloads have no
        # frame to paint, so they stay single-stage.
        self.dashboard = wrap(self._dashboard, 'Dashboard')
        self.definitions = wrap(self._definitions, 'KPI Definitions')
        self.import_data = wrap(self._import_data, 'Import Data')
        self.management = wrap(self._management, 'KPI Management')
        self.template = wrap(self._template)
        self.workbook = wrap(self._workbook) if workbook_template else None
        # Only a branch team has anything to roll up.
        self.overview = wrap(self._overview, 'Dashboard') if branched else None

    def _shell_first(self, view, shell_title):
        """Answer a plain GET with the page frame and a skeleton, no queries.

        The real view then runs on the ?partial=1 fetch that the skeleton kicks
        off, so the skeleton is on screen for exactly as long as the data takes.
        A POST goes straight through: it is going to redirect or to re-render
        with its errors, and neither wants a skeleton.
        """
        def screen(request, *args, **kwargs):
            if not async_content.wants_shell(request):
                return view(request, *args, **kwargs)

            # The branch is resolved even here, so a typo'd branch slug 404s
            # now rather than painting a frame whose fetch then fails. It is one
            # indexed lookup, and it is what titles the page.
            branch_slug = kwargs.get('branch')
            branch = (
                self.branch_or_404(self.team(), branch_slug)
                if branch_slug else None
            )
            return async_content.render_shell(
                request,
                shell_template='kpi/screen_shell.html',
                context={
                    'scope': self.scope_for(branch),
                    'shell_title': shell_title,
                },
            )

        return screen

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
        if self.workbook_template:
            context['workbook_url'] = self.url('kpi_workbook', branch=branch)
        # Drives BOTH the per-row CSV column and the single workbook button,
        # so a screen can never offer neither or both.
        context['per_kpi_templates'] = not self.workbook_template
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
                kpi__team=team, kpi__branch=branch, kpi__is_active=True,
                is_active=True,
            )
            .order_by('kpi_id', '-period_start')
            .only('kpi_id', 'period_start', 'value', 'score', 'value_display')
        ):
            latest.setdefault(record.kpi_id, record)
        return latest

    def scorecard_rows(self, team, branch=None):
        """One dashboard card per live KPI, cached per team and branch.

        Cheap to key because nothing here varies by user or by request: this
        screen is the same for everyone who can reach it, and who can reach it
        is decided by `@team_required` before any of this runs.
        """
        return cache.fetch(
            cache.team_key('scorecard', team.pk, branch.slug if branch else ''),
            lambda: self._scorecard_rows(team, branch),
        )

    def _scorecard_rows(self, team, branch=None):
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

        return async_content.render_content(request, 'kpi/dashboard.html', {
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
        rows = cache.fetch(
            cache.team_key('definitions', team.pk, branch.slug if branch else ''),
            lambda: [self.row(kpi) for kpi in self.queryset(team, branch)],
        )

        return async_content.render_content(request, 'kpi/kpi_definitions.html', {
            **self._urls(branch),
            'kpis': rows,
            'kpi_count': len(rows),
        })

    # --- import data -------------------------------------------------------

    def import_stats(self, team, branch=None):
        """The four Import Data stat cards, cached per team and branch.

        Today's date is part of the key. Two of these tiles are worded against
        the current month, so an entry made yesterday must not still be served
        after midnight saying "August" while the page header says September.
        """
        return cache.fetch(
            cache.team_key(
                'import-stats', team.pk,
                branch.slug if branch else '', timezone.localdate(),
            ),
            lambda: self._import_stats(team, branch),
        )

    def _import_stats(self, team, branch=None):
        """The four Import Data stat cards, counted from the database."""
        records = KpiRecord.objects.filter(
            kpi__team=team, kpi__branch=branch, is_active=True
        )
        today = timezone.localdate()
        last_batch = (
            # A deleted import is not the last import: it is one that never
            # happened as far as this team's data is concerned.
            KpiImportBatch.objects.filter(team=team, branch=branch, is_active=True)
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
        """KPI Records table rows, from `kpi_record`.

        Carries the detail the View modal shows as well as the columns of the
        table. Both come off rows already fetched, so opening a record costs no
        query: the alternative is a per-record endpoint for data the page is
        holding anyway.
        """
        return [
            {
                # The delete form posts this. Records have no slug of their own,
                # and (kpi, period) as a composite handle would be two fields to
                # validate for no gain.
                'pk': record.pk,
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
                # --- View modal only ---
                'frequency': record.kpi.get_frequency_display(),
                'period_start': record.period_start,
                'period_end': record.period_end,
                # The formula plus the operands below is the whole answer to
                # "why is this number what it is?".
                'formula': record.kpi.formula_text or record.kpi.expression,
                'inputs': [
                    {
                        'label': value.input.label,
                        'key': value.input.key,
                        'value': (
                            value.value_date if value.value_number is None
                            else value.value_number
                        ),
                    }
                    # In CSV column order, so the modal reads like the template
                    # the figures were typed into.
                    for value in sorted(
                        record.input_values.all(), key=lambda v: v.input.position
                    )
                ],
                'entered_by': (
                    record.entered_by.get_full_name() or record.entered_by.get_username()
                    if record.entered_by_id
                    else 'System'
                ),
                'created_at': record.created_at,
                'updated_at': record.updated_at,
                'batch_file': (
                    record.import_batch.file_name if record.import_batch_id else ''
                ),
            }
            for record in records_qs
        ]

    def import_rows(self, batches):
        """Recent Import History rows, from `kpi_import_batch`.

        Like `record_rows`, this carries the View modal's detail too, including
        every `kpi_import_issue` the upload raised. A partial import's whole
        point is that some rows were refused, and the count in the table is
        useless without being able to read which ones and why.
        """
        return [
            {
                'pk': batch.pk,
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
                # --- View modal only ---
                'rows_read': batch.row_count,
                'created_count': batch.created_count,
                'updated_count': batch.updated_count,
                'template_version': batch.template_version,
                'file_size': batch.file_size,
                'completed_at': batch.completed_at,
                # How many of this upload's records are still live. A batch
                # whose rows were later deleted one by one should not claim to
                # be holding them.
                'live_records': sum(
                    1 for record in batch.records.all() if record.is_active
                ),
                'issues': [
                    {
                        'row_number': issue.row_number,
                        'column_key': issue.column_key,
                        'raw_value': issue.raw_value,
                        'severity': issue.severity,
                        'severity_label': issue.get_severity_display(),
                        'message': issue.message,
                    }
                    for issue in batch.issues.all()
                ],
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

    def _back_to_records(self, request):
        """Return to the records view the change was made from, filters intact.

        The forms carry no `action`, so they post to the current URL, query
        string included, and `request.GET` still holds whatever search and
        filters were applied. Redirecting to a bare `request.path` would reset
        them underneath the user. The anchor is mandatory for the same reason
        as `_back_to_page()`: a browser reattaches the request's own fragment
        to a Location that has none (RFC 7231 §7.1.2), which would reopen the
        modal that was just submitted.
        """
        query = _link_params(request).urlencode()
        return (
            f'{request.path}{"?" + query if query else ""}#{RECORDS_ANCHOR}'
        )

    def _import_data(self, request, branch=None):
        """Import Data: manual entry and CSV upload both write records."""
        team = self.team()
        branch = self.branch_or_404(team, branch) if branch else None

        add_form = AddRecordForm(team=team, branch=branch)
        import_form = ImportRecordsForm()
        open_add_modal = open_import_modal = False

        if request.method == 'POST':
            # `team_required` said this user may be on the page; this says
            # whether they may change what is on it. A User or a Viewer reads
            # the records and is refused every write below (Part C).
            require_edit(request.user, self.team_slug)

            if request.POST.get('_action') == 'delete-record':
                # SOFT delete (design principle 7): the row leaves every table,
                # tile and chart, but the figure, its raw operands and the
                # import batch it came from all survive. Scoped to this team and
                # branch, so a guessed id from another LOB is a 404, not a
                # delete.
                record = get_object_or_404(
                    KpiRecord,
                    pk=_posted_pk(request, '_record'),
                    kpi__team=team,
                    kpi__branch=branch,
                    is_active=True,
                )
                period = kpi_periods.label(record.period_start, record.kpi.frequency)

                record.is_active = False
                record.save(update_fields=['is_active', 'updated_at'])

                log_action(
                    request,
                    action=AuditLog.Action.DELETED,
                    entity=record,
                    entity_type='kpi_record',
                    team=team,
                    old_values={'is_active': True},
                    new_values={
                        'is_active': False,
                        'kpi': record.kpi.name,
                        'period': period,
                        'value': record.value_display,
                    },
                )

                messages.success(
                    request,
                    f'{record.kpi.name} for {period} has been deleted. '
                    'Re-entering that period restores it.',
                )
                return redirect(self._back_to_records(request))

            if request.POST.get('_action') == 'delete-import':
                # Deleting an upload deletes what it wrote. An import is one
                # act, so undoing it row by row would leave the batch claiming
                # records that are gone and the tiles counting figures nobody
                # meant to enter.
                #
                # Both sides are SOFT (design principle 7): the batch keeps its
                # counts and its rejected rows, the records keep their operands,
                # and the stored file is untouched. Scoped to this team and
                # branch, so a guessed id from another LOB is a 404.
                batch = get_object_or_404(
                    KpiImportBatch,
                    pk=_posted_pk(request, '_batch'),
                    team=team,
                    branch=branch,
                    is_active=True,
                )

                # Only the records this batch is still the source of. A period
                # that was re-uploaded later belongs to that later batch, whose
                # `import_batch` now points there, so it is correctly left alone.
                removed = KpiRecord.objects.filter(
                    import_batch=batch, is_active=True
                ).update(is_active=False)

                batch.is_active = False
                batch.save(update_fields=['is_active'])

                log_action(
                    request,
                    action=AuditLog.Action.DELETED,
                    entity=batch,
                    entity_type='kpi_import_batch',
                    team=team,
                    old_values={'is_active': True},
                    new_values={
                        'is_active': False,
                        'file_name': batch.file_name,
                        'records_removed': removed,
                    },
                )

                messages.success(
                    request,
                    f'{batch.file_name} has been deleted, along with '
                    f'{removed} record{"" if removed == 1 else "s"} it entered. ',
                )
                return redirect(self._back_to_records(request))

            if request.POST.get('_action') == 'import':
                import_form = ImportRecordsForm(request.POST, request.FILES)

                if import_form.is_valid():
                    upload = import_form.cleaned_data['file']
                    parse = (
                        importer.parse_and_apply_workbook
                        if upload.name.lower().endswith('.xlsx')
                        else importer.parse_and_apply
                    )
                    try:
                        result = parse(
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
                        return redirect(self._back_to_records(request))
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
                    return redirect(self._back_to_records(request))

                open_add_modal = True

        # Every category the team HAS, not just the ones currently in use, so
        # the filter still offers a category whose last KPI was deleted.
        categories = sorted(
            KpiCategory.objects.filter(team=team).values_list('name', flat=True)
        )

        # Every KPI a row in this table could belong to. NOT just the live ones:
        # a soft-deleted KPI keeps its records and they still list here, so
        # filtering to one has to stay possible. Deleted ones say so, or the
        # list reads as if the KPI were back.
        kpi_options_qs = (
            KpiDefinition.objects.filter(team=team, branch=branch)
            .filter(Q(is_active=True) | Q(records__is_active=True))
            .distinct()
            .order_by('sort_order', 'name')
        )

        # Search and filters, the same one-GET-form shape as KPI Management:
        # two controls in one form, so applying a filter cannot wipe the search.
        search = request.GET.get('q', '').strip()
        chosen_kpis = [k for k in request.GET.getlist('kpi') if k]
        chosen_categories = [c for c in request.GET.getlist('category') if c]
        chosen_statuses = [s for s in request.GET.getlist('status') if s]
        chosen_sources = [s for s in request.GET.getlist('source') if s]

        records_qs = (
            KpiRecord.objects.filter(
                kpi__team=team, kpi__branch=branch, is_active=True
            )
            .select_related('kpi', 'kpi__category', 'entered_by', 'import_batch')
            # The View modal shows the raw operands behind the figure. Prefetched
            # here so opening one costs no query.
            .prefetch_related('input_values__input')
            .order_by('-period_start', 'kpi__sort_order')
        )
        if search:
            # The KPI's name and the row's own remarks: the two free-text
            # things in this table. Everything else is a facet below.
            records_qs = records_qs.filter(
                Q(kpi__name__icontains=search) | Q(remarks__icontains=search)
            )
        if chosen_kpis:
            # By slug, not pk: it survives in a bookmarked or shared URL and is
            # the same handle the CSV header and the management screen use.
            records_qs = records_qs.filter(kpi__slug__in=chosen_kpis)
        if chosen_categories:
            records_qs = records_qs.filter(kpi__category__name__in=chosen_categories)
        if chosen_statuses:
            # The STORED status, which is what this table prints. The dashboard
            # recomputes instead, because a card must not show a verdict from a
            # target that has since moved; here the filter and the badge have to
            # agree, so both read the same column.
            records_qs = records_qs.filter(status__in=chosen_statuses)
        if chosen_sources:
            records_qs = records_qs.filter(source__in=chosen_sources)

        paginator = Paginator(records_qs, RECORDS_PAGE_SIZE)
        page = paginator.get_page(request.GET.get('page'))
        # Records accumulate every period, so the page list is elided rather
        # than printing one pill per page once a few years of history exist.
        # list(), not the generator: it is single-use, so anything reading it
        # after the template has rendered would find it empty.
        page_numbers = list(
            paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
        )

        # Paginated rather than capped at the ten most recent: an import is the
        # receipt for a figure someone is querying, and "which upload put this
        # number here?" is unanswerable once the file scrolls off a fixed list.
        batches_qs = (
            KpiImportBatch.objects.filter(team=team, branch=branch, is_active=True)
            .select_related('kpi', 'uploaded_by')
            # Both feed the View modal: which rows were refused and why, and how
            # many of the records this upload wrote are still live.
            .prefetch_related('issues', 'records')
            .order_by('-uploaded_at')
        )
        imports_paginator = Paginator(batches_qs, IMPORTS_PAGE_SIZE)
        imports_page = imports_paginator.get_page(
            request.GET.get(IMPORTS_PAGE_PARAM)
        )
        imports_page_numbers = list(
            imports_paginator.get_elided_page_range(
                imports_page.number, on_each_side=1, on_ends=1
            )
        )

        return async_content.render_content(request, 'kpi/import_data.html', {
            **self._urls(branch),
            'add_form': add_form,
            'import_form': import_form,
            'open_add_modal': open_add_modal,
            'open_import_modal': open_import_modal,
            'records': self.record_rows(page.object_list),
            # What the filters MATCHED. The Total Records stat card above keeps
            # counting every record, filtered or not.
            'record_count': paginator.count,
            'page_obj': page,
            'page_numbers': page_numbers,
            'extra_query': _query_without_page(request),
            'extra_params': _params_without_page(request),
            # Each option carries its own checked flag, so the template holds
            # no lookup logic.
            'kpi_options': [
                {
                    'value': kpi.slug,
                    'label': kpi.name if kpi.is_active else f'{kpi.name} (deleted)',
                    'checked': kpi.slug in chosen_kpis,
                }
                for kpi in kpi_options_qs
            ],
            'category_options': [
                {'value': name, 'label': name, 'checked': name in chosen_categories}
                for name in categories
            ],
            'status_options': [
                {'value': value, 'label': label, 'checked': value in chosen_statuses}
                for value, label in KpiRecord.Status.choices
            ],
            'source_options': [
                {'value': value, 'label': label, 'checked': value in chosen_sources}
                for value, label in KpiRecord.Source.choices
            ],
            'search': search,
            # Drives the button's active styling and its count badge. Search is
            # excluded: it has its own visible box.
            'active_filter_count': (
                len(chosen_kpis) + len(chosen_categories)
                + len(chosen_statuses) + len(chosen_sources)
            ),
            'has_any_filter': bool(
                search or chosen_kpis or chosen_categories
                or chosen_statuses or chosen_sources
            ),
            'clear_url': self.url('import_data', branch=branch),
            'imports': self.import_rows(imports_page.object_list),
            # The tab badge counts every upload, not the page.
            'import_count': imports_paginator.count,
            'imports_page_obj': imports_page,
            'imports_page_numbers': imports_page_numbers,
            'imports_page_param': IMPORTS_PAGE_PARAM,
            # Each pager drops only its OWN key, so paging one table cannot
            # reset the other, and both keep the tab and the record filters.
            'imports_query': _query_without_page(request, IMPORTS_PAGE_PARAM),
            'imports_params': _params_without_page(request, IMPORTS_PAGE_PARAM),
            # Which of the two panels is showing. Anything but the imports tab
            # falls back to records, so a typo'd `?tab=` shows the figures
            # rather than an empty card.
            'active_tab': (
                IMPORTS_TAB if request.GET.get('tab') == IMPORTS_TAB
                else RECORDS_TAB
            ),
            'records_tab_url': _tab_url(request, RECORDS_TAB),
            'imports_tab_url': _tab_url(request, IMPORTS_TAB),
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
                'csv_url': (
                    None if self.workbook_template
                    else self.url('kpi_template', kpi.slug, branch=branch)
                ),
                'form': (
                    edit_forms.get(kpi.slug)
                    or EditKpiForm(instance=kpi, team=team, branch=branch, prefix=kpi.slug)
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
        params = _link_params(request)
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

        form = CreateKpiForm(team=team, branch=branch, prefix='create')
        edit_forms = {}

        if request.method == 'POST':
            # Read and write are served from one view, so the write side is
            # guarded here rather than around the whole thing: a read-only role
            # still gets the screen, it just cannot submit from it.
            require_edit(request.user, self.team_slug)

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
                    request.POST, instance=kpi, team=team, branch=branch, prefix=kpi.slug
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
                form = CreateKpiForm(request.POST, team=team, branch=branch, prefix='create')

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

        return async_content.render_content(request, 'kpi/kpi_management.html', {
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

            # A branch's headline number is progress toward hitting every
            # target it has set, the same rule the Overall Dashboard's
            # department cards use — and the same function, so a branch cannot
            # read one figure here and another on the company page.
            #
            # A TARGET WITH NO FIGURE COUNTS AS 0. This used to average only the
            # KPIs that had data, which let SEO's one reported KPI out of five
            # read as a branch at 100%.
            #
            # A KPI with no target is still left out, which is not the same as
            # zero: it has nothing to hit, so it can be neither attained nor
            # missed. `average` is therefore None only for a branch that has set
            # no targets at all.
            scored = [r['attainment'] for r in rows if r['attainment'] is not None]
            average, scorable = scoring.goal_attainment(
                (r['target_min'] is not None or r['target_max'] is not None,
                 r['attainment'])
                for r in rows
            )
            status = 'monitored' if average is None else scoring.status(average)

            cards.append({
                'slug': branch.slug,
                'name': branch.name,
                'url': self.url('index', branch=branch),
                'kpi_count': len(rows),
                'scored_count': len(scored),
                # The figure's denominator, and the gap the card reports.
                'scorable_count': scorable,
                'missing_count': scorable - len(scored),
                'on_track_count': sum(1 for r in rows if r['status'] == 'on_track'),
                'at_risk_count': sum(1 for r in rows if r['status'] == 'at_risk'),
                'below_count': sum(1 for r in rows if r['status'] == 'below'),
                'monitored_count': sum(1 for r in rows if r['status'] == 'monitored'),
                'no_data_count': sum(1 for r in rows if r['status'] == 'no_data'),
                'attainment': average,
                'bar_pct': 0 if average is None else min(int(average), 100),
                'status': status,
                'status_label': (
                    # 'No Target' rather than 'No Data': the only branch with
                    # no figure now is one that has set nothing to hit. A branch
                    # that simply has not reported reads 0%, like any other miss.
                    'No Target' if average is None
                    else KpiRecord.Status(status).label
                ),
            })

        def count(status):
            return sum(1 for r in everything if r['status'] == status)

        today = timezone.localdate()

        return async_content.render_content(request, 'kpi/branch_overview.html', {
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
                        f'{card["on_track_count"]} of {card["scorable_count"]} '
                        'targets met'
                    ),
                    'target_display': '100%',
                    'period': '',
                }
                for card in cards
                # A branch at 0% is charted: that is a real reading now, not an
                # absence. Only a branch with nothing targeted sits out.
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

    # --- one workbook for the whole team -----------------------------------

    def _workbook(self, request, branch=None):
        """Download every live KPI as one .xlsx, a sheet per KPI (§D, revised).

        Built on demand like the CSV and for the same §A.6 reason: a stored
        file goes stale the moment a formula changes. Which sheets exist is
        simply which KPIs are active, so creating or deleting a KPI changes the
        next download with no further action.
        """
        team = self.team()
        branch = self.branch_or_404(team, branch) if branch else None
        kpis = self.queryset(team, branch)

        response = HttpResponse(
            workbook.build(kpis, team, branch),
            content_type=(
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ),
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{workbook.filename(team, branch)}"'
        )
        return response
