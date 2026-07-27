from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required


@login_required
@team_required('academy')
def index(request):
    """VINTAZK Academy line-of-business screen."""
    return render(request, 'academy/index.html', {'lob_name': 'VINTAZK Academy'})
