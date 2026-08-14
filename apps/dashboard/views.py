from datetime import date, datetime
from functools import partial
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.timesince import timesince

from apps.core import async_content
from apps.core import audit
from apps.core import cache
from apps.core import kpi as scoring
from apps.core.access import accessible_teams
from apps.core.forms import AccountSetupForm
from apps.core.models import AuditLog
from apps.kpi import records as kpi_records
from apps.kpi.models import KpiBranch, KpiDefinition, KpiImportBatch, KpiRecord

# settings.TIME_ZONE is UTC, but the org runs on Philippine time and the welcome
# header states today's date — under UTC it would show yesterday for the whole
# Manila morning. Resolved here rather than by changing the project-wide zone.
SITE_TZ = ZoneInfo('Asia/Manila')


# Global filters. LIVE — every figure below the filter card is built from the
# window and the two picklists here.
#
# There is no separate "Reporting Period" preset list: the range picker already
# expresses every window a preset could, including the ones presets can't (daily
# call-log data, an arbitrary week). Two controls over one window would have to
# agree, and the second one only exists to be overridden. There is no "Compare
# To" either — a comparison is not a filter, and "This period vs last" already
# answers it against each department's own previous period.
#
# The value is the STATUS KEY `apps.core.kpi` produces, not the label, so a
# filtered URL can be bookmarked and shared without depending on wording. The
# fifth entry has no target-band meaning: `no_data` is what a KPI nobody has
# reported against scores as, and it is a state the cards show, so leaving it
# out would make it the one state on the page you cannot ask to see.
FILTER_STATUSES = [
    ('on_track', 'On Track'),
    ('at_risk', 'At Risk'),
    ('below', 'Below Target'),
    ('monitored', 'No Target'),
    ('no_data', 'Awaiting Figures'),
]
_STATUS_KEYS = {key for key, _ in FILTER_STATUSES}
_STATUS_LABELS = dict(FILTER_STATUSES)


def _date(raw):
    """An ISO date from a query parameter, or None if it isn't one.

    Anything unparseable is dropped rather than raised. These values arrive off
    a URL somebody may have edited or half-copied, and an unreadable date is a
    filter that cannot be applied, not a broken page.
    """
    try:
        return date.fromisoformat((raw or '').strip())
    except ValueError:
        return None


def _filters(request, teams):
    """The applied filters, cleaned against what this user can actually see.

    `teams` is the user's accessible list, so a department slug from outside it
    is dropped exactly as an unknown one is: the filter card cannot offer a team
    the sidebar doesn't, and neither can a hand-typed URL.
    """
    start = _date(request.GET.get('period_from'))
    end = _date(request.GET.get('period_to'))
    # A range typed backwards is a slip, not an empty window. Reading it in the
    # order given would return nothing and look like "no data".
    if start and end and start > end:
        start, end = end, start

    slug = request.GET.get('team', '').strip()
    chosen = next((team for team in teams if team.slug == slug), None)
    slug = chosen.slug if chosen else ''

    status = request.GET.get('status', '').strip()
    if status not in _STATUS_KEYS:
        status = ''

    return {
        'period_from': start,
        'period_to': end,
        'team': slug,
        # The name, so the summary line can say "Operations" without depending
        # on a department card having survived the status filter to read it off.
        'team_label': chosen.name if chosen else '',
        'status': status,
        'status_label': _STATUS_LABELS.get(status, ''),
        'applied': bool(start or end or slug or status),
    }


def _period_label(filters, today):
    """What window the figures on the page describe, in words.

    An open-ended range is stated as open ("Up to 31 Aug 2026"), not silently
    closed at today: "since records began" and "this month" are different reads
    and the header has to be honest about which one it is.
    """
    start, end = filters['period_from'], filters['period_to']
    if start and end:
        if start == end:
            return f'{start:%d %b %Y}'
        return f'{start:%d %b %Y} to {end:%d %b %Y}'
    if start:
        return f'From {start:%d %b %Y}'
    if end:
        return f'Up to {end:%d %b %Y}'
    return f'{today:%B %Y}'


