from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required

# Glyph cluster behind the banner header (FA4 names, largest first).
BANNER_ICONS = ['code', 'microchip', 'laptop']


# --- PLACEHOLDER DATA -------------------------------------------------------
# Nexzys (internal technology / automation) KPIs with fake "actual" numbers so
# the scorecard + chart render with something to look at. NOT real performance
# data. When the KPI models exist, replace _nexzys_kpis() with a DB-backed query
# returning the same shape; the templates and chart won't need to change.
#
# direction:
#   'up'   → higher is better; attainment = actual / target * 100
#   'down' → lower is better (e.g. provisioning days, incident count);
#            attainment = target / actual * 100
#
# `inputs` lists the raw data each KPI needs — surfaced on the definitions page
# so whoever collects the numbers knows exactly what to bring.
_NEXZYS_KPIS = [
    {'name': 'Automation Hours Saved',  'category': 'Automation & AI', 'target': 2,     'actual': 2.6,   'direction': 'up',
     'target_display': '2 hrs/employee', 'actual_display': '2.6 hrs/employee', 'frequency': 'Monthly',
     'formula': 'Hours Saved = Manual hours − Automated hours (per employee)',
     'description': 'Time given back to employees each month by replacing manual work with automation.',
     'inputs': ['Current manual time', 'Automated time', 'Frequency', 'Employees']},

    {'name': 'Automation ROI',          'category': 'Automation & AI', 'target': 3,     'actual': 3.4,   'direction': 'up',
     'target_display': '≥3× per system', 'actual_display': '3.4×', 'frequency': 'Quarterly',
     'formula': 'ROI = Annual value generated ÷ Annual system cost',
     'description': 'Value each automated system returns against what it costs to run for a year.',
     'inputs': ['Hours saved/month', 'Labor cost/hour', 'Annual software cost']},

    {'name': 'System Uptime',           'category': 'Infrastructure',  'target': 99.99, 'actual': 99.96, 'direction': 'up',
     'target_display': '≥99.99%', 'actual_display': '99.96%', 'frequency': 'Monthly',
     'formula': 'Uptime % = System available time ÷ Total scheduled time × 100',
     'description': 'Share of scheduled time core systems were available to the business.',
     'inputs': ['Total monitoring time', 'Downtime']},

    {'name': 'IT SLA Compliance',       'category': 'Service Delivery', 'target': 95,   'actual': 97.2,  'direction': 'up',
     'target_display': '≥95%', 'actual_display': '97.2%', 'frequency': 'Monthly',
     'formula': 'SLA Compliance = Tickets resolved within SLA ÷ Total tickets × 100',
     'description': 'Share of IT tickets resolved inside their agreed response and fix windows.',
     'inputs': ['Total tickets', 'On-time tickets']},

    {'name': 'New-Hire Provisioning',   'category': 'Service Delivery', 'target': 1,    'actual': 1.4,   'direction': 'down',
     'target_display': '≤1 working day', 'actual_display': '1.4 days', 'frequency': 'Per Wave',
     'formula': 'Provisioning Days = Ready date − Day 0 (wave KPI = longest provisioning time in the wave)',
     'description': 'Working days to get a new hire fully set up. Ready date is the latest completion '
                    'of account setup, access, device, and workstation.',
     'inputs': ['Day 0', 'Account setup date', 'Access date', 'Device date', 'Workstation date']},

    {'name': 'Workstation Readiness',   'category': 'Infrastructure',  'target': 95,    'actual': 91,    'direction': 'up',
     'target_display': '≥95% ready', 'actual_display': '91%', 'frequency': 'Weekly',
     'formula': 'Readiness % = Ready workstations ÷ Total workstations × 100',
     'description': 'Share of workstations built, tested, and ready to deploy — with the backlog cleared.',
     'inputs': ['Ready stations', 'Total stations', 'Backlog count']},

    {'name': 'AI Copilot Adoption',     'category': 'Automation & AI', 'target': 60,    'actual': 48,    'direction': 'up',
     'target_display': '≥60%', 'actual_display': '48%', 'frequency': 'Monthly',
     'formula': 'Adoption % = Employees using AI tools ÷ Eligible employees × 100',
     'description': 'Share of eligible employees actively using the rolled-out AI tools.',
     'inputs': ['Eligible employees', 'Active AI users']},

    {'name': 'Security Incidents',      'category': 'Security',        'target': 0,     'actual': 0,     'direction': 'down',
     'target_display': 'Zero major incidents', 'actual_display': '0 major', 'frequency': 'Monthly',
     'formula': 'Major incidents count',
     # Second measure that rides along with this KPI (100% of staff trained).
     'formula_note': 'Training Completion % = Employees completed security training ÷ Total employees × 100',
     'description': 'Major security incidents in the period. Tracked alongside security-training completion, '
                    'which targets 100% of employees.',
     'inputs': ['Incident count', 'Employees trained', 'Total employees']},
]


