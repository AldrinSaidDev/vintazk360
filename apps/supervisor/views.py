from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Account Managers & Supervisors line-of-business screen."""
    return render(request, 'supervisor/index.html', {'lob_name': 'Account Managers & Supervisors'})
