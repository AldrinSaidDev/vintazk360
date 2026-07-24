from django.shortcuts import render


def home(request):
    """Landing page for the dashboard."""
    return render(request, 'dashboard/home.html', {'title': 'Dashboard'})
