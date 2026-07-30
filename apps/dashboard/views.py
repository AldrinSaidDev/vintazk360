from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

# settings.TIME_ZONE is UTC, but the org runs on Philippine time and the welcome
# header states today's date — under UTC it would show yesterday for the whole
# Manila morning. Resolved here rather than by changing the project-wide zone.
SITE_TZ = ZoneInfo('Asia/Manila')


@login_required
def home(request):
    """Landing page for the dashboard (requires authentication)."""
    # Welcome header. First name when we have one; the employee ID (username)
    # is the fallback, since that's what people log in with.
    user = request.user
    display_name = user.first_name or user.get_username()
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
        'display_name': display_name,
        'today': datetime.now(SITE_TZ).date(),
        'goal_target': goal_target,
        'goal_completed': goal_completed,
        'goal_remaining': goal_remaining,
        'goal_progress': goal_progress,
    })
