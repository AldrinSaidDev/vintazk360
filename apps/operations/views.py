from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Operations line-of-business screen."""
    return render(request, 'operations/index.html', {'lob_name': 'Operations'})
