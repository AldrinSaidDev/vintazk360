"""Role-based access helpers for LOB / team screens.

Central place for the access rule so views, the sidebar context processor,
and any future logic all agree. There are TWO questions, and they are asked
separately because the answers cross (see Part C of ``db_schema.txt``):

*Which teams may I reach?* — ``accessible_teams()`` / ``team_required()``

  * Super Admin  → every team
  * Viewer       → every team
  * Admin        → the teams assigned to them
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
from django.db.models import Q

from .models import Team, UserProfile


def accessible_teams(user):
    """Return a queryset of Teams the given user may access.

    Superusers and users with the Super Admin or Viewer role reach all teams.
    Everyone else reaches only the teams on their profile. Anonymous or
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


def is_superadmin(user):
    """True for the one role that administers the whole organisation.

    Separate from ``is_admin`` because the two differ exactly where user
    management is concerned: an Admin runs their own teams' accounts, a Super
    Admin runs everybody's. A Django superuser counts as one.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return profile is not None and profile.role == UserProfile.Role.SUPERADMIN


def manageable_users(actor):
    """The accounts ``actor`` may see and administer on the Users screen.

    Same two-axis rule the rest of the app follows, applied to people instead
    of KPIs. A Super Admin reaches every account. An Admin reaches only the
    accounts inside their own teams, which is the same reach they have over
    those teams' data, and an Admin with no teams therefore reaches nobody but
    themselves. Anyone else reaches none: this screen is administration, not
    data entry, so ``is_admin`` gates it rather than ``can_edit_data``.

    Two accounts an Admin never reaches: a Super Admin and a Viewer. Both are
    org-wide roles whose reach already exceeds the Admin's, so letting a
    team-scoped Admin edit one would hand out access they do not themselves
    have. Their own row is always included, so the screen never hides its
    reader from them.
    """
    User = get_user_model()
    users = User.objects.select_related('profile').prefetch_related('profile__teams')

    if not is_admin(actor):
        return users.none()
    if is_superadmin(actor):
        return users

    org_wide = Q(is_superuser=True) | Q(profile__role__in=list(UserProfile.ALL_TEAM_ROLES))
    within_teams = Q(profile__teams__in=accessible_teams(actor)) & ~org_wide
    return users.filter(within_teams | Q(pk=actor.pk)).distinct()


def can_manage_user(actor, target):
    """True if ``actor`` may administer ``target``'s account."""
    return manageable_users(actor).filter(pk=target.pk).exists()


def assignable_roles(actor):
    """The roles ``actor`` may hand out, as ``(value, label)`` pairs.

    Super Admin and Viewer both reach every team, so only a Super Admin may
    grant them. Without that rule a team-scoped Admin could create an account
    with more reach than their own, which is the plainest form of privilege
    escalation this screen could allow.
    """
    if is_superadmin(actor):
        return list(UserProfile.Role.choices)
    allowed = {UserProfile.Role.ADMIN, UserProfile.Role.MANAGER, UserProfile.Role.USER}
    return [choice for choice in UserProfile.Role.choices if choice[0] in allowed]


def assignable_teams(actor):
    """The teams ``actor`` may assign, which are the teams they can reach."""
    return accessible_teams(actor)


def require_user_admin(user):
    """Raise ``PermissionDenied`` unless ``user`` may administer accounts."""
    if not is_admin(user):
        raise PermissionDenied(
            'Only administrators can manage user accounts.'
        )


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
