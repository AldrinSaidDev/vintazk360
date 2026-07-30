"""Shared KPI scorecard math + page context, used by the `templates/kpi/` screens.

Operations, Nexzys and Sales each carry their own copy of this logic (they were
built one at a time, before the shape settled). Everything added since — HR,
VINTAZK Academy, VCT — runs through here instead, so the math lives in one file
and the four KPI screens are four shared templates rather than four per LOB.

A KPI is a plain dict::

    {'name', 'category', 'kind', 'direction', 'actual', 'frequency',
     'target_display', 'actual_display', 'formula', 'description', 'inputs': [...],
     # target, as EITHER a single number or a band:
     'target': 95,                       # ← equivalent to a band of width zero
     'target_min': 40, 'target_max': 80, # ← Sales-style range target
    }

``direction`` is 'up' (higher is better) or 'down' (lower is better — cost,
days-to-fill, attrition). A target of ``None`` means the KPI is tracked but not
scored: it gets the 'monitored' status, no bar, and is left off the chart.

``kind`` drives the Add-Record modal's arithmetic (see static/js/kpi-record-modal.js):
'percent' a÷b×100 · 'count' a · 'average' a÷b · 'ratio' a÷b as "3.4×" ·
'cost' a÷b as ₱ · 'difference' a−b · 'days' date a − date b ·
'net_percent' (a−b)÷a×100 (accuracy net of errors) · 'variance' (a−b)÷b×100,
scored on the absolute value · 'accuracy' (1−|a−b|÷b)×100 ·
'scaled' (a÷b)×c, the one kind that shows a third input.

A two-sided tolerance ("within ±5%") is expressed as a 'down' KPI over a
``target_min=0 / target_max=5`` band, with ``actual`` holding the ABSOLUTE
variance and ``actual_display`` keeping the sign.
"""

STATUS_LABEL = {
    'on_track': 'On Track',
    'at_risk': 'At Risk',
    'below': 'Below Target',
    'monitored': 'No Target',
}

DIRECTION_LABEL = {'up': 'Higher is better', 'down': 'Lower is better'}

FREQUENCIES = ['Daily', 'Weekly', 'Monthly', 'Quarterly', 'Annually']


def target_band(kpi):
    """The KPI's target as a ``(low, high)`` pair; ``(None, None)`` if unscored.

    A single ``target`` is treated as a band with both ends equal, so one piece
    of math serves single-number targets and Sales-style ranges alike.
    """
    if kpi.get('target') is not None:
        return kpi['target'], kpi['target']
    return kpi.get('target_min'), kpi.get('target_max')


def attainment(kpi):
    """Normalized % of target reached, or None when the KPI isn't scored.

    Inside the target band is fully on target (100%). Outside it, attainment is
    measured against the edge that was missed, direction-aware. Returned
    unrounded so the status bucket isn't decided by rounding.
    """
    low, high = target_band(kpi)
    if low is None or high is None:
        return None
    actual = kpi['actual']

    if kpi['direction'] == 'down':
        # Zero-tolerance targets (e.g. "zero incidents"): hit or miss.
        if high == 0:
            return 100.0 if actual == 0 else 0.0
        if not actual:
            return 100.0          # nothing beats none when lower is better
        if actual > high:
            return high / actual * 100
        if actual < low:
            return low / actual * 100
        return 100.0

    if not actual:
        return 0.0
    # A zero end on a higher-is-better KPI can't be divided into — treat any
    # value past it as met rather than blowing up.
    if actual < low:
        return 0.0 if low == 0 else actual / low * 100
    if actual > high:
        return 100.0 if high == 0 else actual / high * 100  # over the band still beats target
    return 100.0


def status(value):
    """Bucket an attainment % into a status key used for color/label."""
    if value is None:
        return 'monitored'
    if value >= 100:
        return 'on_track'
    if value >= 90:
        return 'at_risk'
    return 'below'


def shown(value):
    """Attainment rounded for display, never rounding a miss up to 100%."""
    rounded = round(value, 1)
    if value < 100 <= rounded:
        return 99.9
    return rounded


def scorecard(kpis):
    """Return the KPI rows enriched with attainment, bar width, and status."""
    rows = []
    for kpi in kpis:
        value = attainment(kpi)
        key = status(value)
        rows.append({
            **kpi,
            'attainment': None if value is None else shown(value),
            # Capped at 100 so overachievers show a full bar; floored below
            # target so a near-miss never draws as a full one.
            'bar_pct': 0 if value is None else min(int(value), 100),
            'status': key,
            'status_label': STATUS_LABEL[key],
        })
    return rows


def counts(rows):
    """Status tallies for the summary tiles and any branch overview."""
    return {
        'kpi_count': len(rows),
        'on_track_count': sum(1 for r in rows if r['status'] == 'on_track'),
        'at_risk_count': sum(1 for r in rows if r['status'] == 'at_risk'),
        'below_count': sum(1 for r in rows if r['status'] == 'below'),
        'monitored_count': sum(1 for r in rows if r['status'] == 'monitored'),
    }


def dashboard_context(scope, kpis):
    """Context for templates/kpi/dashboard.html."""
    rows = scorecard(kpis)
    return {
        'scope': scope,
        'kpis': rows,
        **counts(rows),
        # KPIs without a target have nothing to plot against, so they're left
        # out of the chart payload (the tile still reports how many).
        'chart_data': [
            {'name': r['name'], 'attainment': r['attainment'], 'status': r['status'],
             'actual_display': r['actual_display'], 'target_display': r['target_display']}
            for r in rows if r['attainment'] is not None
        ],
    }


def definitions_context(scope, kpis):
    """Context for templates/kpi/kpi_definitions.html."""
    return {'scope': scope, 'kpis': kpis, 'kpi_count': len(kpis)}


def management_context(scope, kpis):
    """Context for templates/kpi/kpi_management.html."""
    rows = [{**k, 'direction_label': DIRECTION_LABEL[k['direction']]} for k in kpis]
    return {
        'scope': scope,
        'kpis': rows,
        'kpi_count': len(rows),
        'categories': sorted({k['category'] for k in kpis}),
        # Union so a non-standard cadence already in use stays selectable.
        'frequencies': sorted({*FREQUENCIES, *(k['frequency'] for k in kpis)}),
    }


def import_context(scope, kpis, specs, dimensions=None, dimension_label='Team'):
    """Context for templates/kpi/import_data.html.

    ``specs`` are the Add-Record modal's input labels, one per enterable KPI;
    each is merged with its KPI's kind/target/formula so the modal has
    everything in one structure. ``dimensions`` optionally adds a second
    dropdown (which team / channel / function the record belongs to).
    """
    by_name = {k['name']: k for k in kpis}
    modal = []
    for spec in specs:
        kpi = by_name[spec['name']]
        low, high = target_band(kpi)
        modal.append({
            # Defaults so the template can emit every data-* attribute; a blank
            # b_label / c_label tells the modal script to hide that field.
            'b_label': '', 'b_placeholder': '',
            'c_label': '', 'c_placeholder': '', 'unit': '',
            **spec,
            'kind': kpi['kind'],
            'direction': kpi['direction'],
            'target_min': low,
            'target_max': high,
            'target_display': kpi['target_display'],
            'formula': kpi['formula'],
        })
    return {
        'scope': scope,
        'modal_kpis': modal,
        'dimensions': dimensions or [],
        'dimension_label': dimension_label,
    }
