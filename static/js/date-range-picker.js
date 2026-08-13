/* Date range picker — the behaviour behind templates/partials/date_range_picker.html.
 *
 * One trigger, one popover, three modes. Day mode is a two-click range (start,
 * then end, with a hover preview between them); Month and Year modes are a
 * single click that expands to that whole month / year. Every mode produces the
 * same {start, end} pair, so nothing downstream has to care which was used.
 *
 * Keyed entirely off data-dr-* attributes, so any number of pickers can sit on
 * a page. Class strings are written out in full — Tailwind scans this file and
 * would purge anything assembled from fragments.
 */
(function () {
    const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'];
    const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    // Dates are compared as plain YYYYMMDD numbers — no timezone, no clock.
    const ymd = d => d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
    const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const short = d => `${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
    const lastDay = (y, m) => new Date(y, m + 1, 0).getDate();

    const ACTIVE_TAB = 'rounded-md px-2 py-1.5 text-xs font-semibold transition bg-white text-brand shadow-sm';
    const IDLE_TAB = 'rounded-md px-2 py-1.5 text-xs font-semibold transition text-slate-500 hover:text-slate-700';
    const SELECTED_CELL = 'rounded-lg px-2 py-2 text-xs font-semibold transition bg-brand text-white';
    const IDLE_CELL = 'rounded-lg px-2 py-2 text-xs font-medium transition text-slate-600 hover:bg-slate-100';

    function init(root) {
        const trigger = root.querySelector('[data-dr-trigger]');
        const panel = root.querySelector('[data-dr-panel]');
        const display = root.querySelector('[data-dr-display]');
        const title = root.querySelector('[data-dr-title]');
        const grid = root.querySelector('[data-dr-grid]');
        const months = root.querySelector('[data-dr-months]');
        const years = root.querySelector('[data-dr-years]');
        const summary = root.querySelector('[data-dr-summary]');
        const fromInput = root.querySelector('[data-dr-from]');
        const toInput = root.querySelector('[data-dr-to]');
        if (!trigger || !panel) return;

        const today = new Date();
        let mode = 'day';
        let cursor = new Date(today.getFullYear(), today.getMonth(), 1);
        let start = null;
        let end = null;
        let hover = null;

        /* ---------- selection helpers ---------- */

        // While only the start is picked, the hovered day stands in for the end
        // so the range previews as you move across the grid.
        function bounds() {
            if (!start) return [null, null];
            const other = end || (hover && mode === 'day' ? hover : start);
            const a = ymd(start), b = ymd(other);
            return a <= b ? [a, b] : [b, a];
        }

        function isFullMonth() {
            return start && end
                && start.getFullYear() === end.getFullYear() && start.getMonth() === end.getMonth()
                && start.getDate() === 1 && end.getDate() === lastDay(end.getFullYear(), end.getMonth());
        }

        function isFullYear() {
            return start && end
                && start.getFullYear() === end.getFullYear()
                && start.getMonth() === 0 && start.getDate() === 1
                && end.getMonth() === 11 && end.getDate() === 31;
        }

        // The one place a range is turned into words — trigger and summary share it.
        function label() {
            if (!start) return null;
            if (!end) return `${short(start)} — pick end date`;
            if (isFullYear()) return String(start.getFullYear());
            if (isFullMonth()) return `${MONTHS[start.getMonth()]} ${start.getFullYear()}`;
            if (ymd(start) === ymd(end)) return short(start);
            return `${short(start)} – ${short(end)}`;
        }

        /* ---------- rendering ---------- */

        function renderDays() {
            const [lo, hi] = bounds();
            const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
            const gridStart = new Date(first);
            gridStart.setDate(1 - first.getDay());   // back up to the Sunday

            grid.textContent = '';
            for (let i = 0; i < 42; i++) {
                const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
                const value = ymd(date);
                const inMonth = date.getMonth() === cursor.getMonth();
                const isStart = lo !== null && value === lo;
                const isEnd = hi !== null && value === hi;
                const between = lo !== null && value > lo && value < hi;

                const cell = document.createElement('button');
                cell.type = 'button';
                cell.textContent = date.getDate();
                cell.dataset.drDay = iso(date);

                const base = 'relative flex h-9 w-full items-center justify-center text-sm transition ';
                if (isStart && isEnd) {
                    cell.className = base + 'rounded-lg bg-brand font-semibold text-white';
                } else if (isStart) {
                    cell.className = base + 'rounded-l-lg bg-brand font-semibold text-white';
                } else if (isEnd) {
                    cell.className = base + 'rounded-r-lg bg-brand font-semibold text-white';
                } else if (between) {
                    cell.className = base + 'bg-brand/10 text-brand-dark';
                } else if (!inMonth) {
                    cell.className = base + 'rounded-lg text-slate-300 hover:bg-slate-100';
                } else if (value === ymd(today)) {
                    cell.className = base + 'rounded-lg font-semibold text-brand ring-1 ring-inset ring-brand/40 hover:bg-slate-100';
                } else {
                    cell.className = base + 'rounded-lg text-slate-600 hover:bg-slate-100';
                }
                grid.appendChild(cell);
            }
        }

        function renderMonths() {
            months.textContent = '';
            MONTHS_SHORT.forEach(function (name, index) {
                const selected = isFullMonth()
                    && start.getFullYear() === cursor.getFullYear() && start.getMonth() === index;
                const cell = document.createElement('button');
                cell.type = 'button';
                cell.textContent = name;
                cell.dataset.drMonth = index;
                cell.className = selected ? SELECTED_CELL : IDLE_CELL;
                months.appendChild(cell);
            });
        }

        function yearBase() {
            // Twelve-year pages, aligned so the same years always sit together.
            return Math.floor(cursor.getFullYear() / 12) * 12;
        }

        function renderYears() {
            const base = yearBase();
            years.textContent = '';
            for (let i = 0; i < 12; i++) {
                const year = base + i;
                const selected = isFullYear() && start.getFullYear() === year;
                const cell = document.createElement('button');
                cell.type = 'button';
                cell.textContent = year;
                cell.dataset.drYear = year;
                cell.className = selected ? SELECTED_CELL : IDLE_CELL;
                years.appendChild(cell);
            }
        }

        function render() {
            root.querySelectorAll('[data-dr-tab]').forEach(function (tab) {
                tab.className = tab.dataset.drTab === mode ? ACTIVE_TAB : IDLE_TAB;
            });
            root.querySelectorAll('[data-dr-view]').forEach(function (view) {
                view.hidden = view.dataset.drView !== mode;
            });

            if (mode === 'day') {
                title.textContent = `${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}`;
                renderDays();
            } else if (mode === 'month') {
                title.textContent = cursor.getFullYear();
                renderMonths();
            } else {
                const base = yearBase();
                title.textContent = `${base} – ${base + 11}`;
                renderYears();
            }

            summary.textContent = label() || 'No dates selected';
        }

        /* ---------- open / close ---------- */

        function open() {
            panel.hidden = false;
            trigger.setAttribute('aria-expanded', 'true');
            render();
        }

        function close() {
            panel.hidden = true;
            trigger.setAttribute('aria-expanded', 'false');
            hover = null;
        }

        trigger.addEventListener('click', function () {
            if (panel.hidden) open(); else close();
        });

        document.addEventListener('click', function (event) {
            if (!panel.hidden && !root.contains(event.target)) close();
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && !panel.hidden) { close(); trigger.focus(); }
        });

        /* ---------- interaction ---------- */

        root.querySelectorAll('[data-dr-tab]').forEach(function (tab) {
            tab.addEventListener('click', function () {
                mode = tab.dataset.drTab;
                hover = null;
                render();
            });
        });

        root.querySelector('[data-dr-prev]').addEventListener('click', function () {
            if (mode === 'day') cursor = new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1);
            else if (mode === 'month') cursor = new Date(cursor.getFullYear() - 1, cursor.getMonth(), 1);
            else cursor = new Date(yearBase() - 12, cursor.getMonth(), 1);
            render();
        });

        root.querySelector('[data-dr-next]').addEventListener('click', function () {
            if (mode === 'day') cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
            else if (mode === 'month') cursor = new Date(cursor.getFullYear() + 1, cursor.getMonth(), 1);
            else cursor = new Date(yearBase() + 12, cursor.getMonth(), 1);
            render();
        });

        grid.addEventListener('click', function (event) {
            const cell = event.target.closest('[data-dr-day]');
            if (!cell) return;
            const [y, m, d] = cell.dataset.drDay.split('-').map(Number);
            const picked = new Date(y, m - 1, d);

            // First click (or a fresh one after a complete range) sets the start;
            // clicking before the start restarts rather than making a backwards range.
            if (!start || end || ymd(picked) < ymd(start)) {
                start = picked;
                end = null;
            } else {
                end = picked;
            }
            hover = null;
            render();
        });

        grid.addEventListener('mouseover', function (event) {
            if (!start || end) return;
            const cell = event.target.closest('[data-dr-day]');
            if (!cell) return;
            const [y, m, d] = cell.dataset.drDay.split('-').map(Number);
            hover = new Date(y, m - 1, d);
            renderDays();
        });

        grid.addEventListener('mouseleave', function () {
            if (hover) { hover = null; renderDays(); }
        });

        months.addEventListener('click', function (event) {
            const cell = event.target.closest('[data-dr-month]');
            if (!cell) return;
            const index = Number(cell.dataset.drMonth);
            const year = cursor.getFullYear();
            start = new Date(year, index, 1);
            end = new Date(year, index, lastDay(year, index));
            cursor = new Date(year, index, 1);
            render();
        });

        years.addEventListener('click', function (event) {
            const cell = event.target.closest('[data-dr-year]');
            if (!cell) return;
            const year = Number(cell.dataset.drYear);
            start = new Date(year, 0, 1);
            end = new Date(year, 11, 31);
            cursor = new Date(year, 0, 1);
            render();
        });

        // The trigger's own text, from whatever is currently committed. Shared by
        // Apply, Clear and the start-up restore so the three cannot word the same
        // range differently.
        function showTrigger() {
            const text = label();
            display.textContent = text || 'Select date range';
            display.className = text ? 'truncate text-slate-700' : 'truncate text-slate-400';
        }

        root.querySelector('[data-dr-clear]').addEventListener('click', function () {
            start = end = hover = null;
            fromInput.value = toInput.value = '';
            showTrigger();
            render();
        });

        root.querySelector('[data-dr-apply]').addEventListener('click', function () {
            if (!start) { close(); return; }
            // A range left half-picked applies as that single day.
            const finish = end || start;
            fromInput.value = iso(start);
            toInput.value = iso(finish);
            end = finish;
            showTrigger();
            close();
        });

        /* ---------- restore ---------- */

        // A server-rendered range (the page was loaded with a filter applied)
        // arrives in the hidden inputs. Parsed here so the trigger reads the
        // applied window rather than "Select date range", which would say the
        // filter had been dropped while the form was still carrying it.
        //
        // Split by hand rather than `new Date(iso)`: that parses a bare
        // YYYY-MM-DD as UTC midnight, so anywhere west of Greenwich the picker
        // would open on the day before the one that is applied.
        function restore(value) {
            const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value || '').trim());
            if (!parts) return null;
            const d = new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]));
            return isNaN(d) ? null : d;
        }

        // The picker only ever produces a closed range, so a one-sided value
        // (a hand-typed URL asking for everything up to a date) is squared off
        // to a single day. Both inputs are rewritten to match, or the control
        // would display one window and submit another.
        const savedFrom = restore(fromInput.value);
        const savedTo = restore(toInput.value);
        if (savedFrom || savedTo) {
            start = savedFrom || savedTo;
            end = savedTo || savedFrom;
            if (ymd(end) < ymd(start)) { const swap = start; start = end; end = swap; }
            fromInput.value = iso(start);
            toInput.value = iso(end);
            // Open on the applied range rather than on today.
            cursor = new Date(start.getFullYear(), start.getMonth(), 1);
            if (isFullYear()) mode = 'year';
            else if (isFullMonth()) mode = 'month';
            showTrigger();
        }

        render();
    }

    document.querySelectorAll('[data-date-range]').forEach(init);
})();
