"""VCT (Visual Communication Team) branch definitions — SMM, Content, Visual.

VCT is the second LOB that splits into branches (after Sales), so it follows the
same convention: ``NAV_BRANCHES`` here drives the nested sidebar dropdown, and
``branch_*`` URLs take the branch slug.

PLACEHOLDER DATA — the `actual` numbers are invented so the scorecards and chart
render with something to look at. Targets, formulas and required inputs come
from the business. See apps/core/kpi.py for the dict shape and the math.
"""

# --- 1. Social Media Management ---------------------------------------------
_SMM_KPIS = [
    {'name': 'Applicant Lead Capture Rate', 'category': 'Recruitment Support', 'kind': 'percent', 'direction': 'up',
     'target': 90, 'actual': 93, 'frequency': 'Monthly',
     'target_display': '≥90%', 'actual_display': '93%',
     'formula': 'Capture Rate = (Qualified Applicant Leads Captured ÷ Total Qualified Hiring Inquiries) × 100',
     'description': 'Share of hiring inquiries coming through social that get captured as usable applicant leads.',
     'inputs': ['Hiring inquiries', 'Applicant leads captured']},

    # The target is written as a LEAD COUNT (80/month) while the formula is a
    # share-of-total percentage — the two don't line up, so this is tracked
    # without a scored target until the business confirms which one counts.
    {'name': 'Social Media Client Lead Contribution', 'category': 'Demand Gen', 'kind': 'percent', 'direction': 'up',
     'target': None, 'actual': 34.5, 'frequency': 'Monthly',
     'target_display': '80 qualified leads/month (per presentation)', 'actual_display': '34.5%',
     'formula': 'Contribution % = (Valid Client Leads from Social Media ÷ Total Valid Client Leads) × 100',
     'description': 'Share of all valid client leads that originate on social media. Note: the stated target is a '
                    'lead volume (80/month), not a contribution percentage — confirm which one is scored.',
     'inputs': ['Social media client leads', 'Total client leads']},

    {'name': 'Community Response Compliance', 'category': 'Community', 'kind': 'percent', 'direction': 'up',
     'target': 98, 'actual': 96.2, 'frequency': 'Monthly',
     'target_display': '≥98% within 30 min', 'actual_display': '96.2%',
     'formula': 'Compliance % = (Messages Responded Within SLA ÷ Total Messages Requiring Response) × 100',
     'description': 'Share of inbound messages and comments answered inside the 30-minute response SLA.',
     'inputs': ['Messages received', 'Responses within SLA']},
]

_SMM_MODAL = [
    {'name': 'Applicant Lead Capture Rate',
     'a_label': 'Qualified applicant leads captured', 'a_placeholder': 'e.g. 93',
     'b_label': 'Total qualified hiring inquiries', 'b_placeholder': 'e.g. 100'},
    {'name': 'Social Media Client Lead Contribution',
     'a_label': 'Valid client leads from social media', 'a_placeholder': 'e.g. 69',
     'b_label': 'Total valid client leads', 'b_placeholder': 'e.g. 200'},
    {'name': 'Community Response Compliance',
     'a_label': 'Messages responded within SLA', 'a_placeholder': 'e.g. 1246',
     'b_label': 'Total messages requiring response', 'b_placeholder': 'e.g. 1295'},
]


# --- 2. Content Writer -------------------------------------------------------
_CONTENT_KPIS = [
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

_CONTENT_MODAL = [
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


# --- 3. Visual Team ----------------------------------------------------------
_VISUAL_KPIS = [
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

_VISUAL_MODAL = [
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


BRANCHES = {
    'smm': {
        'slug': 'smm',
        'name': 'Social Media Management',
        'short': 'SMM',
        'blurb': 'Applicant and client lead capture from social, plus community response speed.',
        'kpis': _SMM_KPIS,
        'modal_specs': _SMM_MODAL,
    },
    'content': {
        'slug': 'content',
        'name': 'Content Writer',
        'short': 'Content',
        'blurb': 'Content engagement, sales-enablement delivery, and leads generated from content campaigns.',
        'kpis': _CONTENT_KPIS,
        'modal_specs': _CONTENT_MODAL,
    },
    'visual': {
        'slug': 'visual',
        'name': 'Visual Team',
        'short': 'Visual',
        'blurb': 'Creative quality and turnaround, employer brand perception, and campaign-driven leads.',
        'kpis': _VISUAL_KPIS,
        'modal_specs': _VISUAL_MODAL,
    },
}

# Consumed by apps.core.context_processors to build the nested sidebar nav.
NAV_BRANCHES = [(slug, branch['name']) for slug, branch in BRANCHES.items()]

# Where a record was published / which channel it came from.
CHANNELS = ['Facebook', 'Instagram', 'LinkedIn', 'TikTok', 'YouTube', 'Website / Blog', 'Email']

OVERVIEW_SCOPE = {
    'title': 'VCT',
    'badge': 'VCT',
    'blurb': 'The Visual Communication Team runs as three branches — Social Media Management, Content, and Visual — '
             'each with its own scorecard, targets, and data entry. Pick a branch to see where it stands.',
}


def get_branch(slug):
    """Return a branch definition, or None if the slug isn't one of ours."""
    return BRANCHES.get(slug)


def branch_scope(branch):
    """The {title, badge, blurb} header contract the shared KPI templates read."""
    return {
        'title': branch['name'],
        'badge': f"VCT · {branch['short']}",
        'blurb': branch['blurb'],
    }
