"""Role-based access helpers for LOB / team screens.

Central place for the access rule so views, the sidebar context processor,
and any future logic all agree:

  * Super Admin / Admin  → every team
  * Manager              → the teams assigned to them (may be several)
  * User                 → their single assigned team

Everyone (any authenticated user) always has the shared Dashboard.
"""
from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import Team


def accessible_teams(user):
    """Return a queryset of Teams the given user may access.

    Superusers and users with the Super Admin / Admin role see all teams.
    Everyone else sees only the teams on their profile. Anonymous or
    profile-less users see none.
    """
    if not user.is_authenticated:
        return Team.objects.none()

    # Django superuser flag is an escape hatch that always sees everything.
    if user.is_superuser:
        return Team.objects.all()

    profile = getattr(user, 'profile', None)
    if profile is None:
        return Team.objects.none()

    if profile.sees_all_teams:
        return Team.objects.all()

    return profile.teams.all()


def can_access_team(user, slug):
    """True if ``user`` may access the team identified by ``slug``."""
    return accessible_teams(user).filter(slug=slug).exists()


def team_required(slug):
    """Decorator guarding an LOB view to users who may access ``slug``.

    Assumes the view is already ``@login_required`` (unauthenticated users
    are redirected to login before this runs). Raises ``PermissionDenied``
    (403) for authenticated users who lack access to the team.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not can_access_team(request.user, slug):
                raise PermissionDenied(
                    "You don't have access to this team."
                )
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
