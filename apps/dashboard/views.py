from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """Landing page for the dashboard (requires authentication)."""
    return render(request, 'dashboard/home.html', {'title': 'Dashboard'})
