"""Departments that a role alone does not open.

Finance and Human Resources carry payroll and personnel figures, so reaching
them is a named-person decision rather than a role one. `restricted_teams.json`
holds both halves of that decision: which departments are restricted, and who
is allowed in. Adding a third department or a fourth person is an edit to that
file, not to this module.

**This is a filter on top of the role rules, never a replacement for them.**
`access.accessible_teams()` works out what the role reaches and then removes
the restricted departments this person is not named for, which is why a Super
Admin who is not on the list reaches every other department and not these two.
The Django `is_superuser` escape hatch is filtered too: it exists so a locked
out administrator can still run the system, and that is not a reason to hand
them payroll.

Because it narrows `accessible_teams()`, one edit covers every screen at once:
the sidebar, `team_required`, the dashboard's global department filter, the
search palette and the activity log's Module filter all ask that one function.

Matching is by EMAIL, lower-cased. The employee ID is recorded in the file for
reference but is deliberately not the key: it is assigned by another system and
may not be known when the entry is written, and an entry that matched on a
blank ID would match every account that has none.
"""
import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent / 'restricted_teams.json'


@lru_cache(maxsize=1)
def _config():
    """Read and cache the JSON file.

    Cached because it is read on every request through `accessible_teams()` and
    it only changes on deploy. Call `reload()` after editing it in a shell.

    Fail SAFE, not open: an unreadable or malformed file leaves the restricted
    list empty, so the departments fall back to the ordinary role rules rather
    than becoming unreachable for everybody including the two people who are
    supposed to be in them. The alternative locks the business out of its own
    payroll over a stray comma, and the error is logged either way.
    """
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        logger.exception('Could not read %s; no departments restricted.', _CONFIG_PATH)
        return frozenset(), frozenset()

    teams = frozenset(
        slug.strip().lower()
        for slug in raw.get('restricted_teams', [])
        if isinstance(slug, str) and slug.strip()
    )
    emails = frozenset(
        entry.get('email', '').strip().lower()
        for entry in raw.get('allowed', [])
        if isinstance(entry, dict) and entry.get('email', '').strip()
    )
    return teams, emails


def reload():
    """Drop the cached file so the next call re-reads it."""
    _config.cache_clear()


def restricted_slugs():
    """The team slugs a role alone does not open, as a frozenset."""
    return _config()[0]


def allowed_emails():
    """The lower-cased emails named in the allowlist, as a frozenset."""
    return _config()[1]


def is_allowed(user):
    """True if ``user`` is one of the people named for the restricted teams.

    An account with no email address can never match, which is the intended
    reading of "these two accounts and nobody else": the allowlist names people
    by an address, and an account that has none is not one of them.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    email = (getattr(user, 'email', '') or '').strip().lower()
    return bool(email) and email in allowed_emails()


def hidden_slugs_for(user):
    """The restricted team slugs ``user`` may NOT reach.

    Empty for somebody on the allowlist, and empty when nothing is restricted,
    which is what lets the caller skip the query entirely in the common case.
    """
    if is_allowed(user):
        return frozenset()
    return restricted_slugs()
