"""Template context processors for the shared shell (base.html)."""
from django.urls import NoReverseMatch, reverse

from .access import accessible_teams

# Per-team sub-navigation. Each team's dropdown shows a Dashboard link plus any
# of these extra pages whose URL actually resolves for that team's app. Only
# Operations has Import / KPI Definitions pages built today; other teams simply
# fall back to Dashboard-only because their reverse() lookups fail here.
#
# (url_name, label) — resolved against the team's slug as the URL namespace.
_TEAM_SUBPAGES = [
    ('index', 'Dashboard'),
    ('import_data', 'Import Data'),
    ('kpis', 'KPI Definitions'),
]


def _team_nav(team):
    """Build a team's dropdown: name + the sub-links that actually resolve."""
    links = []
    for url_name, label in _TEAM_SUBPAGES:
        try:
            url = reverse(f'{team.slug}:{url_name}')
        except NoReverseMatch:
            continue  # that page isn't built for this team yet — skip it
        links.append({'label': label, 'url': url})
    return {'name': team.name, 'slug': team.slug, 'links': links}


def navigation(request):
    """Expose the LOB teams (with sub-links) the current user may see.

    ``nav_teams`` is a list of dicts: ``{name, slug, links: [{label, url}]}``.
    The sidebar renders each as a collapsible dropdown. The shared Dashboard
    link is rendered unconditionally in the template.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'nav_teams': []}
    return {'nav_teams': [_team_nav(t) for t in accessible_teams(user)]}
