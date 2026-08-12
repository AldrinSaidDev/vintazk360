"""Content Writing KPI definitions — a standalone department.

PLACEHOLDER DATA — the `actual` numbers are invented so the scorecard and chart
render with something to look at. Targets, formulas and required inputs come
from the business. See apps/core/kpi.py for the dict shape and the math.
"""

KPIS = [
    {'name': 'Content Engagement Rate', 'category': 'Engagement', 'kind': 'percent', 'direction': 'up',
     'target': 1, 'actual': 1.4, 'frequency': 'Monthly',
     'target_display': '≥1%', 'actual_display': '1.4%',
     'formula': 'Engagement Rate = (Engagements ÷ Reach) × 100',
     'description': 'Share of reached users who engage with a post. Note: the target is written as "≥1% of '
                    'followers" while the formula divides by reach — scored against reach as written.',
     'inputs': ['Reach', 'Engagements']},

    {'name': 'Sales Enablement Content Completion', 'category': 'Delivery', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 90, 'frequency': 'Monthly',
     'target_display': '≥95%', 'actual_display': '90%',
     'formula': 'Completion % = (Completed Materials ÷ Planned Materials) × 100',
     'description': 'Share of planned sales-support materials actually delivered in the period.',
     'inputs': ['Planned content', 'Completed content']},

    {'name': 'Link Click Performance', 'category': 'Engagement', 'kind': 'count', 'direction': 'up',
     'target': None, 'actual': 1240, 'frequency': 'Monthly',
     'target_display': 'Meet/exceed campaign target', 'actual_display': '1,240 clicks',
     'formula': 'Total Link Clicks during the measurement period',
     'description': 'Total link clicks earned by content in the period. The target moves per campaign, so this is '
                    'tracked rather than scored against a fixed number.',
     'inputs': ['Link clicks']},

    {'name': 'Content Strategy Completion', 'category': 'Delivery', 'kind': 'percent', 'direction': 'up',
     'target': 95, 'actual': 100, 'frequency': 'Monthly',
     'target_display': '≥95%', 'actual_display': '100%',
     'formula': 'Completion % = (Completed Strategies ÷ Planned Strategies) × 100',
     'description': 'Share of planned content strategies documented and signed off in the period.',
     'inputs': ['Planned strategies', 'Completed strategies']},

    {'name': 'Content-to-Lead Contribution', 'category': 'Demand Gen', 'kind': 'count', 'direction': 'up',
     'target': 80, 'actual': 62, 'frequency': 'Monthly',
     'target_display': '80 qualified leads/month', 'actual_display': '62 leads',
     'formula': 'Qualified Leads Generated from Content Campaigns',
     'description': 'Qualified leads attributed to content campaigns.',
     'inputs': ['Qualified leads from content']},
]

# Add-Record modal inputs, one per KPI. `unit` is appended to the computed value
# for the non-percentage kinds.
MODAL_SPECS = [
    {'name': 'Content Engagement Rate',
     'a_label': 'Engagements', 'a_placeholder': 'e.g. 1680',
     'b_label': 'Reach', 'b_placeholder': 'e.g. 120000'},
    {'name': 'Sales Enablement Content Completion',
     'a_label': 'Completed materials', 'a_placeholder': 'e.g. 18',
     'b_label': 'Planned materials', 'b_placeholder': 'e.g. 20'},
    {'name': 'Link Click Performance', 'unit': 'clicks',
     'a_label': 'Total link clicks', 'a_placeholder': 'e.g. 1240'},
    {'name': 'Content Strategy Completion',
     'a_label': 'Completed strategies', 'a_placeholder': 'e.g. 4',
     'b_label': 'Planned strategies', 'b_placeholder': 'e.g. 4'},
    {'name': 'Content-to-Lead Contribution', 'unit': 'qualified leads',
     'a_label': 'Qualified leads from content campaigns', 'a_placeholder': 'e.g. 62'},
]

# Where the content was published.
CHANNELS = ['Website / Blog', 'Facebook', 'Instagram', 'LinkedIn', 'Email', 'Sales Collateral']

SCOPE = {
    'north_star': 'Qualified client opportunities generated through content and social media per month',
    'icons': ['pencil-square-o', 'file-text-o', 'quote-right'],
    'title': 'Content Writing',
    'badge': 'Content',
    'blurb': 'Content engagement, sales-enablement delivery, and leads generated from content campaigns.',
}
