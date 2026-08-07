from django.urls import path

from . import views

app_name = 'sitelead'

urlpatterns = [
    path('', views.index, name='index'),             # team dashboard (scorecard)
    path('kpis/', views.kpi_reference, name='kpis'),  # KPI definitions reference
    path('import/', views.import_data, name='import_data'),
    path('manage/', views.kpi_management, name='kpi_management'),
    # CSV template, generated from the KPI's own inputs — not a stored file.
    path('manage/<slug:slug>/template.csv', views.kpi_template, name='kpi_template'),
]
