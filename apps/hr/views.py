from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core import kpi
from apps.core.access import team_required

from .kpis import DEPARTMENTS, KPIS, MODAL_SPECS, SCOPE

# All four screens render the shared templates under templates/kpi/ — the only
# per-LOB parts are the KPI list and the modal input labels in kpis.py.


@login_required
@team_required('hr')
def index(request):
    """HR — team dashboard (KPI scorecard: actual vs target + status)."""
    return render(request, 'kpi/dashboard.html', kpi.dashboard_context(SCOPE, KPIS))


@login_required
@team_required('hr')
def kpi_reference(request):
    """HR — KPI definitions reference (targets, cadence, formulas, inputs)."""
    return render(request, 'kpi/kpi_definitions.html', kpi.definitions_context(SCOPE, KPIS))


@login_required
@team_required('hr')
def import_data(request):
    """HR — Import Data screen (static mockup for now)."""
    return render(request, 'kpi/import_data.html', kpi.import_context(
        SCOPE, KPIS, MODAL_SPECS, dimensions=DEPARTMENTS, dimension_label='Department'))


@login_required
@team_required('hr')
def kpi_management(request):
    """HR — KPI Management: edit targets/thresholds, formulas, cadence."""
    return render(request, 'kpi/kpi_management.html', kpi.management_context(SCOPE, KPIS))
