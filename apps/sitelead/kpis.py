"""Site Lead KPI definitions.

PLACEHOLDER DATA — the `actual` numbers are invented so the scorecard and chart
render with something to look at. Targets, formulas and required inputs come
from the business. See apps/core/kpi.py for the dict shape and the math.

HALF THESE KPIs HAVE NO NUMBER YET. The source table states six targets as
"≥ Company Target" / "≥ Target Margin" / "Meet/Exceed Budget" / "Positive",
which can't be scored, so they carry `target: None` and show as "No Target"
(tracked, charted-out, excluded from the on-track tallies). Fill in the numbers
and they start scoring with no other change.
"""

KPIS = [
    {'name': 'Revenue Achievement', 'category': 'Financial', 'kind': 'percent', 'direction': 'up',
     'target': 100, 'actual': 97.5, 'frequency': 'Monthly',
     'target_display': '100% of monthly target', 'actual_display': '97.5%',
     'formula': 'Revenue Achievement % = (Actual Revenue ÷ Revenue Target) × 100',
     'description': 'Revenue delivered against the site\'s monthly revenue target.',
     'inputs': ['Actual revenue', 'Revenue target']},

    {'name': 'EBITDA Margin', 'category': 'Financial', 'kind': 'percent', 'direction': 'up',
     'target': None, 'actual': 18.4, 'frequency': 'Monthly',
     'target_display': '≥ Target margin (not set)', 'actual_display': '18.4%',
     'formula': 'EBITDA Margin % = (EBITDA ÷ Total Revenue) × 100',
     'description': 'Operating profitability before interest, tax, depreciation and amortisation. '
                    'No target margin supplied yet, so this is tracked rather than scored.',
     'inputs': ['EBITDA', 'Total revenue']},

    {'name': 'Client Satisfaction (CSAT)', 'category': 'Client', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 96.2, 'frequency': 'Monthly',
     'target_display': '≥95%', 'actual_display': '96.2%',
     'formula': 'CSAT % = (Positive Client Survey Responses ÷ Total Survey Responses) × 100',
     'description': 'Share of client survey responses that are positive.',
     'inputs': ['Client survey responses', 'Positive responses']},

    {'name': 'Net Promoter Score (NPS)', 'category': 'Client', 'kind': 'difference', 'direction': 'up',
     'target': None, 'actual': 38, 'frequency': 'Quarterly',
     'target_display': 'Positive / company target (not set)', 'actual_display': '+38',
     'formula': 'NPS = % Promoters − % Detractors',
     'description': 'Net client advocacy, from −100 to +100. "Positive" isn\'t a scoreable number — '
                    'supply the company target to score it.',
     'inputs': ['Promoters', 'Passives', 'Detractors']},

    {'name': 'Employee Engagement Score', 'category': 'People', 'kind': 'average', 'direction': 'up',
     'target': None, 'actual': 4.2, 'frequency': 'Quarterly',
     'target_display': '≥ Company target (not set)', 'actual_display': '4.2 / 5.0',
     'formula': 'Engagement Score = Average Employee Survey Score',
     'description': 'Average engagement survey score across the site, on a 5-point scale.',
     'inputs': ['Employee engagement survey results']},

    {'name': 'Employee Retention Rate', 'category': 'People', 'kind': 'percent', 'direction': 'up',
     'target': 90, 'actual': 88, 'frequency': 'Monthly',
     'target_display': '≥90%', 'actual_display': '88%',
     'formula': 'Retention % = (Employees Remaining ÷ Employees at Start of Period) × 100',
     'description': 'Share of the starting workforce still employed at the end of the period.',
     'inputs': ['Starting employees', 'Remaining employees']},

    {'name': 'Attrition Rate', 'category': 'People', 'kind': 'percent', 'direction': 'down',
     'target': None, 'actual': 3.9, 'frequency': 'Monthly',
     'target_display': '≤ Company target (not set)', 'actual_display': '3.9%',
     'formula': 'Attrition % = (Employee Exits ÷ Average Headcount) × 100',
     'description': 'Share of headcount leaving in the period. Lower is better, but no ceiling has been '
                    'supplied — HR scores its own attrition against ≤4.0%.',
     'inputs': ['Employee exits', 'Average headcount']},

    {'name': 'SLA Compliance', 'category': 'Operational', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 97.4, 'frequency': 'Monthly',
     'target_display': '≥95%', 'actual_display': '97.4%',
     'formula': 'SLA Compliance % = (SLAs Met ÷ Total SLAs) × 100',
     'description': 'Share of service-level commitments met across the site\'s accounts.',
     'inputs': ['Total SLA commitments', 'SLAs achieved']},

    {'name': 'Operational Efficiency', 'category': 'Operational', 'kind': 'percent', 'direction': 'up',
     'target': None, 'actual': 94, 'frequency': 'Monthly',
     'target_display': '≥ Target (not set)', 'actual_display': '94%',
     'formula': 'Operational Efficiency % = (Actual Output ÷ Planned Output) × 100',
     'description': 'Actual output delivered against plan. No target supplied yet, so this is tracked '
                    'rather than scored.',
     'inputs': ['Planned output', 'Actual output']},

    {'name': 'Profitability', 'category': 'Financial', 'kind': 'percent', 'direction': 'up',
     'target': None, 'actual': 12.8, 'frequency': 'Monthly',
     'target_display': 'Meet/exceed budget (not set)', 'actual_display': '12.8%',
     'formula': 'Profit Margin % = (Net Profit ÷ Total Revenue) × 100',
     'description': 'Net profit as a share of revenue. "Meet/exceed budget" needs the budgeted margin '
                    'to score against.',
     'inputs': ['Net profit', 'Total revenue']},

    {'name': 'Project / Initiative Completion', 'category': 'Operational', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 83, 'frequency': 'Quarterly',
     'target_display': '≥95%', 'actual_display': '83%',
     'formula': 'Completion % = (Completed Projects ÷ Planned Projects) × 100',
     'description': 'Share of planned site initiatives completed in the period.',
     'inputs': ['Planned initiatives', 'Completed initiatives']},

    {'name': 'Compliance Score', 'category': 'Governance', 'kind': 'percent', 'direction': 'up',
     'target': 100, 'actual': 100, 'frequency': 'Quarterly',
     'target_display': '100%', 'actual_display': '100%',
     'formula': 'Compliance % = (Compliant Audits ÷ Total Audits) × 100',
     'description': 'Share of audits passed without a compliance finding.',
     'inputs': ['Audit results', 'Compliance records']},
]

