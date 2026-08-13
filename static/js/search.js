/* The header search palette (templates/partials/search_palette.html).
 *
 * What may be found is decided on the SERVER (apps/core/search.py), because it
 * is an access-control question: which departments a person can open is
 * apps/core/access.py, and a copy of that rule here would be a second answer to
 * a question that already has one. This file only asks and draws.
 *
 * Three things worth knowing before changing it:
 *
 *  1. An empty query is a real query. The palette opens showing every page the
 *     user can reach, so it is a way to get around and not only a way to look
 *     something up. That first response is kept, so re-opening it costs nothing.
 *  2. Every keystroke aborts the request in flight (AbortController). Without
 *     that, a slow early response can land after a fast later one and paint
 *     results for a query the user has already typed past.
 *  3. Results are built with the DOM API, never innerHTML with a KPI name in
 *     it. A KPI is named by a person through a form.
 */
(function () {
    'use strict';

    /* Long enough that typing a word is one request, short enough that the
       list feels attached to the keyboard. */
    var DEBOUNCE = 140;

    var root = document.querySelector('[data-search-root]');
    if (!root) return;  /* anonymous page — nothing to search */

    var endpoint = root.getAttribute('data-search-url');
    var input = root.querySelector('[data-search-input]');
    var list = root.querySelector('[data-search-results]');
    var scrim = root.querySelector('[data-search-scrim]');

    /* The rendered rows, in the order the arrow keys walk them. */
    var items = [];
    var active = -1;
    var timer = null;
    var pending = null;
    /* The response for the empty query, which never changes within a page. */
    var initial = null;
    /* Where focus was before the palette opened, so Escape can give it back. */
    var opener = null;

    function isOpen() {
        return !root.classList.contains('hidden');
    }

    function open() {
        if (isOpen()) return;
        opener = document.activeElement;
        root.classList.remove('hidden');
        input.value = '';
        input.focus();
        render(initial);
        if (!initial) request('');
    }

    function close() {
        if (!isOpen()) return;
        root.classList.add('hidden');
        abort();
        if (opener && typeof opener.focus === 'function') opener.focus();
        opener = null;
    }

    function abort() {
        if (timer) { clearTimeout(timer); timer = null; }
        if (pending) { pending.abort(); pending = null; }
    }

    /* ---- Fetching ---------------------------------------------------- */

    function request(query) {
        abort();
        var controller = new AbortController();
        pending = controller;
        fetch(endpoint + '?q=' + encodeURIComponent(query), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            signal: controller.signal,
        })
            .then(function (response) {
                if (!response.ok) throw new Error('search failed');
                return response.json();
            })
            .then(function (data) {
                if (controller !== pending) return;  /* superseded */
                pending = null;
                if (!query) initial = data.groups;
                render(data.groups, query);
            })
            .catch(function (err) {
                if (err && err.name === 'AbortError') return;
                pending = null;
                message('Search is unavailable right now. Try again in a moment.');
            });
    }

    function schedule() {
        var query = input.value.trim();
        if (timer) clearTimeout(timer);
        timer = setTimeout(function () {
            timer = null;
            if (!query && initial) { render(initial); return; }
            request(query);
        }, DEBOUNCE);
    }

    /* ---- Drawing ------------------------------------------------------ */

    function clear() {
        while (list.firstChild) list.removeChild(list.firstChild);
        items = [];
        active = -1;
    }

    function message(text) {
        clear();
        var p = document.createElement('p');
        p.className = 'px-3 py-8 text-center text-sm text-slate-400';
        p.textContent = text;
        list.appendChild(p);
    }

    function render(groups, query) {
        if (!groups) { message('Searching…'); return; }
        clear();

        if (!groups.length) {
            message(query ? 'No matches for “' + query + '”.' : 'Nothing to show.');
            return;
        }

        groups.forEach(function (group) {
            var heading = document.createElement('p');
            heading.className = 'px-3 pb-1 pt-3 text-[10px] font-bold uppercase tracking-wider text-slate-400';
            heading.textContent = group.label;
            list.appendChild(heading);

            group.items.forEach(function (entry) {
                list.appendChild(row(entry));
            });
        });

        if (items.length) select(0);
    }

    function row(entry) {
        var link = document.createElement('a');
        link.href = entry.url;
        link.className = 'search-item flex items-center gap-3 rounded-lg px-3 py-2.5 text-left';
        link.setAttribute('role', 'option');
        link.id = 'search-item-' + items.length;

        var icon = document.createElement('span');
        icon.className = 'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-sm text-brand';
        var glyph = document.createElement('i');
        glyph.className = 'fa fa-' + entry.icon;
        glyph.setAttribute('aria-hidden', 'true');
        icon.appendChild(glyph);
        link.appendChild(icon);

        var text = document.createElement('span');
        text.className = 'min-w-0 flex-1';

        var title = document.createElement('span');
        title.className = 'search-item-title block truncate text-sm font-semibold text-ink';
        title.textContent = entry.title;
        text.appendChild(title);

        if (entry.subtitle) {
            var subtitle = document.createElement('span');
            subtitle.className = 'block truncate text-xs text-slate-400';
            subtitle.textContent = entry.subtitle;
            text.appendChild(subtitle);
        }
        link.appendChild(text);

        var index = items.length;
        link.addEventListener('mousemove', function () { select(index); });
        items.push(link);
        return link;
    }

    function select(index) {
        if (!items.length) return;
        if (active >= 0 && items[active]) items[active].classList.remove('is-active');
        active = Math.max(0, Math.min(index, items.length - 1));
        var item = items[active];
        item.classList.add('is-active');
        input.setAttribute('aria-activedescendant', item.id);
        /* nearest, not center: walking down a list should not jump it about. */
        item.scrollIntoView({ block: 'nearest' });
    }

    function move(step) {
        if (!items.length) return;
        /* Wrapping is what makes "up" from the first row reach the last one,
           which is how anyone gets to the bottom of a long list quickly. */
        var next = active + step;
        if (next < 0) next = items.length - 1;
        if (next >= items.length) next = 0;
        select(next);
    }

    /* ---- Wiring -------------------------------------------------------- */

    Array.prototype.forEach.call(
        document.querySelectorAll('[data-search-open]'),
        function (button) {
            button.addEventListener('click', function (event) {
                event.preventDefault();
                open();
            });
        }
    );

    if (scrim) scrim.addEventListener('click', close);

    input.addEventListener('input', schedule);

    input.addEventListener('keydown', function (event) {
        if (event.key === 'ArrowDown') { event.preventDefault(); move(1); return; }
        if (event.key === 'ArrowUp') { event.preventDefault(); move(-1); return; }
        if (event.key === 'Enter') {
            if (active >= 0 && items[active]) {
                event.preventDefault();
                items[active].click();
            }
            return;
        }
        if (event.key === 'Escape') { event.preventDefault(); close(); }
    });

    document.addEventListener('keydown', function (event) {
        /* Ctrl/Cmd+K from anywhere, including inside a form field: it is a
           chord, so it cannot be mistaken for something being typed. */
        if ((event.ctrlKey || event.metaKey) && (event.key === 'k' || event.key === 'K')) {
            event.preventDefault();
            if (isOpen()) close(); else open();
            return;
        }
        if (event.key === 'Escape' && isOpen()) { close(); return; }
        /* "/" is a bare key, so it only opens the palette when the user is not
           typing into something. Entering a KPI figure must stay possible. */
        if (event.key === '/' && !isOpen() && !typing(event.target)) {
            event.preventDefault();
            open();
        }
    });

    function typing(target) {
        if (!target || !target.tagName) return false;
        if (target.isContentEditable) return true;
        var tag = target.tagName.toLowerCase();
        return tag === 'input' || tag === 'textarea' || tag === 'select';
    }
})();
