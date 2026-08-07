"""Sales sub-team ("branch") definitions — SEO & Google Ads, Lead Gen, Transitions.

Sales is the first LOB that splits into branches: each branch gets its own
Dashboard / Import Data / KPI Definitions / KPI Management, all served by the
same four views + templates and driven by the data below.

PLACEHOLDER DATA. The `actual` numbers are invented so the scorecards and chart
render with something to look at — only the targets, formulas and required
inputs come from the business. When the KPI models exist, replace the reads of
``BRANCHES`` with a DB query returning the same shape.

Per-KPI shape
-------------
kind          how the value is produced (also drives the Add-Record modal):
              'count'   → a single tally (leads, dials, calls)
              'percent' → a ÷ b × 100
              'cost'    → a ÷ b, read as money (cost per lead)
direction     'up'   = higher is better
              'down' = lower is better (cost)
target_min /  the target BAND. Sales targets are ranges ("40–80/month"), so
target_max    anything inside the band counts as fully on target. ``None``
              means the KPI is tracked but not scored (the derived rates, and
              anything the business hasn't set a number for yet).
inputs        the raw data someone has to collect — shown on the definitions
              page so the numbers can actually be gathered.
"""

# --- SEO & Google Ads --------------------------------------------------------
_SEO_KPIS = [
    {'name': 'Qualified Leads Generated', 'category': 'Demand Gen', 'kind': 'count', 'direction': 'up',
     'target_min': 40, 'target_max': 80, 'actual': 58,
     'target_display': '40–80/month', 'actual_display': '58 leads', 'frequency': 'Monthly',
     'formula': 'Qualified Leads = Count of leads accepted after qualification',
     'description': 'Leads from SEO and paid search that pass qualification and are accepted by sales.',
     'inputs': ['Qualified leads']},

    {'name': 'Discovery Calls Generated', 'category': 'Pipeline', 'kind': 'count', 'direction': 'up',
     'target_min': 12, 'target_max': 24, 'actual': 15,
     'target_display': '12–24/month', 'actual_display': '15 calls', 'frequency': 'Monthly',
     'formula': 'Discovery Calls = Count of discovery calls booked from qualified leads',
     'description': 'Discovery calls booked off the back of qualified leads from this channel.',
     'inputs': ['Scheduled discovery calls']},

    {'name': 'Landing Page Conversion Rate', 'category': 'Conversion', 'kind': 'percent', 'direction': 'up',
     'target_min': 8, 'target_max': 16, 'actual': 6.9,
     'target_display': '8–16%', 'actual_display': '6.9%', 'frequency': 'Monthly',
     'formula': 'Conversion Rate = (Qualified Leads ÷ Website Visitors) × 100',
     'description': 'Share of landing-page visitors who become qualified leads.',
     'inputs': ['Website visitors', 'Qualified leads']},

    {'name': 'Cost per Qualified Lead (CPL)', 'category': 'Efficiency', 'kind': 'cost', 'direction': 'down',
     'target_min': 750, 'target_max': 1500, 'actual': 1180,
     'target_display': '₱1,500 → ₱750', 'actual_display': '₱1,180', 'frequency': 'Monthly',
     'formula': 'CPL = Ad Spend ÷ Qualified Leads',
     'description': 'Ad spend needed to produce one qualified lead. The target is a reduction journey — '
                    '₱1,500 is the ceiling today, ₱750 the goal.',
     'inputs': ['Ad spend', 'Qualified leads']},

    # The presentation states the target as a CLICK volume (500–1,000) while the
    # formula is a percentage — the two don't line up, so this one is tracked
    # without a scored target until the business confirms which it wants.
    {'name': 'Click-Through Rate (CTR)', 'category': 'Conversion', 'kind': 'percent', 'direction': 'up',
     'target_min': None, 'target_max': None, 'actual': 3.8,
     'target_display': '500–1,000 clicks (per presentation)', 'actual_display': '3.8%', 'frequency': 'Monthly',
     'formula': 'CTR = (Clicks ÷ Impressions) × 100',
     'description': 'Share of ad impressions that earn a click. Note: the presentation target is written as a '
                    'click volume (500–1,000), not a CTR percentage — confirm which one is scored.',
     'inputs': ['Clicks', 'Impressions']},
]

