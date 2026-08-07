"""Nexzys KPI definitions.

Nexzys is the internal technology and automation LOB. Unlike Operations, not
every KPI here is a percentage: each MODAL_SPECS entry declares a `kind` that
names the arithmetic ('ratio', 'days', 'count'), which is what
`apps/kpi/seeding.py` turns into a real expression and its `kpi_input` rows.

Nothing renders from this module: every Nexzys screen reads the database. It
survives as the input to `manage.py seed_lob_kpis nexzys`.
"""

KPIS = [
    {'name': 'Automation Hours Saved',  'category': 'Automation & AI', 'target': 2,     'actual': 2.6,   'direction': 'up',
     'target_display': '2 hrs/employee', 'actual_display': '2.6 hrs/employee', 'frequency': 'Monthly',
     'formula': 'Hours Saved = Manual hours − Automated hours (per employee)',
     'description': 'Time given back to employees each month by replacing manual work with automation.',
     'inputs': ['Current manual time', 'Automated time', 'Frequency', 'Employees']},

    {'name': 'Automation ROI',          'category': 'Automation & AI', 'target': 3,     'actual': 3.4,   'direction': 'up',
     'target_display': '≥3× per system', 'actual_display': '3.4×', 'frequency': 'Quarterly',
     'formula': 'ROI = Annual value generated ÷ Annual system cost',
     'description': 'Value each automated system returns against what it costs to run for a year.',
     'inputs': ['Hours saved/month', 'Labor cost/hour', 'Annual software cost']},

    {'name': 'System Uptime',           'category': 'Infrastructure',  'target': 99.99, 'actual': 99.96, 'direction': 'up',
     'target_display': '≥99.99%', 'actual_display': '99.96%', 'frequency': 'Monthly',
     'formula': 'Uptime % = System available time ÷ Total scheduled time × 100',
     'description': 'Share of scheduled time core systems were available to the business.',
     'inputs': ['Total monitoring time', 'Downtime']},

    {'name': 'IT SLA Compliance',       'category': 'Service Delivery', 'target': 95,   'actual': 97.2,  'direction': 'up',
     'target_display': '≥95%', 'actual_display': '97.2%', 'frequency': 'Monthly',
     'formula': 'SLA Compliance = Tickets resolved within SLA ÷ Total tickets × 100',
     'description': 'Share of IT tickets resolved inside their agreed response and fix windows.',
     'inputs': ['Total tickets', 'On-time tickets']},

    {'name': 'New-Hire Provisioning',   'category': 'Service Delivery', 'target': 1,    'actual': 1.4,   'direction': 'down',
     'target_display': '≤1 working day', 'actual_display': '1.4 days', 'frequency': 'Per Wave',
     'formula': 'Provisioning Days = Ready date − Day 0 (wave KPI = longest provisioning time in the wave)',
     'description': 'Working days to get a new hire fully set up. Ready date is the latest completion '
                    'of account setup, access, device, and workstation.',
     'inputs': ['Day 0', 'Account setup date', 'Access date', 'Device date', 'Workstation date']},

    {'name': 'Workstation Readiness',   'category': 'Infrastructure',  'target': 95,    'actual': 91,    'direction': 'up',
     'target_display': '≥95% ready', 'actual_display': '91%', 'frequency': 'Weekly',
     'formula': 'Readiness % = Ready workstations ÷ Total workstations × 100',
     'description': 'Share of workstations built, tested, and ready to deploy — with the backlog cleared.',
     'inputs': ['Ready stations', 'Total stations', 'Backlog count']},

    {'name': 'AI Copilot Adoption',     'category': 'Automation & AI', 'target': 60,    'actual': 48,    'direction': 'up',
     'target_display': '≥60%', 'actual_display': '48%', 'frequency': 'Monthly',
     'formula': 'Adoption % = Employees using AI tools ÷ Eligible employees × 100',
     'description': 'Share of eligible employees actively using the rolled-out AI tools.',
     'inputs': ['Eligible employees', 'Active AI users']},

    {'name': 'Security Incidents',      'category': 'Security',        'target': 0,     'actual': 0,     'direction': 'down',
     'target_display': 'Zero major incidents', 'actual_display': '0 major', 'frequency': 'Monthly',
     'formula': 'Major incidents count',
     # Second measure that rides along with this KPI (100% of staff trained).
     'formula_note': 'Training Completion % = Employees completed security training ÷ Total employees × 100',
     'description': 'Major security incidents in the period. Tracked alongside security-training completion, '
                    'which targets 100% of employees.',
     'inputs': ['Incident count', 'Employees trained', 'Total employees']},
]


