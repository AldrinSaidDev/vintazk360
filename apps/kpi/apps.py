from django.apps import AppConfig


class KpiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.kpi'
    # Short label so the tables stay `kpi_*` rather than `apps_kpi_*`
    # (each model also names its db_table explicitly).
    label = 'kpi'
    verbose_name = 'KPI'

    def ready(self):
        # Cache invalidation: a write to any KPI table retires its team's
        # cached roll-ups on commit. See signals.py for why it is wired here
        # rather than at each call site.
        from . import signals  # noqa: F401
