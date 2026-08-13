"""Read-through caching for the expensive read paths, with invalidation on write.

**The store is Redis (Render Key Value), and Postgres is not a cache.** Postgres
holds the source of truth and nothing else; every entry in here is a derived
answer that can be rebuilt from it. That split is the reason this module can be
as relaxed as it is about losing data: a Key Value restart wipes the lot, the
next reader misses, recomputes from Postgres and re-stores, and the only cost is
one slower page. Nothing here is ever the only copy of anything.

Three numbers describe an entry's life, and they are not the same thing:

* **Stale time (5 minutes).** How long a cached answer is served as-is. Inside
  it a reader gets the stored value and the database is not touched. Past it the
  next reader recomputes and re-stores. Nothing is ever handed out stale.
* **GC time (30 minutes).** The key's TTL in Redis, and the only thing that
  bounds the keyspace. It is longer than the stale time on purpose, and it has a
  real job: invalidation here works by bumping a VERSION token that is part of
  the key, so a write orphans the old entries rather than deleting them. The TTL
  is what sweeps those orphans, plus the entries for teams nobody has opened.
  Shortening it to the stale time would work, but every filter combination still
  being read would then be recomputed and rewritten every five minutes.
* **Invalidation (immediate).** A write does not wait for either clock. Saving a
  KPI, a record, an import or a category bumps its team's version token, so the
  very next read builds a key nothing is stored under and goes to the database.
  That is the guarantee: an edit is visible on the next page load, not in five
  minutes.

**Why a version token rather than deleting keys.** The cached answers for one
team are spread across several keys (the department card, each branch's
scorecard, the definitions list, the import tiles) and some carry the dashboard
filters in them, so the set is open-ended and cannot be enumerated. Bumping one
token retires all of them at once, and it works across every gunicorn worker
because the token lives in the shared cache, not in a process. Enumerating
Redis keys with `SCAN` would be the alternative, and it is a worse one: an
O(keyspace) sweep on every write against a token that is one `SET`.

**The token is a timestamp, not a counter.** A counter that fell out of the
cache would restart at 1 and could make retired keys reachable again. A token
minted from the clock is always greater than every token before it, so a lost
one can only ever retire more than it should, never resurrect. That property is
what makes eviction safe: Key Value should run `allkeys-lru`, which is allowed
to drop a version token like any other key, and dropping one costs a round of
recomputation rather than a wrong answer.

**Every call here is fail-soft.** Redis is a dependency of the fast path, not of
the app: if it is unreachable, `_safe` swallows the error and the caller behaves
exactly as it would on a miss, which means a page built from Postgres. An
invalidation lost that way cannot leave a stale answer behind either, because
there is no reachable cache for a stale answer to live in.

**Batching.** The org dashboard asks for ten departments at once, and asked one
at a time that is ten version reads plus ten value reads. `versions()`,
`team_keys()` and `fetch_many()` do the same work in two round trips whatever
the department count, which matters far more against a network hop than it did
against a local table.
"""
from __future__ import annotations

import hashlib
import logging
import time
from functools import partial

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)

# How long a stored answer counts as fresh, and how long the key survives at
# all. Overridable per environment; the defaults are the project's stated policy.
STALE_SECONDS = getattr(settings, 'CACHE_STALE_SECONDS', 300)
GC_SECONDS = getattr(settings, 'CACHE_GC_SECONDS', 1800)

# Namespaces every key this module writes, so a `redis-cli` session can tell our
# entries from Django's own (anything added later). Django adds its own
# KEY_PREFIX in front of this.
PREFIX = 'vz'

# Version tokens must outlive the entries they stamp, or an entry could survive
# its own token and be reachable under a freshly minted one. They are given a
# long TTL rather than none: a token nobody has read in a month belongs to a
# team nobody has opened in a month, and an unbounded key is the one kind this
# module would never clean up by itself. Losing one early is harmless (see the
# module docstring), so the margin over GC_SECONDS only has to be generous.
VERSION_SECONDS = getattr(settings, 'CACHE_VERSION_SECONDS', 30 * 24 * 3600)


def _safe(operation, default=None):
    """Run a cache operation, treating an unreachable cache as a miss.

    Redis is where the fast answers live, not where the data lives, so nothing
    in the app should fail because it is down. A failed read behaves as a miss
    and a failed write as a write nobody will read.
    """
    try:
        return operation()
    except Exception:  # noqa: BLE001 - backend-specific; all of them mean "no cache"
        logger.warning('Cache unavailable, falling back to the database.',
                       exc_info=True)
        return default


def _token():
    """A version token: the wall clock, so a later one always sorts later."""
    return f'{time.time():.6f}'


def _version_key(scope):
    return f'{PREFIX}:ver:{scope}'


def version(scope):
    """The current version token for `scope`, minting one if there is none."""
    return versions([scope])[scope]


def versions(scopes):
    """Current version tokens for many scopes, in ONE round trip.

    Minting is batched too, so the first hit on a cold cache costs one read and
    one write however many scopes are asked for.
    """
    # Order-preserving dedupe: two branches of one team share a scope.
    scopes = list(dict.fromkeys(scopes))
    keys = {scope: _version_key(scope) for scope in scopes}

    found = _safe(lambda: cache.get_many(list(keys.values())), {}) or {}

    tokens, minted = {}, {}
    for scope, cache_key in keys.items():
        token = found.get(cache_key)
        if token is None:
            token = _token()
            minted[cache_key] = token
        tokens[scope] = token

    if minted:
        _safe(lambda: cache.set_many(minted, VERSION_SECONDS))
    return tokens