def _in_window(record, start, end):
    """True when a record's reporting period meets the filter window.

    Overlap, not containment, and that is the whole point. A KPI's period is a
    span rather than a day, and the ten LOBs report on four different cadences,
    so a week in August has to reach the August monthly record AND the Q3
    quarterly one. Requiring the period to sit inside the window would mean only
    a range at least a quarter long could ever see a quarterly KPI.
    """
    return (
        (end is None or record.period_start <= end)
        and (start is None or record.period_end >= start)
    )


def _recent_records(team, start=None, end=None):
    """The current record per KPI and the one before it, keyed by KPI id.

    One query across every branch the team has, since this page is the org-wide
    rollup and a branch team's KPIs are still that team's KPIs. Two records
    rather than one because the comparison section reads this period against the
    last, and a second query per KPI to fetch the previous period would be one
    per row.

    The window applies to the FIRST of the two only. The current record is the
    newest one whose period meets the filter, and its partner is simply the
    record before it, in or out of the window. Filtering both would break
    "This period vs last" for exactly the window that makes it most useful: ask
    for one month and there is only ever one record in it, so every department
    would report no comparison.
    """
    history = {}
    for record in (
        KpiRecord.objects.filter(
            kpi__team=team, kpi__is_active=True, is_active=True,
        )
        .order_by('kpi_id', '-period_start')
        .only('kpi_id', 'period_start', 'period_end', 'value', 'score')
    ):
        seen = history.setdefault(record.kpi_id, [])
        if len(seen) >= 2:
            continue
        # Nothing chosen yet: keep skipping back until a period meets the
        # window. Once one has, the very next record is the previous period.
        if seen or _in_window(record, start, end):
            seen.append(record)
    # A KPI whose every record fell outside the window has an empty list, which
    # is not the same as a KPI with no records. Both read as "no figures for
    # this window", which is what the empty list already means downstream.
    return {kpi_id: seen for kpi_id, seen in history.items() if seen}


def _graded(record):
    """The number a record is SCORED on.

    `score` holds it only when it differs from the displayed value (a signed
    variance shows -3.2% and grades as 3.2).
    """
    value = record.score if record.score is not None else record.value
    return float(value)


# The gauge arc is divided by KPI state, in the order a reader ranks them:
# healthy first, then the two problem states, then the ones carrying no verdict.
#
# The colour is NOT decided here. Tailwind scans templates and JS, never Python,
# so a `stroke-status-good` built in this file would be purged out of
# output.css. The template maps the key to a literal class.
_GAUGE_BANDS = ['on_track', 'at_risk', 'below', 'unscored']


def _gauge_segments(counts, total):
    """Arc segments for the card gauge, as percentages of the semicircle.

    Each segment carries its own start offset so the template can render it
    with one `stroke-dasharray` / `stroke-dashoffset` pair against a path
    normalised to `pathLength="100"` — the same trick the delete-timer ring
    uses, which keeps the maths a straight percentage instead of depending on
    the arc's real length.
    """
    if not total:
        return []

    segments = []
    start = 0.0
    for key in _GAUGE_BANDS:
        count = counts[key]
        if not count:
            continue
        pct = count / total * 100
        segments.append({
            'key': key,
            'count': count,
            'pct': round(pct, 3),
            'start': round(start, 3),
        })
        start += pct
    return segments


