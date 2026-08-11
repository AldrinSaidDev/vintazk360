"""The guided tour: which steps this user gets, and where each one points.

The tour is BUILT ON THE SERVER because every question it has to answer is a
server question. Which department it walks you through depends on which teams
you can reach; whether it visits Import Data and KPI Management at all depends
on whether your role may write. Deciding that in JavaScript would mean shipping
the access rules to the browser and keeping a second copy of them in step with
``apps.core.access``.

A step is a dict:

    page    the URL the step lives on. The tour navigates when the next step
            has a different one.
    target  a CSS selector for the element to spotlight, or None for a step
            that sits in the middle of the screen (the welcome and the sign
            off). A target that isn't on the page is SKIPPED, not an error:
            the Actual vs Target chart only renders once a KPI has been
            scored, and a tour that stalled on an empty team would be worse
            than one that says less.
    title   / body — the copy.
    reveal  optional fragment to open first (the sidebar is an off-canvas
            drawer below md, and `:target` is the only thing that opens it).

Everything a step points at carries a ``data-tour="…"`` attribute. Those are
the tour's own handles, deliberately not ids or utility classes: restyling a
panel then cannot silently break the tour, and a reader of the template can see
that the element is spoken for.
"""
from django.urls import NoReverseMatch, reverse

from .access import accessible_teams, can_edit_data


def _url(namespace, name, args=()):
    """Reverse a screen, or None when that LOB does not have it."""
    try:
        return reverse(f'{namespace}:{name}', args=args)
    except NoReverseMatch:
        return None


def _branch_of(team):
    """The first branch of a branch team as ``(slug, name)``, or None if flat.

    Same convention the sidebar uses (``apps/<slug>/branches.py``), read the
    same way: by import, so a new branch team needs no registry entry here.
    """
    from importlib import import_module

    try:
        module = import_module(f'apps.{team.slug}.branches')
    except ModuleNotFoundError:
        return None
    branches = getattr(module, 'NAV_BRANCHES', [])
    return branches[0] if branches else None


def _team_urls(team, branch):
    """The team screens the tour visits, branch-aware. Missing ones are None.

    KPI Definitions is deliberately not among them: it is a reference page a
    reader opens when a figure is unclear, and stopping there taught nothing
    the department dashboard had not already shown.
    """
    if branch is None:
        return {
            'index': _url(team.slug, 'index'),
            'import_data': _url(team.slug, 'import_data'),
            'kpi_management': _url(team.slug, 'kpi_management'),
        }
    # A branch team's four screens are per branch. Its team-level page is the
    # rollup dashboard, which is a different screen with a different layout, so
    # the tour walks the branch the same way it walks a flat LOB.
    args = (branch[0],)
    return {
        'index': _url(team.slug, 'branch_index', args),
        'import_data': _url(team.slug, 'branch_import_data', args),
        'kpi_management': _url(team.slug, 'branch_kpi_management', args),
    }


def _example_team(user):
    """The department the tour walks through.

    The first team this user can reach, in sidebar order. For a User or a
    Manager that is their own department. For a Super Admin, an Admin or a
    Viewer, who reach several, it is whichever sits first in the sidebar, so
    the tour points at the entry they are already looking at.
    """
    return accessible_teams(user).first()


def steps_for(user):
    """The whole tour for this user, in order. Empty if there is nothing to show."""
    home = reverse('dashboard:home')

    steps = [
        {
            'page': home,
            'target': None,
            'title': 'Welcome to Vintazk 360',
            'body': (
                "A quick look around, about a minute. You can leave any time, "
                "and the help button in the header brings this back."
            ),
        },
        {
            'page': home,
            'target': '[data-tour="overall-goal"]',
            'title': 'The company score',
            'body': (
                "How every department is doing this period, averaged into one "
                "number. The line under it shows how many have reported."
            ),
        },
        {
            'page': home,
            'target': '[data-tour="global-filters"]',
            'title': 'Pick a period',
            'body': (
                "Choose the period and the status you want to see. Everything "
                "on this page follows what you set here."
            ),
        },
        # The department cards, the two charts and the period comparison are the
        # same performance read three ways. Stopping at each in turn made three
        # steps that said one thing, so they are one step over the whole region.
        {
            'page': home,
            'target': '[data-tour="dashboard-detail"]',
            'title': 'The detail below',
            'body': (
                "A card for each department, then charts for who is "
                "contributing most and what has changed since last period. "
                "Scroll while this is open, the highlight follows."
            ),
        },
        {
            'page': home,
            'target': '#sidebar',
            'reveal': '#sidebar',
            'title': 'Your departments',
            'body': (
                "Every department you can open is listed here, with its own "
                "pages inside. Logs and Settings sit at the bottom."
            ),
        },
    ]

    team = _example_team(user)
    if team is None:
        # No team, no department screens to show. The dashboard steps still
        # stand on their own, so the tour ends after them.
        steps.append(_finish(home))
        return steps

    branch = _branch_of(team)
    urls = _team_urls(team, branch)
    may_write = can_edit_data(user)
    # A branch team's screens are titled with the BRANCH, so the tour names what
    # the page it is standing on names. On a flat LOB the two are the same thing.
    where = f'{team.name}, {branch[1]}' if branch else team.name

    # One step for the whole department dashboard, on its North Star banner.
    # Walking the tiles, the chart and the scorecard in turn described a page
    # the reader can already see, so the step names the goal the department is
    # measured against and points at the rest rather than narrating it.
    if urls['index']:
        steps.append({
            'page': urls['index'],
            'target': '[data-tour="north-star"]',
            # "your department" would be wrong for the roles that reach every
            # team, and this same step is what a Viewer or an Admin gets.
            'title': f'{where} dashboard',
            'body': (
                "This is the goal the department is measured against. The "
                "cards and charts below show how each KPI is doing against "
                "its target."
            ),
        })

    # The Add Record and Import buttons sit in this section's own header, so one
    # step covers both the table and the two ways of filling it.
    if may_write and urls['import_data']:
        steps.append({
            'page': urls['import_data'],
            'target': '[data-tour="kpi-records"]',
            'title': 'KPI Records',
            'body': (
                "Every figure entered, with Delete on each row. Add Record "
                "enters one by hand and Import uploads a filled in workbook. "
                "Use the search box and Filter to narrow the list by KPI, "
                "category, status or source."
            ),
        })

    if may_write and urls['kpi_management']:
        steps += [
            {
                'page': urls['kpi_management'],
                'target': '[data-tour="manage-actions"]',
                'title': 'Setting up KPIs',
                'body': (
                    "Create KPI adds a new measure and its target. Download "
                    "template gives you the workbook to fill in, one sheet per "
                    "KPI."
                ),
            },
            {
                'page': urls['kpi_management'],
                'target': '[data-tour="kpi-definitions"]',
                'title': 'Your KPI list',
                'body': (
                    "Edit or remove any KPI here. Changing a target or a "
                    "formula is recorded in the Logs, since it changes how "
                    "past figures read."
                ),
            },
        ]

    steps.append(_finish(steps[-1]['page']))
    return steps


def _finish(page):
    return {
        'page': page,
        'target': None,
        'title': "You're all set",
        'body': (
            "Start on the dashboard, or open a department in the sidebar. The "
            "small info marks beside a heading explain that panel, and the "
            "help button replays this tour any time."
        ),
    }