def invalidate(scope):
    """Retire every cached entry under `scope`.

    Nothing is deleted. The token moves, so every existing key for the scope
    stops being built by `key()` and ages out on its own TTL.
    """
    _safe(lambda: cache.set(_version_key(scope), _token(), VERSION_SECONDS))


def key(scope, name, *parts, token=None):
    """A cache key for `name` under `scope`, varying on `parts`.

    `parts` are hashed rather than joined in plain: a dashboard key carries the
    filter window and the status, and neither a key length nor a stray colon
    should be something a filter value can decide.

    `token` skips the version read for callers that have already batched it.
    """
    if token is None:
        token = version(scope)
    tail = '|'.join('' if part is None else str(part) for part in parts)
    digest = hashlib.sha256(tail.encode('utf-8')).hexdigest()[:24]
    return f'{PREFIX}:{scope}:{token}:{name}:{digest}'


# A stored `None` is a real answer (a department the filters emptied), so a
# sentinel is what separates "cached nothing" from "nothing cached".
_MISS = object()


def _envelope_value(entry, now, stale):
    """The stored value if the envelope is still fresh, else `_MISS`."""
    if isinstance(entry, dict) and 'at' in entry and now - entry['at'] < stale:
        return entry['value']
    return _MISS


def fetch(cache_key, producer, *, stale=None, gc=None):
    """Return the cached value for `cache_key`, computing it if it isn't fresh.

    `producer` is called only on a miss or past the stale time, and its result
    is stored with the GC timeout. It has to return something picklable, which
    every caller here satisfies by returning plain dicts and lists rather than
    model instances or querysets. A queryset would also be a trap: pickling one
    stores the ROWS, so a cached queryset is a snapshot pretending to be live.
    """
    stale = STALE_SECONDS if stale is None else stale
    gc = GC_SECONDS if gc is None else gc

    now = time.time()
    value = _envelope_value(_safe(lambda: cache.get(cache_key)), now, stale)
    if value is not _MISS:
        return value

    # `now` was read before the query, so the freshness clock starts when the
    # data was asked for rather than when a slow query happened to finish.
    value = producer()
    _safe(lambda: cache.set(cache_key, {'at': now, 'value': value}, gc))
    return value


def fetch_many(items, *, stale=None, gc=None):
    """`fetch` over several keys at once: one read, then one write.

    `items` is `(identity, cache_key, producer)` triples and the return is
    `{identity: value}`. **Producers run only for the keys that missed**, one at
    a time and only then, so asking for ten departments on a warm cache runs no
    queries at all and asking on a cold one runs exactly the ten it has to.

    Two keys in one call may repeat (two departments cannot, but a caller is not
    forbidden from it); the later producer simply overwrites the earlier value
    for the same key, which is the same answer.
    """
    stale = STALE_SECONDS if stale is None else stale
    gc = GC_SECONDS if gc is None else gc

    items = list(items)
    if not items:
        return {}

    now = time.time()
    stored = _safe(lambda: cache.get_many([k for _, k, _ in items]), {}) or {}

    results, write = {}, {}
    for identity, cache_key, producer in items:
        value = _envelope_value(stored.get(cache_key), now, stale)
        if value is _MISS:
            value = producer()
            write[cache_key] = {'at': now, 'value': value}
        results[identity] = value

    if write:
        _safe(lambda: cache.set_many(write, gc))
    return results


# --- team scope -------------------------------------------------------------
#
# Everything cached in this project is a roll-up of one team's KPI data, so the
# team is the unit of invalidation. A user's own role or team assignment needs
# no scope of its own: which cached team rows get assembled into a page is
# decided per request from `accessible_teams`, so a role change takes effect on
# the next request without touching the cache at all.


def team_scope(team_id):
    return f'team:{team_id}'


def team_key(name, team_id, *parts):
    """A cache key for one team's `name`, varying on `parts`."""
    return key(team_scope(team_id), name, *parts)


def team_keys(name, team_ids, *parts):
    """`team_key` for many teams at once: `{team_id: cache_key}`.

    One version read covers the lot, which is what keeps the org dashboard's
    cost flat as departments are added.
    """
    team_ids = list(team_ids)
    tokens = versions(team_scope(team_id) for team_id in team_ids)
    return {
        team_id: key(team_scope(team_id), name, *parts,
                     token=tokens[team_scope(team_id)])
        for team_id in team_ids
    }


def invalidate_team(team_id):
    """Retire every cached answer derived from this team's data."""
    if team_id is not None:
        invalidate(team_scope(team_id))


def invalidate_team_on_commit(team_id):
    """Retire a team's cache once the writing transaction has committed.

    On commit, not on save. Bumping the token first would let a concurrent
    reader recompute from the pre-commit database and store THAT under the new
    token, which is the one ordering that leaves a wrong answer cached as fresh.
    Outside a transaction Django runs the callback immediately, which is the
    same thing one statement later.

    A bulk write registers one callback per row and they all set the same key to
    (near enough) the same value. That is a handful of tiny writes on a path
    that is already writing a row per record, and it is the price of never
    having to remember which call sites write.
    """
    if team_id is None:
        return
    transaction.on_commit(partial(invalidate_team, team_id))
