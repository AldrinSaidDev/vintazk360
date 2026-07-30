from django.urls import path

from . import views

app_name = 'marketing'

urlpatterns = [
    path('', views.index, name='index'),  # overview of the three branches

    # VCT splits into branches (SMM / Content Writer / Visual Team). Each gets
    # the same four screens, served by shared views + templates and keyed on
    # the branch slug.
    path('<slug:branch>/', views.branch_index, name='branch_index'),
    path('<slug:branch>/kpis/', views.branch_kpis, name='branch_kpis'),
    path('<slug:branch>/import/', views.branch_import_data, name='branch_import_data'),
    path('<slug:branch>/manage/', views.branch_kpi_management, name='branch_kpi_management'),
]
