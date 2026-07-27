from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required


@login_required
@team_required('finance')
def index(request):
    """Finance line-of-business screen."""
    return render(request, 'finance/index.html', {'lob_name': 'Finance'})
