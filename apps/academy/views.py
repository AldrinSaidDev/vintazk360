"""VINTAZK Academy — the four KPI screens, all served by the shared kit.

Everything these pages show comes from `kpi_definition` / `kpi_record`, scoped
to this team. The per-LOB parts are the banner copy in `kpis.py` and nothing
else: see apps/kpi/screens.py for the implementation and CLAUDE.md for the
pattern.
"""

from apps.kpi.screens import KpiScreens

from .kpis import SCOPE

screens = KpiScreens(
    team_slug='academy', namespace='academy', scope=SCOPE, workbook_template=True,
)

index = screens.dashboard                 # team dashboard (KPI scorecard)
kpi_reference = screens.definitions       # KPI definitions reference
import_data = screens.import_data         # manual entry + CSV import
kpi_management = screens.management       # create / edit / soft-delete
kpi_template = screens.template           # per-KPI CSV (kept: existing links)
kpi_workbook = screens.workbook           # ONE .xlsx for the whole team
