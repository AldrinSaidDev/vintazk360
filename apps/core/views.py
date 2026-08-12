"""Shared, non-LOB screens: the activity log, account settings, and users."""

import datetime as dt

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import activity, async_content, audit
from .access import (
    accessible_teams,
    assignable_roles,
    assignable_teams,
    is_superadmin,
    manageable_users,
    require_user_admin,
)
from .forms import AdminPasswordForm, CreateUserForm, EditUserForm
from .models import AuditLog, UserProfile

# Rows per page on the Logs table.
PAGE_SIZE = 20

# The table's own id, so a pager link lands on the table rather than the top of
# the page. See the note on `anchor` in partials/pagination.html.
_TABLE_ANCHOR = 'activity-log'


def _link_params(request):
    """``request.GET`` with the two-stage render flag taken out.

    These screens render in two stages, so on the fetch that builds the content
    ``request.GET`` carries ``partial=1``. Anything that rebuilds a URL from it
    would hand that flag to a link the user clicks, and clicking it returns the
    bare fragment: no sidebar, no header. Every link and redirect below starts
    here. (Same trap as the KPI screens; see the note in CLAUDE.md.)
    """
    params = request.GET.copy()
    params.pop(async_content.PARTIAL_PARAM, None)
    return params


def _query_without_page(request, key='page'):
    params = _link_params(request)
    params.pop(key, None)
    return params.urlencode()


def _params_without_page(request, key='page'):
    return [
        {'key': name, 'value': value}
        for name, values in _link_params(request).lists()
        if name != key
        for value in values
        if value
    ]


