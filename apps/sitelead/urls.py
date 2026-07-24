from django.urls import path

from . import views

app_name = 'sitelead'

urlpatterns = [
    path('', views.index, name='index'),
]
