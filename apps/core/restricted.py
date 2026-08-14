"""Departments that most roles do not open, and the roles that do.

Finance and Human Resources carry payroll and personnel figures, so they are
not reachable by seniority alone: an Admin sits above a Manager and still has
no business in payroll. Two questions decide them, and they are asked in this
order:

  1. Is this person a Super Admin? They answer for the whole system, so they
     reach both restricted departments.
  2. Otherwise, does their role name one of these departments? The **Finance**
     role reaches Finance, the **HR** role reaches Human Resources, and neither
     reaches the other one. That is what makes them two roles rather than one.

Everybody else, an Admin and a Viewer included, does not reach either.

**This is a filter on top of the role rules, never a replacement for them.**
`access.accessible_teams()` works out what the role reaches and then removes
the restricted departments this person does not hold, which is why an Admin
reaches every other department and not these two.

Because it narrows `accessible_teams()`, one edit covers every screen at once:
the sidebar, `team_required`, the dashboard's global department filter, the
search palette and the activity log's Module filter all ask that one function.

This replaced a named-person allowlist read out of `restricted_teams.json`,
which meant reaching payroll was an edit to a config file rather than a role
somebody holds. Two people were hard-coded into it. Don't reintroduce it: who
may open Finance is now answered the same way every other access question is.
"""
from .models import UserProfile

# Team slug → the ONE role that opens it, besides Super Admin. Adding a third
# restricted department means a row here and a role on `UserProfile.Role`.
RESTRICTED_TEAMS = {
    'finance': UserProfile.Role.FINANCE,
    'hr': UserProfile.Role.HR,
}


def restricted_slugs():
    """The team slugs a role alone does not open, as a frozenset."""
    return frozenset(RESTRICTED_TEAMS)


def _role_of(user):
    """The user's profile role, or None when there is no profile."""
    profile = getattr(user, 'profile', None)
    return profile.role if profile is not None else None


def reachable_slugs_for(user):
    """The restricted team slugs ``user`` MAY reach."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return frozenset()

    # `is_superuser` is honoured here, unlike in the allowlist this replaced.
    # It is the escape hatch that lets a locked out administrator run the
    # system, and a Super Admin is exactly who these departments are open to.
    if getattr(user, 'is_superuser', False):
        return restricted_slugs()

    role = _role_of(user)
    if role == UserProfile.Role.SUPERADMIN:
        return restricted_slugs()
    return frozenset(
        slug for slug, allowed in RESTRICTED_TEAMS.items() if role == allowed
    )


def hidden_slugs_for(user):
    """The restricted team slugs ``user`` may NOT reach.

    Empty for a Super Admin, and the other department for somebody holding the
    Finance or HR role. Everyone else gets both.
    """
    return restricted_slugs() - reachable_slugs_for(user)
