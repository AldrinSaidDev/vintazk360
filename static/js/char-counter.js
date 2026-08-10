/* Live "characters left" for any length-capped field.
 *
 * Generic on purpose: it reads the cap from the field's own `maxlength`, so a
 * field's limit is stated once in the form (which is itself generated from
 * REMARKS_MAX_LENGTH in apps/kpi/models.py) and never restated here. Add a
 * counter to a new field by adding one span, with no change to this file.
 *
 * Markup contract:
 *
 *   <textarea id="id_remarks" maxlength="300"></textarea>
 *   <span data-char-count="id_remarks"></span>
 *
 * The counter is filled in by this script and starts empty, so a browser with
 * no JS shows nothing rather than a number frozen at the wrong value.
 */
(function () {
    "use strict";

    // Under this many characters left, the count stops being background
    // information and starts being a warning.
    var WARN_AT = 20;

    var QUIET = "text-slate-400";
    var WARN = "text-status-warn";
    var FULL = "text-status-bad";

    function init() {
        var counters = Array.prototype.slice.call(
            document.querySelectorAll("[data-char-count]")
        );
        if (!counters.length) return;

        counters.forEach(function (counter) {
            var field = document.getElementById(counter.dataset.charCount);
            if (!field) return;

            var max = parseInt(field.getAttribute("maxlength"), 10);
            if (!max) return;

            function update() {
                var left = max - field.value.length;

                counter.textContent = left + " left";
                counter.classList.remove(QUIET, WARN, FULL);
                counter.classList.add(left <= 0 ? FULL : left <= WARN ? WARN : QUIET);
            }

            field.addEventListener("input", update);
            // Run once now: the field can already hold text when a failed POST
            // re-renders the form with what was typed.
            update();
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