def _department_rows(teams, filters):
    """One summary row per accessible department.

    `teams` has already been narrowed by the department filter, and `filters`
    carries the window and the status. Both are applied HERE rather than to the
    finished rows, because every figure on the page is derived from these tallies
    and filtering afterwards would leave the percentages describing a set the
    reader can no longer see.

    Attainment is RECOMPUTED through `records.score()` rather than read from
    `kpi_record.attainment`, for the same reason every LOB dashboard does it:
    the stored score is a snapshot of the target in force when the row was
    written, so a moved target would leave the old verdict on screen.

    A department's figure is the mean over every KPI it is POSSIBLE to score,
    and a targeted KPI with no figure counts as **0**, not as absent. A target
    nobody has reported against has not been met, and averaging only the KPIs
    that happen to have data let one reported KPI out of seventeen read as a
    department at 100%.

    The denominator is the TARGETED KPIs, not all of them. A KPI with no target
    has a figure but nothing to judge it against, so it can be neither attained
    nor missed — the same rule the `monitored` status already encodes. Counting
    those as losses would also put 100% permanently out of reach for any
    department that owns one.
    """
    # Cached per department, not per page. Two people looking at the same
    # unfiltered dashboard are asking for the same ten answers, and a
    # department's row depends on nothing but that department's data and the
    # window — not on who is reading. Caching the finished page instead would
    # give every combination of accessible teams its own entry and share almost
    # nothing.
    #
    # The filter combinations are cached too, not just the unfiltered view. A
    # filtered row costs the same to build as an unfiltered one and the window
    # is usually a period the whole company is looking at that week, so the
    # combinations people actually use are worth keeping. They cost nothing to
    # keep either: the key carries the window and the status, and an unused
    # combination expires on the GC clock like anything else.
    #
    # Batched, and it has to be: the version token and the row are two round
    # trips whatever the department count, rather than two per department. The
    # producers stay lazy — `fetch_many` calls one only for a department that
    # actually missed, so a warm page runs no queries at all.
    keys = cache.team_keys(
        'dept-row', [team.pk for team in teams],
        filters['period_from'], filters['period_to'], filters['status'],
    )
    cached = cache.fetch_many(
        (team.pk, keys[team.pk], partial(_department_row, team, filters))
        for team in teams
    )
    rows = [row for row in (cached[team.pk] for team in teams) if row is not None]

    # Highest attainment first; departments with nothing scored sink to the
    # bottom rather than reading as 0%.
    rows.sort(key=lambda r: (r['avg'] is not None, r['avg'] or 0), reverse=True)
    return rows


def _reporting_activity(team):
    """When this department last put a figure in, broken down by business unit.

    "Reported" means either way in: somebody typed a record on Import Data, or
    somebody uploaded a workbook. Both count, because the reader's question is
    "is this department keeping its numbers up to date", and answering it from
    imports alone would show a department that types everything by hand as
    silent. `updated_at` rather than `created_at`: correcting last month's
    figure today is reporting activity, not a month-old event.

    **Deliberately outside the period filters.** Those pick which reporting
    PERIODS are being scored; this is about when a person last acted, and a
    range covering July must not make a department look abandoned because the
    figures it entered yesterday were for August.

    Two grouped queries per department whatever the unit count, plus one for
    the unit names. Soft-deleted records and imports are excluded, so undoing
    an import correctly takes its timestamp back off the card with it.
    """
    branches = list(KpiBranch.objects.filter(team=team, is_active=True))

    def _by_branch(rows, key):
        """Fold a values().annotate() result into {branch_pk or None: datetime}."""
        return {row[key]: row['last'] for row in rows if row['last'] is not None}

    records = _by_branch(
        KpiRecord.objects
        .filter(kpi__team=team, is_active=True, kpi__is_active=True)
        .values('kpi__branch')
        .annotate(last=Max('updated_at')),
        'kpi__branch',
    )
    imports = _by_branch(
        KpiImportBatch.objects
        .filter(team=team, is_active=True)
        .values('branch')
        .annotate(last=Max('created_at')),
        'branch',
    )

    def _latest(*values):
        real = [v for v in values if v is not None]
        return max(real) if real else None

    def _ago(value):
        """How long ago, to ONE unit ("3 days", not "3 days, 4 hours").

        The card answers "is this department keeping up", and the reader makes
        that call on the leading unit. The second one is noise at a glance, and
        the exact stamp is on the element's title for anyone who wants it.
        Rendered here rather than by the `timesince` filter, which always gives
        two. `depth=1` on the utility is the same code with the tail cut off.
        """
        return timesince(value, depth=1) if value is not None else None

    # The department's own figure is the latest anything happened anywhere
    # under it, units included: a rollup that ignored its units would read
    # "never reported" for a department reporting every week.
    team_last = _latest(*records.values(), *imports.values())

    units = []
    for branch in branches:
        try:
            url = reverse(f'{team.slug}:branch_index', args=(branch.slug,))
        except NoReverseMatch:
            url = None
        last_at = _latest(records.get(branch.pk), imports.get(branch.pk))
        units.append({
            'name': branch.name,
            'slug': branch.slug,
            'url': url,
            'last_at': last_at,
            'ago': _ago(last_at),
        })

    # Most recent first, and the ones that have never reported last. A card is
    # read to find who is behind, and the silent units are that answer. Split
    # rather than sorted on a tuple: two Nones would be compared to each other.
    reported = [unit for unit in units if unit['last_at'] is not None]
    silent = [unit for unit in units if unit['last_at'] is None]
    reported.sort(key=lambda unit: unit['last_at'], reverse=True)

    return {'last_at': team_last, 'ago': _ago(team_last), 'units': reported + silent}


