/* Page loader.
 *
 * Shows the overlay when a navigation actually starts and lets the arriving
 * document take it away. There is no timer anywhere in here: the loader lasts
 * exactly as long as the server takes, whether that is 80ms or eight seconds.
 * A fixed duration would be a lie in both directions, and a timeout that hides
 * the overlay early would tell the user the page had arrived when it had not.
 *
 * What it covers, which is everything this app does to change pages:
 *   - clicking an internal link (sidebar, pagination, tabs, table row links)
 *   - submitting a form (sign in, filters, search, add record, upload, delete)
 *
 * Anything that does NOT replace the document is excluded, because nothing
 * would ever be there to hide the overlay again. The :target modals, the
 * sidebar drawer and the CSV/workbook downloads all fall in that bucket.
 */
(function () {
    'use strict';

    var overlay = document.getElementById('page-loader');
    if (!overlay) return;

    /* Files served as a download leave the current document in place, so a
       navigation never happens and nothing would clear the overlay. */
    var DOWNLOAD_EXTENSIONS = /\.(csv|xlsx|xls|pdf|zip|png|jpe?g|svg|txt|json)$/i;

    function show() {
        overlay.classList.add('is-active');
        overlay.setAttribute('aria-hidden', 'false');
    }

    function hide() {
        overlay.classList.remove('is-active');
        overlay.setAttribute('aria-hidden', 'true');
    }

    /* A link that only moves the fragment (#kpiEdit-csat, #sidebar, #) drives a
       :target modal or the drawer. Same document, so no loader. */
    function isSamePage(url) {
        return url.pathname === window.location.pathname
            && url.search === window.location.search;
    }

    function shouldLoad(link, event) {
        if (event.defaultPrevented) return false;
        if (event.button !== 0) return false;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
        if (link.hasAttribute('download')) return false;
        if (link.hasAttribute('data-no-loader')) return false;
        if (link.target && link.target !== '_self') return false;

        var href = link.getAttribute('href');
        if (!href || href.charAt(0) === '#') return false;

        var url;
        try {
            url = new URL(link.href, window.location.href);
        } catch (err) {
            return false;
        }

        if (url.protocol !== 'http:' && url.protocol !== 'https:') return false;
        if (url.origin !== window.location.origin) return false;
        if (DOWNLOAD_EXTENSIONS.test(url.pathname)) return false;
        if (url.hash && isSamePage(url)) return false;

        return true;
    }

    document.addEventListener('click', function (event) {
        var link = event.target.closest ? event.target.closest('a[href]') : null;
        if (!link) return;
        if (shouldLoad(link, event)) show();
    });

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (event.defaultPrevented) return;
        if (!form || form.hasAttribute('data-no-loader')) return;
        if (form.target && form.target !== '_self') return;
        show();
    });

    /* Back and forward. A page restored from the back/forward cache keeps the
       DOM it was unloaded with, overlay still up, so it has to be cleared on
       arrival as well as on first paint. */
    window.addEventListener('pageshow', hide);

    /* Someone cancelling the navigation (Esc, or a download dialog appearing on
       a link we failed to recognise) leaves the document in place. Esc is the
       one way back out that costs nothing to support. */
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') hide();
    });

    hide();

    /* Exposed for anything that loads content without changing page, so a future
       async table or modal fetch can reuse the same overlay. */
    window.VintazkLoader = { show: show, hide: hide };
})();
