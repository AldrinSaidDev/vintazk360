from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from apps.core import kpi
from apps.core.access import team_required

from .branches import BRANCHES, CHANNELS, OVERVIEW_SCOPE, branch_scope, get_branch

# Every screen renders the shared templates under templates/kpi/ — the only
# per-branch parts are the KPI list and modal labels in branches.py.


def _resolve(slug):
    """Look up a branch by slug or 404 — every branch view starts here."""
    branch = get_branch(slug)
    if branch is None:
        raise Http404(f'Unknown VCT branch: {slug}')
    return branch


@login_required
@team_required('marketing')
def index(request):
    """VCT — overview of the three branches and where each one stands."""
    cards = []
    for branch in BRANCHES.values():
        rows = kpi.scorecard(branch['kpis'])
        cards.append({
            **branch,
            **kpi.counts(rows),
            # Resolved here so the shared overview template stays app-agnostic.
            'url_dashboard': reverse('marketing:branch_index', args=(branch['slug'],)),
        })
    return render(request, 'kpi/branch_overview.html', {
        'scope': OVERVIEW_SCOPE,
        'branches': cards,
    })


@login_required
@team_required('marketing')
def branch_index(request, branch):
    """VCT branch — dashboard (KPI scorecard: actual vs target + status)."""
    branch = _resolve(branch)
    return render(request, 'kpi/dashboard.html',
                  kpi.dashboard_context(branch_scope(branch), branch['kpis']))


@login_required
@team_required('marketing')
def branch_kpis(request, branch):
    """VCT branch — KPI definitions reference."""
    branch = _resolve(branch)
    return render(request, 'kpi/kpi_definitions.html',
                  kpi.definitions_context(branch_scope(branch), branch['kpis']))


@login_required
@team_required('marketing')
def branch_import_data(request, branch):
    """VCT branch — Import Data screen (static mockup for now)."""
    branch = _resolve(branch)
    return render(request, 'kpi/import_data.html', kpi.import_context(
        branch_scope(branch), branch['kpis'], branch['modal_specs'],
        dimensions=CHANNELS, dimension_label='Channel'))


@login_required
@team_required('marketing')
def branch_kpi_management(request, branch):
    """VCT branch — KPI Management: edit targets, cadence, formulas."""
    branch = _resolve(branch)
    return render(request, 'kpi/kpi_management.html',
                  kpi.management_context(branch_scope(branch), branch['kpis']))
