from django.urls import path

from . import views

app_name = 'sales'

urlpatterns = [
    path('', views.index, name='index'),  # team rollup across the three branches

    # Sales splits into branches (SEO & Google Ads / Lead Gen / Transitions).
    # Each gets the same four screens, served by the shared kit and keyed on the
    # branch slug. KpiScreens.url() reverses these by prefixing "branch_", so
    # the names have to keep that shape.
    path('<slug:branch>/', views.branch_index, name='branch_index'),
    path('<slug:branch>/kpis/', views.branch_kpis, name='branch_kpis'),
    path('<slug:branch>/import/', views.branch_import_data, name='branch_import_data'),
    path('<slug:branch>/manage/', views.branch_kpi_management, name='branch_kpi_management'),
    # CSV template, generated from the KPI's own inputs — not a stored file.
    path(
        '<slug:branch>/manage/<slug:slug>/template.csv',
        views.branch_kpi_template,
        name='branch_kpi_template',
    ),
]
