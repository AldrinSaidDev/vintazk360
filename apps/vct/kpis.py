"""Visual and Content Team (VCT) KPI definitions.

VCT is the visual/creative department — a standalone LOB, not a parent of SMM or
Content Writing (those are their own departments; see apps/smm and apps/content).
The name is always spelled out in the UI; "VCT" only appears in code/slugs.

PLACEHOLDER DATA — the `actual` numbers are invented so the scorecard and chart
render with something to look at. Targets, formulas and required inputs come
from the business. See apps/core/kpi.py for the dict shape and the math.
"""

KPIS = [
    {'name': 'First-Pass Approval Rate', 'category': 'Quality', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 91, 'frequency': 'Monthly',
     'target_display': '≥95%', 'actual_display': '91%',
     'formula': 'Approval Rate = (Deliverables Approved on First Review ÷ Total Deliverables Reviewed) × 100',
     'description': 'Share of creative approved on the first review — the measure of rework avoided.',
     'inputs': ['Deliverables reviewed', 'First-pass approvals']},

    {'name': 'On-Time Delivery Rate', 'category': 'Delivery', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 97, 'frequency': 'Monthly',
     'target_display': '≥95%', 'actual_display': '97%',
     'formula': 'Delivery Rate = (Deliverables Submitted On Time ÷ Total Deliverables Due) × 100',
     'description': 'Share of creative deliverables submitted by their due date.',
     'inputs': ['Deliverables due', 'On-time submissions']},

    {'name': 'Link Click Performance', 'category': 'Engagement', 'kind': 'count', 'direction': 'up',
     'target': 250, 'actual': 310, 'frequency': 'Monthly',
     'target_display': '>250 clicks', 'actual_display': '310 clicks',
     'formula': 'Total Link Clicks during the measurement period',
     'description': 'Total link clicks earned by visual assets. The standing floor is 250; the working goal is to '
                    'beat the previous month.',
     'inputs': ['Link clicks']},

    {'name': 'Employer Brand Rating', 'category': 'Employer Brand', 'kind': 'average', 'direction': 'up',
     'target': 4.5, 'actual': 4.6, 'frequency': 'Quarterly',
     'target_display': '≥4.5 / 5.0', 'actual_display': '4.6 / 5.0',
     'formula': 'Employer Brand Rating = Average Employer Rating Score',
     'description': 'Average score the employer brand earns in rating surveys, on a 5-point scale.',
     'inputs': ['Employer rating survey']},

    {'name': 'Marketing Conversion Contribution', 'category': 'Demand Gen', 'kind': 'count', 'direction': 'up',
     'target': 80, 'actual': 71, 'frequency': 'Monthly',
     'target_display': '80 qualified leads/month', 'actual_display': '71 leads',
     'formula': 'Qualified Leads Generated from Marketing Campaigns',
     'description': 'Qualified leads attributed to marketing campaigns.',
     'inputs': ['Qualified marketing leads']},
]

# Add-Record modal inputs, one per KPI. `unit` is appended to the computed value
# for the non-percentage kinds, so it carries its own leading space.
MODAL_SPECS = [
    {'name': 'First-Pass Approval Rate',
     'a_label': 'Deliverables approved on first review', 'a_placeholder': 'e.g. 91',
     'b_label': 'Total deliverables reviewed', 'b_placeholder': 'e.g. 100'},
    {'name': 'On-Time Delivery Rate',
     'a_label': 'Deliverables submitted on time', 'a_placeholder': 'e.g. 97',
     'b_label': 'Total deliverables due', 'b_placeholder': 'e.g. 100'},
    {'name': 'Link Click Performance', 'unit': 'clicks',
     'a_label': 'Total link clicks', 'a_placeholder': 'e.g. 310'},
    {'name': 'Employer Brand Rating', 'unit': ' / 5.0',
     'a_label': 'Total rating points', 'a_placeholder': 'e.g. 331',
     'b_label': 'Valid survey responses', 'b_placeholder': 'e.g. 72'},
    {'name': 'Marketing Conversion Contribution', 'unit': 'qualified leads',
     'a_label': 'Qualified leads from marketing campaigns', 'a_placeholder': 'e.g. 71'},
]

# Where a record was published / which channel it came from.
CHANNELS = ['Facebook', 'Instagram', 'LinkedIn', 'TikTok', 'YouTube', 'Website / Blog', 'Email']

SCOPE = {
    'title': 'Visual and Content Team',
    'badge': 'Visual and Content Team',
    'blurb': 'Creative quality and turnaround, employer brand perception, and campaign-driven leads.',
}
