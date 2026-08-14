from django.urls import path

from . import views

app_name = 'operations'

# Branch routes, same names Sales uses: KpiScreens.url() reverses them by
# prefixing `branch_` and passing the business unit's slug first, so the names
# are part of the contract rather than a local choice.
urlpatterns = [
    path('', views.index, name='index'),                       # rollup across every unit
    path('<slug:branch>/', views.branch_index, name='branch_index'),
    path('<slug:branch>/kpis/', views.branch_kpis, name='branch_kpis'),
    path('<slug:branch>/import/', views.branch_import_data, name='branch_import_data'),
    path('<slug:branch>/manage/', views.branch_kpi_management, name='branch_kpi_management'),
    # ONE workbook per business unit, a sheet per KPI. Generated on demand,
    # never stored, so its sheets are always the KPIs that exist right now.
    path('<slug:branch>/manage/templates.xlsx', views.branch_kpi_workbook, name='branch_kpi_workbook'),
    # The per-KPI CSV. Kept working so a template downloaded before the
    # workbook landed can still be uploaded.
    path('<slug:branch>/manage/<slug:slug>/template.csv', views.branch_kpi_template, name='branch_kpi_template'),
]
