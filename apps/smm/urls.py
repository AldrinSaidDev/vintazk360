from django.urls import path

from . import views

app_name = 'smm'

urlpatterns = [
    path('', views.index, name='index'),             # team dashboard (scorecard)
    path('kpis/', views.kpi_reference, name='kpis'),  # KPI definitions reference
    path('import/', views.import_data, name='import_data'),
    path('manage/', views.kpi_management, name='kpi_management'),
    # ONE workbook for the whole team, a sheet per KPI. Generated on demand,
    # never stored, so its sheets are always the KPIs that exist right now.
    path('manage/templates.xlsx', views.kpi_workbook, name='kpi_workbook'),
    # The per-KPI CSV. Kept working so a template downloaded before the
    # workbook landed can still be uploaded.
    path('manage/<slug:slug>/template.csv', views.kpi_template, name='kpi_template'),
]
