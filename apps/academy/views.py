from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """VINTAZK Academy line-of-business screen."""
    return render(request, 'academy/index.html', {'lob_name': 'VINTAZK Academy'})
