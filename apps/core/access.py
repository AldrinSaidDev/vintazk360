"""Role-based access helpers for LOB / team screens.

Central place for the access rule so views, the sidebar context processor,
and any future logic all agree. There are TWO questions, and they are asked
separately because the answers cross (see Part C of ``db_schema.txt``):

*Which teams may I reach?* — ``accessible_teams()`` / ``team_required()``

  * Super Admin  → every team
  * Admin        → every team
  * Viewer       → every team
  * Manager      → the teams assigned to them
  * User         → their assigned team (normally one)

*May I change anything there?* — ``can_edit_data()`` / ``edit_required()``

  * Super Admin / Admin / Manager → yes
  * User / Viewer                 → no, read only

Reaching a team is not permission to write in it, and a Viewer proves why:
they read every dashboard in the org and may not touch a single figure.

Everyone (any authenticated user) always has the shared Dashboard.
"""
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from .models import Team, UserProfile


def accessible_teams(user):
    """Return a queryset of Teams the given user may access.

    Superusers and users with the Super Admin, Admin or Viewer role reach all
    teams. Everyone else reaches only the teams on their profile. Anonymous or
    profile-less users reach none.
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


def can_edit_data(user):
    """True if this user's ROLE may change KPI data.

    Says nothing about which team: a write needs this AND team access, which
    is why ``can_edit_team()`` asks both rather than either being enough.
    """
    if not user.is_authenticated:
        return False

    # The Django superuser flag is the same escape hatch it is for team reach.
    if user.is_superuser:
        return True

    profile = getattr(user, 'profile', None)
    return profile is not None and profile.can_edit_data


def can_edit_team(user, slug):
    """True if ``user`` may change data in the team identified by ``slug``."""
    return can_edit_data(user) and can_access_team(user, slug)


def require_edit(user, slug):
    """Raise ``PermissionDenied`` unless ``user`` may write in ``slug``.

    Called at the top of a POST handler rather than wrapped around the view,
    because the KPI screens serve their read and their write from one view:
    a Viewer must still get the page, just not be able to submit from it.
    """
    if not can_edit_team(user, slug):
        raise PermissionDenied(
            "Your role is read only. You can view this team's KPIs but not "
            "change them."
        )


def edit_required(view_func):
    """Decorator refusing a whole SCREEN to a read-only role.

    Different question from ``require_edit()``, and both are needed. The four
    KPI screens serve their read and their write from one view, so Dashboard
    and KPI Definitions must still render for a User or a Viewer and only their
    POSTs are refused. **Import Data and KPI Management are not like that**:
    every reason to open one is a reason to write. Import Data is a data-entry
    console and KPI Management is where formulas and targets are authored, so a
    read-only role is refused the page itself rather than shown one with every
    control stripped out of it.

    Only the ROLE is asked here, because the team was already established by
    ``team_required()``, which every screen is wrapped in as well.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not can_edit_data(request.user):
            raise PermissionDenied(
                'Your role is read only, so this screen is not available to '
                "you. The team's dashboard and its KPI definitions are."
            )
        return view_func(request, *args, **kwargs)

    return _wrapped


def is_admin(user):
    """True for the roles that administer the system itself.

    Not the same as ``can_edit_data``: a Manager writes their team's KPI data
    but does not manage users, presets or system settings.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return profile is not None and profile.is_admin


def manageable_users(actor):
    """The accounts ``actor`` may see and administer on the Users screen.

    Administration is org-wide, so a Super Admin and an Admin both reach every
    account. Anyone else reaches none: this screen is administration, not data
    entry, so ``is_admin`` gates it rather than ``can_edit_data``.
    """
    User = get_user_model()
    users = User.objects.select_related('profile').prefetch_related('profile__teams')

    if not is_admin(actor):
        return users.none()
    return users


def can_manage_user(actor, target):
    """True if ``actor`` may administer ``target``'s account."""
    return manageable_users(actor).filter(pk=target.pk).exists()


def assignable_roles(actor):
    """The roles ``actor`` may hand out, as ``(value, label)`` pairs.

    An administrator's reach is the whole organisation, so there is no role
    here that would grant more than the granter already holds. Anyone who is
    not an administrator never reaches this screen at all.
    """
    if not is_admin(actor):
        return []
    return list(UserProfile.Role.choices)


def assignable_teams(actor):
    """The teams ``actor`` may assign, which are the teams they can reach."""
    return accessible_teams(actor)


def require_admin(user, message='Only administrators can open this screen.'):
    """Raise ``PermissionDenied`` unless ``user`` administers the system.

    The activity log is administration, not team data: it carries sign-ins,
    failed sign-ins and role changes alongside KPI edits, which is why reaching
    a team's figures was never enough to read it. A Manager writes their team's
    data and administers nothing, so they are refused it too.
    """
    if not is_admin(user):
        raise PermissionDenied(message)


def require_user_admin(user):
    """Raise ``PermissionDenied`` unless ``user`` may administer accounts."""
    require_admin(user, 'Only administrators can manage user accounts.')


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
