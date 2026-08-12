/* The guided tour (see apps/core/tour.py for the steps and why they are built
 * on the server).
 *
 * The tour spans SEVERAL PAGES: the dashboard, then a department's own screens.
 * There is no single-page app underneath, so "next" on the last step of a page
 * is a real navigation. Progress therefore lives in sessionStorage rather than
 * in a variable, and every page load asks "is a tour running, and is this the
 * page its current step belongs to?".
 *
 * Two rules worth keeping in mind before changing anything here:
 *
 *  1. A step whose element is not on the page is SKIPPED, never fatal. The
 *     Actual vs Target chart only renders once a KPI has been scored, so a new
 *     team has pages the tour would otherwise stall on.
 *  2. Most screens render in two stages (apps/core/async_content.py), so at
 *     DOMContentLoaded the panels do not exist yet. The tour waits for the
 *     content event before it looks for anything.
 */
(function () {
    'use strict';

    var STORE_KEY = 'vintazk:tour';
    /* Breathing room between the highlighted element and the ring around it. */
    var PAD = 8;
    /* Gap between the ring and the card, and the card's margin from the edge. */
    var GAP = 14;
    /* How close the ring may come to the viewport edge when it is clamped. */
    var EDGE = 6;

    var root = document.querySelector('[data-tour-root]');
    var data = document.getElementById('tour-steps');
    if (!root || !data) return;

    var steps;
    try {
        steps = JSON.parse(data.textContent);
    } catch (err) {
        return;
    }
    if (!steps || !steps.length) return;

    var blocker = root.querySelector('[data-tour-blocker]');
    var spotlight = root.querySelector('[data-tour-spotlight]');
    var card = root.querySelector('[data-tour-card]');
    var titleEl = root.querySelector('[data-tour-title]');
    var bodyEl = root.querySelector('[data-tour-body]');
    var indexEl = root.querySelector('[data-tour-index]');
    var totalEl = root.querySelector('[data-tour-total]');
    var progressEl = root.querySelector('[data-tour-progress]');
    var backBtn = root.querySelector('[data-tour-back]');
    var nextBtn = root.querySelector('[data-tour-next]');
    var skipBtn = root.querySelector('[data-tour-skip]');

    var current = -1;
    /* The tracking loop's requestAnimationFrame handle, null while it is off. */
    var loop = null;
    /* The element the open step points at, resolved once when the step opens
       rather than on every frame of the tracking loop. */
    var active = null;
    /* Whether the card has been positioned for the step that is open. */
    var placed = false;
    /* Timer that takes the move animation off again (see `.is-shifting`). */
    var shift = null;

    /* ---- progress across pages ------------------------------------------- */

    function read() {
        try {
            var raw = window.sessionStorage.getItem(STORE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (err) {
            return null;   /* private mode, or storage disabled */
        }
    }

    function write(index) {
        try {
            window.sessionStorage.setItem(STORE_KEY, JSON.stringify({ index: index }));
        } catch (err) { /* the tour still runs, it just cannot cross a page */ }
    }

    function clear() {
        try {
            window.sessionStorage.removeItem(STORE_KEY);
        } catch (err) { /* nothing to clean up */ }
    }

    /* ---- steps ------------------------------------------------------------ */

    function here() {
        return window.location.pathname;
    }

    function element(step) {
        if (!step.target) return null;
        try {
            return document.querySelector(step.target);
        } catch (err) {
            return null;
        }
    }

    /* An element counts as present only if it actually occupies space. Below md
       the sidebar is display:none until its fragment is open, which is what
       `reveal` is for: try opening it before writing the step off. */
    function shown(el) {
        return !!el && el.getClientRects().length > 0;
    }

    /* Is this step showable as the page stands? Asks and changes nothing. */
    function present(step) {
        return !step.target || shown(element(step));   /* centred steps need nothing */
    }

    /* The same question for a step we are about to LAND on, which may open
       something first. Kept apart from `present` on purpose: the scans below run
       over steps the user is not going to see, and opening the sidebar drawer
       merely to work out whether Back should be enabled would be a drawer
       sliding out of nowhere. */
    function usable(step) {
        if (present(step)) return true;
        if (step.reveal && element(step) && window.location.hash !== step.reveal) {
            window.location.hash = step.reveal;
            return present(step);
        }
        return false;
    }

    /* The next showable step at or after `from`, walking forwards. A step on
       another page is returned as-is: whether it is showable is that page's
       question, asked again once we are on it. */
    function forwards(from) {
        var i = from;
        while (i < steps.length) {
            if (steps[i].page !== here() || usable(steps[i])) return i;
            i++;
        }
        return steps.length;
    }

    function backwards(from) {
        var i = from;
        while (i >= 0) {
            if (steps[i].page !== here() || present(steps[i])) return i;
            i--;
        }
        return -1;
    }

    /* ---- placement -------------------------------------------------------- */

    /* What the ring is allowed to cover.
     *
     * For anything inside the page's scroll container that is the CONTENT AREA,
     * not the whole window: the header and the footer are fixed chrome the
     * highlighted panel scrolls under, so a ring drawn across them would claim
     * to be highlighting them too. Clamped this way the ring is tucked between
     * them, and both stay dimmed like the rest of the page.
     *
     * The sidebar step is the exception that makes this a test rather than a
     * constant: it points at an element outside that container, so it gets the
     * window.
     */
    function frame(vw, vh) {
        var host = document.querySelector('main');
        var box = { top: EDGE, left: EDGE, right: vw - EDGE, bottom: vh - EDGE };

        if (!host || !active || !host.contains(active)) return box;

        var rect = host.getBoundingClientRect();
        return {
            top: Math.max(box.top, rect.top + EDGE),
            left: Math.max(box.left, rect.left + EDGE),
            right: Math.min(box.right, rect.right - EDGE),
            bottom: Math.min(box.bottom, rect.bottom - EDGE)
        };
    }

    /* The ring's box: the element's rectangle, padded, then clamped to the frame
       above. The clamp is what makes a long region workable. "Department by
       department" and the charts under it are several screens tall, and a ring
       drawn around the whole thing would be a line off the top of the screen and
       another off the bottom, with the card pushed into a corner to avoid a box
       that has no room anywhere. Clamped, the ring hugs the part you can
       actually see and re-cuts itself as you scroll, since this runs every
       frame. Null when the element has scrolled out of sight entirely. */
    function ringBox(edges) {
        if (!shown(active)) return null;

        var rect = active.getBoundingClientRect();
        var top = Math.max(rect.top - PAD, edges.top);
        var left = Math.max(rect.left - PAD, edges.left);
        var bottom = Math.min(rect.bottom + PAD, edges.bottom);
        var right = Math.min(rect.right + PAD, edges.right);

        if (bottom - top < 8 || right - left < 8) return null;
        return { top: top, left: left, width: right - left, height: bottom - top };
    }

    /* The card is kept inside the same frame, so it cannot end up sitting over
       the header or the footer either. */
    function placeCard(box, edges) {
        var cw = card.offsetWidth;
        var ch = card.offsetHeight;
        /* Everything below is in viewport coordinates, the same ones the ring
           uses, so `edges` are read as positions rather than as a size. */
        var lastTop = edges.bottom - ch - GAP;
        var lastLeft = edges.right - cw - GAP;
        var top, left;

        if (!box) {
            top = (edges.top + edges.bottom - ch) / 2;
            left = (edges.left + edges.right - cw) / 2;
        } else {
            /* Below the element, above it, or beside it — the first that fits,
               so the card never covers what it is describing. A region that
               fills the frame leaves none of those, and then the card takes the
               bottom right corner: overlapping is unavoidable there, and a
               corner is at least a place it stays put while you scroll. */
            left = box.left + (box.width - cw) / 2;

            if (box.top + box.height + GAP + ch <= edges.bottom) {
                top = box.top + box.height + GAP;
            } else if (box.top - GAP - ch >= edges.top) {
                top = box.top - GAP - ch;
            } else if (box.left + box.width + GAP + cw <= edges.right) {
                top = box.top;
                left = box.left + box.width + GAP;
            } else if (box.left - GAP - cw >= edges.left) {
                top = box.top;
                left = box.left - GAP - cw;
            } else {
                top = lastTop;
                left = lastLeft;
            }
        }

        card.style.top = Math.max(edges.top + GAP, Math.min(top, lastTop)) + 'px';
        card.style.left = Math.max(edges.left + GAP, Math.min(left, lastLeft)) + 'px';
    }

    function place() {
        if (current < 0) return;

        var edges = frame(document.documentElement.clientWidth,
                          document.documentElement.clientHeight);
        var box = ringBox(edges);

        if (box) {
            spotlight.hidden = false;
            blocker.classList.remove('is-dim');
            spotlight.style.top = box.top + 'px';
            spotlight.style.left = box.left + 'px';
            spotlight.style.width = box.width + 'px';
            spotlight.style.height = box.height + 'px';
        } else {
            /* Nothing to point at, either because the step has no target or
               because the reader scrolled past it. Dim the page flat. */
            spotlight.hidden = true;
            blocker.classList.add('is-dim');
        }

        /* The card only moves while there is something to anchor it to. Scroll a
           target out of view and it stays where it was rather than sliding to
           the middle of the screen and back. */
        if (box || !placed) {
            placeCard(box, edges);
            placed = true;
        }
    }

    /* One loop while the tour is open, rather than listeners on scroll, resize
       and every layout shift the page can make. The spotlight has to track the
       element through a smooth scroll anyway, so the frame is already needed. */
    function track() {
        place();
        loop = window.requestAnimationFrame(track);
    }

    /* ---- running ---------------------------------------------------------- */

    function render() {
        var step = steps[current];
        active = element(step);
        placed = false;

        titleEl.textContent = step.title;
        bodyEl.textContent = step.body;
        indexEl.textContent = current + 1;
        totalEl.textContent = steps.length;
        progressEl.style.width = ((current + 1) / steps.length * 100) + '%';
        backBtn.disabled = backwards(current - 1) < 0;
        nextBtn.textContent = current === steps.length - 1 ? 'Done' : 'Next';

        root.hidden = false;
        if (loop === null) track();

        /* Animate this one move, then get out of the way of the frame loop. */
        spotlight.classList.add('is-shifting');
        window.clearTimeout(shift);
        shift = window.setTimeout(function () {
            spotlight.classList.remove('is-shifting');
        }, 220);

        if (shown(active)) {
            /* A region several screens tall has no centre worth scrolling to:
               start at its top and let the reader scroll through it. */
            var tall = active.getBoundingClientRect().height
                     > document.documentElement.clientHeight - GAP * 2;
            active.scrollIntoView({
                block: tall ? 'start' : 'center', behavior: 'smooth'
            });
        }
        place();
        card.focus();
    }

    /* Move to `index`, navigating if that step lives on another page. */
    function go(index) {
        if (index < 0 || index >= steps.length) return finish();
        write(index);
        if (steps[index].page !== here()) {
            /* page-loader.js hooks link clicks and form submits, and this is
               neither, so the wait between two steps would be a dead card. Same
               class it sets; the arriving document is what clears it. */
            var loader = document.getElementById('page-loader');
            if (loader) loader.classList.add('is-active');
            window.location.href = steps[index].page;
            return;
        }
        current = index;
        render();
    }

    function next() {
        if (current === steps.length - 1) return finish();
        go(forwards(current + 1));
    }

    function back() {
        var index = backwards(current - 1);
        if (index >= 0) go(index);
    }

    /* Finishing and skipping are the same event as far as the account is
       concerned: this user has been shown around, so the tour stops opening by
       itself. Replaying it from the help button never gets here with anything
       to clear, since the flag is already false by then. */
    function finish() {
        stop();
        clear();
        var url = root.getAttribute('data-tour-seen-url');
        var token = root.getAttribute('data-tour-csrf');
        if (!url || !token || !window.fetch) return;
        window.fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': token, 'X-Requested-With': 'XMLHttpRequest' }
        }).catch(function () { /* the tour is over either way */ });
    }

    function stop() {
        root.hidden = true;
        current = -1;
        active = null;
        if (loop !== null) {
            window.cancelAnimationFrame(loop);
            loop = null;
        }
        window.clearTimeout(shift);
        spotlight.classList.remove('is-shifting');
    }

    function start(index) {
        var at = forwards(index || 0);
        if (at >= steps.length) return;
        go(at);
    }

    /* ---- wiring ----------------------------------------------------------- */

    nextBtn.addEventListener('click', next);
    backBtn.addEventListener('click', back);
    skipBtn.addEventListener('click', finish);

    /* Clicks are swallowed here rather than by the overlay, because the overlay
       has to let the wheel through: the page must still SCROLL while the tour is
       open, which is the whole point of the ring re-cutting itself every frame.
       An overlay that catches the pointer catches the scroll with it, so it is
       pointer-events: none and this listener does the blocking instead —
       capture phase, so it lands before any link or button on the page. */
    document.addEventListener('click', function (event) {
        if (root.hidden) return;
        if (card.contains(event.target)) return;
        event.preventDefault();
        event.stopPropagation();
    }, true);

    document.addEventListener('keydown', function (event) {
        if (root.hidden) return;
        if (event.key === 'Escape') { event.preventDefault(); finish(); }
        else if (event.key === 'ArrowRight') { event.preventDefault(); next(); }
        else if (event.key === 'ArrowLeft') { event.preventDefault(); back(); }
    });

    /* The help button in the header. Replaying is always allowed and always
       starts from the beginning, which means going back to the dashboard when
       you are not on it. */
    document.addEventListener('click', function (event) {
        var trigger = event.target.closest ? event.target.closest('[data-tour-start]') : null;
        if (!trigger) return;
        event.preventDefault();
        start(0);
    });

    function boot() {
        var state = read();

        if (state && typeof state.index === 'number') {
            var step = steps[state.index];
            /* A tour resumes only on the page its step belongs to. If the user
               wandered off mid-tour, drop it rather than letting it ambush them
               on some later visit. */
            if (step && step.page === here()) {
                go(forwards(state.index));
            } else {
                clear();
            }
            return;
        }

        if (root.getAttribute('data-tour-autostart') === '1') start(0);
    }

    /* Two-stage render: on a screen that fetches its own content there is
       nothing to point at yet, so wait for it to arrive. */
    function ready() {
        var pending = document.querySelector('[data-async-content][aria-busy="true"]');
        if (!pending) return boot();
        document.addEventListener('vintazk:content-loaded', function once() {
            document.removeEventListener('vintazk:content-loaded', once);
            boot();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ready);
    } else {
        ready();
    }
})();
