from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """Landing page for the dashboard (requires authentication)."""
    # Static placeholder until KPI values are DB-backed. Drives the Overall Goal
    # track: the bar width, the mid label, and whether the goal marker reads as
    # reached (100) or still pending (< 100, rendered dimmed).
    goal_progress = 38

    return render(request, 'dashboard/home.html', {
        'title': 'Dashboard',
        'goal_progress': goal_progress,
    })
