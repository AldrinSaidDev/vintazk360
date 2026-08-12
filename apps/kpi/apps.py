from django.apps import AppConfig


class KpiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.kpi'
    # Short label so the tables stay `kpi_*` rather than `apps_kpi_*`
    # (each model also names its db_table explicitly).
    label = 'kpi'
    verbose_name = 'KPI'
