// Password visibility toggles for any field wrapped with the shared partial.
//
// The button finds its input INSIDE ITS OWN WRAPPER, never by id. The Users
// screen renders the Add User modal plus one Set password modal per row, and
// every one of them is the same form, so `id_password1` appears eighteen times
// on that page. `getElementById` returns the first, which meant every row's eye
// silently drove the Add User field: the modal you were looking at did nothing
// and a password box in a closed modal was revealed instead. Same trap the
// password checklist and the generator already scope around, and the reason
// neither of them keys off an id either.
//
// `data-password-target` is still emitted for anything that needs to name a
// field somewhere else on the page, and is only consulted when the wrapper
// holds no input of its own.
(function () {
    'use strict';

    function inputFor(button) {
        var wrapper = button.parentElement;
        var input = wrapper ? wrapper.querySelector('input') : null;
        if (input) return input;
        var targetId = button.getAttribute('data-password-target');
        return targetId ? document.getElementById(targetId) : null;
    }

    function setState(button, input, visible) {
        // Only write when it actually differs. The MutationObserver below
        // watches this same attribute, and writing it queues a mutation record
        // even when the value is unchanged. An unconditional write therefore
        // re-entered the observer, wrote again, and re-entered again; observer
        // callbacks are microtasks, so the queue never drained and the tab
        // locked up the moment anyone clicked the eye.
        var wanted = visible ? 'text' : 'password';
        if (input.type !== wanted) input.type = wanted;
        button.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
        button.setAttribute('aria-pressed', visible ? 'true' : 'false');

        var label = button.querySelector('[data-password-toggle-label]');
        if (label) label.textContent = visible ? 'Hide password' : 'Show password';

        var slash = button.querySelector('[data-password-toggle-slash]');
        if (slash) {
            slash.classList.toggle('opacity-0', !visible);
            slash.classList.toggle('opacity-100', visible);
        }
    }

    document.querySelectorAll('[data-password-toggle]').forEach(function (button) {
        var input = inputFor(button);
        if (!input) return;

        setState(button, input, input.type !== 'password');

        var observer = new MutationObserver(function () {
            setState(button, input, input.type !== 'password');
        });
        observer.observe(input, { attributes: true, attributeFilter: ['type'] });

        button.addEventListener('click', function () {
            setState(button, input, input.type === 'password');
            try {
                input.focus({ preventScroll: true });
            } catch (error) {
                input.focus();
            }
        });
    });
}());