_SEO_MODAL = [
    {'name': 'Qualified Leads Generated', 'a_label': 'Qualified leads accepted', 'a_placeholder': 'e.g. 58'},
    {'name': 'Discovery Calls Generated', 'a_label': 'Discovery calls booked', 'a_placeholder': 'e.g. 15'},
    {'name': 'Landing Page Conversion Rate', 'a_label': 'Qualified leads', 'a_placeholder': 'e.g. 58',
     'b_label': 'Website visitors', 'b_placeholder': 'e.g. 840'},
    {'name': 'Cost per Qualified Lead (CPL)', 'a_label': 'Ad spend (₱)', 'a_placeholder': 'e.g. 68440',
     'b_label': 'Qualified leads', 'b_placeholder': 'e.g. 58'},
    {'name': 'Click-Through Rate (CTR)', 'a_label': 'Clicks', 'a_placeholder': 'e.g. 760',
     'b_label': 'Impressions', 'b_placeholder': 'e.g. 20000'},
]


# --- Lead Generation ---------------------------------------------------------
_LEADGEN_KPIS = [
    {'name': 'Qualified Leads Generated', 'category': 'Demand Gen', 'kind': 'count', 'direction': 'up',
     'target_min': 1220, 'target_max': 1340, 'actual': 1185,
     'target_display': '1,220–1,340/month', 'actual_display': '1,185 leads', 'frequency': 'Monthly',
     'formula': 'Count of qualified leads generated',
     'description': 'Total qualified leads produced by the lead generation team in the period.',
     'inputs': ['Qualified leads']},

    {'name': 'Sales Opportunities', 'category': 'Pipeline', 'kind': 'count', 'direction': 'up',
     'target_min': 47, 'target_max': 69, 'actual': 52,
     'target_display': '47–69/month', 'actual_display': '52 opportunities', 'frequency': 'Monthly',
     'formula': 'Count of qualified opportunities created',
     'description': 'Qualified opportunities created from the lead pool and entered into the pipeline.',
     'inputs': ['Opportunities']},

    # The source table carries two separate bands under one row (Lead Gen and
    # Referral). Split so each keeps its own target instead of blending them.
    {'name': 'New Logos / HC — Lead Gen', 'category': 'Growth', 'kind': 'count', 'direction': 'up',
     'target_min': 9, 'target_max': 44, 'actual': 12,
     'target_display': '9–44 HC/month', 'actual_display': '12 HC', 'frequency': 'Monthly',
     'formula': 'Count of successful hires/clients attributed to lead generation',
     'description': 'New logos or headcount won where lead generation is the attributed source.',
     'inputs': ['New logos or headcount']},

    {'name': 'New Logos / HC — Referral', 'category': 'Growth', 'kind': 'count', 'direction': 'up',
     'target_min': 4, 'target_max': 18, 'actual': 3,
     'target_display': '4–18 HC/month', 'actual_display': '3 HC', 'frequency': 'Monthly',
     'formula': 'Count of successful hires/clients attributed to referral',
     'description': 'New logos or headcount won where referral is the attributed source.',
     'inputs': ['New logos or headcount']},

    {'name': 'Lead Qualification Rate', 'category': 'Conversion', 'kind': 'percent', 'direction': 'up',
     'target_min': None, 'target_max': None, 'actual': 41.2,
     'target_display': 'No target set', 'actual_display': '41.2%', 'frequency': 'Monthly',
     'formula': 'Qualified Leads ÷ Total Leads × 100',
     'description': 'Derived KPI — how much of the raw lead volume survives qualification.',
     'inputs': ['Total leads', 'Qualified leads']},

    {'name': 'Opportunity Conversion Rate', 'category': 'Conversion', 'kind': 'percent', 'direction': 'up',
     'target_min': None, 'target_max': None, 'actual': 4.4,
     'target_display': 'No target set', 'actual_display': '4.4%', 'frequency': 'Monthly',
     'formula': 'Sales Opportunities ÷ Qualified Leads × 100',
     'description': 'Derived KPI — how many qualified leads turn into real sales opportunities.',
     'inputs': ['Opportunities', 'Qualified leads']},
]

