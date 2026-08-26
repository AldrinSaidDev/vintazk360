"""The reviewed aggregation configuration, decision by decision.

`kpi.0007` derived every input's aggregation from the formula and `kpi.0008`
corrected the both-sides-of-a-divide case. Both were inference. This one is not:
each entry below was reviewed against what the metric measures and approved by
the KPI owner, which is why it is an EXPLICIT MAP and not another walk of the
AST. A rule that produced this list would be a rule that had already been wrong
twice.

Keyed on (KPI name, input key) rather than pk, so the intent survives a rebuilt
database and reads as the decision it was. It also covers the Operations
business units in one line each: seven or eight rows share a KPI name, and they
share the answer too.

WHAT THIS FIXES. The inference refused to add up anything under a division,
which protects `average_headcount` but freezes the denominator of nearly every
rate: leads, tickets, survey responses and impressions are counts that must grow
as a period fills. `_TO_LAST` is the mirror image, where a numerator adds up
against a fixed denominator and the percentage passes 100 on the second entry.

STILL UNRESOLVED, deliberately left alone — see `_AWAITING_BUSINESS` at the
bottom. Four plan/target denominators whose answer is a reporting habit rather
than a property of the formula, and two notes that are not aggregation problems.
"""

from django.db import migrations

# --- approved: counts of things that happened, so they add up ---------------
_TO_SUM = [
    ('Content Engagement Rate', 'reach'),
    ('Collections Efficiency', 'amount_due'),
    ('Days Sales Outstanding (DSO)', 'total_credit_sales'),
    ('Payroll On-Time Completion', 'total_payroll_runs'),
    ('Vendor Payment Timeliness', 'total_vendor_payments'),
    ('90-Day Retention Rate', 'employees_hired_90_days_ago'),
    ('Internal Promotion Rate', 'total_leadership_positions_filled'),
    ('Offer Acceptance Rate', 'total_offers_extended'),
    ('Time-to-Fill (Agents)', 'agent_positions_filled'),
    ('Time-to-Fill (Support/Leadership)', 'positions_filled'),
    ('IT SLA Compliance', 'total_tickets'),
    ('System Uptime', 'total_scheduled_time_hrs'),
    ('Billable Hours Achievement', 'required_billable_hours'),
    ('CSAT', 'total_survey_responses'),
    ('EBR Completion', 'scheduled_reviews'),
    ('Click-Through Rate (CTR)', 'impressions'),
    ('Cost per Qualified Lead (CPL)', 'qualified_leads'),
    ('Dial-to-Discovery Rate', 'total_dials'),
    ('Landing Page Conversion Rate', 'website_visitors'),
    ('Lead Nurturing Rate', 'qualified_leads'),
    ('Lead Qualification Rate', 'total_leads'),
    ('Opportunity Conversion Rate', 'qualified_leads'),
    ('Client Satisfaction (CSAT)', 'total_survey_responses'),
    ('Compliance Score', 'total_audits'),
    ('EBITDA Margin', 'total_revenue'),
    ('Employee Engagement Score', 'valid_survey_responses'),
    ('Profitability', 'total_revenue'),
    ('SLA Compliance', 'total_slas'),
    ('Applicant Lead Capture Rate', 'total_qualified_hiring_inquiries'),
    ('Community Response Compliance', 'total_messages_requiring_response'),
    ('Social Media Client Lead Contribution', 'total_valid_client_leads'),
    ('90-Day Retention Rate', 'eligible_graduates'),
    ('Leadership Development Attainment', 'total_leadership_trainees'),
    ('Speed-to-Proficiency', 'graduates_who_reached_proficiency'),
    ('Trainee Satisfaction Score', 'valid_survey_responses'),
    ('Training Pass Rate', 'total_graduates'),
    ('Training Throughput', 'total_trainees'),
    ('Employer Brand Rating', 'valid_survey_responses'),
    ('First-Pass Approval Rate', 'total_deliverables_reviewed'),
    ('On-Time Delivery Rate', 'total_deliverables_due'),
    # Plan/target denominators resolved as per-slice counts: a week's worth of
    # reports due, a week's worth of modules due. The other four are unresolved.
    ('Financial Report Timeliness', 'total_required_reports'),
    ('Learning Material Currency', 'modules_due_for_review'),
]

# --- approved: the metric names an average, so average the readings ---------
# Covers Operations (7 units, all sharing the KPI name "Attrition Rate"),
# Site Lead (also "Attrition Rate") and HR ("Monthly Attrition"): the same
# decision everywhere the input is called `average_headcount`.
_TO_AVG = [
    ('Attrition Rate', 'average_headcount'),
    ('Monthly Attrition', 'average_headcount'),
]

