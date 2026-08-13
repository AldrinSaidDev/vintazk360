// Hides the Teams block on a user form while the selected role reaches every
// team (Super Admin, Admin, Viewer). Assigning teams to one of those roles does
// nothing, so a grid of ticks that is silently ignored is worse than no grid.
//
// Which roles those are is NOT written out here: apps/core/forms.py emits
// UserProfile.ALL_TEAM_ROLES onto the select as data-all-team-roles, so the
// model stays the one place that decides.
//
// Scoped per FORM, not by id. The Users screen renders the create modal plus one
// Edit modal per row, so every id on these fields repeats down the page.
//
// Nothing is unticked when the block hides: switching to Viewer and back must
// not silently discard the teams that were already picked, and the server
// ignores the M2M for those roles anyway.
(function () {
    'use strict';

    function init(select) {
        var form = select.closest('form');
        if (!form) return;
        var field = form.querySelector('[data-teams-field]');
        var note = form.querySelector('[data-teams-all-note]');
        if (!field) return;

        var allTeamRoles = (select.dataset.allTeamRoles || '').split(',');

        function sync() {
            var allTeams = allTeamRoles.indexOf(select.value) !== -1;
            field.classList.toggle('hidden', allTeams);
            if (note) note.classList.toggle('hidden', !allTeams);
        }

        select.addEventListener('change', sync);
        sync();  // a failed POST re-renders with the posted role selected
    }

    document.querySelectorAll('select[data-role-select]').forEach(init);
})();
