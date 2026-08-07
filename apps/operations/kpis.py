"""Operations KPI definitions.

Operations was the first LOB wired to the database, so these dicts no longer
render anything: every screen reads `kpi_definition`. They survive as the input
to `manage.py seed_lob_kpis operations`, which turns them into real rows.
"""

KPIS = [
    {'name': 'Attrition Rate', 'category': 'People', 'kind': 'percent', 'direction': 'down',
     'target': 3.5, 'actual': 3.1, 'frequency': 'Monthly',
     'target_display': 'Threshold 3.5%', 'actual_display': '3.1%',
     'formula': 'Total exits ÷ Average headcount × 100',
     'description': 'Percentage of employees who leave during the reporting period.'},

    {'name': 'Client Retention Rate', 'category': 'Financial', 'kind': 'percent', 'direction': 'up',
     'target': 100, 'actual': 96, 'frequency': 'Monthly',
     'target_display': '100%', 'actual_display': '96%',
     'formula': 'Clients retained ÷ Total existing clients × 100',
     'description': 'Percentage of clients retained over the period, excluding clients acquired within the last month.'},

    {'name': 'Billable Hours Achievement', 'category': 'Financial', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 92, 'frequency': 'Monthly',
     'target_display': '≥95%', 'actual_display': '92%',
     'formula': 'Actual billable hours ÷ Required billable hours × 100',
     'description': 'Percentage of required client-billable hours successfully delivered.'},

    {'name': 'CSAT', 'category': 'Client Impact', 'kind': 'percent', 'direction': 'up',
     'target': 90, 'actual': 93, 'frequency': 'Quarterly',
     'target_display': '≥90%', 'actual_display': '93%',
     'formula': 'Positive responses ÷ Total survey responses × 100',
     'description': 'Percentage of customers who give a positive satisfaction rating.'},

    {'name': 'EBR Completion', 'category': 'Operational', 'kind': 'percent', 'direction': 'up',
     'target': 100, 'actual': 100, 'frequency': 'Quarterly',
     'target_display': '100%', 'actual_display': '100%',
     'formula': 'Completed compliant reviews ÷ Scheduled reviews × 100',
     'description': 'Percentage of scheduled business reviews completed accurately and on time.'},

    {'name': 'Seat Expansion', 'category': 'Financial', 'kind': 'percent', 'direction': 'up',
     'target': 100, 'actual': 78, 'frequency': 'Monthly',
     'target_display': '30% of target', 'actual_display': '78% of goal',
     'formula': 'Actual billable headcount ÷ Target headcount (500) × 100',
     'description': 'Progress toward the 500-headcount target through billable seat growth.'},

]

# Add-Record modal inputs, one per KPI. Every Operations KPI is a
# numerator over a denominator as a percentage, so all nine are kind "percent".
MODAL_SPECS = [
    {'name': 'Attrition Rate', 'kind': 'percent',
     'a_label': 'Total exits', 'a_placeholder': '',
     'b_label': 'Average headcount', 'b_placeholder': ''},
    {'name': 'Client Retention Rate', 'kind': 'percent',
     'a_label': 'Clients retained', 'a_placeholder': '',
     'b_label': 'Total existing clients', 'b_placeholder': ''},
    {'name': 'Billable Hours Achievement', 'kind': 'percent',
     'a_label': 'Actual billable hours', 'a_placeholder': '',
     'b_label': 'Required billable hours', 'b_placeholder': ''},
    {'name': 'CSAT', 'kind': 'percent',
     'a_label': 'Positive responses', 'a_placeholder': '',
     'b_label': 'Total survey responses', 'b_placeholder': ''},
    {'name': 'EBR Completion', 'kind': 'percent',
     'a_label': 'Completed compliant reviews', 'a_placeholder': '',
     'b_label': 'Scheduled reviews', 'b_placeholder': ''},
    {'name': 'Seat Expansion', 'kind': 'percent',
     'a_label': 'Actual billable headcount', 'a_placeholder': '',
     'b_label': 'Target headcount (500)', 'b_placeholder': ''},
]


SCOPE = {
    'title': 'Operations',
    'badge': 'Operations',
    'north_star': 'Net Revenue Retention ≥ 110%',
    'blurb': 'Keep every client and grow inside them.',
    'definitions_blurb': 'The metrics below define how Operations measures success, each with its target, cadence, and formula.',
    'icons': ['cogs', 'tasks', 'line-chart'],
    'lead_size': 'sm',
}
