from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """Landing page for the dashboard (requires authentication)."""
    # Static placeholder until KPI values are DB-backed. Drives the Overall Goal
    # track: the bar width, the mid label, and whether the goal marker reads as
    # reached (100) or still pending (< 100, rendered dimmed) — plus the four
    # stats in the "Overall Goal Information" modal.
    #
    # Progress is DERIVED from the two counts so the track and the modal can't
    # drift apart: 190 of 500 = 38%.
    goal_target = 500
    goal_completed = 190
    goal_remaining = goal_target - goal_completed
    goal_progress = round(goal_completed / goal_target * 100)

    return render(request, 'dashboard/home.html', {
        'title': 'Dashboard',
        'goal_target': goal_target,
        'goal_completed': goal_completed,
        'goal_remaining': goal_remaining,
        'goal_progress': goal_progress,
    })
