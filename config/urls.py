"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    # Built-in auth views: login, logout, password change/reset, etc.
    path('', include('django.contrib.auth.urls')),
    path('', include('apps.dashboard.urls')),

    # Line-of-business (LOB) screens — each its own app.
    path('sales/', include('apps.sales.urls')),
    path('hr/', include('apps.hr.urls')),
    path('academy/', include('apps.academy.urls')),
    path('operations/', include('apps.operations.urls')),
    path('finance/', include('apps.finance.urls')),
    path('sitelead/', include('apps.sitelead.urls')),
    path('marketing/', include('apps.marketing.urls')),
    path('nexzys/', include('apps.nexzys.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
