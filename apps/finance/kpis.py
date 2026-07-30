"""Finance KPI definitions.

PLACEHOLDER DATA — the `actual` numbers are invented so the scorecard and chart
render with something to look at. Targets, formulas and required inputs come
from the business. See apps/core/kpi.py for the dict shape and the math.
"""

KPIS = [
    {'name': 'Payroll Accuracy', 'category': 'Payroll', 'kind': 'net_percent', 'direction': 'up',
     'target': 99.9, 'actual': 99.94, 'frequency': 'Monthly',
     'target_display': '≥99.9%', 'actual_display': '99.94%',
     'formula': 'Payroll Accuracy % = ((Total Payroll Transactions − Payroll Errors) ÷ Total Payroll Transactions) × 100',
     'description': 'Share of payroll transactions processed without error.',
     'inputs': ['Total payroll transactions', 'Payroll errors']},

    {'name': 'Payroll On-Time Completion', 'category': 'Payroll', 'kind': 'percent', 'direction': 'up',
     'target': 100, 'actual': 100, 'frequency': 'Monthly',
     'target_display': '100%', 'actual_display': '100%',
     'formula': 'On-Time % = (Payroll Runs Completed On or Before Deadline ÷ Total Payroll Runs) × 100',
     'description': 'Share of payroll runs completed on or before their deadline.',
     'inputs': ['Payroll runs', 'On-time payroll runs']},

    {'name': 'Collections Efficiency', 'category': 'Receivables', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 91.5, 'frequency': 'Monthly',
     'target_display': '≥95%', 'actual_display': '91.5%',
     'formula': 'Collections % = (Amount Collected ÷ Amount Due) × 100',
     'description': 'Share of the amount due that was actually collected in the period.',
     'inputs': ['Amount due', 'Amount collected']},

    {'name': 'Days Sales Outstanding (DSO)', 'category': 'Receivables', 'kind': 'scaled', 'direction': 'down',
     'target': 30, 'actual': 34, 'frequency': 'Monthly',
     'target_display': '≤30 days', 'actual_display': '34 days',
     'formula': 'DSO = (Accounts Receivable ÷ Total Credit Sales) × Number of Days',
     'description': 'Average days it takes to convert receivables into cash.',
     'inputs': ['Accounts receivable', 'Credit sales', 'Period days']},

    {'name': 'Invoice Accuracy', 'category': 'Controls', 'kind': 'net_percent', 'direction': 'up',
     'target': 99, 'actual': 98.2, 'frequency': 'Monthly',
     'target_display': '≥99%', 'actual_display': '98.2%',
     'formula': 'Invoice Accuracy % = ((Total Invoices − Invoice Errors) ÷ Total Invoices) × 100',
     'description': 'Share of invoices issued without error — the upstream driver of collections disputes.',
     'inputs': ['Total invoices', 'Invoice errors']},

    {'name': 'Vendor Payment Timeliness', 'category': 'Payables', 'kind': 'percent', 'direction': 'up',
     'target': 98, 'actual': 98.6, 'frequency': 'Monthly',
     'target_display': '≥98%', 'actual_display': '98.6%',
     'formula': 'Timeliness % = (Vendor Payments Made On Time ÷ Total Vendor Payments) × 100',
     'description': 'Share of vendor payments released on or before their due date.',
     'inputs': ['Total vendor payments', 'On-time payments']},

    # A two-sided tolerance: ±5% either way is acceptable, so it's scored as a
    # 'down' KPI over a 0–5 band on the ABSOLUTE variance. `actual` holds the
    # magnitude (3.2); `actual_display` keeps the sign so over- and under-spend
    # stay distinguishable on the card.
    {'name': 'Budget Variance', 'category': 'Planning', 'kind': 'variance', 'direction': 'down',
     'target_min': 0, 'target_max': 5, 'actual': 3.2, 'frequency': 'Quarterly',
     'target_display': 'Within ±5%', 'actual_display': '+3.2%',
     'formula': 'Budget Variance % = ((Actual Expenses − Budgeted Expenses) ÷ Budgeted Expenses) × 100',
     'description': 'How far actual spend drifted from budget. Scored on the size of the gap, so overspend and '
                    'underspend are both penalised once past ±5%.',
     'inputs': ['Budgeted expenses', 'Actual expenses']},

    {'name': 'Financial Report Timeliness', 'category': 'Controls', 'kind': 'percent', 'direction': 'up',
     'target': 100, 'actual': 92, 'frequency': 'Monthly',
     'target_display': '100%', 'actual_display': '92%',
     'formula': 'Report Timeliness % = (Reports Submitted On Time ÷ Total Required Reports) × 100',
     'description': 'Share of required financial reports filed by their deadline.',
     'inputs': ['Required reports', 'Reports submitted on time']},

    {'name': 'Cash Flow Forecast Accuracy', 'category': 'Planning', 'kind': 'accuracy', 'direction': 'up',
     'target': 95, 'actual': 85, 'frequency': 'Monthly',
     'target_display': '≥95%', 'actual_display': '85%',
     'formula': 'Forecast Accuracy % = (1 − |Forecast Cash Flow − Actual Cash Flow| ÷ Actual Cash Flow) × 100',
     'description': 'How close the cash-flow forecast landed to actual, in either direction.',
     'inputs': ['Forecast cash flow', 'Actual cash flow']},
]

