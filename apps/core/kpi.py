"""The KPI band math: attainment, status, and how attainment is displayed.

This is the one implementation of "how far off target is this number?", used by
`apps.kpi.records.score()` on every write and by every LOB dashboard on every
read. It is deliberately free of Django: it takes a dict and returns numbers.

A KPI is scored against a target BAND::

    {'target_min': 40, 'target_max': 80, 'direction': 'up', 'actual': 62}

A single figure is a band of width zero, so one piece of math serves single
targets and Sales-style ranges alike. `direction` is 'up' (higher is better) or
'down' (lower is better: cost, days-to-fill, attrition). A band of
`(None, None)` means the KPI is tracked but not scored, which surfaces as the
'monitored' status.

A two-sided tolerance ("within ±5%") is a 'down' KPI over a
`target_min=0 / target_max=5` band on the ABSOLUTE value, so overspend and
underspend are penalised alike and anything inside the tolerance is 100%.

The page context that used to live here went with the static KPI screens; every
LOB but Sales now builds its context in `apps/kpi/screens.py` from the database.
"""

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
