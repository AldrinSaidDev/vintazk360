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
