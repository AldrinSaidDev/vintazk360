// "Generate password" on the Add user modal.
//
// Adding a colleague should not mean inventing a password for them, and an
// administrator adding ten in a sitting will otherwise reach for the same one
// ten times. This makes one, fills both boxes and shows what it made, since a
// password you cannot read is a password you cannot hand over.
//
// Every rule here mirrors apps/core/validators.py, which is what actually
// enforces the policy on save: at least 6 characters, one uppercase letter and
// one special character. The length below is well past that on purpose. The
// policy is a floor for something a person has to remember; nobody has to
// remember this one, so there is no reason for it to be short.
(function () {
    'use strict';

    var LENGTH = 16;

    // No I, l, 1, O or 0. This gets read down a phone or copied out of a chat
    // message, and a character somebody has to guess the case of is a support
    // call rather than a sign-in.
    var UPPER = 'ABCDEFGHJKMNPQRSTUVWXYZ';
    var LOWER = 'abcdefghijkmnpqrstuvwxyz';
    var DIGIT = '23456789';
    // Nothing here needs escaping in a shell, a URL or a spreadsheet cell, so
    // pasting the password around cannot quietly mangle it.
    var SPECIAL = '!@#$%^&*-_=+?';

    var ALL = UPPER + LOWER + DIGIT + SPECIAL;

    /* A whole number below `max`, from the CSPRNG rather than Math.random.
       The rejection loop is what keeps it uniform: taking a raw byte modulo the
       pool size favours the first few characters, because 256 does not divide
       evenly by 23. */
    function below(max) {
        var limit = 256 - (256 % max);
        var byte = new Uint8Array(1);
        do {
            window.crypto.getRandomValues(byte);
        } while (byte[0] >= limit);
        return byte[0] % max;
    }

    function pick(pool) {
        return pool.charAt(below(pool.length));
    }

    /* Fisher-Yates, over the same source. */
    function shuffle(chars) {
        for (var i = chars.length - 1; i > 0; i--) {
            var j = below(i + 1);
            var swap = chars[i];
            chars[i] = chars[j];
            chars[j] = swap;
        }
        return chars;
    }

    function generate() {
        // One of each class first, so the policy is met by construction rather
        // than by generating and hoping. Then shuffled, or the shape of every
        // password this app hands out would be public knowledge.
        var chars = [pick(UPPER), pick(LOWER), pick(DIGIT), pick(SPECIAL)];
        while (chars.length < LENGTH) chars.push(pick(ALL));
        return shuffle(chars).join('');
    }

    document.addEventListener('click', function (event) {
        var button = event.target.closest ? event.target.closest('[data-password-generate]') : null;
        if (!button) return;
        event.preventDefault();

        // Scoped to the container the two boxes and the rule checklist share.
        // The Users screen renders one password form per row, so id_password1
        // repeats down the page and querying the document would fill the wrong
        // modal's fields.
        var box = button.closest('[data-password-checklist]');
        if (!box) return;

        var fields = box.querySelectorAll('input[type="password"], input[type="text"]');
        if (!fields.length) return;

        var value = generate();
        Array.prototype.forEach.call(fields, function (field) {
            field.value = value;
            // Shown, not masked. The administrator has to be able to read it to
            // pass it on, and it is on screen for one modal either way: the
            // details card that follows the save prints it in full.
            field.type = 'text';
            // The live rule checklist listens for `input`, and setting `.value`
            // from a script does not fire one.
            field.dispatchEvent(new Event('input', { bubbles: true }));
        });
    });
}());
