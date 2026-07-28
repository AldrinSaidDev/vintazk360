from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render
from django.urls import reverse

# Static placeholder rows — same directive as the KPI screens: no DB yet. When an
# audit-log model lands, only this list is replaced; the template already loops.
# status ∈ success | warning | failed  → drives the pill color (status tokens).
_LOG_ENTRIES = [
    {'timestamp': 'Jul 28, 2026 · 09:41 AM', 'user': 'admin', 'role': 'Super Admin',
     'action': 'Imported Excel file', 'module': 'Operations',
     'details': 'BPAO_Scorecard_July2026.xlsx — 128 records', 'status': 'success'},
    {'timestamp': 'Jul 28, 2026 · 09:02 AM', 'user': '2026-01-439', 'role': 'Manager',
     'action': 'Added performance record', 'module': 'Operations',
     'details': 'CSAT — 92.4% vs target 90%', 'status': 'success'},
    {'timestamp': 'Jul 27, 2026 · 04:47 PM', 'user': 'demo_manager', 'role': 'Manager',
     'action': 'Updated KPI target', 'module': 'Operations',
     'details': 'Attrition threshold 5% → 4.5%', 'status': 'warning'},
    {'timestamp': 'Jul 27, 2026 · 02:15 PM', 'user': 'demo_admin', 'role': 'Admin',
     'action': 'Changed user role', 'module': 'Access Control',
     'details': 'demo_sales → Manager', 'status': 'success'},
    {'timestamp': 'Jul 27, 2026 · 11:38 AM', 'user': 'demo_sales', 'role': 'User',
     'action': 'Import failed', 'module': 'Sales',
     'details': 'Unrecognized column "Rev Target Q3"', 'status': 'failed'},
    {'timestamp': 'Jul 27, 2026 · 08:05 AM', 'user': 'demo_hr', 'role': 'User',
     'action': 'Signed in', 'module': 'Authentication',
     'details': 'Session started', 'status': 'success'},
    {'timestamp': 'Jul 26, 2026 · 05:20 PM', 'user': 'admin', 'role': 'Super Admin',
     'action': 'Deleted KPI record', 'module': 'Finance',
     'details': 'Billable Hours — June 2026', 'status': 'warning'},
    {'timestamp': 'Jul 26, 2026 · 01:11 PM', 'user': 'demo_academy', 'role': 'User',
     'action': 'Failed sign-in attempt', 'module': 'Authentication',
     'details': 'Incorrect password (3rd attempt)', 'status': 'failed'},
]

# Filter dropdown options. Static for now; these become distinct values off the
# log table once it exists.
_LOG_MODULES = ['Operations', 'Sales', 'HR', 'Finance', 'Access Control', 'Authentication']
_LOG_ACTIONS = ['Import', 'Record change', 'Target change', 'Access change', 'Sign-in']


@login_required
def logs(request):
    """Activity log (static placeholder — controls are inert until it's DB-backed)."""
    return render(request, 'core/logs.html', {
        'title': 'Logs',
        'entries': _LOG_ENTRIES,
        'modules': _LOG_MODULES,
        'actions': _LOG_ACTIONS,
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


@login_required
def account_settings(request):
    """Account settings: profile details, password change, and own activity.

    Unlike the KPI screens this one is real — the password form is Django's
    ``PasswordChangeForm`` and actually changes the password. Only the Activity
    tab is placeholder, since it reads the same static log list as /logs/.
    """
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
    username = request.user.get_username()

    return render(request, 'core/settings.html', {
        'title': 'Settings',
        'tab': tab,
        'form': form,
        'profile': profile,
        'teams': profile.teams.all() if profile else [],
        # This account's slice of the activity log (same static source as /logs/).
        'my_entries': [e for e in _LOG_ENTRIES if e['user'] == username],
    })