_LEADGEN_MODAL = [
    {'name': 'Qualified Leads Generated', 'a_label': 'Qualified leads', 'a_placeholder': 'e.g. 1185'},
    {'name': 'Sales Opportunities', 'a_label': 'Qualified opportunities created', 'a_placeholder': 'e.g. 52'},
    {'name': 'New Logos / HC — Lead Gen', 'a_label': 'Hires/clients from lead gen', 'a_placeholder': 'e.g. 12'},
    {'name': 'New Logos / HC — Referral', 'a_label': 'Hires/clients from referral', 'a_placeholder': 'e.g. 3'},
    {'name': 'Lead Qualification Rate', 'a_label': 'Qualified leads', 'a_placeholder': 'e.g. 1185',
     'b_label': 'Total leads', 'b_placeholder': 'e.g. 2876'},
    {'name': 'Opportunity Conversion Rate', 'a_label': 'Sales opportunities', 'a_placeholder': 'e.g. 52',
     'b_label': 'Qualified leads', 'b_placeholder': 'e.g. 1185'},
]


# --- Transitions Team --------------------------------------------------------
_TRANSITIONS_KPIS = [
    {'name': 'Qualified Leads Managed', 'category': 'Activity', 'kind': 'count', 'direction': 'up',
     'target_min': None, 'target_max': None, 'actual': 640,
     'target_display': 'Tracked monthly', 'actual_display': '640 leads', 'frequency': 'Monthly',
     'formula': 'Count of qualified leads handled by the team',
     'description': 'Qualified leads the transitions team is actively working. Reported monthly; '
                    'no numeric target set yet.',
     'inputs': ['Qualified leads']},

    {'name': 'Lead Nurturing', 'category': 'Activity', 'kind': 'count', 'direction': 'up',
     'target_min': None, 'target_max': None, 'actual': 412,
     'target_display': 'Tracked monthly', 'actual_display': '412 follow-ups', 'frequency': 'Monthly',
     'formula': 'Count of follow-ups / nurtured leads completed',
     'description': 'Follow-up and nurture activities completed against the managed lead pool. '
                    'Reported monthly; no numeric target set yet.',
     'inputs': ['Follow-up activities', 'Nurtured leads']},

    {'name': 'Total Dials', 'category': 'Activity', 'kind': 'count', 'direction': 'up',
     'target_min': 1560, 'target_max': 2280, 'actual': 1840,
     'target_display': '1,560–2,280/month', 'actual_display': '1,840 dials', 'frequency': 'Monthly',
     'formula': 'Count of outbound dials made',
     'description': 'Outbound dial volume — the activity base the whole funnel sits on.',
     'inputs': ['Total dials']},

    {'name': 'Discovery Calls Scheduled', 'category': 'Pipeline', 'kind': 'count', 'direction': 'up',
     'target_min': 47, 'target_max': 69, 'actual': 41,
     'target_display': '47–69/month', 'actual_display': '41 calls', 'frequency': 'Monthly',
     'formula': 'Count of discovery calls successfully scheduled',
     'description': 'Discovery calls the team gets on the calendar from its outbound effort.',
     'inputs': ['Scheduled discovery calls']},

    {'name': 'Dial-to-Discovery Rate', 'category': 'Conversion', 'kind': 'percent', 'direction': 'up',
     'target_min': None, 'target_max': None, 'actual': 2.2,
     'target_display': 'No target set', 'actual_display': '2.2%', 'frequency': 'Monthly',
     'formula': 'Discovery Calls Scheduled ÷ Total Dials × 100',
     'description': 'Derived KPI — how many dials it takes to book a discovery call.',
     'inputs': ['Discovery calls', 'Total dials']},

    {'name': 'Lead Nurturing Rate', 'category': 'Conversion', 'kind': 'percent', 'direction': 'up',
     'target_min': None, 'target_max': None, 'actual': 64.4,
     'target_display': 'No target set', 'actual_display': '64.4%', 'frequency': 'Monthly',
     'formula': 'Nurtured Leads ÷ Qualified Leads × 100',
     'description': 'Derived KPI — share of the managed lead pool that actually gets nurtured.',
     'inputs': ['Nurtured leads', 'Qualified leads']},
]

