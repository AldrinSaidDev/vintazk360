"""Operations screens.

A branch team, the same shape as Sales: `index` is the rollup across every
business unit, and the four KPI screens are branch-scoped. `KpiScreens` does
all the work; this module only names which view is which.
"""
from apps.kpi.screens import KpiScreens

from .branches import SCOPE

screens = KpiScreens(
    team_slug='operations', namespace='operations', scope=SCOPE, branched=True,
    workbook_template=True,
)

index = screens.overview                  # team rollup across all business units

branch_index = screens.dashboard          # one unit's KPI scorecard
branch_kpis = screens.definitions          # KPI definitions reference
branch_import_data = screens.import_data   # manual entry + CSV/workbook import
branch_kpi_management = screens.management  # create / edit / soft-delete
branch_kpi_template = screens.template      # per-KPI CSV (kept: existing links)
branch_kpi_workbook = screens.workbook      # ONE .xlsx per unit, a sheet per KPI