# Formula inputs for the Add-Record modal. Unlike Operations (every KPI is a
# num ÷ den × 100 percentage), Nexzys KPIs come in several shapes, so each entry
# declares a `kind` that tells the modal how to compute and word the result:
#   percent    → a ÷ b × 100      (uptime, SLA, readiness, adoption)
#   ratio      → a ÷ b            (ROI, reads as "3.4×")
#   difference → a − b            (hours saved)
#   days       → date a − date b  (provisioning turnaround)
#   count      → a                (major incidents; no denominator)
# `sub_a`/`sub_b` add an optional second percentage line (security training).
MODAL_SPECS = [
    {'name': 'Automation Hours Saved', 'kind': 'difference', 'unit': 'hrs',
     'a_label': 'Manual hours per employee',   'a_placeholder': 'e.g. 9.5',
     'b_label': 'Automated hours per employee', 'b_placeholder': 'e.g. 6.9'},

    {'name': 'Automation ROI', 'kind': 'ratio', 'unit': '×',
     'a_label': 'Annual value generated', 'a_placeholder': 'e.g. 850000',
     'b_label': 'Annual system cost',     'b_placeholder': 'e.g. 250000'},

    {'name': 'System Uptime', 'kind': 'percent', 'unit': '%',
     'a_label': 'System available time (hrs)', 'a_placeholder': 'e.g. 743.7',
     'b_label': 'Total scheduled time (hrs)',  'b_placeholder': 'e.g. 744'},

    {'name': 'IT SLA Compliance', 'kind': 'percent', 'unit': '%',
     'a_label': 'Tickets resolved within SLA', 'a_placeholder': 'e.g. 486',
     'b_label': 'Total tickets',               'b_placeholder': 'e.g. 500'},

    {'name': 'New-Hire Provisioning', 'kind': 'days', 'unit': 'days',
     'a_label': 'Ready date (last item completed)', 'a_placeholder': '',
     'b_label': 'Day 0 (start date)',               'b_placeholder': ''},

    {'name': 'Workstation Readiness', 'kind': 'percent', 'unit': '%',
     'a_label': 'Ready workstations', 'a_placeholder': 'e.g. 182',
     'b_label': 'Total workstations', 'b_placeholder': 'e.g. 200'},

    {'name': 'AI Copilot Adoption', 'kind': 'percent', 'unit': '%',
     'a_label': 'Employees using AI tools', 'a_placeholder': 'e.g. 240',
     'b_label': 'Eligible employees',       'b_placeholder': 'e.g. 500'},

    {'name': 'Security Incidents', 'kind': 'count', 'unit': '',
     'a_label': 'Major incidents this period', 'a_placeholder': 'e.g. 0',
     'b_label': '', 'b_placeholder': '',
     'sub_a_label': 'Employees completed security training',
     'sub_b_label': 'Total employees'},
]


SCOPE = {
    'title': 'Nexzys',
    'badge': 'Nexzys',
    # No North Star has been set for Nexzys yet, so the banner carries a
    # descriptive line instead of a number nobody agreed to.
    'north_star': 'Automate the manual, keep the lights on, and make every tool earn its cost.',
    'north_star_pending': True,
    'blurb': 'Automation returns, system reliability, IT service delivery, and security posture.',
    'definitions_blurb': 'The metrics below define how Nexzys measures success, each with its target, cadence, and formula.',
    'icons': ['code', 'microchip', 'laptop'],
    'lead_size': 'sm',
}
