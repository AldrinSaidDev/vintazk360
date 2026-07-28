from django.contrib.auth.decorators import login_required
from django.shortcuts import render

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
