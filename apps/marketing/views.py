from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import team_required


@login_required
@team_required('marketing')
def index(request):
    """Social Media & Marketing line-of-business screen."""
    return render(request, 'marketing/index.html', {'lob_name': 'Social Media & Marketing'})