# Add-Record modal inputs, one per KPI. `unit` is appended to the computed value
# for the non-percentage kinds, so it carries its own leading space.
MODAL_SPECS = [
    {'name': 'Revenue Achievement',
     'a_label': 'Actual revenue', 'a_placeholder': 'e.g. 4875000',
     'b_label': 'Revenue target', 'b_placeholder': 'e.g. 5000000'},
    {'name': 'EBITDA Margin',
     'a_label': 'EBITDA', 'a_placeholder': 'e.g. 897000',
     'b_label': 'Total revenue', 'b_placeholder': 'e.g. 4875000'},
    {'name': 'Client Satisfaction (CSAT)',
     'a_label': 'Positive client survey responses', 'a_placeholder': 'e.g. 154',
     'b_label': 'Total survey responses', 'b_placeholder': 'e.g. 160'},
    {'name': 'Net Promoter Score (NPS)',
     'a_label': 'Promoters (% of responses)', 'a_placeholder': 'e.g. 52',
     'b_label': 'Detractors (% of responses)', 'b_placeholder': 'e.g. 14'},
    {'name': 'Employee Engagement Score', 'unit': ' / 5.0',
     'a_label': 'Total survey score points', 'a_placeholder': 'e.g. 1428',
     'b_label': 'Valid survey responses', 'b_placeholder': 'e.g. 340'},
    {'name': 'Employee Retention Rate',
     'a_label': 'Employees remaining', 'a_placeholder': 'e.g. 396',
     'b_label': 'Employees at start of period', 'b_placeholder': 'e.g. 450'},
    {'name': 'Attrition Rate',
     'a_label': 'Employee exits', 'a_placeholder': 'e.g. 17',
     'b_label': 'Average headcount', 'b_placeholder': 'e.g. 436'},
    {'name': 'SLA Compliance',
     'a_label': 'SLAs met', 'a_placeholder': 'e.g. 187',
     'b_label': 'Total SLAs', 'b_placeholder': 'e.g. 192'},
    {'name': 'Operational Efficiency',
     'a_label': 'Actual output', 'a_placeholder': 'e.g. 9400',
     'b_label': 'Planned output', 'b_placeholder': 'e.g. 10000'},
    {'name': 'Profitability',
     'a_label': 'Net profit', 'a_placeholder': 'e.g. 624000',
     'b_label': 'Total revenue', 'b_placeholder': 'e.g. 4875000'},
    {'name': 'Project / Initiative Completion',
     'a_label': 'Completed projects', 'a_placeholder': 'e.g. 10',
     'b_label': 'Planned projects', 'b_placeholder': 'e.g. 12'},
    {'name': 'Compliance Score',
     'a_label': 'Compliant audits', 'a_placeholder': 'e.g. 8',
     'b_label': 'Total audits', 'b_placeholder': 'e.g. 8'},
]

SCOPE = {
    'title': 'Site Lead',
    'badge': 'Site Lead',
    'blurb': 'Site-level ownership: revenue and margin, client satisfaction, the workforce, and whether commitments '
             'and compliance hold.',
}
