from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('logs/', views.logs, name='logs'),
    path('settings/', views.account_settings, name='settings'),
    path('tour/seen/', views.tour_seen, name='tour_seen'),
]