def _department_row(team, filters):
    """One department's summary row, or None when the filters leave nothing.

    Split out of `_department_rows` so it can be cached on its own. It must stay
    a pure function of `(team, filters)` and return plain data: it is what goes
    into the cache, so a model instance or a queryset in here would be stored as
    a snapshot pretending to be live.
    """
    status_filter = filters['status']

    kpis = list(KpiDefinition.objects.filter(team=team, is_active=True))
    if not kpis:
        return None
    history = _recent_records(
        team, filters['period_from'], filters['period_to'],
    )

    counts = {'on_track': 0, 'at_risk': 0, 'below': 0,
              'monitored': 0, 'no_data': 0}
    # `(has_target, attainment)` per KPI, handed to `scoring.goal_attainment`
    # so this page and the branch overview apply one rule.
    entries = []
    # The subset that has a real figure. Drives the coverage line and the
    # focus/best picks, which are about performance and would be meaningless
    # if a KPI nobody has reported could win or lose them.
    scores = []
    # The KPIs worth naming on the card: the worst and the best scorer.
    scored = []
    # This period against the last, over the KPIs that have BOTH. Comparing
    # a full current set against a smaller previous one would report the
    # arrival of new data as a change in performance.
    now_paired, then_paired = [], []

    # The KPIs that survived the status filter. This is the gauge's total
    # and the card's "N KPIs", so an unfiltered page counts every KPI the
    # team owns and a filtered one counts only what it is showing.
    kept = 0

    for kpi in kpis:
        recent = history.get(kpi.pk)
        if recent:
            attainment, status = kpi_records.score(kpi, _graded(recent[0]))
        else:
            attainment, status = None, 'no_data'

        # Scored FIRST, then filtered. A KPI's status is what the filter
        # selects on, so it has to exist before the decision can be made.
        if status_filter and status != status_filter:
            continue
        kept += 1
        counts[status] += 1

        if not recent:
            # `is_scored` is the KPI's own "does this have a target". A
            # target with nothing reported against it has not been met, so
            # it enters the roll-up as a miss rather than as an absence.
            entries.append((kpi.is_scored, None))
            continue

        entries.append((attainment is not None, attainment))
        if attainment is None:
            # No target: a figure that cannot be attained or missed.
            continue

        scores.append(attainment)
        scored.append({'name': kpi.name, 'attainment': attainment,
                       'status': status})

        if len(recent) > 1:
            previous, _ = kpi_records.score(kpi, _graded(recent[1]))
            if previous is not None:
                now_paired.append(attainment)
                then_paired.append(previous)

    # A status filter no KPI in this team matches drops the card entirely.
    # Rendering it at 0% would read as a department failing rather than as
    # one with nothing in the state being asked about.
    if not kept:
        return None

    # None only when the department owns no targeted KPI at all. That is
    # "cannot be scored", not "scored zero", and it is what keeps such a
    # department out of the company denominator instead of capping the
    # company figure below 100 forever.
    avg, scorable_count = scoring.goal_attainment(entries)

    # "Needs attention" is the lowest scorer that is not already on track.
    scored.sort(key=lambda k: k['attainment'])
    focus = next((k for k in scored if k['status'] != 'on_track'), None)
    best = scored[-1] if scored else None

    trend = None
    if then_paired:
        now = sum(now_paired) / len(now_paired)
        then = sum(then_paired) / len(then_paired)
        trend = {
            'now': round(now, 1),
            'then': round(then, 1),
            # Points, not percent: the difference between two percentages.
            'delta': round(now - then, 1),
            'kpi_count': len(now_paired),
        }

    # A team whose dashboard route isn't built yet renders as a plain card
    # rather than a dead link.
    try:
        url = reverse(f'{team.slug}:index')
    except NoReverseMatch:
        url = None

    # The gauge divides every KPI the team owns, so the two states with no
    # verdict (no target, no figures) share one neutral band rather than
    # being dropped — leaving them out would make a team with two reported
    # KPIs out of twelve look fully covered.
    unscored = counts['monitored'] + counts['no_data']

    activity = _reporting_activity(team)

    return {
        'name': team.name,
        'slug': team.slug,
        'url': url,
        # When somebody last put a figure in, and the same per business unit
        # for a department that has them. Not the same question as the gauge
        # above it: a department can be fully on target and three weeks stale.
        'last_reported_at': activity['last_at'],
        'last_reported_ago': activity['ago'],
        'units': activity['units'],
        'avg': avg,
        # Capped so an overachiever fills the track; the figure beside it
        # still reads the true number.
        'bar_pct': 0 if avg is None else min(round(avg), 100),
        'kpi_count': kept,
        'scored_count': len(scores),
        # The figure's denominator, and the gap between the two is what the
        # card's coverage line reports.
        'scorable_count': scorable_count,
        'missing_count': scorable_count - len(scores),
        'has_data': bool(scores),
        'focus': focus,
        'best': best,
        'trend': trend,
        'segments': _gauge_segments({**counts, 'unscored': unscored}, kept),
        **counts,
    }