_TRANSITIONS_MODAL = [
    {'name': 'Qualified Leads Managed', 'a_label': 'Qualified leads handled', 'a_placeholder': 'e.g. 640'},
    {'name': 'Lead Nurturing', 'a_label': 'Follow-ups / nurtured leads', 'a_placeholder': 'e.g. 412'},
    {'name': 'Total Dials', 'a_label': 'Outbound dials made', 'a_placeholder': 'e.g. 1840'},
    {'name': 'Discovery Calls Scheduled', 'a_label': 'Discovery calls scheduled', 'a_placeholder': 'e.g. 41'},
    {'name': 'Dial-to-Discovery Rate', 'a_label': 'Discovery calls scheduled', 'a_placeholder': 'e.g. 41',
     'b_label': 'Total dials', 'b_placeholder': 'e.g. 1840'},
    {'name': 'Lead Nurturing Rate', 'a_label': 'Nurtured leads', 'a_placeholder': 'e.g. 412',
     'b_label': 'Qualified leads', 'b_placeholder': 'e.g. 640'},
]


BRANCHES = {
    'seo': {
        'slug': 'seo',
        'name': 'SEO & Google Ads',
        'blurb': 'Organic and paid search — lead volume, landing-page conversion, and cost efficiency.',
        'kpis': _SEO_KPIS,
        'modal_kpis': _SEO_MODAL,
    },
    'leadgen': {
        'slug': 'leadgen',
        'name': 'Lead Generation',
        'blurb': 'Outbound lead volume through to qualified opportunities and new logos.',
        'kpis': _LEADGEN_KPIS,
        'modal_kpis': _LEADGEN_MODAL,
    },
    'transitions': {
        'slug': 'transitions',
        'name': 'Transitions Team',
        'blurb': 'Dial activity, lead nurturing, and discovery calls booked from the managed lead pool.',
        'kpis': _TRANSITIONS_KPIS,
        'modal_kpis': _TRANSITIONS_MODAL,
    },
}

# Consumed by apps.core.context_processors to build the nested sidebar nav.
# Any LOB app that splits into sub-teams can expose the same constant.
NAV_BRANCHES = [(slug, branch['name']) for slug, branch in BRANCHES.items()]


def get_branch(slug):
    """Return a branch definition, or None if the slug isn't one of ours."""
    return BRANCHES.get(slug)


def modal_kpis(branch):
    """Merge each modal entry with its KPI's kind/target/formula for the modal."""
    by_name = {k['name']: k for k in branch['kpis']}
    merged = []
    for entry in branch['modal_kpis']:
        kpi = by_name[entry['name']]
        merged.append({
            'b_label': '', 'b_placeholder': '',   # count KPIs have no second figure
            **entry,
            **{key: kpi[key] for key in
               ('kind', 'direction', 'target_min', 'target_max', 'target_display', 'formula')},
        })
    return merged


SCOPE = {
    'title': 'Sales',
    'badge': 'Sales',
    'blurb': 'Lead volume through to qualified opportunities, conversion, and cost per lead.',
    'overview_blurb': 'Sales runs as three branches, each with its own scorecard, targets, and data '
                      'entry. This page rolls all three together; open a branch for its own KPIs.',
    'definitions_blurb': 'The metrics below define how this branch measures success, each with its '
                         'target, cadence, and formula.',
    'icons': ['line-chart', 'bullhorn', 'handshake-o'],
    # Per-branch banner overrides, keyed by branch slug. KpiScreens.scope_for()
    # merges these over SCOPE, so a branch page can carry its own blurb while
    # the icons and styling stay the team's.
    'branches': {
        slug: {'blurb': branch['blurb']} for slug, branch in BRANCHES.items()
    },
}