# Formula inputs for the Add-Record modal. Unlike Operations (every KPI is a
# num ÷ den × 100 percentage), Nexzys KPIs come in several shapes, so each entry
# declares a `kind` that tells the modal how to compute and word the result:
#   percent    → a ÷ b × 100      (uptime, SLA, readiness, adoption)
#   ratio      → a ÷ b            (ROI, reads as "3.4×")
#   difference → a − b            (hours saved)
#   days       → date a − date b  (provisioning turnaround)
#   count      → a                (major incidents; no denominator)
# `sub_a`/`sub_b` add an optional second percentage line (security training).
_MODAL_KPIS = [
    {'name': 'Automation Hours Saved', 'kind': 'difference', 'unit': 'hrs',
     'a_label': 'Manual hours per employee',   'a_placeholder': 'e.g. 9.5',
     'b_label': 'Automated hours per employee', 'b_placeholder': 'e.g. 6.9'},

    {'name': 'Automation ROI', 'kind': 'ratio', 'unit': '×',
     'a_label': 'Annual value generated', 'a_placeholder': 'e.g. 850000',
     'b_label': 'Annual system cost',     'b_placeholder': 'e.g. 250000'},

    {'name': 'System Uptime', 'kind': 'percent', 'unit': '%',
     'a_label': 'System available time (hrs)', 'a_placeholder': 'e.g. 743.7',
     'b_label': 'Total scheduled time (hrs)',  'b_placeholder': 'e.g. 744'},

    {'name': 'IT SLA Compliance', 'kind': 'percent', 'unit': '%',
     'a_label': 'Tickets resolved within SLA', 'a_placeholder': 'e.g. 486',
     'b_label': 'Total tickets',               'b_placeholder': 'e.g. 500'},

    {'name': 'New-Hire Provisioning', 'kind': 'days', 'unit': 'days',
     'a_label': 'Ready date (last item completed)', 'a_placeholder': '',
     'b_label': 'Day 0 (start date)',               'b_placeholder': ''},

    {'name': 'Workstation Readiness', 'kind': 'percent', 'unit': '%',
     'a_label': 'Ready workstations', 'a_placeholder': 'e.g. 182',
     'b_label': 'Total workstations', 'b_placeholder': 'e.g. 200'},

    {'name': 'AI Copilot Adoption', 'kind': 'percent', 'unit': '%',
     'a_label': 'Employees using AI tools', 'a_placeholder': 'e.g. 240',
     'b_label': 'Eligible employees',       'b_placeholder': 'e.g. 500'},

    {'name': 'Security Incidents', 'kind': 'count', 'unit': '',
     'a_label': 'Major incidents this period', 'a_placeholder': 'e.g. 0',
     'b_label': '', 'b_placeholder': '',
     'sub_a_label': 'Employees completed security training',
     'sub_b_label': 'Total employees'},
]

# Merge in target/direction/target_display/formula from the master KPI list so
# the modal has everything it needs in one structure.
_MODAL_KPIS = [
    {**m, **{k: src[k] for k in ('target', 'direction', 'target_display', 'formula')}}
    for m in _MODAL_KPIS
    for src in _NEXZYS_KPIS if src['name'] == m['name']
]