def _pct(part, whole):
    """`part` as a whole-number percentage of `whole`; 0 when there is nothing."""
    return round(part / whole * 100) if whole else 0


def _org_summary(departments):
    """The Overall Goal figure and the counts behind it.

    This tile is GOAL PROGRESS, not average performance, which is what decides
    the denominator. The goal is every department at target, so the figure is
    the mean over EVERY department that can be scored, and one that has
    reported nothing counts as 0. It used to average only the departments that
    had reported, which let a single KPI in one department out of ten light the
    trophy at 100%.

    Each department still counts ONCE. Pooling all KPI scores instead would let
    Sales' seventeen KPIs outvote Social Media Management's three, making the
    company figure a measure of who tracks the most KPIs.

    The only department left out is one with no targeted KPI at all (`avg` is
    None): it cannot be scored, so counting it as 0 would put 100% permanently
    out of reach rather than describing anything.
    """
    counted = [d for d in departments if d['avg'] is not None]
    attainment = (
        round(sum(d['avg'] for d in counted) / len(counted), 1)
        if counted else None
    )
    # Kept separate from the denominator: this is the coverage story ("who has
    # actually entered figures"), which is now a caveat on a real number rather
    # than the thing the number is made of.
    reporting = [d for d in departments if d['has_data']]

    # Movement is the mean of the department movements, over the departments
    # that have a comparable previous period. Same one-vote-each rule.
    moved = [d['trend']['delta'] for d in departments if d['trend']]
    delta = round(sum(moved) / len(moved), 1) if moved else None

    return {
        'attainment': attainment,
        # Capped so an overachieving company fills the track; the figure under
        # it still reads the true number.
        'bar_pct': 0 if attainment is None else min(round(attainment), 100),
        'reached': attainment is not None and attainment >= 100,
        'reporting': len(reporting),
        # How many departments the figure is divided by. Only differs from
        # `department_count` when one owns no targeted KPI.
        'counted': len(counted),
        'department_count': len(departments),
        # Coverage as a proportion, so the panel can draw it rather than
        # leaving the reader to divide two numbers in their head.
        'reporting_pct': _pct(len(reporting), len(departments)),
        # Against the TARGETED KPIs, which is the figure's real denominator.
        # Measuring coverage against all 79 while scoring against 64 would put
        # a ceiling on the meter that nobody could explain.
        'kpis_scored_pct': _pct(
            sum(d['scored_count'] for d in departments),
            sum(d['scorable_count'] for d in departments),
        ),
        'complete': bool(reporting) and len(reporting) == len(departments),
        'at_target': sum(1 for d in counted if d['avg'] >= 100),
        'below_target': sum(1 for d in counted if d['avg'] < 100),
        'kpis_on_track': sum(d['on_track'] for d in departments),
        'kpis_scored': sum(d['scored_count'] for d in departments),
        'kpis_targeted': sum(d['scorable_count'] for d in departments),
        'kpis_missing': sum(d['missing_count'] for d in departments),
        'kpis_total': sum(d['kpi_count'] for d in departments),
        # The ones sitting out entirely: a figure, but no target to judge it by.
        'kpis_untargeted': sum(
            d['kpi_count'] - d['scorable_count'] for d in departments
        ),
        'delta': delta,
        'delta_departments': len(moved),
    }


