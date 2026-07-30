"""HR KPI definitions.

PLACEHOLDER DATA — the `actual` numbers are invented so the scorecard and chart
render with something to look at. Targets, formulas and required inputs come
from the business. See apps/core/kpi.py for the dict shape and the math.
"""

KPIS = [
    {'name': 'Net Headcount vs Plan', 'category': 'Workforce', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 92.4, 'frequency': 'Monthly',
     'target_display': '≥95% monthly', 'actual_display': '92.4%',
     'formula': 'Net Headcount % = (Actual Headcount ÷ Planned Headcount) × 100',
     'description': 'How closely live headcount tracks the staffing plan for the period.',
     'inputs': ['Actual headcount', 'Planned headcount']},

    {'name': 'Gross Hires / Month', 'category': 'Talent Acquisition', 'kind': 'percent', 'direction': 'up',
     'target': 100, 'actual': 104, 'frequency': 'Monthly',
     'target_display': '100% of hiring target', 'actual_display': '104%',
     'formula': 'Gross Hires % = (Actual Hires ÷ Target Hires) × 100',
     'description': 'Hires delivered against the month\'s hiring target.',
     'inputs': ['Actual hires', 'Hiring target']},

    {'name': 'Time-to-Fill (Agents)', 'category': 'Talent Acquisition', 'kind': 'average', 'direction': 'down',
     'target': 10, 'actual': 8.6, 'frequency': 'Monthly',
     'target_display': '≤10 days', 'actual_display': '8.6 days',
     'formula': 'Average Days = Total Days to Fill Agent Positions ÷ Number of Agent Positions Filled',
     'description': 'Average working days from opening an agent requisition to a signed hire.',
     'inputs': ['Job opening date', 'Hire date']},

    {'name': 'Time-to-Fill (Support/Leadership)', 'category': 'Talent Acquisition', 'kind': 'average', 'direction': 'down',
     'target': 30, 'actual': 37, 'frequency': 'Monthly',
     'target_display': '≤30 days', 'actual_display': '37 days',
     'formula': 'Average Days = Total Days to Fill Support/Leadership Positions ÷ Positions Filled',
     'description': 'Average working days to fill support and leadership roles, which run a longer cycle than agents.',
     'inputs': ['Job opening date', 'Hire date']},

    {'name': 'Offer Acceptance Rate', 'category': 'Talent Acquisition', 'kind': 'percent', 'direction': 'up',
     'target': 80, 'actual': 84, 'frequency': 'Monthly',
     'target_display': '≥80%', 'actual_display': '84%',
     'formula': 'Offer Acceptance % = (Accepted Offers ÷ Total Offers Extended) × 100',
     'description': 'Share of extended offers that candidates accept.',
     'inputs': ['Offers extended', 'Offers accepted']},

    {'name': '90-Day Retention Rate', 'category': 'Retention', 'kind': 'percent', 'direction': 'up',
     'target': 85, 'actual': 81, 'frequency': 'Monthly',
     'target_display': '≥85%', 'actual_display': '81%',
     'formula': 'Retention % = (Employees Still Active After 90 Days ÷ Employees Hired 90 Days Ago) × 100',
     'description': 'Share of new hires still with the company at the 90-day mark.',
     'inputs': ['New hires', 'Retained hires']},

    {'name': 'Monthly Attrition', 'category': 'Retention', 'kind': 'percent', 'direction': 'down',
     'target': 4.0, 'actual': 3.6, 'frequency': 'Monthly',
     'target_display': '≤4.0%', 'actual_display': '3.6%',
     'formula': 'Attrition % = (Employee Exits ÷ Average Headcount) × 100',
     'description': 'Share of headcount leaving each month. The threshold tightens to ≤3.5% in Q2 2027 — '
                    'scored against the current ≤4.0% until then.',
     'inputs': ['Employee exits', 'Average headcount']},

    {'name': 'Internal Promotion Rate', 'category': 'Growth', 'kind': 'percent', 'direction': 'up',
     'target': 60, 'actual': 45, 'frequency': 'Monthly',
     'target_display': '≥60%', 'actual_display': '45%',
     'formula': 'Promotion % = (Internal Promotions ÷ Total Leadership Positions Filled) × 100',
     'description': 'Share of leadership vacancies filled by promoting from within rather than hiring externally.',
     'inputs': ['Promotions', 'Leadership vacancies']},

    {'name': 'Employee Net Promoter Score (eNPS)', 'category': 'Engagement', 'kind': 'difference', 'direction': 'up',
     'target': 20, 'actual': 26, 'frequency': 'Quarterly',
     'target_display': '+20', 'actual_display': '+26',
     'formula': 'eNPS = % Promoters − % Detractors',
     'description': 'Net employee advocacy from the engagement survey. Ranges −100 to +100.',
     'inputs': ['Employee survey responses']},
]

# Add-Record modal inputs, one per KPI. `unit` is appended to the computed value
# for the non-percentage kinds, so it carries its own leading space.
MODAL_SPECS = [
    {'name': 'Net Headcount vs Plan',
     'a_label': 'Actual headcount', 'a_placeholder': 'e.g. 462',
     'b_label': 'Planned headcount', 'b_placeholder': 'e.g. 500'},
    {'name': 'Gross Hires / Month',
     'a_label': 'Actual hires', 'a_placeholder': 'e.g. 52',
     'b_label': 'Target hires', 'b_placeholder': 'e.g. 50'},
    {'name': 'Time-to-Fill (Agents)', 'unit': ' days',
     'a_label': 'Total days to fill agent positions', 'a_placeholder': 'e.g. 430',
     'b_label': 'Agent positions filled', 'b_placeholder': 'e.g. 50'},
    {'name': 'Time-to-Fill (Support/Leadership)', 'unit': ' days',
     'a_label': 'Total days to fill support/leadership positions', 'a_placeholder': 'e.g. 259',
     'b_label': 'Positions filled', 'b_placeholder': 'e.g. 7'},
    {'name': 'Offer Acceptance Rate',
     'a_label': 'Accepted offers', 'a_placeholder': 'e.g. 42',
     'b_label': 'Total offers extended', 'b_placeholder': 'e.g. 50'},
    {'name': '90-Day Retention Rate',
     'a_label': 'Employees still active after 90 days', 'a_placeholder': 'e.g. 41',
     'b_label': 'Employees hired 90 days ago', 'b_placeholder': 'e.g. 51'},
    {'name': 'Monthly Attrition',
     'a_label': 'Employee exits', 'a_placeholder': 'e.g. 17',
     'b_label': 'Average headcount', 'b_placeholder': 'e.g. 470'},
    {'name': 'Internal Promotion Rate',
     'a_label': 'Internal promotions', 'a_placeholder': 'e.g. 9',
     'b_label': 'Total leadership positions filled', 'b_placeholder': 'e.g. 20'},
    {'name': 'Employee Net Promoter Score (eNPS)',
     'a_label': 'Promoters (% of responses)', 'a_placeholder': 'e.g. 46',
     'b_label': 'Detractors (% of responses)', 'b_placeholder': 'e.g. 20'},
]

# Which part of the org a record belongs to.
DEPARTMENTS = [
    'Operations', 'Site Lead', 'Sales', 'HR', 'VINTAZK Academy', 'Finance',
    'Visual and Content Team', 'Social Media Management', 'Content Writing', 'Nexzys',
]

SCOPE = {
    'title': 'HR',
    'badge': 'HR',
    'blurb': 'Headcount against plan, hiring speed and quality, retention, and how the workforce feels about working here.',
}
