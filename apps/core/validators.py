"""Password policy for Vintazk 360.

Replaces Django's four default validators with a single house rule (see
``AUTH_PASSWORD_VALIDATORS`` in ``config/settings/base.py``):

    at least 6 characters, one uppercase letter, and one special character.

Applies anywhere a password is set — the Settings > Account tab, the admin,
and ``createsuperuser``. Existing passwords are never re-checked, so accounts
created before this rule keep working until their password next changes.
"""
import re

from django.core.exceptions import ValidationError

MIN_LENGTH = 6

# "Special" = anything that isn't a letter or a digit, so punctuation, symbols,
# and spaces all count.
_SPECIAL = re.compile(r'[^A-Za-z0-9]')
_UPPERCASE = re.compile(r'[A-Z]')


class PasswordPolicyValidator:
    """Enforce length + one uppercase + one special character."""

    def validate(self, password, user=None):
        errors = []

        if len(password) < MIN_LENGTH:
            errors.append(ValidationError(
                f'Password must be at least {MIN_LENGTH} characters.',
                code='password_too_short',
            ))

        if not _UPPERCASE.search(password):
            errors.append(ValidationError(
                'Password must contain at least one uppercase letter.',
                code='password_no_upper',
            ))

        if not _SPECIAL.search(password):
            errors.append(ValidationError(
                'Password must contain at least one special character.',
                code='password_no_special',
            ))

        # Raise them together so the user sees every unmet rule at once rather
        # than fixing one and discovering the next on the following submit.
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return (
            f'At least {MIN_LENGTH} characters, including one uppercase letter '
            'and one special character.'
        )


# --- Employee ID ------------------------------------------------------------
#
# The sign-in credential, and the `entity_name` on every audit row, so its shape
# is worth pinning down: YYYY-MM-NNN, e.g. 2026-07-462.
#
#   YYYY  the year the person was hired
#   MM    the month they were hired, 01 to 12, always two digits
#   NNN   three digits, issued with no pattern, so nothing here can check it
#         beyond its length
#
# Digits and two dashes only. Letters and punctuation are refused outright
# rather than stripped, since silently rewriting somebody's ID would hand them a
# credential different from the one they were given.
EMPLOYEE_ID_FORMAT = 'YYYY-MM-NNN'
EMPLOYEE_ID_EXAMPLE = '2026-07-462'

_EMPLOYEE_ID = re.compile(r'^(\d{4})-(\d{2})-(\d{3})$')

# For the `pattern` attribute on the input, which is HTML's own dialect and has
# no `re` flags. It anchors on its own, so no ^ or $.
EMPLOYEE_ID_HTML_PATTERN = r'\d{4}-(0[1-9]|1[0-2])-\d{3}'


def validate_employee_id(value):
    """Refuse anything that is not YYYY-MM-NNN with a real month."""
    match = _EMPLOYEE_ID.match(value or '')
    if not match:
        raise ValidationError(
            f'Employee ID must be in the format {EMPLOYEE_ID_FORMAT}, '
            f'for example {EMPLOYEE_ID_EXAMPLE}. Numbers and dashes only.',
            code='employee_id_format',
        )

    month = int(match.group(2))
    # The regex cannot say this: it counts digits, and 00 and 13 are both two of
    # them. A hire month is a calendar month.
    if not 1 <= month <= 12:
        raise ValidationError(
            'The middle two digits are the hire month, so they must be 01 to 12.',
            code='employee_id_month',
        )
