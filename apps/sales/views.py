from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required


@login_required
@team_required('sales')
def index(request):
    """Sales line-of-business screen."""
    return render(request, 'sales/index.html', {'lob_name': 'Sales'})
