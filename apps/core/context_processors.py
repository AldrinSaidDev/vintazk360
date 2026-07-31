"""Template context processors for the shared shell (base.html)."""
from importlib import import_module

from django.urls import NoReverseMatch, reverse

from .access import accessible_teams

# Per-team sub-navigation. Each team's dropdown shows a Dashboard link plus any
# of these extra pages whose URL actually resolves for that team's app. Teams
# without those pages built simply fall back to Dashboard-only because their
# reverse() lookups fail here.
#
# (url_name, label) — resolved against the team's slug as the URL namespace.
_TEAM_SUBPAGES = [
    ('index', 'Dashboard'),
    ('import_data', 'Import Data'),
    ('kpis', 'KPI Definitions'),
    ('kpi_management', 'KPI Management'),
]

# The same four screens, for teams that split into sub-teams ("branches" — see
# apps/sales/branches.py). These URLs take the branch slug as an argument.
_BRANCH_SUBPAGES = [
    ('branch_index', 'Dashboard'),
    ('branch_import_data', 'Import Data'),
    ('branch_kpis', 'KPI Definitions'),
    ('branch_kpi_management', 'KPI Management'),
]


def _branches_of(team_slug):
    """A team's sub-teams as ``[(slug, name), …]``, or [] if it has none.

    Convention: an LOB app that splits into branches exposes ``NAV_BRANCHES``
    from ``apps/<slug>/branches.py``. Anything else is a flat team.
    """
    try:
        module = import_module(f'apps.{team_slug}.branches')
    except ModuleNotFoundError:
        return []
    return getattr(module, 'NAV_BRANCHES', [])


def _links(namespace, subpages, args=()):
    """Reverse each (url_name, label), skipping the pages that aren't built."""
    links = []
    for url_name, label in subpages:
        try:
            url = reverse(f'{namespace}:{url_name}', args=args)
        except NoReverseMatch:
            continue  # that page isn't built for this team yet — skip it
        links.append({'label': label, 'url': url})
    return links


def _team_nav(team, path):
    """Build a team's dropdown: its own links plus any branch sub-dropdowns."""
    links = _links(team.slug, _TEAM_SUBPAGES)

    branches = []
    for slug, name in _branches_of(team.slug):
        branch_links = _links(team.slug, _BRANCH_SUBPAGES, args=(slug,))
        if not branch_links:
            continue
        branches.append({
            'name': name,
            'slug': slug,
            'links': branch_links,
            'active': any(link['url'] == path for link in branch_links),
        })

    # The team-level page of a branch team stays "Dashboard": it IS one — a
    # rollup of every branch — and the nesting already tells you it sits above
    # each branch's own. (It read "Overview" before that page grew tiles and a
    # chart; the label no longer matched what's on it.)

    return {
        'name': team.name,
        'slug': team.slug,
        'links': links,
        'branches': branches,
        'active': any(link['url'] == path for link in links)
                  or any(branch['active'] for branch in branches),
    }


def navigation(request):
    """Expose the LOB teams (with sub-links) the current user may see.

    ``nav_teams`` is a list of dicts:
    ``{name, slug, active, links: [{label, url}], branches: [{name, slug, active, links}]}``.
    The sidebar renders each as a collapsible dropdown — branches nest one level
    deeper. The shared Dashboard link is rendered unconditionally in the template.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'nav_teams': []}
    path = request.path
    return {'nav_teams': [_team_nav(t, path) for t in accessible_teams(user)]}
