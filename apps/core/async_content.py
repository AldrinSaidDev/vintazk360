"""Two-stage page rendering: an instant shell, then the data.

Every screen in this project builds its whole context before it returns, so the
browser sits on the *previous* page for the entire query and a skeleton in the
template would arrive already filled in. This module splits that into two
requests so there is a real gap for the skeleton to occupy:

    1. GET /operations/          -> the shell. No queries, so it paints at once:
                                    sidebar, header, and the skeleton.
    2. GET /operations/?partial=1 -> the same view, running for real, returning
                                    only its content fragment.

The skeleton therefore lasts exactly as long as the query does. Nothing here is
on a timer, and no view has to guess how slow it is going to be.

Why one template can serve both stages
--------------------------------------
A screen template extends ``base_template`` rather than naming ``base.html``
outright. Stage 2 hands it ``partials/fragment_base.html``, which emits the
content and scripts blocks and nothing else. No screen had to be split into a
page half and a fragment half, so there is no second copy to keep in step.

Three shapes, not two
---------------------
A POST that fails validation re-renders the page in place, with its form errors
and its modal forced open. That response must carry the real content, not a
skeleton pointing at a fetch that would throw the errors away. ``full`` is that
case: the whole page, rendered the old way. It is also the fallback for anything
that cannot use the shell.
"""

from urllib.parse import urlencode

from django.shortcuts import render

# The flag stage 2 sets. A query parameter rather than a header, so the fragment
# URL is something you can open in a browser to see what the page is actually
# fetching, and so the <noscript> link is a real address.
PARTIAL_PARAM = 'partial'

FRAGMENT_BASE = 'partials/fragment_base.html'
PAGE_BASE = 'base.html'

GENERIC_SKELETON = 'partials/skeletons/generic.html'


def is_partial(request):
    """True when this is stage 2, the fetch for the content itself."""
    return request.GET.get(PARTIAL_PARAM) == '1'


def wants_shell(request):
    """True when this request should get the instant skeleton.

    GET only. A POST is either going to redirect or to re-render with errors,
    and neither is improved by a skeleton.
    """
    return request.method == 'GET' and not is_partial(request)


def partial_url(request):
    """This request's URL with the stage 2 flag added.

    Built from ``request.GET`` rather than from the path alone, so a filtered or
    paginated screen fetches the page the user actually asked for. Without this
    every fetch would quietly return page 1 unfiltered.
    """
    params = request.GET.copy()
    params[PARTIAL_PARAM] = '1'
    return f'{request.path}?{urlencode(params, doseq=True)}'


def render_shell(request, *, shell_template, skeleton=GENERIC_SKELETON, context=None):
    """Stage 1. The page frame and a skeleton, with none of the page's data."""
    data = dict(context or {})
    data['async_src'] = partial_url(request)
    data['skeleton_template'] = skeleton
    return render(request, shell_template, data)


def render_content(request, template, context):
    """Stage 2 or the full page, decided by which request this is.

    Views call this in place of ``render``. On a POST or any non-partial request
    it renders the complete page exactly as before, so a validation failure keeps
    its errors and an open modal.
    """
    data = dict(context)
    data['base_template'] = FRAGMENT_BASE if is_partial(request) else PAGE_BASE
    return render(request, template, data)