# --- approved: levels, not totals -------------------------------------------
# All six currently SUM against a fixed denominator, so today a second entry in
# a period pushes the percentage past 100.
_TO_LAST = [
    ('Net Headcount vs Plan', 'actual_headcount'),
    ('AI Copilot Adoption', 'employees_using_ai_tools'),
    ('Workstation Readiness', 'ready_workstations'),
    ('Client Retention Rate', 'clients_retained'),
    ('Seat Expansion', 'actual_billable_headcount'),
    ('Employee Retention Rate', 'employees_remaining'),
]

# Left exactly as they are, and NOT an oversight in any of these six cases.
_AWAITING_BUSINESS = """
    planned_output      Operational Efficiency          Site Lead
    planned_projects    Project / Initiative Completion Site Lead
    planned_strategies  Content Strategy Completion     Content Writing
    planned_materials   Sales Enablement Content Compl. Content Writing
        Four plan denominators. SUM means each entry carries its own slice of
        the plan; LAST means every entry restates the whole period's. Both land
        on the same figure at period close and differ all the way through it,
        so the answer is a reporting habit and has to come from the team.

    employees_at_start_of_period   Employee Retention Rate   Site Lead
        Properly wants a FIRST aggregation, which does not exist. Harmless on
        LAST while every entry restates the same opening number. Revisit if a
        FIRST option is ever added.

    day_0_start_date               New-Hire Provisioning     Nexzys
        Not an aggregation problem. A period covering several new hires wants
        one record per hire, which is a data-model question.
"""

def apply_decisions(apps, schema_editor):
    KpiInput = apps.get_model('kpi', 'KpiInput')
    wanted = {}
    for pairs, aggregation in ((_TO_SUM, 'sum'), (_TO_AVG, 'avg'), (_TO_LAST, 'last')):
        for name, key in pairs:
            wanted[(name, key)] = aggregation

    changed, matched = [], set()
    for row in KpiInput.objects.select_related('kpi'):
        target = wanted.get((row.kpi.name, row.key))
        if target is None:
            continue
        matched.add((row.kpi.name, row.key))
        if row.aggregation != target:
            row.aggregation = target
            changed.append(row)

    KpiInput.objects.bulk_update(changed, ['aggregation'], batch_size=200)

    # A KPI renamed since the review is the one failure mode this shape has:
    # its decision would silently not land. So check that every approved name
    # was FOUND, rather than that a fixed number of rows moved.
    #
    # NOT a hardcoded row count, which was the first attempt and was wrong: it
    # fired on any database without this seed data, taking the test suite and
    # every fresh deploy down with it. An empty table means there is nothing to
    # configure yet, not that something is broken.
    if not KpiInput.objects.exists():
        return

    missing = sorted(set(wanted) - matched)
    if missing:
        raise RuntimeError(
            'These approved decisions matched no KPI input, so they did not '
            'apply: ' + ', '.join(f'{name} / {key}' for name, key in missing) +
            '. A KPI has probably been renamed since the review — check the '
            'names in _TO_SUM / _TO_AVG / _TO_LAST against the database.'
        )


def revert(apps, schema_editor):
    """Back to what `kpi.0008` derived, so the review can be redone from scratch.

    Not a stored per-row snapshot: 0008's derivation is reproducible, and
    re-running it is both simpler and honest about what "before" means.
    """
    from apps.kpi import formula
    from apps.kpi.models import DataType

    KpiDefinition = apps.get_model('kpi', 'KpiDefinition')
    KpiInput = apps.get_model('kpi', 'KpiInput')
    changed = []

    for kpi in KpiDefinition.objects.prefetch_related('inputs'):
        try:
            denominators = formula.divisors(kpi.expression or '')
        except formula.FormulaError:
            denominators = set()
        for row in kpi.inputs.all():
            derived = (
                'last'
                if row.data_type == DataType.DATE or row.key in denominators
                else 'sum'
            )
            if row.aggregation != derived:
                row.aggregation = derived
                changed.append(row)

    KpiInput.objects.bulk_update(changed, ['aggregation'], batch_size=200)


class Migration(migrations.Migration):

    dependencies = [
        ('kpi', '0008_fix_shared_divisor_aggregation'),
    ]

    operations = [
        migrations.RunPython(apply_decisions, revert),
    ]
