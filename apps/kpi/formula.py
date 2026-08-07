"""Parse, validate, render and evaluate a KPI formula.

A KPI's `expression` is written by a manager in the browser, so it is untrusted
input that ends up being calculated server-side. It is therefore parsed with
Python's `ast` module and walked against the whitelist below — **never
`eval()`**, which on a manager-supplied string would be a remote-code-execution
hole in a login-protected admin tool (`db_schema.txt` §A.2).

Four jobs, all keyed off the same tiny grammar:

    parse/validate  — reject anything outside the whitelist, at SAVE time
    names           — which inputs an expression references
    render_text     — the readable sentence `KpiDefinition.formula_text` stores
    evaluate        — the number, once the raw operands are known

The grammar is deliberately small: input keys, numeric constants, `+ - * /`,
parentheses, and five functions.
"""

from __future__ import annotations

import ast
import datetime as _dt


class FormulaError(ValueError):
    """A formula that cannot be stored or evaluated. Message is user-facing."""


# --- the whitelist ---------------------------------------------------------

def _days_between(start, end):
    """Whole days from `start` to `end` — `days_between(day_zero, ready_date)`."""
    if not isinstance(start, _dt.date) or not isinstance(end, _dt.date):
        raise FormulaError('days_between() needs two dates.')
    return (end - start).days


ALLOWED_FUNCTIONS = {
    'abs': abs,
    'min': min,
    'max': max,
    'round': round,
    'days_between': _days_between,
}

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}

# Precedence and display symbol, used by both the whitelist and the renderer.
_PRECEDENCE = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2}
_SYMBOL = {ast.Add: '+', ast.Sub: '−', ast.Mult: '×', ast.Div: '÷'}


# --- parsing ---------------------------------------------------------------


def parse(expression: str) -> ast.Expression:
    """Parse `expression` and reject every node outside the whitelist.

    Raises `FormulaError` with a message meant for the person who typed it.
    """
    text = (expression or '').strip()
    if not text:
        raise FormulaError('Enter a formula.')

    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError:
        raise FormulaError('That formula is not valid — check the brackets and operators.')

    _check(tree.body)
    return tree


def _check(node):
    """Walk one node, rejecting anything the grammar does not allow."""
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BIN_OPS:
            raise FormulaError('Only + − × ÷ are allowed.')
        _check(node.left)
        _check(node.right)

    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.UAdd, ast.USub)):
            raise FormulaError('Only a leading + or − is allowed.')
        _check(node.operand)

    elif isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FormulaError('Only numbers can appear in a formula.')

    elif isinstance(node, ast.Name):
        if not isinstance(node.ctx, ast.Load):
            raise FormulaError('A formula can only read its inputs.')

    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
            allowed = ', '.join(sorted(ALLOWED_FUNCTIONS))
            raise FormulaError(f'Only these functions are allowed: {allowed}.')
        if node.keywords:
            raise FormulaError('Functions take plain arguments only.')
        for argument in node.args:
            _check(argument)

    else:
        # Attributes, subscripts, comparisons, lambdas, comprehensions, strings —
        # everything else is out, including __import__ and open.
        raise FormulaError('That formula contains something that is not allowed.')


def names(expression: str) -> set[str]:
    """Every input key the expression references.

    A called function is an `ast.Name` too, so `days_between(a, b)` would
    otherwise report `days_between` as a missing input.
    """
    tree = parse(expression)
    called = {
        node.func
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node not in called
    }


def validate(expression: str, keys) -> str:
    """Check the expression against this KPI's declared input keys.

    Enforces both halves of `db_schema.txt` §A.2: every name in the expression
    is a declared input, and every declared input is actually used. Returns the
    normalised expression string.
    """
    keys = list(keys)
    used = names(expression)

    unknown = sorted(used - set(keys))
    if unknown:
        raise FormulaError(
            'The formula uses ' + ', '.join(unknown) + ' but there is no such input. '
            'Add it under Inputs, or correct the spelling.'
        )

    unused = [key for key in keys if key not in used]
    if unused:
        raise FormulaError(
            'These inputs are not used in the formula: ' + ', '.join(unused) + '. '
            'Every input becomes a CSV column, so an unused one would never be filled in.'
        )

    if not used:
        raise FormulaError('A formula needs at least one input, not only numbers.')

    # A KPI whose formula cannot be worked out at all is not worth storing, so
    # dry-run it once against a sample row of 1s (§A.2).
    sample = {key: 1 for key in keys}
    try:
        evaluate(expression, sample, _sample=True)
    except FormulaError:
        raise
    except Exception:
        raise FormulaError('That formula could not be calculated — check its structure.')

    return (expression or '').strip()


# --- rendering the human sentence ------------------------------------------


def render_text(expression: str, labels: dict[str, str] | None = None) -> str:
    """Render the readable sentence stored in `KpiDefinition.formula_text`.

    `'total_exits / average_headcount * 100'` with the KPI's input labels
    becomes `'Total exits ÷ Average headcount × 100'`. Generated, never typed,
    so the sentence can't drift from the maths (`db_schema.txt` §5).
    """
    return _render(parse(expression).body, labels or {})


def _render(node, labels, parent_precedence=0, is_right=False):
    if isinstance(node, ast.BinOp):
        precedence = _PRECEDENCE[type(node.op)]
        text = (
            _render(node.left, labels, precedence)
            + f' {_SYMBOL[type(node.op)]} '
            + _render(node.right, labels, precedence, is_right=True)
        )
        # Keep the brackets the author meant: a lower-precedence child always
        # needs them, and so does an equal-precedence right operand of − or ÷.
        if precedence < parent_precedence or (precedence == parent_precedence and is_right):
            return f'({text})'
        return text

    if isinstance(node, ast.UnaryOp):
        sign = '−' if isinstance(node.op, ast.USub) else '+'
        return sign + _render(node.operand, labels, 3)

    if isinstance(node, ast.Name):
        return labels.get(node.id, node.id)

    if isinstance(node, ast.Constant):
        value = node.value
        return str(int(value)) if float(value).is_integer() else str(value)

    if isinstance(node, ast.Call):
        rendered = [_render(a, labels, 0) for a in node.args]
        if node.func.id == 'days_between' and len(rendered) == 2:
            return f'days between {rendered[0]} and {rendered[1]}'
        return f"{node.func.id}({', '.join(rendered)})"

    raise FormulaError('That formula contains something that is not allowed.')


# --- evaluation ------------------------------------------------------------


def evaluate(expression: str, values: dict, _sample: bool = False):
    """Calculate the expression against one row of raw operand values."""
    return _eval(parse(expression).body, values, _sample)


def _eval(node, values, sample):
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, values, sample)
        right = _eval(node.right, values, sample)
        if isinstance(node.op, ast.Div) and right == 0:
            raise FormulaError('This works out to a division by zero.')
        return _BIN_OPS[type(node.op)](left, right)

    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, values, sample)
        return -operand if isinstance(node.op, ast.USub) else +operand

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in values:
            raise FormulaError(f'No value was given for {node.id}.')
        return values[node.id]

    if isinstance(node, ast.Call):
        arguments = [_eval(a, values, sample) for a in node.args]
        if sample and node.func.id == 'days_between':
            # The dry run feeds 1s, not dates — the shape is what is being checked.
            return 1
        return ALLOWED_FUNCTIONS[node.func.id](*arguments)

    raise FormulaError('That formula contains something that is not allowed.')
