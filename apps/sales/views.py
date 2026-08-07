"""Sales — the only branch team, on the same shared kit as every other LOB.

Sales splits into three branches (SEO & Google Ads / Lead Generation /
Transitions), each with its own four screens, plus a team-level rollup at
`/sales/`. `KpiScreens(branched=True)` takes the branch slug from the URL and
scopes every query to `kpi_definition.branch`; the branch rows themselves live
in `kpi_branch`, so a fourth branch is a row rather than a deploy.

`branches.py` still holds the KPI data, but only as seed input for
`manage.py seed_lob_kpis sales` — no screen reads it.
"""

from apps.kpi.screens import KpiScreens

from .branches import SCOPE

screens = KpiScreens(team_slug='sales', namespace='sales', scope=SCOPE, branched=True)

index = screens.overview                        # team rollup across all branches

branch_index = screens.dashboard                # one branch's KPI scorecard
branch_kpis = screens.definitions
branch_import_data = screens.import_data
branch_kpi_management = screens.management
branch_kpi_template = screens.template
