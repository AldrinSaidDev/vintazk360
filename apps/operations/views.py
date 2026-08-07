from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from apps.core.audit import log_action
from apps.core.models import AuditLog, Team
from apps.kpi import csv_template
from apps.kpi.models import KpiCategory, KpiDefinition
from .forms import CreateKpiForm, EditKpiForm

# Glyph cluster behind the banner header (FA4 names, largest first).
BANNER_ICONS = ['cogs', 'tasks', 'line-chart']


# --- PLACEHOLDER DATA -------------------------------------------------------
# Sample Operations KPIs with fake "actual" numbers so the scorecard + chart
# render with something to look at. NOT real performance data. When the KPI
# models exist, replace _operations_kpis() with a DB-backed query returning the
# same shape; the template and chart won't need to change.
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


def _attainment(kpi):
    """Normalized % of target reached (100 = on target), direction-aware."""
    target, actual = kpi['target'], kpi['actual']
    if not target or not actual:
        return 0.0
    if kpi['direction'] == 'down':
        pct = target / actual * 100
    else:
        pct = actual / target * 100
    return round(pct, 1)


def _status(attainment):
    """Bucket an attainment % into a status key used for color/label."""
    if attainment >= 100:
        return 'on_track'
    if attainment >= 90:
        return 'at_risk'
    return 'below'


_STATUS_LABEL = {'on_track': 'On Track', 'at_risk': 'At Risk', 'below': 'Below Target'}


def _operations_kpis():
    """Return the KPI rows enriched with attainment + status (placeholder)."""
    rows = []
    for kpi in _OPERATIONS_KPIS:
        attainment = _attainment(kpi)
        status = _status(attainment)
        rows.append({
            **kpi,
            'attainment': attainment,
            # Progress-bar fill width, capped at 100 so overachievers show a
            # full bar (the % label still shows the true value, e.g. 112.9%).
            'bar_pct': min(round(attainment), 100),
            'status': status,
            'status_label': _STATUS_LABEL[status],
        })
    return rows


@login_required
@team_required('operations')
def index(request):
    """Operations — team dashboard (KPI scorecard: actual vs target + status)."""
    kpis = _operations_kpis()
    context = {
        'banner_icons': BANNER_ICONS,
        'kpis': kpis,
        'on_track_count': sum(1 for k in kpis if k['status'] == 'on_track'),
        'below_count': sum(1 for k in kpis if k['status'] == 'below'),
        'at_risk_count': sum(1 for k in kpis if k['status'] == 'at_risk'),
        'kpi_count': len(kpis),
        # Compact payload the bar chart reads via json_script.
        'chart_data': [
            {'name': k['name'], 'attainment': k['attainment'], 'status': k['status'],
             'actual_display': k['actual_display'], 'target_display': k['target_display']}
            for k in kpis
        ],
    }
    return render(request, 'operations/dashboard.html', context)


@login_required
@team_required('operations')
def kpi_reference(request):
    """Operations — KPI definitions reference (North Star + formulas/targets)."""
    context = {
        'banner_icons': BANNER_ICONS,
        'lob_name': 'Operations',
        'kpis': _OPERATIONS_KPIS,
        'kpi_count': len(_OPERATIONS_KPIS),
    }
    return render(request, 'operations/index.html', context)


@login_required
@team_required('operations')
def import_data(request):
    """Operations — Import Data screen (static mockup for now)."""
    return render(request, 'operations/import_data.html', {'modal_kpis': _MODAL_KPIS})


# How each KPI's direction reads on the management screen.
_DIRECTION_LABEL = {'up': 'Higher is better', 'down': 'Lower is better'}

# Picklists for the edit modal. Derived from the KPI list so a new category or
# cadence shows up in the dropdowns without touching the template.
_FREQUENCIES = ['Daily', 'Weekly', 'Monthly', 'Quarterly', 'Annually']


# Rows per page on the KPI Management table.
PAGE_SIZE = 10


def _management_queryset(team):
    return (
        KpiDefinition.objects.filter(team=team, is_active=True)
        .select_related('category')
        .prefetch_related('inputs')
        .order_by('sort_order', 'name')
    )


def _management_rows(kpis, team, edit_forms=None):
    """The KPI Management table, from the database.

    The FIRST Operations screen to read `kpi_definition` instead of the static
    `_OPERATIONS_KPIS` dicts (rollout step 5). The row shape is deliberately
    the same one the static list produced, so the template did not change shape
    around it — only `csv_url`, `input_count` and `form` are new.

    Each row carries its own bound-or-fresh `EditKpiForm`, so the Edit modal
    renders real fields with real validation messages rather than a mockup.
    Only the CURRENT PAGE gets forms built — that is what keeps this to ten.
    """
    edit_forms = edit_forms or {}

    return [
        {
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
            # Generated on demand — see apps/kpi/csv_template.py for why it is
            # not a stored file.
            'csv_url': reverse('operations:kpi_template', args=[kpi.slug]),
            'template_version': kpi.template_version,
            'input_count': len(kpi.inputs.all()),
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
                f'KPI "{kpi.name}" deleted. Its records and history are kept.',
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

                messages.success(request, f'KPI "{kpi.name}" created.')

                return redirect(_back_to_page(request))

            open_create_modal = True

    kpis = _management_queryset(operations_team)
    paginator = Paginator(kpis, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    rows = _management_rows(page.object_list, operations_team, edit_forms)

    # Every category the team HAS, not just the ones on this page, so the
    # filter still offers a category whose last KPI was deleted
    categories = sorted(
        KpiCategory.objects.filter(team=operations_team).values_list("name", flat=True)
    )

    return render(
        request,
        "operations/kpi_management.html",
        {
            "form": form,
            "open_create_modal": open_create_modal,
            "open_edit_slug": open_edit_slug,
            "kpis": rows,
            "page_obj": page,
            # kpi_count is the WHOLE set, not this page — the stat card counts
            # the scorecard, not what happens to be visible.
            "kpi_count": paginator.count,
            "categories": categories,
            "frequencies": _FREQUENCIES,
        },
    )


# Where a successful POST lands. It is an anchor on the table, and it has to be
# a real one: modals open via CSS :target, and a browser REATTACHES the original
# request's fragment to a redirect whose Location carries none of its own
# (RFC 7231 §7.1.2). Without this, saving from #kpiEdit-<slug> would redirect to
# a fragment-less URL, the browser would put #kpiEdit-<slug> back, and the modal
# would spring open again on the fresh page.
_TABLE_ANCHOR = "kpi-definitions"


def _back_to_page(request):
    """Return to the page the change was made from, with every modal closed."""
    url = reverse("operations:kpi_management")
    page = request.POST.get("_page")
    query = f"?page={page}" if page and page.isdigit() else ""
    return f"{url}{query}#{_TABLE_ANCHOR}"