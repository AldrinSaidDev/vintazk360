// Closing a modal that was forced open by the server.
//
// Every other modal in the app is CSS `:target`: the link that opens it puts an
// id in the URL, and `href="#"` takes it out again, so closing needs no script.
// The sign-in details card cannot work that way. It is opened by the render
// that follows a create, not by a link, so it carries `!flex` outright — and a
// `href="#"` next to that clears a fragment which was never what was holding it
// open. It looked exactly like a dead button, because it was one.
//
// So the overlays this handles say so, with data-forced-modal, and the script
// takes them off the page. Removing rather than hiding: this card shows the one
// readable copy of a password and is deliberately not reopenable, so leaving it
// in the DOM would leave the password sitting in the page for the rest of the
// session with nothing on screen to say so.
//
// No graceful degradation is lost here. The screens this runs on render their
// content from a fetch, so with the script blocked there is no modal to close.
(function () {
    'use strict';

    var OVERLAY = '[data-forced-modal]';

    function close(overlay) {
        if (overlay) overlay.remove();
    }

    document.addEventListener('click', function (event) {
        if (!event.target.closest) return;

        var closer = event.target.closest('[data-modal-close]');
        if (closer) {
            event.preventDefault();
            return close(closer.closest(OVERLAY));
        }

        // The backdrop. `event.target === overlay` is the test that matters:
        // the card is a child of the overlay, so without it every click inside
        // the card would close the thing the user is reading from.
        var overlay = event.target.closest(OVERLAY);
        if (overlay && event.target === overlay) close(overlay);
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        var open = document.querySelectorAll(OVERLAY);
        if (!open.length) return;
        event.preventDefault();
        Array.prototype.forEach.call(open, close);
    });
}());
