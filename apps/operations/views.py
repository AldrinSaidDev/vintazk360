from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Operations — team dashboard (KPI scorecard: actual vs target + status)."""
    return render(request, 'operations/dashboard.html')


@login_required
def kpi_reference(request):
    """Operations — KPI definitions reference (North Star + formulas/targets)."""
    return render(request, 'operations/index.html', {'lob_name': 'Operations'})


@login_required
def import_data(request):
    """Operations — Import Data screen (static mockup for now)."""
    return render(request, 'operations/import_data.html')
