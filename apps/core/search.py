"""Header search: the one index behind the search palette.

Everything the palette offers is built HERE, on the server, for exactly the
reason the guided tour is (`apps/core/tour.py`): which departments a person may
open, and whether they administer accounts, is `apps/core/access.py`. A copy of
that rule in JavaScript would be a second answer to a question that already has
one, and the wrong copy would offer somebody a link to a 403.

Two kinds of result, in this order:

  * Pages — the shared Dashboard, every screen of every department the user can
    reach (branches included), plus Logs, Settings and User Profiles. The list
    is discovered the same way the sidebar's is, by reversing each screen's URL
    and keeping the ones that resolve, so a new per-team page becomes findable
    without being registered anywhere.
  * KPIs — live KPI definitions in those same departments. Each points at its
    team's KPI Definitions screen, which is the one KPI page EVERY role can
    open: sending a read-only user to KPI Management would be a search result
    that raises PermissionDenied on arrival.

Nothing here is cached. The page list is a few dozen `reverse()` calls and the
KPI side is one indexed query, both an order of magnitude cheaper than the
dashboard rows that are cached.
"""
from django.db.models import Q
from django.urls import NoReverseMatch, reverse

from apps.kpi.models import KpiDefinition

from .access import accessible_teams, can_edit_data, is_admin, is_superadmin
from .context_processors import team_nav

# How many of each kind a query returns. The palette scrolls, but a list long
# enough to scroll through is a list you read instead of refining.
PAGE_LIMIT = 8
KPI_LIMIT = 8

# Font Awesome 4 names, matching the icons the screens themselves use.
_PAGE_ICONS = {
    'Dashboard': 'dashboard',
    'Import Data': 'upload',
    'KPI Definitions': 'book',
    'KPI Management': 'sliders',
}
_DEFAULT_PAGE_ICON = 'file-text-o'
_KPI_ICON = 'line-chart'


def _entry(title, subtitle, url, icon):
    return {'title': title, 'subtitle': subtitle, 'url': url, 'icon': icon}


def _pages(user):
    """Every page this user may open, as search entries.

    Order is deliberate: the shared dashboard, then the departments in sidebar
    order, then the account-wide screens. A query re-ranks it, but an empty
    query shows it as it stands and it should read like the sidebar.
    """
    pages = [_entry(
        'Dashboard',
        'Organisation-wide KPI rollup',
        reverse('dashboard:home'),
        'dashboard',
    )]

    writer = can_edit_data(user)
    for team in accessible_teams(user):
        # The path is only used to mark the current page, which a search result
        # has no use for, so it is passed empty. `writer` drops Import Data and
        # KPI Management for a read-only role, exactly as it does in the
        # sidebar: those two views refuse the role outright, so offering one
        # here would be a result that 403s on arrival.
        nav = team_nav(team, '', writer)
        for link in nav['links']:
            pages.append(_entry(
                link['label'],
                nav['name'],
                link['url'],
                _PAGE_ICONS.get(link['label'], _DEFAULT_PAGE_ICON),
            ))
        for branch in nav['branches']:
            for link in branch['links']:
                pages.append(_entry(
                    link['label'],
                    f"{nav['name']} · {branch['name']}",
                    link['url'],
                    _PAGE_ICONS.get(link['label'], _DEFAULT_PAGE_ICON),
                ))

    # Both are administration, and the log is administration even though it
    # reads like team data: it carries sign-ins and role changes as well. The
    # log audits what an Admin does too, so it is offered to every
    # administrator, exactly as the sidebar is.
    if is_admin(user):
        pages.append(_entry(
            'User Profiles',
            'Create and administer accounts',
            reverse('core:users'),
            'users',
        ))

    if is_admin(user):
        pages.append(_entry(
            'Logs',
            'Activity across the organisation',
            reverse('core:logs'),
            'history',
        ))

    pages.append(_entry(
        'Settings',
        'Your account, password and recent activity',
        reverse('core:settings'),
        'cog',
    ))
    return pages


def _rank(entry, terms):
    """How well an entry matches, lower being better, or None for no match.

    Every term has to appear somewhere in the title or the subtitle, so
    "operations import" finds one page rather than every page of Operations
    plus every Import Data screen in the org. The rank itself is decided by the
    FIRST term against the title, which is what puts "Import Data" above
    "Operations" when somebody types "imp".
    """
    title = entry['title'].lower()
    haystack = f"{title} {entry['subtitle'].lower()}"
    if not all(term in haystack for term in terms):
        return None
    first = terms[0]
    if title.startswith(first):
        return 0
    if first in title:
        return 1
    return 2


def _definitions_url(team, branch):
    """The KPI Definitions URL for a team, or its branch. None if not built."""
    try:
        if branch is not None:
            return reverse(f'{team.slug}:branch_kpis', args=[branch.slug])
        return reverse(f'{team.slug}:kpis')
    except NoReverseMatch:
        return None


def _kpis(user, terms):
    """Live KPI definitions in the user's teams matching every term."""
    queryset = (
        KpiDefinition.objects
        .filter(is_active=True, team__in=accessible_teams(user))
        .select_related('team', 'branch', 'category')
    )
    for term in terms:
        queryset = queryset.filter(
            Q(name__icontains=term)
            | Q(category__name__icontains=term)
            | Q(team__name__icontains=term)
        )

    # Ranked in Python, so a prefix match sorts above a mid-word one. The slice
    # bounds the work: a term matching a whole team would otherwise pull every
    # KPI it owns back just to show eight of them.
    entries = []
    urls = {}
    for kpi in queryset.order_by('name')[:60]:
        key = (kpi.team_id, kpi.branch_id)
        if key not in urls:
            urls[key] = _definitions_url(kpi.team, kpi.branch)
        url = urls[key]
        if url is None:
            continue  # that team has no definitions screen — nowhere to send anyone

        parts = [kpi.team.name]
        if kpi.branch_id:
            parts.append(kpi.branch.name)
        if kpi.category_id:
            parts.append(kpi.category.name)
        entries.append(_entry(kpi.name, ' · '.join(parts), url, _KPI_ICON))

    ranked = [(_rank(e, terms), e) for e in entries]
    ranked = [(r, e) for r, e in ranked if r is not None]
    ranked.sort(key=lambda pair: (pair[0], pair[1]['title']))
    return [entry for _, entry in ranked[:KPI_LIMIT]]


def search(user, query):
    """Grouped results for ``query``, as ``[{label, items: [entry, …]}, …]``.

    An empty query is not an empty result: the palette opens on the full list
    of pages this user can reach, which is what makes it a way to get around
    and not only a way to look something up.
    """
    if not user.is_authenticated:
        return []

    terms = [term for term in query.lower().split() if term][:6]
    if not terms:
        return [{'label': 'Jump to', 'items': _pages(user)}]

    ranked = [(_rank(page, terms), page) for page in _pages(user)]
    ranked = [(r, p) for r, p in ranked if r is not None]
    ranked.sort(key=lambda pair: (pair[0], pair[1]['subtitle'], pair[1]['title']))
    pages = [page for _, page in ranked[:PAGE_LIMIT]]

    groups = []
    if pages:
        groups.append({'label': 'Pages', 'items': pages})
    kpis = _kpis(user, terms)
    if kpis:
        groups.append({'label': 'KPIs', 'items': kpis})
    return groups
