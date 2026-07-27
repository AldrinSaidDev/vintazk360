from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required


@login_required
@team_required('nexzys')
def index(request):
    """Nexzys Intelligence line-of-business screen."""
    return render(request, 'nexzys/index.html', {'lob_name': 'Nexzys Intelligence'})