# How many departments an insight names before it stops listing and counts.
# Past four the sentence stops being readable and starts being the list the
# Departments section already is.
_INSIGHT_NAMES = 4


def _names(rows):
    """A readable list of department names, truncated past `_INSIGHT_NAMES`."""
    names = [row['name'] for row in rows]
    if len(names) > _INSIGHT_NAMES:
        return f'{", ".join(names[:_INSIGHT_NAMES])} and {len(names) - _INSIGHT_NAMES} more'
    if len(names) > 1:
        return f'{", ".join(names[:-1])} and {names[-1]}'
    return names[0] if names else ''


def _insights(departments):
    """Findings about the departments, ranked by what to act on first.

    This replaced a "By department" list, which was the Departments section on
    the page behind it printed a second time in a smaller font. A modal opened
    from the Overall Goal figure should explain that figure, so each finding
    names the departments involved and says what it means for the number, which
    is the one thing the cards outside cannot say.

    Grouped rather than one row per department, on purpose: ten rows saying
    "reporting" is a list, and the point of opening this is to find the two or
    three that need something done.

    `tone` is a key, not a class. Tailwind scans templates and JS but never
    Python, so a colour built here would be purged out of output.css.
    """
    if not departments:
        return []

    # A department with targets and not one figure against them. First, because
    # it is the largest and cheapest correction available to the company figure.
    silent = [d for d in departments if d['scorable_count'] and not d['scored_count']]
    partial = [d for d in departments if d['scored_count'] and d['missing_count']]
    at_target = [d for d in departments if d['avg'] is not None and d['avg'] >= 100]
    behind = sorted(
        (d for d in departments
         if d['avg'] is not None and d['avg'] < 100 and d['has_data']),
        key=lambda d: d['avg'],
    )
    rising = sorted(
        (d for d in departments if d['trend'] and d['trend']['delta'] > 0),
        key=lambda d: -d['trend']['delta'],
    )
    falling = sorted(
        (d for d in departments if d['trend'] and d['trend']['delta'] < 0),
        key=lambda d: d['trend']['delta'],
    )
    untargeted = [d for d in departments if d['kpi_count'] - d['scorable_count']]

    found = []

    if silent:
        zeros = sum(d['scorable_count'] for d in silent)
        found.append({
            'tone': 'bad',
            'icon': 'exclamation-triangle',
            'title': 'Nothing reported yet',
            'body': (
                f'{_names(silent)} '
                f'{"has" if len(silent) == 1 else "have"} entered no figures. '
                f'{zeros} target{"" if zeros == 1 else "s"} '
                f'count{"s" if zeros == 1 else ""} as zero because of it, '
                f'which is the biggest single thing holding the company figure down.'
            ),
        })

    if behind:
        worst = behind[0]
        drag = ''
        if worst['focus']:
            drag = (
                f' Its weakest KPI is {worst["focus"]["name"]} '
                f'at {worst["focus"]["attainment"]}%.'
            )
        # With one department there is no ranking to report, and "N is lowest"
        # over a field of one reads as a template that forgot to branch.
        lead = (
            f'{worst["name"]} is short of target at {worst["avg"]}%.'
            if len(behind) == 1 else
            f'{len(behind)} departments are short of 100%. '
            f'{worst["name"]} is lowest at {worst["avg"]}%.'
        )
        found.append({
            'tone': 'warn',
            'icon': 'line-chart',
            'title': 'Below target',
            'body': f'{lead}{drag}',
        })

    if falling:
        steepest = falling[0]
        others = len(falling) - 1
        also = f' {others} other{"" if others == 1 else "s"} also slipped.' if others else ''
        found.append({
            'tone': 'bad',
            'icon': 'long-arrow-down',
            'title': 'Losing ground',
            'body': (
                f'{steepest["name"]} is down {abs(steepest["trend"]["delta"])} points '
                f'against its previous period.{also}'
            ),
        })

    if partial:
        gaps = sum(d['missing_count'] for d in partial)
        found.append({
            'tone': 'warn',
            'icon': 'clock-o',
            'title': 'Reporting part way',
            'body': (
                f'{_names(partial)} '
                f'{"has" if len(partial) == 1 else "have"} reported some targets but not all. '
                f'{gaps} target{"" if gaps == 1 else "s"} '
                f'{"is" if gaps == 1 else "are"} still counting as zero, so entering '
                f'{"that figure" if gaps == 1 else "those figures"} raises the score '
                f'with no change to how anyone works.'
            ),
        })

    if at_target:
        found.append({
            'tone': 'good',
            'icon': 'check-circle',
            'title': 'At target',
            # No "across every target it owns" clause: under a status filter the
            # average covers only the KPIs in that state, and the sentence would
            # be claiming more than the number behind it.
            'body': (
                f'{_names(at_target)} '
                f'{"is" if len(at_target) == 1 else "are"} at or above 100%.'
            ),
        })

    if rising:
        best = rising[0]
        others = len(rising) - 1
        also = f' {others} other{"" if others == 1 else "s"} improved too.' if others else ''
        found.append({
            'tone': 'good',
            'icon': 'long-arrow-up',
            'title': 'Improving',
            'body': (
                f'{best["name"]} is up {best["trend"]["delta"]} points '
                f'against its previous period.{also}'
            ),
        })

    if untargeted:
        loose = sum(d['kpi_count'] - d['scorable_count'] for d in untargeted)
        found.append({
            'tone': 'muted',
            'icon': 'info-circle',
            'title': 'Tracked but not scored',
            'body': (
                f'{loose} KPI{"" if loose == 1 else "s"} across {len(untargeted)} '
                f'department{"" if len(untargeted) == 1 else "s"} '
                f'{"has" if loose == 1 else "have"} no target set, so '
                f'{"it is" if loose == 1 else "they are"} left out of every figure here. '
                f'Setting a target starts scoring {"it" if loose == 1 else "them"}.'
            ),
        })

    return found