@login_required
def logs(request):
    """The activity log, read from `audit_log`.

    Scoped by `activity.visible_to`: an admin sees everything, everyone else
    sees their teams' entries plus their own. Filters are plain GET, so a
    filtered view is a URL somebody can send to somebody else.

    Two-stage render (apps/core/async_content.py): the frame comes back at once
    and the entries arrive on the follow-up fetch. This page scans and paginates
    the whole audit table, and the filters make that cost vary a lot from one
    view to the next, which is exactly when a skeleton earns its place.
    """
    if async_content.wants_shell(request):
        return async_content.render_shell(
            request, shell_template='core/logs_shell.html',
        )

    entries = activity.visible_to(request.user)

    search = request.GET.get('q', '').strip()
    chosen_modules = [m for m in request.GET.getlist('module') if m]
    chosen_actions = [a for a in request.GET.getlist('action') if a]
    on_date = request.GET.get('date', '').strip()

    if search:
        entries = entries.filter(
            Q(user__username__icontains=search)
            | Q(entity_name__icontains=search)
            | Q(entity_type__icontains=search)
        )
    if chosen_actions:
        entries = entries.filter(action__in=chosen_actions)
    if chosen_modules:
        # "Authentication" and the other system modules are not teams, so the
        # module filter is two filters wearing one coat: team names match a
        # team, the rest match the actions that produce them.
        team_names = [m for m in chosen_modules if m not in activity.SYSTEM_MODULE_NAMES]
        system = [m for m in chosen_modules if m in activity.SYSTEM_MODULE_NAMES]
        condition = Q()
        if team_names:
            condition |= Q(team__name__in=team_names)
        if system:
            condition |= Q(action__in=activity.actions_for_modules(system))
        entries = entries.filter(condition)

    date_error = ''
    if on_date:
        try:
            # `__date` compares in the project timezone. Handing a plain date to
            # a DateTimeField would compare a naive value and slide entries
            # either side of midnight.
            entries = entries.filter(created_at__date=dt.date.fromisoformat(on_date))
        except ValueError:
            date_error = 'That date could not be read. Use the picker.'
            on_date = ''

    paginator = Paginator(entries, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    page_numbers = list(
        paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    )

    # Only the modules this user could actually see, so the filter never offers
    # a team whose entries would all be hidden anyway.
    modules = activity.module_options(request.user, chosen_modules)

    return async_content.render_content(request, 'core/logs.html', {
        'title': 'Logs',
        'entries': activity.rows(page.object_list),
        'entry_count': paginator.count,
        'page_obj': page,
        'page_numbers': page_numbers,
        'anchor': _TABLE_ANCHOR,
        'search': search,
        'date': on_date,
        'date_error': date_error,
        'module_options': modules,
        'action_options': [
            {'value': value, 'label': label, 'checked': value in chosen_actions}
            for value, label in AuditLog.Action.choices
        ],
        'active_filter_count': (
            len(chosen_modules) + len(chosen_actions) + (1 if on_date else 0)
        ),
        'has_any_filter': bool(search or chosen_modules or chosen_actions or on_date),
        'clear_url': reverse('core:logs'),
        'page_query': _query_without_page(request),
        'page_params': _params_without_page(request),
        # Says whose log this is, since a manager and an admin see the same page
        # with very different contents.
        'is_scoped': not activity.sees_whole_log(request.user),
        'scoped_teams': (
            accessible_teams(request.user)
            if not activity.sees_whole_log(request.user)
            else None
        ),
    })


# Settings tabs. Server-rendered via ?tab= rather than JS/CSS toggling, so the
# active tab survives a reload and the password POST can land back on its own tab.
_SETTINGS_TABS = ('profile', 'account', 'activity')

# Shared input styling — applied to the password form's widgets so Django's
# rendered fields match the hand-written inputs elsewhere in the app.
_INPUT_CLASSES = (
    'w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm '
    'focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20'
)

# Entries shown on the Activity tab. It is a recent-history panel, not the log.
MY_ACTIVITY_LIMIT = 20


@login_required
def account_settings(request):
    """Account settings: profile details, password change, and own activity.

    The password form is Django's ``PasswordChangeForm`` and really changes the
    password; the Activity tab is this account's own slice of `audit_log`.

    Two-stage render, same as the other screens. The shell has to carry the tab
    through: the fetch URL is rebuilt from request.GET, so ?tab=account lands
    back on the tab the user asked for rather than resetting to Profile.
    """
    if async_content.wants_shell(request):
        return async_content.render_shell(
            request, shell_template='core/settings_shell.html',
        )

    tab = request.GET.get('tab', 'profile')
    if tab not in _SETTINGS_TABS:
        tab = 'profile'

    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        tab = 'account'  # a failed submit must come back to the form it came from
        if form.is_valid():
            form.save()
            # Changing the password rotates the session hash — without this the
            # user is logged straight out after a successful change.
            update_session_auth_hash(request, form.user)
            messages.success(request, 'Your password has been updated.')
            return redirect(f"{reverse('core:settings')}?tab=account")
    else:
        form = PasswordChangeForm(user=request.user)

    for field in form.fields.values():
        field.widget.attrs['class'] = _INPUT_CLASSES

    profile = getattr(request.user, 'profile', None)

    return async_content.render_content(request, 'core/settings.html', {
        'title': 'Settings',
        'tab': tab,
        'form': form,
        'profile': profile,
        'teams': profile.teams.all() if profile else [],
        # This account's own entries, newest first. `visible_to` is not needed:
        # your own actions are yours to read.
        'my_entries': activity.rows(
            AuditLog.objects.filter(user=request.user)
            .select_related('user', 'team', 'user__profile')[:MY_ACTIVITY_LIMIT]
        ),
        'my_activity_limit': MY_ACTIVITY_LIMIT,
        'logs_url': reverse('core:logs'),
    })


@login_required
@require_POST
def tour_seen(request):
    """Mark the guided tour as done for this account.

    Posted once, when the user finishes the last step or skips out. It only
    ever clears the flag: replaying the tour from the help button leaves it
    alone, so nothing a user does by choice can put them back into the
    automatic first-run path.

    A profile-less account (a bare superuser created before the signal) has
    nothing to record, and that is not an error worth showing anyone.
    """
    profile = getattr(request.user, 'profile', None)
    if profile is not None and profile.is_new_user:
        profile.is_new_user = False
        profile.save(update_fields=['is_new_user'])
    return JsonResponse({'ok': True})


# --- Users ------------------------------------------------------------------
#
# Account administration for Super Admins and Admins. Who appears here, whose
# role may be handed out, and which teams may be assigned are all decided in
# `apps/core/access.py`, so this view never re-derives an access rule.

USERS_PAGE_SIZE = 20

# The table's own id, so a pager link and a successful save both land on the
# table rather than the top of the page. It also gives every redirect below a
# fragment of its own, which is what stops the browser reattaching the
# #userEdit-<pk> one and reopening the modal on a saved form (RFC 7231 §7.1.2).
_USERS_ANCHOR = 'user-accounts'

_STATUS_OPTIONS = [('active', 'Active'), ('inactive', 'Deactivated')]


def _posted_pk(value):
    """A pk posted by a modal, or 0 for anything that is not one.

    A hand-made POST carrying '' or 'abc' would reach the lookup as a
    ValueError, which is a 500 where a 404 belongs. 0 never matches a row.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _back_to_users(request):
    """The Users URL a redirect should land on, filters and page intact."""
    query = _link_params(request).urlencode()
    url = reverse('core:users')
    return f'{url}?{query}#{_USERS_ANCHOR}' if query else f'{url}#{_USERS_ANCHOR}'


def _snapshot(user):
    """What an account looks like right now, for the audit trail.

    The profile is re-read rather than taken off ``user.profile``: the form
    saves through its own instance, so the one cached on the user object is the
    state from before the edit and the "after" snapshot would match the
    "before" one.
    """
    profile = UserProfile.objects.filter(user=user).first()
    return {
        'employee_id': user.get_username(),
        'name': user.get_full_name() or '(not set)',
        'email': user.email or '(not set)',
        'role': profile.get_role_display() if profile else '(no profile)',
        'teams': ', '.join(t.name for t in profile.teams.all()) if profile else '',
        'status': 'active' if user.is_active else 'deactivated',
    }


def _changed(before, after):
    """Only the fields that actually moved, as (old, new).

    Logging the whole snapshot on every edit would make the Details column read
    the same whether one field changed or six.
    """
    moved = [key for key, value in after.items() if before.get(key) != value]
    return (
        {key: before[key] for key in moved},
        {key: after[key] for key in moved},
    )


def _log_user(request, action, target, old_values=None, new_values=None):
    """One audit entry about an account.

    `team` is deliberately None: an account is not a team's data, so it belongs
    to the system's own trail and is read by whoever administers it. That is
    the same rule sign-ins follow, and `activity` already files entity_type
    'user' under the Access Control module.
    """
    audit.log_action(
        request,
        action=action,
        entity_type='user',
        entity_id=target.pk,
        entity_name=target.get_username(),
        old_values=old_values,
        new_values=new_values,
    )


@login_required
def users(request):
    """User Profiles: every account this administrator may see and change.

    One view, four modals, same shape as KPI Management: each form posts an
    `_action` (create / edit / password / deactivate / activate) plus the pk it
    is about, and a failed one re-renders the page with its own modal forced
    back open. Read and write share the view, so every write branch re-checks
    permission rather than trusting that the button was rendered.
    """
    require_user_admin(request.user)

    people = manageable_users(request.user)

    create_form = None
    open_create = False
    bound_edit = {}
    open_edit_pk = None
    bound_password = {}
    open_password_pk = None

    if request.method == 'POST':
        action = request.POST.get('_action', '')

        if action == 'create':
            form = CreateUserForm(request.POST, actor=request.user)
            if form.is_valid():
                created = form.save()
                _log_user(request, AuditLog.Action.CREATED, created,
                          new_values=_snapshot(created))
                messages.success(
                    request,
                    f'Account {created.get_username()} created. '
                    'Share the password with them and ask them to change it in Settings.',
                )
                return redirect(_back_to_users(request))
            create_form, open_create = form, True

        elif action in ('edit', 'password', 'deactivate', 'activate'):
            # Scoped to what this administrator may manage, so a guessed pk
            # from outside their teams is a 404 rather than an edit.
            target = get_object_or_404(people, pk=_posted_pk(request.POST.get('_pk')))

            if action == 'edit':
                before = _snapshot(target)
                form = EditUserForm(request.POST, actor=request.user, target=target)
                if form.is_valid():
                    form.save()
                    target.refresh_from_db()
                    old, new = _changed(before, _snapshot(target))
                    if new:
                        _log_user(request, AuditLog.Action.UPDATED, target,
                                  old_values=old, new_values=new)
                        messages.success(request, f'{target.get_username()} updated.')
                    else:
                        messages.info(request, 'Nothing changed.')
                    return redirect(_back_to_users(request))
                bound_edit[target.pk], open_edit_pk = form, target.pk

            elif action == 'password':
                if target.pk == request.user.pk:
                    # Your own password lives in Settings, where changing it
                    # keeps you signed in. Doing it here would log you out.
                    messages.error(
                        request,
                        'Change your own password in Settings, under Account Settings.',
                    )
                    return redirect(_back_to_users(request))
                form = AdminPasswordForm(request.POST, target=target)
                if form.is_valid():
                    form.save()
                    _log_user(request, AuditLog.Action.UPDATED, target,
                              new_values={'password': 'reset by an administrator'})
                    messages.success(
                        request,
                        f"Password set for {target.get_username()}. "
                        'They are signed out of any open sessions the next time they load a page.',
                    )
                    return redirect(_back_to_users(request))
                bound_password[target.pk], open_password_pk = form, target.pk

            else:
                activating = action == 'activate'
                if not activating and target.pk == request.user.pk:
                    # Nobody locks themselves out of the screen that would let
                    # them back in.
                    messages.error(request, 'You cannot deactivate your own account.')
                    return redirect(_back_to_users(request))
                if target.is_active != activating:
                    target.is_active = activating
                    target.save(update_fields=['is_active'])
                    _log_user(
                        request, AuditLog.Action.UPDATED, target,
                        old_values={'status': 'deactivated' if activating else 'active'},
                        new_values={'status': 'active' if activating else 'deactivated'},
                    )
                    messages.success(request, (
                        f'{target.get_username()} can sign in again.' if activating
                        else f'{target.get_username()} has been deactivated and can no longer sign in.'
                    ))
                return redirect(_back_to_users(request))

    elif async_content.wants_shell(request):
        return async_content.render_shell(
            request, shell_template='core/users_shell.html',
        )

    # --- the list ---------------------------------------------------------
    search = request.GET.get('q', '').strip()
    chosen_roles = [r for r in request.GET.getlist('role') if r]
    chosen_teams = [t for t in request.GET.getlist('team') if t]
    chosen_status = [s for s in request.GET.getlist('status') if s]

    listing = people
    if search:
        listing = listing.filter(
            Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
        )
    if chosen_roles:
        listing = listing.filter(profile__role__in=chosen_roles)
    if chosen_teams:
        listing = listing.filter(profile__teams__slug__in=chosen_teams)
    # Both boxes ticked is the same set as neither, so it is left unfiltered
    # rather than turned into two contradictory conditions.
    if len(chosen_status) == 1:
        listing = listing.filter(is_active=chosen_status[0] == 'active')

    listing = listing.distinct().order_by('username')

    paginator = Paginator(listing, USERS_PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    page_numbers = list(
        paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    )

    rows = []
    for person in page.object_list:
        profile = getattr(person, 'profile', None)
        rows.append({
            'pk': person.pk,
            'username': person.get_username(),
            'full_name': person.get_full_name(),
            'email': person.email,
            'role': profile.get_role_display() if profile else 'No role',
            'role_value': profile.role if profile else '',
            'teams': list(profile.teams.all()) if profile else [],
            'sees_all_teams': profile.sees_all_teams if profile else False,
            'is_active': person.is_active,
            'last_login': person.last_login,
            'date_joined': person.date_joined,
            'is_self': person.pk == request.user.pk,
            # Only the current page builds forms, and a failed submit keeps its
            # own bound one so the errors survive the re-render.
            'form': bound_edit.get(person.pk) or EditUserForm(
                actor=request.user,
                target=person,
                initial=EditUserForm.initial_for(person),
            ),
            'password_form': bound_password.get(person.pk) or AdminPasswordForm(target=person),
        })

    total = people.count()
    active = people.filter(is_active=True).count()
    admins = people.filter(
        Q(is_superuser=True) | Q(profile__role__in=list(UserProfile.ADMIN_ROLES))
    ).distinct().count()

    return async_content.render_content(request, 'core/users.html', {
        'title': 'User Profiles',
        'rows': rows,
        'result_count': paginator.count,
        'page_obj': page,
        'page_numbers': page_numbers,
        'anchor': _USERS_ANCHOR,
        'search': search,
        'role_options': [
            {'value': value, 'label': label, 'checked': value in chosen_roles}
            for value, label in UserProfile.Role.choices
        ],
        'team_options': [
            {'value': team.slug, 'label': team.name, 'checked': team.slug in chosen_teams}
            for team in assignable_teams(request.user)
        ],
        'status_options': [
            {'value': value, 'label': label, 'checked': value in chosen_status}
            for value, label in _STATUS_OPTIONS
        ],
        'active_filter_count': len(chosen_roles) + len(chosen_teams) + len(chosen_status),
        'has_any_filter': bool(search or chosen_roles or chosen_teams or chosen_status),
        'clear_url': reverse('core:users'),
        'page_query': _query_without_page(request),
        'page_params': _params_without_page(request),
        'stats': {
            'total': total,
            'active': active,
            'deactivated': total - active,
            'admins': admins,
        },
        'create_form': create_form or CreateUserForm(actor=request.user),
        'open_create': open_create,
        'open_edit_pk': open_edit_pk,
        'open_password_pk': open_password_pk,
        # Says whose list this is: an Admin sees their teams' accounts, a Super
        # Admin sees the org's, and the same page with two very different
        # contents should say which one it is showing.
        'is_scoped': not is_superadmin(request.user),
        'scoped_teams': (
            accessible_teams(request.user)
            if not is_superadmin(request.user) else None
        ),
        'assignable_role_labels': [label for _, label in assignable_roles(request.user)],
    })
