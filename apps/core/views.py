"""Shared, non-LOB screens: the activity log and account settings."""

import datetime as dt

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse

from . import activity, async_content
from .access import accessible_teams
from .models import AuditLog

# Rows per page on the Logs table.
PAGE_SIZE = 20

# The table's own id, so a pager link lands on the table rather than the top of
# the page. See the note on `anchor` in partials/pagination.html.
_TABLE_ANCHOR = 'activity-log'


def _query_without_page(request):
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()


def _params_without_page(request):
    return [
        {'key': key, 'value': value}
        for key, values in request.GET.lists()
        if key != 'page'
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
