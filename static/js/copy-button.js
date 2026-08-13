// Copy-to-clipboard buttons: any [data-copy="…"] element copies its own value.
//
// Used by the sign-in details card on the Users screen, which is the one place
// in the app showing something the reader has to get out of the page and into a
// message. Delegated from the document, so a button inside a modal that was
// rendered by a fetch works without being wired up again.
(function () {
    'use strict';

    // Full class strings, written out literally: Tailwind purges what it cannot
    // see as a literal, and it does scan inside .js files in the content globs.
    // The `!` matters: the buttons this lands on already carry a text colour
    // (text-brand, or white on the filled one), and which of two plain
    // utilities wins is decided by their order in output.css, not by the order
    // they are listed on the element.
    var DONE = '!text-status-good';

    // How long the button says it worked before going back to saying what it does.
    var SETTLE = 1600;

    /* execCommand is deprecated and the promise API is the real one, but
       navigator.clipboard is undefined outside a secure context, and staging is
       reached over plain HTTP on a Render preview more often than anyone would
       like. Falling back keeps the button honest there rather than silently
       doing nothing. */
    function legacy(text) {
        var pad = document.createElement('textarea');
        pad.value = text;
        // Off-screen rather than hidden: a display:none element cannot be
        // selected, so the copy would come back empty.
        pad.setAttribute('readonly', '');
        pad.style.position = 'fixed';
        pad.style.top = '-1000px';
        document.body.appendChild(pad);
        pad.select();
        var ok = false;
        try {
            ok = document.execCommand('copy');
        } catch (err) {
            ok = false;
        }
        document.body.removeChild(pad);
        return ok ? Promise.resolve() : Promise.reject();
    }

    function copy(text) {
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text);
        }
        return legacy(text);
    }

    /* Only the wording changes, never the button's own contents. A button that
       carries an icon beside its label would otherwise lose the icon the first
       time it was pressed, since rewriting textContent takes the <i> with it. */
    function flash(button, message, ok) {
        var label = button.querySelector('[data-copy-label]') || button;
        if (label.dataset.copyRest === undefined) {
            label.dataset.copyRest = label.textContent.trim();
        }
        label.textContent = message;
        button.classList.toggle(DONE, ok);
        window.clearTimeout(button._copyTimer);
        button._copyTimer = window.setTimeout(function () {
            label.textContent = label.dataset.copyRest;
            button.classList.remove(DONE);
        }, SETTLE);
    }

    document.addEventListener('click', function (event) {
        var button = event.target.closest ? event.target.closest('[data-copy]') : null;
        if (!button) return;
        event.preventDefault();

        copy(button.getAttribute('data-copy')).then(function () {
            flash(button, 'Copied', true);
        }).catch(function () {
            // Saying so beats a button that looks like it worked. The value is
            // still on screen and can be selected by hand.
            flash(button, 'Select it by hand', false);
        });
    });
}());
