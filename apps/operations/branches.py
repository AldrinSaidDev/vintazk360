"""Operations' business units.

Operations oversees several client-facing teams, so it runs the branch shape
Sales already runs: `/operations/` is the rollup across every unit, and each
unit gets its own dashboard, definitions, import and management screens under
`/operations/<unit>/`.

**This module names the units and nothing else.** Unlike `apps/sales/branches.py`
it carries no KPI seed data: the `kpi_branch` rows and the KPIs under them are
already in place, so re-seeding them here would create a second, competing
description of figures the business has since edited. Every screen reads the
database, exactly as it does for every other LOB.

The seven units all track the same KPI set today. That is a fact about the
data, not about the code: they are ordinary branches, and one unit's targets
can move without the others following.
"""

# Sidebar order. `apps.core.context_processors` reads this to build the nested
# dropdown, and `breadcrumbs` reads it to name a unit, so the slug here has to
# match the `kpi_branch.slug` the rows were created with.
NAV_BRANCHES = [
    ('moxxi-jade', 'Moxxi & Jade'),
    ('hermes', 'Hermes'),
    ('pddl', 'PDDL'),
    ('adparlor', 'AdParlor'),
    ('csteam', 'CSTeam'),
    ('jac-media', 'JAC & Media'),
    ('adops', 'AdOps'),
]


SCOPE = {
    'title': 'Operations',
    'badge': 'Operations',
    'north_star': 'Net Revenue Retention ≥ 110%',
    'blurb': 'Keep every client and grow inside them.',
    'overview_blurb': 'Operations runs as seven business units, each with its own scorecard, '
                      'targets, and data entry. This page rolls them all together; open a unit '
                      'for its own KPIs.',
    'definitions_blurb': 'The metrics below define how this business unit measures success, each '
                         'with its target, cadence, and formula.',
    'icons': ['cogs', 'tasks', 'line-chart'],
    'lead_size': 'sm',
}
