"""Operations' business units.

Operations uses the same branch shape as Sales: `/operations/` is the rollup
across every unit, and each unit gets its own dashboard, definitions, import
and management screens under `/operations/<unit>/`.

This module names the units and exposes the branch seed data the seeder reads.
`apps.operations.kpis` holds the shared KPI specs for the seven units; this
file packages them into the `BRANCHES` mapping that
`manage.py seed_lob_kpis operations` consumes.
"""

from .kpis import KPIS, MODAL_SPECS


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


_BRANCH_SPECS = [
    ('moxxi-jade', 'Moxxi & Jade', 'Moxxi & Jade operations scorecard.'),
    ('hermes', 'Hermes', 'Hermes operations scorecard.'),
    ('pddl', 'PDDL', 'PDDL operations scorecard.'),
    ('adparlor', 'AdParlor', 'AdParlor operations scorecard.'),
    ('csteam', 'CSTeam', 'CSTeam operations scorecard.'),
    ('jac-media', 'JAC & Media', 'JAC & Media operations scorecard.'),
    ('adops', 'AdOps', 'AdOps operations scorecard.'),
]


def _branch(slug, name, blurb):
    return {
        'slug': slug,
        'name': name,
        'blurb': blurb,
        'kpis': list(KPIS),
        'modal_kpis': list(MODAL_SPECS),
    }


BRANCHES = {slug: _branch(slug, name, blurb) for slug, name, blurb in _BRANCH_SPECS}


SCOPE = {
    'title': 'Operations',
    'badge': 'Operations',
    'north_star': 'Net Revenue Retention >= 110%',
    'blurb': 'Keep every client and grow inside them.',
    'overview_blurb': 'Operations runs as seven business units, each with its own scorecard, '
                      'targets, and data entry. This page rolls them all together; open a unit '
                      'for its own KPIs.',
    'definitions_blurb': 'The metrics below define how this business unit measures success, each '
                         'with its target, cadence, and formula.',
    'icons': ['cogs', 'tasks', 'line-chart'],
    'lead_size': 'sm',
    'branches': {
        slug: {'blurb': blurb}
        for slug, _, blurb in _BRANCH_SPECS
    },
}
