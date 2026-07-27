from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required


# --- PLACEHOLDER DATA -------------------------------------------------------
# Site Lead KPI definitions (reference). Static for now — no DB. When the KPI
# models exist, replace this list with a DB query returning the same shape;
# the template won't need to change.
_SITELEAD_KPIS = [
    {'name': 'Client Service Performance', 'category': 'Operational',
     'description': 'Whether all accounts are consistently delivering the quality and service promised to clients.',
     'formula': 'SLA commitments met ÷ Total SLA commitments due × 100',
     'target_display': '≥95% SLA attainment', 'frequency': 'Weekly & Monthly'},
    {'name': 'Operational Efficiency', 'category': 'Operational',
     'description': 'How effectively scheduled workforce hours are converted into productive, client-billable hours.',
     'formula': 'Actual approved billable hours ÷ Planned billable hours × 100',
     'target_display': '≥95%', 'frequency': 'Monthly'},
    {'name': 'Workforce Retention Rate', 'category': 'People',
     'description': "The site's ability to retain employees and maintain a stable workforce while supporting growth.",
     'formula': '(Employees at end − New hires) ÷ Employees at start × 100',
     'target_display': '96.5% monthly retention', 'frequency': 'Monthly'},
    {'name': 'Growth & Capacity Readiness', 'category': 'Operational',
     'description': 'Whether staffing, leadership, equipment, facilities, and systems are ready before hiring waves or account expansion.',
     'formula': 'Fully ready capacity ÷ Forecasted capacity requirement × 100',
     'target_display': '100% before hiring/launch', 'frequency': 'Quarterly'},
    {'name': 'Client Retention Rate', 'category': 'Client Impact',
     'description': "The site's ability to retain existing clients and protect recurring revenue.",
     'formula': '(Clients at end − New clients) ÷ Clients at start × 100',
     'target_display': '100%', 'frequency': 'Quarterly'},
    {'name': 'Revenue Target Attainment', 'category': 'Financial',
     'description': 'Whether the site achieves the revenue committed in the approved financial and operational plan.',
     'formula': 'Actual site revenue ÷ Budgeted site revenue × 100',
     'target_display': '≥98%', 'frequency': 'Monthly'},
    {'name': 'Operational Risk & BCP Compliance', 'category': 'Operational',
     'description': "The site's preparedness to prevent, respond to, and recover from operational disruptions, compliance risks, and critical incidents.",
     'formula': 'Passed risk, compliance & BCP requirements ÷ Total requirements due × 100',
     'target_display': '100% compliance', 'frequency': 'Quarterly'},
    {'name': 'Account Profitability', 'category': 'Financial',
     'description': 'Whether client accounts achieve or exceed the Finance-approved margin requirement.',
     'formula': 'Accounts meeting the approved margin floor ÷ Total active accounts × 100',
     'target_display': '100% (exceptions need exec approval)', 'frequency': 'Monthly & Quarterly'},
]


@login_required
@team_required('sitelead')
def index(request):
    """Site Lead — KPI definitions reference (North Star + formulas/targets)."""
    context = {
        'lob_name': 'Site Lead',
        'kpis': _SITELEAD_KPIS,
        'kpi_count': len(_SITELEAD_KPIS),
    }
    return render(request, 'sitelead/index.html', context)
