"""SMM (Social Media Management) KPI definitions — a standalone department.

PLACEHOLDER DATA — the `actual` numbers are invented so the scorecard and chart
render with something to look at. Targets, formulas and required inputs come
from the business. See apps/core/kpi.py for the dict shape and the math.
"""

KPIS = [
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

# Add-Record modal inputs, one per KPI.
MODAL_SPECS = [
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

# Which platform a record came from.
CHANNELS = ['Facebook', 'Instagram', 'LinkedIn', 'TikTok', 'YouTube', 'X / Twitter', 'Messenger']

SCOPE = {
    'title': 'Social Media Management',
    'badge': 'SMM',
    'blurb': 'Applicant and client lead capture from social, plus how fast the community gets a response.',
}
