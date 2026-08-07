"""Turn a LOB's static KPI dicts into real `kpi_definition` rows.

Every LOB was built as a Python list of KPI dicts: a name, a target, a prose
formula, and an Add-Record `kind` naming the arithmetic ('percent', 'days',
'variance'…). That was enough to render a mockup. It is not enough to store an
actual, because `db_schema.txt` wants the formula as DATA (§A.2) and the
operands as `kpi_input` rows whose `key` is at once the expression variable, the
CSV column header and the form field name (§6).

This module is the bridge. Given `kind` plus the modal's operand labels it
derives:

  * an `expression` in the whitelisted grammar `apps/kpi/formula.py` accepts,
  * one `KpiInput` per operand, keyed off a slug of its own label,
  * and, where the graded number differs from the shown one, a
    `score_expression` (a signed budget variance shows −3.2% and grades as 3.2).

The prose `formula` string in the LOB modules is NOT parsed. It was written for
humans, it varies in shape from LOB to LOB, and guessing at it would produce
formulas nobody checked. `formula_text` is regenerated from the expression and
the operand labels instead, exactly as the create form does it.

Deriving the key from the LABEL rather than emitting a/b/c is deliberate: the
key becomes a CSV column header that a manager fills in by hand, so
`total_exits` is worth having over `a`.
"""

from decimal import Decimal

from django.db import transaction
from django.utils.text import slugify

from . import formula as formula_engine
from .models import (
    Accumulation,
    DataType,
    DisplayFormat,
    Frequency,
    KpiCategory,
    KpiDefinition,
    KpiFormulaHistory,
    KpiInput,
)


class SeedError(ValueError):
    """A KPI spec that cannot be turned into a definition. Names the KPI."""


# --- kind → arithmetic ------------------------------------------------------
#
# `expression` uses the placeholders A/B/C, substituted for the real input keys
# below. `score` is set only where the graded number differs from the shown one.
# `operands` is how many inputs the kind consumes; `dates` marks the ones whose
# inputs are dates rather than numbers.
KINDS = {
    'percent':     {'operands': 2, 'expression': 'A / B * 100',            'format': DisplayFormat.PERCENT},
    'net_percent': {'operands': 2, 'expression': '(A - B) / A * 100',      'format': DisplayFormat.PERCENT},
    'accuracy':    {'operands': 2, 'expression': '(1 - abs(A - B) / B) * 100', 'format': DisplayFormat.PERCENT},
    'variance':    {'operands': 2, 'expression': '(A - B) / B * 100',      'format': DisplayFormat.PERCENT,
                    # Shown signed, graded on the magnitude against a ±tolerance band.
                    'score': 'abs((A - B) / B * 100)'},
    'average':     {'operands': 2, 'expression': 'A / B',                  'format': DisplayFormat.NUMBER},
    'ratio':       {'operands': 2, 'expression': 'A / B',                  'format': DisplayFormat.RATIO},
    'cost':        {'operands': 2, 'expression': 'A / B',                  'format': DisplayFormat.CURRENCY},
    'difference':  {'operands': 2, 'expression': 'A - B',                  'format': DisplayFormat.NUMBER},
    'scaled':      {'operands': 3, 'expression': 'A / B * C',              'format': DisplayFormat.NUMBER},
    'days':        {'operands': 2, 'expression': 'days_between(B, A)',     'format': DisplayFormat.DAYS,
                    # a_label is the END date ("ready date"), b_label the start.
                    'dates': True},
    'count':       {'operands': 1, 'expression': 'A',                      'format': DisplayFormat.INTEGER},
}

# The LOB modules spell frequencies as display labels.
_FREQUENCY = {label: value for value, label in Frequency.choices}
# Nexzys' provisioning KPI reports "Per Wave", which is not a calendar cadence.
# Monthly is the closest real period and keeps the CSV template usable.
_FREQUENCY_ALIASES = {'Per Wave': Frequency.MONTHLY, 'Per Campaign': Frequency.MONTHLY}


def frequency_value(label):
    value = _FREQUENCY.get(label) or _FREQUENCY_ALIASES.get(label)
    if value is None:
        raise SeedError(f'Unknown frequency "{label}".')
    return value


def input_key(label, taken):
    """A valid, unique `kpi_input.key` derived from the operand's label.

    The key has to match `^[a-z][a-z0-9_]*$` (§6) and be unique within the KPI,
    since it is simultaneously an expression variable and a CSV header.
    """
    base = slugify(label).replace('-', '_').strip('_')[:40] or 'value'
    if not base[0].isalpha():
        base = f'v_{base}'
    candidate, counter = base, 2
    while candidate in taken:
        candidate = f'{base}_{counter}'
        counter += 1
    taken.add(candidate)
    return candidate


