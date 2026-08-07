"""Reading the audit log: who may see a row, and how a row reads.

`apps/core/audit.py` writes `audit_log`; this reads it. The two screens that
show activity (the Logs page and the Activity tab in Settings) both come
through here, so a row cannot describe itself one way in one place and another
way in the other.

Three jobs:

  * `visible_to(user)` — the access rule, matching `apps/core/access.py`.
  * `describe(entry)`  — one readable sentence from `old_values`/`new_values`.
  * `row(entry)`       — the display dict the templates loop over.

The log stores WHAT CHANGED as two JSON blobs rather than a prose message, so
the sentence is rendered here rather than frozen at write time. That is the
same reasoning as `formula_text`: store the data, render the words.
"""

from django.db.models import Q

from .access import accessible_teams
from .models import AuditLog

# An action that rewrites how existing data reads is worth a second look, so it
# is not shown in the same colour as an ordinary create. Nothing writes a
# `failed` row except a failed sign-in.
_WARNING_ACTIONS = {
    AuditLog.Action.DELETED,
    AuditLog.Action.TARGET_CHANGED,
    AuditLog.Action.FORMULA_CHANGED,
}
_FAILED_ACTIONS = {AuditLog.Action.LOGIN_FAILED}

# Actions that are not about a team's data, so the Module column names the area
# rather than a team that would always be blank.
_SYSTEM_MODULES = {
    AuditLog.Action.LOGIN: 'Authentication',
    AuditLog.Action.LOGOUT: 'Authentication',
    AuditLog.Action.LOGIN_FAILED: 'Authentication',
}

_ENTITY_MODULES = {
    'user': 'Access Control',
    'user_profile': 'Access Control',
    'session': 'Authentication',
}

# How an entity type reads in a sentence.
_ENTITY_LABEL = {
    'kpi_definition': 'KPI',
    'kpi_record': 'record',
    'kpi_import_batch': 'import',
    'kpi_category': 'category',
    'kpi_branch': 'branch',
    'user': 'user',
}

# Fields whose before/after is noise in a one-line summary:
#   expression / formula_text / inputs — long, and the Action column plus the
#     KPI name already say a formula moved; the detail lives on the KPI screen.
#   slug / kpi — restate the entity the line already names.
#   is_active — "Deleted" is the Action; "is active True → False" repeats it.
_QUIET_FIELDS = {
    'expression', 'formula_text', 'inputs', 'slug', 'kpi', 'is_active',
}


# Module names that are NOT teams. The Module filter has to know the difference:
# a team name filters on `team`, one of these filters on `action`.
SYSTEM_MODULE_NAMES = sorted({*_SYSTEM_MODULES.values(), *_ENTITY_MODULES.values(), 'System'})


def actions_for_modules(names):
    """The actions that produce these system modules, for the Module filter."""
    wanted = set(names)
    return [action for action, name in _SYSTEM_MODULES.items() if name in wanted]


