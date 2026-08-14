"""Template context processors for the shared shell (base.html)."""
from importlib import import_module

from django.urls import NoReverseMatch, reverse

from . import async_content, tour as tour_steps
from .access import accessible_teams, can_edit_data, is_admin, is_superadmin
from .models import Team

# Per-team sub-navigation. Each team's dropdown shows a Dashboard link plus any
# of these extra pages whose URL actually resolves for that team's app. Teams
# without those pages built simply fall back to Dashboard-only because their
# reverse() lookups fail here.
#
# (url_name, label, writers_only) — resolved against the team's slug as the URL
# namespace. Import Data and KPI Management are writers only: the views
# themselves refuse a read-only role (`access.edit_required`), so listing them
# here for a User or a Viewer would be a sidebar entry that 403s on arrival.
_TEAM_SUBPAGES = [
    ('index', 'Dashboard', False),
    ('import_data', 'Import Data', True),
    ('kpis', 'KPI Definitions', False),
    ('kpi_management', 'KPI Management', True),
]

# The same four screens, for teams that split into sub-teams ("branches" — see
# apps/sales/branches.py). These URLs take the branch slug as an argument.
_BRANCH_SUBPAGES = [
    ('branch_index', 'Dashboard', False),
    ('branch_import_data', 'Import Data', True),
    ('branch_kpis', 'KPI Definitions', False),
    ('branch_kpi_management', 'KPI Management', True),
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


def _links(namespace, subpages, args=(), writer=True):
    """Reverse each (url_name, label), skipping the pages that aren't built.

    A page is skipped for two reasons: its URL does not resolve, so that team
    has not had it built, or it is writers only and this reader is read only.
    """
    links = []
    for url_name, label, writers_only in subpages:
        if writers_only and not writer:
            continue
        try:
            url = reverse(f'{namespace}:{url_name}', args=args)
        except NoReverseMatch:
            continue  # that page isn't built for this team yet — skip it
        links.append({'label': label, 'url': url})
    return links


def team_nav(team, path, writer=True):
    """Build a team's dropdown: its own links plus any branch sub-dropdowns.

    Public because `apps/core/search.py` builds the search palette's page list
    from it: the sidebar and the search results must offer the same screens, or
    a page becomes reachable one way and not the other. `writer` is that
    caller's `can_edit_data(user)`, for the same reason: both lists have to
    drop the two screens a read-only role is refused.
    """
    links = _links(team.slug, _TEAM_SUBPAGES, writer=writer)

    branches = []
    for slug, name in _branches_of(team.slug):
        branch_links = _links(
            team.slug, _BRANCH_SUBPAGES, args=(slug,), writer=writer
        )
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
    writer = can_edit_data(user)
    return {
        'nav_teams': [
            team_nav(t, path, writer) for t in accessible_teams(user)
        ]
    }


def permissions(request):
    """Expose the write permission to every template.

    `can_edit` is a ROLE test, not a team one, which is all a template needs:
    a screen is only rendered once `team_required` has already established
    that this user may be on it, so the only remaining question is whether
    they may act. The view still calls `access.require_edit()` on POST, since
    hiding a button is not access control.

    `is_admin` and `is_superadmin` are two levels, not one flag read twice.
    `is_admin` opens the accounts screen and the KPI delete control;
    `is_superadmin` is what grants the top role, deactivates an account and
    reads the activity log. Every template that hides one of those asks the
    narrower question, and the view refuses the POST regardless.
    """
    user = getattr(request, 'user', None)
    if user is None:
        return {'can_edit': False, 'is_admin': False, 'is_superadmin': False}
    return {
        'can_edit': can_edit_data(user),
        'is_admin': is_admin(user),
        'is_superadmin': is_superadmin(user),
    }


# Every screen's own name, keyed by the URL name that resolves to it. The four
# KPI screens come from the two lists above rather than being repeated here, so
# a page renamed in the sidebar is renamed in the breadcrumb by the same edit.
_PAGE_LABELS = {
    **{url_name: label for url_name, label, _ in _TEAM_SUBPAGES},
    **{url_name: label for url_name, label, _ in _BRANCH_SUBPAGES},
    'logs': 'Logs',
    'users': 'User Profiles',
    'settings': 'Settings',
}

# Pages that hang off the shared Dashboard rather than off a department.
_CORE_PAGES = {'logs', 'users', 'settings'}


def _crumb(label, url=None):
    return {'label': label, 'url': url}


def breadcrumbs(request):
    """The trail under the header: where this page sits, and how to walk back up.

    Built from the RESOLVED URL, not from the path, so it names a screen the
    same way the sidebar does rather than title-casing a slug. Three shapes:

        Dashboard
        Dashboard › Operations › Moxxi & Jade › Import Data
        Dashboard › User Profiles

    Every crumb but the last carries a URL; the last IS the page you are on, so
    it is text. That is also why the Dashboard-only case renders nothing: a
    trail whose single entry is the page you are looking at tells you nothing.

    It renders in `base.html`, which is the SHELL of a two-stage screen, so it
    arrives with the page frame and never waits on the content fetch. That is
    the whole reason it is a context processor rather than per-view context:
    ten LOB views and four shared ones would each have to build the same list,
    and the shells would have to build it a second time.
    """
    match = getattr(request, 'resolver_match', None)
    if match is None:
        return {'breadcrumbs': []}

    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'breadcrumbs': []}

    namespace = match.namespace
    url_name = match.url_name

    # The dashboard is the root of every trail, so on the dashboard itself
    # there is no trail: one crumb naming the current page is decoration.
    if namespace == 'dashboard':
        return {'breadcrumbs': []}

    trail = [_crumb('Dashboard', reverse('dashboard:home'))]

    if namespace == 'core' and url_name in _CORE_PAGES:
        trail.append(_crumb(_PAGE_LABELS[url_name]))
        return {'breadcrumbs': trail}

    # An LOB screen. The URL namespace IS the team slug (the sidebar and
    # `team_required` both rely on that already), so one indexed lookup names
    # the department without the view having to pass anything down.
    team = Team.objects.filter(slug=namespace).first()
    if team is None:
        return {'breadcrumbs': []}

    try:
        team_url = reverse(f'{namespace}:index')
    except NoReverseMatch:
        team_url = None
    trail.append(_crumb(team.name, team_url))

    branch_slug = match.kwargs.get('branch')
    if branch_slug:
        # Named from NAV_BRANCHES, the same list the sidebar reads, so the
        # breadcrumb cannot call a business unit something the sidebar doesn't.
        # A slug with no entry falls back to itself rather than dropping the
        # crumb, since a trail that silently skips a level is worse than an
        # ugly one.
        names = dict(_branches_of(namespace))
        try:
            branch_url = reverse(f'{namespace}:branch_index', args=(branch_slug,))
        except NoReverseMatch:
            branch_url = None
        trail.append(_crumb(names.get(branch_slug, branch_slug), branch_url))

    # The department's own landing page is the crumb already added, so it is
    # not repeated as a leaf. Same for a branch's dashboard.
    if url_name not in ('index', 'branch_index'):
        label = _PAGE_LABELS.get(url_name)
        if label:
            trail.append(_crumb(label))

    # The leaf is the page you are on, so it never carries a link. Walking back
    # up to the department is what the crumb above it is for.
    trail[-1]['url'] = None
    return {'breadcrumbs': trail}