def operands(spec, kind):
    """The modal spec's a/b/c labels, as many as this kind consumes."""
    labels = [
        (spec.get('a_label') or '').strip(),
        (spec.get('b_label') or '').strip(),
        (spec.get('c_label') or '').strip(),
    ][: KINDS[kind]['operands']]

    if not all(labels):
        raise SeedError(
            f'"{spec["name"]}" is kind "{kind}", which needs '
            f'{KINDS[kind]["operands"]} labelled input(s).'
        )
    return labels


def build_formula(kind, labels):
    """`(expression, score_expression, inputs)` for one KPI.

    `inputs` are ready-to-create `KpiInput` kwargs, in CSV column order.
    """
    rule = KINDS[kind]
    taken = set()
    inputs = []
    for position, label in enumerate(labels, start=1):
        key = input_key(label, taken)
        inputs.append({
            'key': key,
            'label': label[:120],
            'placeholder': '',
            'data_type': DataType.DATE if rule.get('dates') else DataType.NUMBER,
            'position': position,
        })

    mapping = dict(zip('ABC', (item['key'] for item in inputs)))

    def substitute(template):
        # Longest-first is not needed (A/B/C are single chars and the keys are
        # lowercase), but replace in one pass so a key containing 'A' cannot be
        # re-substituted.
        return ''.join(mapping.get(char, char) for char in template)

    expression = substitute(rule['expression'])
    score = substitute(rule['score']) if rule.get('score') else ''
    return expression, score, inputs


def unit_suffix(kind, spec):
    """The unit as `format_value()` wants it, or '' when the format carries one.

    The LOB modules disagree about spacing: HR writes `' days'` with a leading
    space, Nexzys writes `'hrs'` without. A word needs the space ("8.6 days"), a
    symbol must not have one ("3.4×"), so the space is decided here rather than
    trusted from nine hand-written modules.
    """
    if kind in ('percent', 'net_percent', 'accuracy', 'variance'):
        return ''  # these already print a '%'; a unit on top would double it

    unit = (spec.get('unit') or '').strip()
    if not unit or unit == '%':
        return ''
    return f' {unit}' if unit[0].isalnum() else unit


def _decimal(value):
    return None if value is None else Decimal(str(value))


def target_band(kpi):
    """`(min, max)`, treating a single target as a band of width zero."""
    if kpi.get('target') is not None:
        return _decimal(kpi['target']), _decimal(kpi['target'])
    return _decimal(kpi.get('target_min')), _decimal(kpi.get('target_max'))


def unique_slug(team, name):
    """A slug stable enough to bind a downloaded CSV to."""
    base = slugify(name)[:110] or 'kpi'
    candidate, counter = base, 2
    existing = KpiDefinition.objects.filter(team=team, branch=None)
    while existing.filter(slug=candidate).exists():
        candidate = f'{base}-{counter}'
        counter += 1
    return candidate


@transaction.atomic
def seed_kpi(team, kpi, spec, *, sort_order=0, user=None):
    """Create one `KpiDefinition` with its inputs and seed formula history.

    Returns the definition. The caller decides whether to skip an existing slug;
    this always creates.
    """
    kind = kpi.get('kind') or spec.get('kind')
    if kind not in KINDS:
        raise SeedError(f'"{kpi["name"]}" has unknown kind "{kind}".')

    labels = operands(spec, kind)
    expression, score_expression, inputs = build_formula(kind, labels)

    # Same validation the create form runs, so a seeded KPI is indistinguishable
    # from a hand-authored one.
    expression = formula_engine.validate(expression, [i['key'] for i in inputs])
    formula_text = formula_engine.render_text(
        expression, {i['key']: i['label'] for i in inputs}
    )[:255]

    category = None
    if kpi.get('category'):
        category, _ = KpiCategory.objects.get_or_create(
            team=team, name=kpi['category']
        )

    target_min, target_max = target_band(kpi)

    definition = KpiDefinition.objects.create(
        team=team,
        category=category,
        name=kpi['name'],
        slug=unique_slug(team, kpi['name']),
        description=kpi.get('description', ''),
        expression=expression,
        score_expression=score_expression,
        formula_text=formula_text,
        frequency=frequency_value(kpi['frequency']),
        direction=kpi['direction'],
        target_min=target_min,
        target_max=target_max,
        target_display=kpi.get('target_display', ''),
        display_format=KINDS[kind]['format'],
        unit=unit_suffix(kind, spec),
        precision=1,
        accumulation=Accumulation.PERIOD,
        sort_order=sort_order,
        created_by=user,
    )

    KpiInput.objects.bulk_create(
        KpiInput(kpi=definition, **item) for item in inputs
    )

    # The formula this KPI shipped with, so its first period is as explainable
    # as every later one (§12, §E.3).
    KpiFormulaHistory.objects.create(
        kpi=definition,
        expression=definition.expression,
        score_expression=definition.score_expression,
        formula_text=definition.formula_text,
        template_version=definition.template_version,
        effective_from=definition.created_at.date(),
        reason='Initial formula',
        changed_by=user,
    )

    return definition
