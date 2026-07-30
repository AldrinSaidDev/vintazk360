from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.core.access import team_required

from .branches import BRANCHES, get_branch, modal_kpis

# Glyph cluster behind the banner header (FA4 names, largest first).
BANNER_ICONS = ['line-chart', 'bullhorn', 'handshake-o']

# Sales KPI values are still static placeholders (see branches.py) — these
# helpers turn that data into scorecard rows. Swapping in a KPI model later
# means changing where `branch['kpis']` comes from, nothing else.


def _attainment(kpi):
    """Normalized % of target reached, or None when the KPI isn't scored.

    Sales targets are BANDS ("40–80/month"), so anything inside the band is
    fully on target (100%). Outside it, attainment is measured against the edge
    that was missed, direction-aware. Returned unrounded so the status bucket
    isn't decided by rounding.
    """
    low, high, actual = kpi['target_min'], kpi['target_max'], kpi['actual']
    if low is None or high is None:
        return None                       # tracked, but no target set
    if not actual:
        return 0.0
    if kpi['direction'] == 'down':        # cost — under the band is better
        if actual > high:
            return high / actual * 100
        if actual < low:
            return low / actual * 100
        return 100.0
    if actual < low:
        return actual / low * 100
    if actual > high:
        return actual / high * 100        # over the band still beats target
    return 100.0


def _status(attainment):
    """Bucket an attainment % into a status key used for color/label."""
    if attainment is None:
        return 'monitored'
    if attainment >= 100:
        return 'on_track'
    if attainment >= 90:
        return 'at_risk'
    return 'below'


def _shown(attainment):
    """Attainment rounded for display, never rounding a miss up to 100%."""
    value = round(attainment, 1)
    if attainment < 100 <= value:
        return 99.9
    return value


_STATUS_LABEL = {
    'on_track': 'On Track',
    'at_risk': 'At Risk',
    'below': 'Below Target',
    'monitored': 'No Target',
}


def _scorecard(branch):
    """Return the branch's KPI rows enriched with attainment + status."""
    rows = []
    for kpi in branch['kpis']:
        attainment = _attainment(kpi)
        status = _status(attainment)
        rows.append({
            **kpi,
            'attainment': None if attainment is None else _shown(attainment),
            # Bar fill capped at 100 so overachievers show a full bar; floored
            # below target so a near-miss never draws as a full one.
            'bar_pct': 0 if attainment is None else min(int(attainment), 100),
            'status': status,
            'status_label': _STATUS_LABEL[status],
        })
    return rows


def _counts(rows):
    """Status tallies used by both the branch dashboard and the Sales overview."""
    return {
        'kpi_count': len(rows),
        'on_track_count': sum(1 for r in rows if r['status'] == 'on_track'),
        'at_risk_count': sum(1 for r in rows if r['status'] == 'at_risk'),
        'below_count': sum(1 for r in rows if r['status'] == 'below'),
        'monitored_count': sum(1 for r in rows if r['status'] == 'monitored'),
    }


def _resolve(slug):
    """Look up a branch by slug or 404 — every branch view starts here."""
    branch = get_branch(slug)
    if branch is None:
        raise Http404(f'Unknown Sales branch: {slug}')
    return branch


@login_required
@team_required('sales')
def index(request):
    """Sales — overview of the three branches and where each one stands."""
    cards = []
    for branch in BRANCHES.values():
        cards.append({**branch, **_counts(_scorecard(branch))})
    return render(request, 'sales/overview.html', {'branches': cards})


@login_required
@team_required('sales')
def branch_index(request, branch):
    """Sales branch — dashboard (KPI scorecard: actual vs target + status)."""
    branch = _resolve(branch)
    rows = _scorecard(branch)
    context = {
        'banner_icons': BANNER_ICONS,
        'branch': branch,
        'kpis': rows,
        **_counts(rows),
        # Compact payload the bar chart reads via json_script. KPIs without a
        # target have nothing to plot against, so they're left out.
        'chart_data': [
            {'name': r['name'], 'attainment': r['attainment'], 'status': r['status'],
             'actual_display': r['actual_display'], 'target_display': r['target_display']}
            for r in rows if r['attainment'] is not None
        ],
    }
    return render(request, 'sales/dashboard.html', context)


@login_required
@team_required('sales')
def branch_kpis(request, branch):
    """Sales branch — KPI definitions reference (targets, cadence, formulas)."""
    branch = _resolve(branch)
    return render(request, 'sales/kpi_definitions.html', {
        'banner_icons': BANNER_ICONS,
        'branch': branch,
        'kpis': branch['kpis'],
        'kpi_count': len(branch['kpis']),
    })


@login_required
@team_required('sales')
def branch_import_data(request, branch):
    """Sales branch — Import Data screen (static mockup for now)."""
    branch = _resolve(branch)
    return render(request, 'sales/import_data.html', {
        'branch': branch,
        'modal_kpis': modal_kpis(branch),
    })


# How each KPI's direction reads on the management screen.
_DIRECTION_LABEL = {'up': 'Higher is better', 'down': 'Lower is better'}

# Picklist for the edit modal. Union'd with whatever cadences are in use so a
# non-standard one stays selectable.
_FREQUENCIES = ['Daily', 'Weekly', 'Monthly', 'Quarterly', 'Annually']


@login_required
@team_required('sales')
def branch_kpi_management(request, branch):
    """Sales branch — KPI Management: edit target bands, cadence, formulas.

    Static like the rest of the KPI screens: the table and edit modals render
    from ``branches.py`` and Save is not wired to anything yet.
    """
    branch = _resolve(branch)
    rows = [
        {**kpi, 'direction_label': _DIRECTION_LABEL[kpi['direction']]}
        for kpi in branch['kpis']
    ]
    return render(request, 'sales/kpi_management.html', {
        'branch': branch,
        'kpis': rows,
        'kpi_count': len(rows),
        'categories': sorted({kpi['category'] for kpi in branch['kpis']}),
        'frequencies': sorted({*_FREQUENCIES, *(k['frequency'] for k in branch['kpis'])}),
    })