# --- First sign-in setup -----------------------------------------------------
#
# An account created from the Users screen is an Employee ID and a generated
# password, and deliberately nothing else: an administrator adding a dozen
# colleagues should not have to know a dozen email addresses. The rest is asked
# for here, once, the first time the person opens the dashboard.
#
# It is handled by this view rather than a `core` one for the reason KPI
# Management handles its own three modals: a form that fails validation has to
# re-render the page it is standing on, with its errors and its card still open.
# A separate view would have nowhere to put the errors on the way back.
SETUP_ACTION = 'account-setup'


def _needs_setup(user):
    """True while this account has never given its own name, email or password."""
    profile = getattr(user, 'profile', None)
    return profile is not None and profile.needs_setup


def _handle_setup(request):
    """The setup card's POST. Returns a response to send, or the failed form.

    Returning either is what lets `home` treat "done, go away" and "try again,
    here is what is wrong" as the two outcomes they are.
    """
    if not _needs_setup(request.user):
        # Already finished: a refreshed submit, or a second tab that was sitting
        # on the card. Nothing to do and nothing to complain about.
        return redirect('dashboard:home')

    form = AccountSetupForm(request.POST, user=request.user)
    if not form.is_valid():
        return form

    form.save()
    if form.password_changed:
        # Setting a password rotates the session hash. Without this the person
        # is signed straight out by the first thing they did after signing in.
        update_session_auth_hash(request, request.user)
    audit.log_action(
        request,
        action=AuditLog.Action.UPDATED,
        entity_type='user',
        entity_id=request.user.pk,
        entity_name=request.user.get_username(),
        # What was set, never what it was set TO where the password is
        # concerned. The log is permanent; the password is not for reading.
        new_values={
            'name': request.user.get_full_name(),
            'email': request.user.email,
            'password': (
                'set by the account holder' if form.password_changed
                else 'kept the one the account was created with'
            ),
        },
    )
    messages.success(request, 'Your account is set up. Welcome to Vintazk 360.')
    # Redirected rather than rendered, so a refresh cannot re-post the form and
    # so the guided tour gets a page load with `needs_setup` already cleared.
    return redirect('dashboard:home')