def sees_everything(user):
    """True for a superuser or an admin/superadmin role.

    Same test `accessible_teams` makes, named so the log can say whose view
    this is without re-deriving the rule at each call site.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return profile is not None and profile.sees_all_teams


def module_options(user, chosen):
    """Module checkboxes: the teams this user can see, plus the system areas.

    Offering a team whose entries would all be filtered out anyway is a filter
    that silently returns nothing, which reads as a bug.
    """
    names = list(accessible_teams(user).values_list('name', flat=True))
    return [
        {'value': name, 'label': name, 'checked': name in chosen}
        for name in [*sorted(names), *SYSTEM_MODULE_NAMES]
    ]


def visible_to(user):
    """The audit entries this user is allowed to read.

    Same rule as `access.accessible_teams`, with two additions that only make
    sense for a log: an entry with no team (a sign-in, a role change) is
    system-wide and belongs to whoever can see every team, and everyone can
    always see their OWN entries whatever team they touched.
    """
    entries = AuditLog.objects.select_related('user', 'team', 'user__profile')

    if not user.is_authenticated:
        return entries.none()

    if sees_everything(user):
        return entries

    return entries.filter(
        Q(team__in=accessible_teams(user)) | Q(user=user)
    ).distinct()


def module(entry):
    """The area of the app an entry belongs to, for the Module column."""
    if entry.action in _SYSTEM_MODULES:
        return _SYSTEM_MODULES[entry.action]
    if entry.team_id:
        return entry.team.name
    return _ENTITY_MODULES.get(entry.entity_type, 'System')


def status(entry):
    """`success` / `warning` / `failed`, driven by what actually happened.

    An import that rejected rows is a warning even though the import itself
    succeeded, because "imported" on its own would hide the rejected rows.
    """
    if entry.action in _FAILED_ACTIONS:
        return 'failed'
    if entry.action in _WARNING_ACTIONS:
        return 'warning'
    if entry.action == AuditLog.Action.IMPORTED and (entry.new_values or {}).get('errors'):
        return 'warning'
    return 'success'


def _changes(entry, name=''):
    """`field: before → after` for each field that actually moved.

    `name` is the entity name the caller has already put at the front of the
    line, so a field that merely restates it ("Temp Probe: name Temp Probe") is
    dropped rather than said twice.
    """
    old = entry.old_values or {}
    new = entry.new_values or {}
    parts = []
    for field in new:
        if field in _QUIET_FIELDS:
            continue
        before, after = old.get(field), new[field]
        if field not in old and str(after) == name:
            continue
        label = field.replace('_', ' ')
        if field in old and before != after:
            parts.append(f'{label} {before} → {after}')
        else:
            parts.append(f'{label} {after}')
    return parts


def _short_name(entry):
    """`entity_name` without the team prefix its `__str__` puts on the front.

    `KpiDefinition.__str__` is "Human Resources · Monthly Attrition", which is
    correct in the admin and redundant here: the Module column already said
    Human Resources.
    """
    name = entry.entity_name or _ENTITY_LABEL.get(entry.entity_type, 'record')
    if entry.team_id and name.startswith(f'{entry.team.name} · '):
        return name[len(entry.team.name) + 3:]
    return name


def describe(entry):
    """One line saying what happened, built from the stored values."""
    name = _short_name(entry)

    if entry.action in (AuditLog.Action.LOGIN, AuditLog.Action.LOGOUT):
        return 'Session started' if entry.action == AuditLog.Action.LOGIN else 'Session ended'
    if entry.action == AuditLog.Action.LOGIN_FAILED:
        return f'Incorrect credentials for "{entry.entity_name}"' if entry.entity_name else 'Incorrect credentials'

    if entry.action == AuditLog.Action.IMPORTED:
        values = entry.new_values or {}
        summary = (
            f'{values.get("file_name", name)}: '
            f'{values.get("created", 0)} created, {values.get("updated", 0)} updated'
        )
        errors = values.get('errors')
        return f'{summary}, {errors} rejected' if errors else summary

    if entry.action == AuditLog.Action.DELETED:
        # The Action column carries the verb; repeating the flag adds nothing.
        return name

    changes = _changes(entry, name)
    # Past three fields the line stops being a summary and starts being a dump.
    if changes:
        shown = ', '.join(changes[:3])
        extra = len(changes) - 3
        return f'{name}: {shown}' + (f' and {extra} more' if extra > 0 else '')
    return name


def role_of(entry):
    """The actor's role at read time, or a note that there was no actor."""
    if entry.user_id is None:
        return 'System'
    profile = getattr(entry.user, 'profile', None)
    return profile.get_role_display() if profile else 'No role'


def row(entry):
    """One entry as both templates want it."""
    return {
        'timestamp': entry.created_at,
        'user': entry.user.get_username() if entry.user_id else 'System',
        'role': role_of(entry),
        'action': entry.get_action_display(),
        'module': module(entry),
        'details': describe(entry),
        'status': status(entry),
        'ip': entry.ip_address or '',
    }


def rows(entries):
    return [row(entry) for entry in entries]
