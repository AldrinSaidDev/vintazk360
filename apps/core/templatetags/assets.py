"""`{% asset %}` — a static URL that changes whenever the file does.

Why this exists rather than plain `{% static %}`: the KPI screens render in two
stages, so the tags in their `{% block scripts %}` are INJECTED by
async-content.js after the page has loaded. A browser fetches an injected
script under ordinary cache rules, and **a hard refresh does not reach it** — a
hard refresh revalidates the document and the subresources the document itself
references, which an element created by script afterwards is not. `runserver`
sends `Last-Modified` and no `Cache-Control`, so the browser is entitled to
serve its own copy for hours.

That is not hypothetical. An edit to `formula_builder.js` went live beside a
template it had rewritten, the cached script knew nothing about the new panel,
and the screen rendered half of each: the inputs listed, the per-input
aggregation pickers missing, and the "add an input" note showing underneath two
inputs. Nothing in the page said the script was stale.

The file's mtime goes in the query string, so the URL changes exactly when the
file does and the stale copy is never asked for again. A file that cannot be
stat'd falls back to the plain static URL — a missing cache-buster is a slow
reload, never a broken page.
"""

import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def asset(path):
    try:
        found = finders.find(path)
        stamp = int(os.path.getmtime(found)) if found else None
    except OSError:
        stamp = None

    url = static(path)
    if stamp is None:
        return url
    return f"{url}{'&' if '?' in url else '?'}v={stamp:x}"
