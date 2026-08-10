/* Arms a destructive confirm button on a timer.
 *
 * Used by the delete confirms on Import Data (a record) and KPI Management (a
 * KPI). One implementation for both: a second copy would be a second clock to
 * keep in step, and the two screens must not disagree about how long "wait"
 * lasts or when the button goes live.
 *
 * Markup contract, inside any `.modal-overlay`:
 *
 *   [data-delete-timer][data-delete-seconds="5"]   the hint block, starts hidden
 *   [data-delete-ring]                             SVG <rect> tracing the button
 *   [data-delete-confirm]                          the submit button
 *   [data-delete-countdown]                        empty <span> in the label
 *
 * The button is rendered ENABLED. If this file never loads the guard is lost
 * but deleting still works, which beats a permanently dead button.
 *
 * ONE clock, the same principle as the toast countdown: a single
 * requestAnimationFrame loop drives the ring, the count and the disabled state
 * off one timestamp, so the count can never read 0 while the button is locked.
 */
(function () {
    "use strict";

    var RING_RADIUS = 8;   // matches the buttons' rounded-lg corner

    function init() {
        var timers = Array.prototype.slice.call(
            document.querySelectorAll("[data-delete-timer]")
        );
        if (!timers.length) return;

        var frame = null;

        // Where the button's END edge sits along its own outline, as a
        // percentage of the perimeter. An SVG rect path starts at the top-left
        // corner and runs clockwise, so without this the sweep would begin at
        // the wrong end. It depends on the rendered size, so it is measured
        // rather than guessed.
        function endEdgePhase(button) {
            var box = button.getBoundingClientRect();
            if (!box.width || !box.height) return 0;

            var flatTop = Math.max(0, box.width - 2 * RING_RADIUS);
            var flatSide = Math.max(0, box.height - 2 * RING_RADIUS);
            var corner = Math.PI * RING_RADIUS / 2;
            var perimeter = 2 * flatTop + 2 * flatSide + 4 * corner;
            if (!perimeter) return 0;

            // Along the top edge, round the first corner, then half way down
            // the right-hand side.
            return (flatTop + corner + flatSide / 2) / perimeter * 100;
        }

        function clear(modal) {
            var button = modal && modal.querySelector("[data-delete-confirm]");
            var ring = modal && modal.querySelector("[data-delete-ring]");
            var label = modal && modal.querySelector("[data-delete-countdown]");
            // "0 100" is a zero-length dash: no outline is drawn at all.
            if (ring) ring.style.strokeDasharray = "0 100";
            if (label) label.textContent = "";
            if (button) button.disabled = false;
        }

        function disarm(block) {
            block.classList.add("hidden");
            clear(block.closest(".modal-overlay"));
        }

        function arm(block) {
            var modal = block.closest(".modal-overlay");
            if (!modal) return;

            var button = modal.querySelector("[data-delete-confirm]");
            var ring = modal.querySelector("[data-delete-ring]");
            var label = modal.querySelector("[data-delete-countdown]");
            if (!button || !ring || !label) return;

            var total = (parseFloat(block.dataset.deleteSeconds) || 5) * 1000;
            var start = null;

            button.disabled = true;
            block.classList.remove("hidden");
            // Measured with the modal already open, so the box is real.
            var phase = endEdgePhase(button);

            function tick(now) {
                if (start === null) start = now;
                var left = Math.max(0, total - (now - start));
                var drawn = left / total * 100;

                // The drawn arc ENDS at the button's end edge, so the gap opens
                // there and eats its way round as the seconds go.
                ring.style.strokeDasharray = drawn + " " + (100 - drawn);
                ring.style.strokeDashoffset = drawn - phase;

                if (left > 0) {
                    // Non-breaking space: the count belongs to the label and
                    // must never wrap onto a line of its own.
                    label.textContent = " (" + Math.ceil(left / 1000) + ")";
                    frame = window.requestAnimationFrame(tick);
                    return;
                }
                // Ring and count both go at zero, leaving a plain live button.
                frame = null;
                clear(modal);
            }

            frame = window.requestAnimationFrame(tick);
        }

        function sync() {
            if (frame !== null) {
                window.cancelAnimationFrame(frame);
                frame = null;
            }
            timers.forEach(disarm);

            // getElementById, not querySelector: a hash is not always a valid
            // CSS selector.
            var open = location.hash
                ? document.getElementById(location.hash.slice(1))
                : null;
            var block = open && open.querySelector("[data-delete-timer]");
            if (block) arm(block);
        }

        window.addEventListener("hashchange", sync);
        sync();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
