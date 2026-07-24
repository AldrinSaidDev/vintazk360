from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Sales line-of-business screen."""
    return render(request, 'sales/index.html', {'lob_name': 'Sales'})
