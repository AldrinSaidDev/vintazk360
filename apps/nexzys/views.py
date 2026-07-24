from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Nexzys Intelligence line-of-business screen."""
    return render(request, 'nexzys/index.html', {'lob_name': 'Nexzys Intelligence'})
