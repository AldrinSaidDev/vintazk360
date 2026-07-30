from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core import kpi
from apps.core.access import team_required

from .kpis import CHANNELS, KPIS, MODAL_SPECS, SCOPE

# All four screens render the shared templates under templates/kpi/ — the only
# per-LOB parts are the KPI list and the modal input labels in kpis.py.


@login_required
@team_required('content')
def index(request):
    """Content Writing — team dashboard (KPI scorecard: actual vs target + status)."""
    return render(request, 'kpi/dashboard.html', kpi.dashboard_context(SCOPE, KPIS))


@login_required
@team_required('content')
def kpi_reference(request):
    """Content Writing — KPI definitions reference (targets, cadence, formulas, inputs)."""
    return render(request, 'kpi/kpi_definitions.html', kpi.definitions_context(SCOPE, KPIS))


@login_required
@team_required('content')
def import_data(request):
    """Content Writing — Import Data screen (static mockup for now)."""
    return render(request, 'kpi/import_data.html', kpi.import_context(
        SCOPE, KPIS, MODAL_SPECS, dimensions=CHANNELS, dimension_label='Channel'))


@login_required
@team_required('content')
def kpi_management(request):
    """Content Writing — KPI Management: edit targets/thresholds, formulas, cadence."""
    return render(request, 'kpi/kpi_management.html', kpi.management_context(SCOPE, KPIS))
