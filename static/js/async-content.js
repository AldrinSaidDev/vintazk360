/* Stage 2 of the two-stage page render (see apps/core/async_content.py).
 *
 * The shell has already painted with a skeleton in it. This fetches the same URL
 * with ?partial=1 and swaps the real markup in. The skeleton is on screen for
 * exactly as long as the server takes, which is the whole point: no timer sets
 * how long it shows, and none hides it early.
 */
(function () {
    'use strict';

    /* Scripts inserted with innerHTML never execute, so each one is rebuilt as a
       fresh element to make it run — ONE AT A TIME, waiting for a src to finish
       loading before the next goes in.

       The waiting is the whole point. A screen's scripts block is a library and
       then the inline code that uses it:

           <script src="chart.umd.min.js"></script>
           <script>new Chart(...)</script>

       Inserted together, the inline block runs the moment it is added to the
       document while the 200KB library is still downloading, so it finds no
       `Chart`, returns, and leaves a blank panel where the chart should be.
       Setting `async = false` does not fix that: it orders src scripts against
       each other, but an inline script has nothing to wait for and runs
       immediately whatever the flag says. Sequencing them here is what restores
       document order. A script that fails to load does not stall the rest. */
    function runScripts(container) {
        var scripts = Array.prototype.slice.call(container.querySelectorAll('script'));

        (function next(i) {
            if (i >= scripts.length) return;

            var old = scripts[i];
            var fresh = document.createElement('script');
            Array.prototype.forEach.call(old.attributes, function (attr) {
                fresh.setAttribute(attr.name, attr.value);
            });
            fresh.async = false;

            if (old.getAttribute('src')) {
                var carryOn = function () { next(i + 1); };
                fresh.addEventListener('load', carryOn);
                fresh.addEventListener('error', carryOn);
                old.parentNode.replaceChild(fresh, old);
                return;
            }

            fresh.textContent = old.textContent;
            old.parentNode.replaceChild(fresh, old);
            next(i + 1);
        })(0);
    }

    /* The browser applies a :target modal and scrolls to an anchor when the
       document loads. At that point this content did not exist yet, so the
       scroll has to be redone once it does. Without it, saving a KPI returns you
       to the top of the page instead of to the table you were reading, which is
       exactly what _back_to_page() adds the anchor to prevent. */
    function restoreAnchor() {
        if (!window.location.hash) return;
        var target;
        try {
            target = document.querySelector(window.location.hash);
        } catch (err) {
            return;
        }
        if (target) target.scrollIntoView();
    }

    /* A toast is pinned to the viewport and must not live inside <main>, which is
       the page's scroll container. If the fragment carried one, move it out to
       the body where base.html would have put it. */
    function liftToasts(container) {
        var regions = container.querySelectorAll('[data-toast-region]');
        Array.prototype.forEach.call(regions, function (region) {
            document.body.appendChild(region);
        });
    }

    function fail(host, url) {
        host.innerHTML = ''
            + '<div class="rounded-xl border border-status-bad/30 bg-white p-6 text-sm">'
            + '<p class="font-semibold text-ink">This page could not load its data.</p>'
            + '<p class="mt-1 text-slate-600">The connection may have dropped. '
            + '<a href="' + url + '" class="font-semibold text-brand hover:underline">Try again</a>.</p>'
            + '</div>';
        host.setAttribute('aria-busy', 'false');
    }

    function load(host) {
        var src = host.getAttribute('data-async-src');
        if (!src) return;

        fetch(src, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (response) {
                /* A session that expired mid-visit redirects to the login page,
                   and fetch follows it, so the fragment would come back as a
                   whole login document dropped inside the dashboard. Reloading
                   hands the user the real login screen instead. */
                if (response.redirected) {
                    window.location.href = response.url;
                    return null;
                }
                if (!response.ok) throw new Error('HTTP ' + response.status);
                return response.text();
            })
            .then(function (html) {
                if (html === null) return;
                host.innerHTML = html;
                host.setAttribute('aria-busy', 'false');
                liftToasts(host);
                runScripts(host);
                restoreAnchor();
                document.dispatchEvent(new CustomEvent('vintazk:content-loaded', {
                    detail: { container: host }
                }));
            })
            .catch(function () {
                /* The reload link points at the page, not at the fragment: a
                   fragment opened on its own would render without the shell. */
                fail(host, window.location.href);
            });
    }

    function start() {
        var hosts = document.querySelectorAll('[data-async-content]');
        Array.prototype.forEach.call(hosts, load);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