@login_required
def home(request):
    """Landing page for the dashboard (requires authentication)."""
    # The setup card, before anything else: it is the only POST this screen
    # takes, and a failure has to fall through to the full render below rather
    # than to the skeleton, which would throw the errors away.
    setup_form = None
    if request.method == 'POST' and request.POST.get('_action') == SETUP_ACTION:
        outcome = _handle_setup(request)
        if not isinstance(outcome, AccountSetupForm):
            return outcome
        setup_form = outcome

    # Two-stage render (apps/core/async_content.py). This page is the landing
    # screen after sign-in and the heaviest one in the app: it walks every
    # department the user can see and scores two periods of every KPI in each.
    # Answering the first request with the frame and a skeleton means the sign-in
    # lands on the dashboard immediately, and the wait for the numbers happens
    # here with something to look at rather than on the login screen.
    #
    # This returns before any of that work starts. Everything below runs on the
    # follow-up fetch.
    if async_content.wants_shell(request):
        return async_content.render_shell(
            request,
            shell_template='dashboard/shell.html',
            skeleton='partials/skeletons/dashboard.html',
        )

    # Welcome header. First name when we have one; the employee ID (username)
    # is the fallback, since that's what people log in with.
    user = request.user
    display_name = user.first_name or user.get_username()

    # The filter card's own options come from here, so it can only ever offer a
    # department this user could already open in the sidebar.
    all_teams = list(accessible_teams(user))
    filters = _filters(request, all_teams)
    teams = (
        [team for team in all_teams if team.slug == filters['team']]
        if filters['team'] else all_teams
    )

    departments = _department_rows(teams, filters)
    # One org figure, computed once. The Overall Goal track, the modal behind
    # it and the "against the company average" list all read this, so the page
    # cannot show two different company numbers.
    org = _org_summary(departments)
    # Contribution is each department's share of the summed attainment, which is
    # what the donut divides up. A department at 0 contributes nothing, so it
    # sits the chart out: it counts against the Overall Goal figure above, but
    # drawing ten zero-width slices would just be a legend of empty names.
    contributing = [d for d in departments if d['avg']]
    total = sum(d['avg'] for d in contributing)
    chart_data = [
        {
            'name': d['name'],
            'avg': d['avg'],
            'share': round(d['avg'] / total * 100, 1) if total else 0,
        }
        for d in contributing
    ]

    # Period-over-period, ranked by movement so the biggest swing in either
    # direction is the first thing read. Only departments with a comparable
    # previous period appear.
    movers = sorted(
        (d for d in departments if d['trend']),
        key=lambda d: d['trend']['delta'], reverse=True,
    )

    today = datetime.now(SITE_TZ).date()

    return async_content.render_content(request, 'dashboard/home.html', {
        'title': 'Dashboard',
        'display_name': display_name,
        'today': today,
        # What window the figures actually describe. It names the filter when
        # one is set, since the modal header would otherwise say "August 2026"
        # over a chart built from July.
        'period_label': _period_label(filters, today),
        'filters': filters,
        'filter_statuses': FILTER_STATUSES,
        # Every accessible team, NOT the filtered list: narrowing the dropdown
        # to the current selection would leave no way back to the others.
        'filter_teams': all_teams,
        'departments': departments,
        'org': org,
        # Findings for the Overall Goal modal. Built from the same rows the page
        # is, so an insight cannot describe a department the cards contradict.
        'insights': _insights(departments),
        'chart_data': chart_data,
        'movers': movers,
        # The first-sign-in card. None for everybody else, which is what the
        # template branches on, so the markup costs nothing on the other 99% of
        # dashboard loads.
        'setup_form': setup_form or (
            AccountSetupForm(user=user) if _needs_setup(user) else None
        ),
    })
