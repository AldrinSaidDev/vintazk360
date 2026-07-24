from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Human Resources line-of-business screen."""
    return render(request, 'hr/index.html', {'lob_name': 'Human Resources'})
