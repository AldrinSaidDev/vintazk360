from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Site Lead line-of-business screen."""
    return render(request, 'sitelead/index.html', {'lob_name': 'Site Lead'})