# Add-Record modal inputs, one per KPI. `unit` is appended to the computed value
# for the non-percentage kinds, so it carries its own leading space.
MODAL_SPECS = [
    {'name': 'Payroll Accuracy',
     'a_label': 'Total payroll transactions', 'a_placeholder': 'e.g. 4820',
     'b_label': 'Payroll errors', 'b_placeholder': 'e.g. 3'},
    {'name': 'Payroll On-Time Completion',
     'a_label': 'Payroll runs completed on time', 'a_placeholder': 'e.g. 2',
     'b_label': 'Total payroll runs', 'b_placeholder': 'e.g. 2'},
    {'name': 'Collections Efficiency',
     'a_label': 'Amount collected', 'a_placeholder': 'e.g. 4575000',
     'b_label': 'Amount due', 'b_placeholder': 'e.g. 5000000'},
    {'name': 'Days Sales Outstanding (DSO)', 'unit': ' days',
     'a_label': 'Accounts receivable', 'a_placeholder': 'e.g. 5666000',
     'b_label': 'Total credit sales', 'b_placeholder': 'e.g. 5000000',
     'c_label': 'Days in period', 'c_placeholder': 'e.g. 30'},
    {'name': 'Invoice Accuracy',
     'a_label': 'Total invoices', 'a_placeholder': 'e.g. 340',
     'b_label': 'Invoice errors', 'b_placeholder': 'e.g. 6'},
    {'name': 'Vendor Payment Timeliness',
     'a_label': 'Vendor payments made on time', 'a_placeholder': 'e.g. 212',
     'b_label': 'Total vendor payments', 'b_placeholder': 'e.g. 215'},
    {'name': 'Budget Variance',
     'a_label': 'Actual expenses', 'a_placeholder': 'e.g. 5160000',
     'b_label': 'Budgeted expenses', 'b_placeholder': 'e.g. 5000000'},
    {'name': 'Financial Report Timeliness',
     'a_label': 'Reports submitted on time', 'a_placeholder': 'e.g. 11',
     'b_label': 'Total required reports', 'b_placeholder': 'e.g. 12'},
    {'name': 'Cash Flow Forecast Accuracy',
     'a_label': 'Forecast cash flow', 'a_placeholder': 'e.g. 4250000',
     'b_label': 'Actual cash flow', 'b_placeholder': 'e.g. 5000000'},
]

# Which finance function a record belongs to.
FUNCTIONS = [
    'Payroll', 'Accounts Receivable', 'Accounts Payable',
    'Financial Planning & Analysis', 'Compliance & Reporting', 'Treasury',
]

SCOPE = {
    'title': 'Finance',
    'badge': 'Finance',
    'blurb': 'Payroll accuracy and timeliness, cash in and out, budget discipline, and how reliably the numbers get reported.',
}