def tour(request):
    """Expose the guided tour (apps/core/tour.py) to base.html.

    `tour_steps` is the whole walk-through for this user, already narrowed to
    the screens their role can reach. `tour_autostart` is the first-run case
    only: a profile that has never finished or skipped it, landing on the
    dashboard, which is where the tour begins. Everywhere else it waits for the
    help button.

    Skipped for the ?partial=1 fetch. That response renders the content block
    alone, so the tour markup in base.html is not in it and building the steps
    would be work thrown away.
    """
    empty = {'tour_steps': [], 'tour_autostart': False}

    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return empty
    if async_content.is_partial(request):
        return empty

    steps = tour_steps.steps_for(user)
    if not steps:
        return empty

    profile = getattr(user, 'profile', None)
    # `needs_setup` holds the tour back rather than cancelling it. An account an
    # administrator has just created lands on the dashboard behind the setup
    # card, and starting a walk around the app underneath a form the person has
    # to fill in first would be two things talking at once. The flag clears on
    # save, the page redirects, and the tour plays on the render after that, off
    # the same `is_new_user` it always did.
    first_run = (
        profile is not None and profile.is_new_user and not profile.needs_setup
    )

    return {
        'tour_steps': steps,
        'tour_autostart': first_run and request.path == steps[0]['page'],
    }
