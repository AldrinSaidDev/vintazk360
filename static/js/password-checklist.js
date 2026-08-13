// Live password rule checklist — ticks each rule as the user types.
//
// Client-side hinting only: apps/core/validators.py is what enforces the policy
// on save, and the rules below are a copy of it. Keep the two in sync.
//
// Every [data-password-checklist] element on the page is initialised, and the
// password inputs are found INSIDE that element rather than by id. The Users
// screen renders one Set password form per row, so id_password1 repeats down the
// page and getElementById would drive every checklist off the first modal's field.
(function () {
    'use strict';

    // Full class strings, written out literally. Tailwind purges classes it
    // cannot see as literals, and it does scan inside .js files in the content
    // globs. Building these by concatenation would leave them out of output.css.
    var MET_TEXT = 'text-status-good';
    var UNMET_TEXT = 'text-slate-400';
    var MET_MARK = 'rule-mark inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-status-good bg-status-good text-[9px] text-white';
    var UNMET_MARK = 'rule-mark inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-slate-300 text-[9px]';

    function init(container) {
        var list = container.querySelector('[data-password-rules]');
        if (!list) return;

        // The markers are what a form with a THIRD password box needs: Settings
        // asks for the current password first, so "the first password input" is
        // the wrong field there. Falling back to position keeps a two-field form
        // working without them.
        var fields = container.querySelectorAll('input[type="password"]');
        var main = container.querySelector('[data-password-main]') || fields[0];
        var confirm = container.querySelector('[data-password-confirm]') || fields[1] || null;
        if (!main) return;

        var rules = {
            length: function (v) { return v.length >= 6; },
            upper: function (v) { return /[A-Z]/.test(v); },
            special: function (v) { return /[^A-Za-z0-9]/.test(v); },
            // An empty pair is not a match. Ticking this before either field has
            // been typed in would say the passwords agree when neither exists.
            match: function (v) { return v.length > 0 && confirm !== null && v === confirm.value; },
        };

        function render() {
            var value = main.value;
            list.querySelectorAll('li[data-rule]').forEach(function (li) {
                var rule = rules[li.dataset.rule];
                if (!rule) return;
                var ok = rule(value);
                li.classList.toggle(MET_TEXT, ok);
                li.classList.toggle(UNMET_TEXT, !ok);
                var mark = li.querySelector('.rule-mark');
                mark.className = ok ? MET_MARK : UNMET_MARK;
                mark.innerHTML = ok ? '<i class="fa fa-check"></i>' : '';
            });
        }

        main.addEventListener('input', render);
        if (confirm) confirm.addEventListener('input', render);
        render();  // reflect anything the browser restored on reload
    }

    document.querySelectorAll('[data-password-checklist]').forEach(init);
})();
