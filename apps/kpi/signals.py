"""Cache invalidation: any write to a team's KPI data retires that team's cache.

**Signals rather than call sites.** The alternative was a line in `save_record`,
another in each delete branch, another in the importer, another in the two KPI
forms, and one more in every screen a future feature adds. One of them would
eventually be forgotten and the symptom would be a stale figure nobody could
reproduce. A `post_save` receiver cannot be forgotten: it also covers the Django
admin (the only place a deleted record or import can be restored) and
`manage.py seed_lob_kpis`, neither of which goes anywhere near a view.

**Soft deletes are saves.** `KpiDefinition`, `KpiRecord`, `KpiEntry` and
`KpiImportBatch` are all deleted by setting `is_active=False`, so `post_save`
sees them.
`post_delete` is wired anyway for the hard deletes that do happen: replacing a
record's operand rows, removing an input, and anything done from a shell.

Everything is retired together, per team, rather than per screen. The cached
answers overlap heavily (a record feeds the team dashboard, the department card
on the org dashboard and the import tiles) and working out which of them a given
row touches is exactly the bookkeeping that goes wrong. Rebuilding a team's
roll-ups is a handful of queries.
"""
from __future__ import annotations

from functools import lru_cache

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.cache import invalidate_team_on_commit

from .models import (
    KpiBranch,
    KpiCategory,
    KpiDefinition,
    KpiEntry,
    KpiImportBatch,
    KpiInput,
    KpiRecord,
)


@lru_cache(maxsize=4096)
def _team_of_kpi(kpi_id):
    """Which team owns a KPI, remembered for the life of the process.

    A record save would otherwise cost an extra SELECT just to find the team to
    invalidate, once per row of an import. Memoising is safe because a KPI never
    moves between teams: `team` is set when it is created and no screen, form or
    command offers a way to change it.
    """
    return (
        KpiDefinition.objects.filter(pk=kpi_id)
        .values_list('team_id', flat=True)
        .first()
    )


def _team_via_kpi(instance):
    """The team behind a row that hangs off a KPI, without a query when possible."""
    # Already-loaded relation (the usual case: `save_record` holds the KPI).
    kpi = instance.__dict__.get('kpi')
    if kpi is not None:
        return kpi.team_id
    return _team_of_kpi(instance.kpi_id)


# --- rows that name their team directly -------------------------------------

@receiver(post_save, sender=KpiDefinition)
@receiver(post_delete, sender=KpiDefinition)
@receiver(post_save, sender=KpiCategory)
@receiver(post_delete, sender=KpiCategory)
@receiver(post_save, sender=KpiImportBatch)
@receiver(post_delete, sender=KpiImportBatch)
@receiver(post_save, sender=KpiBranch)
@receiver(post_delete, sender=KpiBranch)
def invalidate_from_team_field(sender, instance, **kwargs):
    invalidate_team_on_commit(instance.team_id)


# --- rows that reach their team through a KPI -------------------------------

@receiver(post_save, sender=KpiRecord)
@receiver(post_delete, sender=KpiRecord)
@receiver(post_save, sender=KpiEntry)
@receiver(post_delete, sender=KpiEntry)
@receiver(post_save, sender=KpiInput)
@receiver(post_delete, sender=KpiInput)
def invalidate_from_kpi(sender, instance, **kwargs):
    invalidate_team_on_commit(_team_via_kpi(instance))
