"""VINTAZK Academy (Training & Development) KPI definitions.

PLACEHOLDER DATA — the `actual` numbers are invented so the scorecard and chart
render with something to look at. Targets, formulas and required inputs come
from the business. See apps/core/kpi.py for the dict shape and the math.
"""

KPIS = [
    {'name': 'Training Throughput', 'category': 'Throughput', 'kind': 'percent', 'direction': 'up',
     'target': 90, 'actual': 93, 'frequency': 'Monthly',
     'target_display': '≥90%', 'actual_display': '93%',
     'formula': 'Throughput % = (Graduates ÷ Total Trainees) × 100',
     'description': 'Share of trainees who make it through the program rather than dropping out.',
     'inputs': ['Total trainees', 'Graduates']},

    {'name': 'Training Pass Rate', 'category': 'Quality', 'kind': 'percent', 'direction': 'up',
     'target': 90, 'actual': 88, 'frequency': 'Monthly',
     'target_display': '≥90%', 'actual_display': '88%',
     'formula': 'Pass Rate = (Passers ÷ Total Graduates) × 100',
     'description': 'Share of graduates who pass the final assessment.',
     'inputs': ['Graduates', 'Passers']},

    {'name': 'Speed-to-Proficiency', 'category': 'Throughput', 'kind': 'average', 'direction': 'down',
     'target': 40, 'actual': 44, 'frequency': 'Monthly',
     'target_display': '≤40 days', 'actual_display': '44 days',
     'formula': 'Average Days = Total Days to Reach Proficiency ÷ Graduates Who Reached Proficiency',
     'description': 'Average days from program start to a graduate performing at production standard.',
     'inputs': ['Days to proficiency per graduate']},

    {'name': '90-Day Retention Rate', 'category': 'Retention', 'kind': 'percent', 'direction': 'up',
     'target': 92, 'actual': 94, 'frequency': 'Monthly',
     'target_display': '≥92%', 'actual_display': '94%',
     'formula': 'Retention % = (Graduates Active on Day 90 ÷ Total Graduates Eligible for Measurement) × 100',
     'description': 'Share of graduates still active 90 days after leaving the program.',
     'inputs': ['Eligible graduates', 'Retained graduates']},

    {'name': 'Leadership Development Attainment', 'category': 'Leadership', 'kind': 'percent', 'direction': 'up',
     'target': 90, 'actual': 78, 'frequency': 'Quarterly',
     'target_display': '90%', 'actual_display': '78%',
     'formula': 'Attainment % = (Leadership Program Graduates ÷ Total Leadership Trainees) × 100',
     'description': 'Completion rate of the leadership development track — the internal promotion pipeline.',
     'inputs': ['Leadership trainees', 'Graduates']},

    {'name': 'Trainee Satisfaction Score', 'category': 'Experience', 'kind': 'average', 'direction': 'up',
     'target': 4.7, 'actual': 4.8, 'frequency': 'Monthly',
     'target_display': '≥4.7 / 5.0', 'actual_display': '4.8 / 5.0',
     'formula': 'Average Rating = Total Survey Rating Points ÷ Valid Survey Responses',
     'description': 'Average rating trainees give the program on a 5-point scale.',
     'inputs': ['Survey ratings', 'Valid responses']},

    {'name': 'Learning Material Currency', 'category': 'Quality', 'kind': 'percent', 'direction': 'up',
     'target': 100, 'actual': 100, 'frequency': 'Quarterly',
     'target_display': '100%', 'actual_display': '100%',
     'formula': 'Currency % = (Modules Reviewed & Approved On Time ÷ Modules Due for Review) × 100',
     'description': 'Share of training modules reviewed and re-approved on schedule, so nothing taught is out of date.',
     'inputs': ['Modules due', 'Modules reviewed and approved']},
]

# Add-Record modal inputs, one per KPI. `unit` is appended to the computed value
# for the non-percentage kinds, so it carries its own leading space.
MODAL_SPECS = [
    {'name': 'Training Throughput',
     'a_label': 'Graduates', 'a_placeholder': 'e.g. 93',
     'b_label': 'Total trainees', 'b_placeholder': 'e.g. 100'},
    {'name': 'Training Pass Rate',
     'a_label': 'Passers', 'a_placeholder': 'e.g. 82',
     'b_label': 'Total graduates', 'b_placeholder': 'e.g. 93'},
    {'name': 'Speed-to-Proficiency', 'unit': ' days',
     'a_label': 'Total days to reach proficiency', 'a_placeholder': 'e.g. 3960',
     'b_label': 'Graduates who reached proficiency', 'b_placeholder': 'e.g. 90'},
    {'name': '90-Day Retention Rate',
     'a_label': 'Graduates active on day 90', 'a_placeholder': 'e.g. 79',
     'b_label': 'Eligible graduates', 'b_placeholder': 'e.g. 84'},
    {'name': 'Leadership Development Attainment',
     'a_label': 'Leadership program graduates', 'a_placeholder': 'e.g. 14',
     'b_label': 'Total leadership trainees', 'b_placeholder': 'e.g. 18'},
    {'name': 'Trainee Satisfaction Score', 'unit': ' / 5.0',
     'a_label': 'Total survey rating points', 'a_placeholder': 'e.g. 408',
     'b_label': 'Valid survey responses', 'b_placeholder': 'e.g. 85'},
    {'name': 'Learning Material Currency',
     'a_label': 'Modules reviewed & approved on time', 'a_placeholder': 'e.g. 24',
     'b_label': 'Modules due for review', 'b_placeholder': 'e.g. 24'},
]

# Which program a record belongs to.
PROGRAMS = [
    'New Hire Training', 'Product / Account Training', 'Upskilling',
    'Leadership Development', 'Compliance & Refresher',
]

SCOPE = {
    # Reserved: the Academy North Star is still being defined.
    'north_star': 'To be defined',
    'north_star_pending': True,
    'lead_shift': 'far',  # sits further off the right edge
    'icons': ['graduation-cap', 'book', 'certificate'],
    'title': 'VINTAZK Academy',
    'badge': 'Academy',
    'blurb': 'Trainees through the program, how well they perform after it, and how fast they get to production standard.',
}
