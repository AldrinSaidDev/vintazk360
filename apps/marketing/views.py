from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Social Media & Marketing line-of-business screen."""
    return render(request, 'marketing/index.html', {'lob_name': 'Social Media & Marketing'})
