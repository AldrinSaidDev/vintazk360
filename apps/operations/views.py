from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required


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


@login_required
@team_required('operations')
def kpi_management(request):
    """Operations — KPI Management: edit targets/thresholds, formulas, cadence.

    Static like the rest of the KPI screens: the table and edit modals render
    from ``_OPERATIONS_KPIS`` and Save is not wired to anything yet. Swapping
    in a KPI model later means changing this query only.
    """
    rows = [
        {**kpi, 'direction_label': _DIRECTION_LABEL[kpi['direction']]}
        for kpi in _OPERATIONS_KPIS
    ]
    categories = sorted({kpi['category'] for kpi in _OPERATIONS_KPIS})

    return render(request, 'operations/kpi_management.html', {
        'kpis': rows,
        'kpi_count': len(rows),
        'categories': categories,
        # Union so any cadence already in use is selectable even if it's not
        # one of the standard five.
        'frequencies': sorted({*_FREQUENCIES, *(k['frequency'] for k in _OPERATIONS_KPIS)}),
    })
