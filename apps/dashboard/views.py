from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.core.access import accessible_teams
from apps.kpi import records as kpi_records
from apps.kpi.models import KpiDefinition, KpiRecord

# settings.TIME_ZONE is UTC, but the org runs on Philippine time and the welcome
# header states today's date — under UTC it would show yesterday for the whole
# Manila morning. Resolved here rather than by changing the project-wide zone.
SITE_TZ = ZoneInfo('Asia/Manila')


# Global filter picklists. FRONT-END ONLY for now — nothing is wired to a
# queryset, so these are the shape of the controls rather than live options.
# They live here so there's one source to swap when filtering becomes real.
#
# Periods are named rather than dates because KPIs are scored per reporting
# period (monthly / quarterly), not per calendar day — a single date can't
# address a monthly KPI.
#
# 'Custom range' pairs with the From/To inputs beside it: presets cover the
# routine questions, the range covers the ones they don't — daily data (the
# outbound call logs) and arbitrary windows like "the week of the escalation".
FILTER_PERIODS = [
    'This Month', 'Last Month', 'This Quarter', 'Last Quarter', 'Year to Date',
    'Custom range',
]
FILTER_STATUSES = ['On Track', 'At Risk', 'Below Target', 'No Target']
FILTER_COMPARISONS = ['Previous period', 'Same period last year']


def _recent_records(team):
    """The two most recent active records per KPI, keyed by KPI id, newest first.

    One query across every branch the team has, since this page is the org-wide
    rollup and a branch team's KPIs are still that team's KPIs. Two rather than
    one because the comparison section reads this period against the last, and
    a second query per KPI to fetch the previous period would be one per row.
    """
    history = {}
    for record in (
        KpiRecord.objects.filter(
            kpi__team=team, kpi__is_active=True, is_active=True,
        )
        .order_by('kpi_id', '-period_start')
        .only('kpi_id', 'period_start', 'value', 'score')
    ):
        seen = history.setdefault(record.kpi_id, [])
        if len(seen) < 2:
            seen.append(record)
    return history


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


def _department_rows(user):
    """One summary row per accessible department, plus the org-wide average.

    Attainment is RECOMPUTED through `records.score()` rather than read from
    `kpi_record.attainment`, for the same reason every LOB dashboard does it:
    the stored score is a snapshot of the target in force when the row was
    written, so a moved target would leave the old verdict on screen.
    """
    rows = []
    org_scores = []

    for team in accessible_teams(user):
        kpis = list(KpiDefinition.objects.filter(team=team, is_active=True))
        if not kpis:
            continue
        history = _recent_records(team)

        counts = {'on_track': 0, 'at_risk': 0, 'below': 0,
                  'monitored': 0, 'no_data': 0}
        scores = []
        # The KPIs worth naming on the card: the worst and the best scorer.
        scored = []
        # This period against the last, over the KPIs that have BOTH. Comparing
        # a full current set against a smaller previous one would report the
        # arrival of new data as a change in performance.
        now_paired, then_paired = [], []

        for kpi in kpis:
            recent = history.get(kpi.pk)
            if not recent:
                counts['no_data'] += 1
                continue

            attainment, status = kpi_records.score(kpi, _graded(recent[0]))
            counts[status] += 1
            if attainment is None:
                continue

            scores.append(attainment)
            scored.append({'name': kpi.name, 'attainment': attainment,
                           'status': status})

            if len(recent) > 1:
                previous, _ = kpi_records.score(kpi, _graded(recent[1]))
                if previous is not None:
                    now_paired.append(attainment)
                    then_paired.append(previous)

        avg = round(sum(scores) / len(scores), 1) if scores else None
        org_scores.extend(scores)

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

        rows.append({
            'name': team.name,
            'slug': team.slug,
            'url': url,
            'avg': avg,
            # Capped so an overachiever fills the track; the figure beside it
            # still reads the true number.
            'bar_pct': 0 if avg is None else min(round(avg), 100),
            'kpi_count': len(kpis),
            'scored_count': len(scores),
            'focus': focus,
            'best': best,
            'trend': trend,
            'segments': _gauge_segments({**counts, 'unscored': unscored}, len(kpis)),
            **counts,
        })

    # Highest attainment first; departments with nothing scored sink to the
    # bottom rather than reading as 0%.
    rows.sort(key=lambda r: (r['avg'] is not None, r['avg'] or 0), reverse=True)
    return rows


def _pct(part, whole):
    """`part` as a whole-number percentage of `whole`; 0 when there is nothing."""
    return round(part / whole * 100) if whole else 0


def _org_summary(departments):
    """The Overall Goal figure and the counts behind it.

    The headline is the mean of each department's OWN attainment, so every
    department counts once. Pooling all KPI scores instead would let Sales'
    seventeen KPIs outvote Social Media Management's three, which would make
    the company figure a measure of who tracks the most KPIs.

    A department with nothing scored is EXCLUDED rather than counted as 0%.
    Counting it would report an unentered department as a failing one. That
    makes coverage part of the reading, so `reporting` is published alongside
    the figure and the template states it under the track.
    """
    reporting = [d for d in departments if d['avg'] is not None]
    attainment = (
        round(sum(d['avg'] for d in reporting) / len(reporting), 1)
        if reporting else None
    )

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
        'department_count': len(departments),
        # Coverage as a proportion, so the panel can draw it rather than
        # leaving the reader to divide two numbers in their head.
        'reporting_pct': _pct(len(reporting), len(departments)),
        'kpis_scored_pct': _pct(
            sum(d['scored_count'] for d in departments),
            sum(d['kpi_count'] for d in departments),
        ),
        'complete': bool(reporting) and len(reporting) == len(departments),
        'at_target': sum(1 for d in reporting if d['avg'] >= 100),
        'below_target': sum(1 for d in reporting if d['avg'] < 100),
        'kpis_on_track': sum(d['on_track'] for d in departments),
        'kpis_scored': sum(d['scored_count'] for d in departments),
        'kpis_total': sum(d['kpi_count'] for d in departments),
        'delta': delta,
        'delta_departments': len(moved),
    }


@login_required
def home(request):
    """Landing page for the dashboard (requires authentication)."""
    # Welcome header. First name when we have one; the employee ID (username)
    # is the fallback, since that's what people log in with.
    user = request.user
    display_name = user.first_name or user.get_username()

    departments = _department_rows(user)
    # One org figure, computed once. The Overall Goal track, the modal behind
    # it and the "against the company average" list all read this, so the page
    # cannot show two different company numbers.
    org = _org_summary(departments)
    # Contribution is each department's share of the summed attainment, which is
    # what the donut divides up. Departments with nothing scored sit it out.
    contributing = [d for d in departments if d['avg'] is not None]
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

    return render(request, 'dashboard/home.html', {
        'title': 'Dashboard',
        'display_name': display_name,
        'today': today,
        'period_label': f'{today:%B %Y}',
        'filter_periods': FILTER_PERIODS,
        'filter_statuses': FILTER_STATUSES,
        'filter_comparisons': FILTER_COMPARISONS,
        'departments': departments,
        'org': org,
        'chart_data': chart_data,
        'movers': movers,
    })
