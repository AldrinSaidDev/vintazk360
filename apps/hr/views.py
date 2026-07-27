from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required


@login_required
@team_required('hr')
def index(request):
    """Human Resources line-of-business screen."""
    return render(request, 'hr/index.html', {'lob_name': 'Human Resources'})
