from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Finance line-of-business screen."""
    return render(request, 'finance/index.html', {'lob_name': 'Finance'})