def _attainment(kpi):
    """Normalized % of target reached (100 = on target), direction-aware.

    Returned unrounded — status is bucketed off the exact value so a near-miss
    like 99.96% uptime against a 99.99% target doesn't round its way to
    "On Track".
    """
    target, actual = kpi['target'], kpi['actual']
    if kpi['direction'] == 'down':
        # Zero-tolerance KPIs (target 0, e.g. major incidents): hit or miss.
        if target == 0:
            return 100.0 if actual == 0 else 0.0
        # Nothing is better than "none" for a lower-is-better KPI.
        if not actual:
            return 100.0
        return target / actual * 100
    if not target or not actual:
        return 0.0
    return actual / target * 100


def _shown(attainment):
    """Attainment rounded for display, never rounding a miss up to 100%."""
    value = round(attainment, 1)
    if attainment < 100 <= value:
        return 99.9
    return value


def _status(attainment):
    """Bucket an attainment % into a status key used for color/label."""
    if attainment >= 100:
        return 'on_track'
    if attainment >= 90:
        return 'at_risk'
    return 'below'


_STATUS_LABEL = {'on_track': 'On Track', 'at_risk': 'At Risk', 'below': 'Below Target'}


def _nexzys_kpis():
    """Return the KPI rows enriched with attainment + status (placeholder)."""
    rows = []
    for kpi in _NEXZYS_KPIS:
        attainment = _attainment(kpi)
        status = _status(attainment)
        rows.append({
            **kpi,
            'attainment': _shown(attainment),
            # Progress-bar fill width, capped at 100 so overachievers show a
            # full bar (the % label still shows the true value, e.g. 130.0%).
            # Floored below target so a near-miss never draws as a full bar.
            'bar_pct': min(int(attainment), 100),
            'status': status,
            'status_label': _STATUS_LABEL[status],
        })
    return rows


@login_required
@team_required('nexzys')
def index(request):
    """Nexzys — team dashboard (KPI scorecard: actual vs target + status)."""
    kpis = _nexzys_kpis()
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
    return render(request, 'nexzys/dashboard.html', context)


@login_required
@team_required('nexzys')
def kpi_reference(request):
    """Nexzys — KPI definitions reference (targets, cadence, formulas, inputs)."""
    context = {
        'banner_icons': BANNER_ICONS,
        'lob_name': 'Nexzys',
        'kpis': _NEXZYS_KPIS,
        'kpi_count': len(_NEXZYS_KPIS),
    }
    return render(request, 'nexzys/kpi_definitions.html', context)


@login_required
@team_required('nexzys')
def import_data(request):
    """Nexzys — Import Data screen (static mockup for now)."""
    return render(request, 'nexzys/import_data.html', {'modal_kpis': _MODAL_KPIS})


# How each KPI's direction reads on the management screen.
_DIRECTION_LABEL = {'up': 'Higher is better', 'down': 'Lower is better'}

# Picklists for the edit modal. Derived from the KPI list so a new category or
# cadence shows up in the dropdowns without touching the template.
_FREQUENCIES = ['Daily', 'Weekly', 'Monthly', 'Quarterly', 'Annually']


@login_required
@team_required('nexzys')
def kpi_management(request):
    """Nexzys — KPI Management: edit targets/thresholds, formulas, cadence.

    Static like the rest of the KPI screens: the table and edit modals render
    from ``_NEXZYS_KPIS`` and Save is not wired to anything yet. Swapping in a
    KPI model later means changing this query only.
    """
    rows = [
        {**kpi, 'direction_label': _DIRECTION_LABEL[kpi['direction']]}
        for kpi in _NEXZYS_KPIS
    ]
    categories = sorted({kpi['category'] for kpi in _NEXZYS_KPIS})

    return render(request, 'nexzys/kpi_management.html', {
        'kpis': rows,
        'kpi_count': len(rows),
        'categories': categories,
        # Union so any cadence already in use is selectable even if it's not
        # one of the standard five.
        'frequencies': sorted({*_FREQUENCIES, *(k['frequency'] for k in _NEXZYS_KPIS)}),
    })
