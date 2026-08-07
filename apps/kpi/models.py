"""
KPI definitions, actuals and import history.

This is the database behind `db_schema.txt` — read that first; it explains what
these tables are *for*. The short version:

    A KPI stores a FORMULA as an expression over NAMED INPUTS, and those inputs
    ARE the CSV columns. A manager creates the KPI, downloads a template built
    from its own inputs, fills it in, uploads it, and the record is scored.

Table names are set explicitly (`kpi_definition`, `kpi_record`, …) so they read
the same in SQL as they do in the schema document.

Two things live elsewhere on purpose:
  * `AuditLog` is in `apps.core` — it records logins and user management too,
    not just KPI activity, so it belongs to the shared layer every app imports.
  * The band/attainment/status math is still `apps.core.kpi`, in production
    across seven LOBs. It moves here (as `scoring.py`) when the views switch
    from their static dicts to querysets.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import Team

# ---------------------------------------------------------------------------
# Shared vocabularies
#
# Presets and definitions describe the same things, so they share these rather
# than each declaring their own copy.
# ---------------------------------------------------------------------------


class Direction(models.TextChoices):
    """Which way is good."""
    UP = 'up', 'Higher is better'
    DOWN = 'down', 'Lower is better'


class Frequency(models.TextChoices):
    """The reporting cadence — also decides the CSV's `period` format."""
    DAILY = 'daily', 'Daily'
    WEEKLY = 'weekly', 'Weekly'
    MONTHLY = 'monthly', 'Monthly'
    QUARTERLY = 'quarterly', 'Quarterly'
    ANNUALLY = 'annually', 'Annually'


class DisplayFormat(models.TextChoices):
    """How the computed number PRINTS — deliberately separate from how it is
    calculated. `a / b` is a percentage, an average, a ratio and a cost per
    unit; only the formatting differs."""
    PERCENT = 'percent', 'Percentage'
    NUMBER = 'number', 'Number'
    INTEGER = 'integer', 'Whole number'
    CURRENCY = 'currency', 'Currency'
    RATIO = 'ratio', 'Ratio'
    DAYS = 'days', 'Days'


class DataType(models.TextChoices):
    """What a single cell in the CSV must contain."""
    NUMBER = 'number', 'Number'
    INTEGER = 'integer', 'Whole number'
    DATE = 'date', 'Date'
    CURRENCY = 'currency', 'Currency'


class Aggregation(models.TextChoices):
    """How one input's column collapses over a reporting period.

    `NONE` means exactly one row per period and more than one is an error;
    `COUNT` is what turns "one CSV row per hire" into a headcount.
    """
    NONE = 'none', 'One row per period'
    SUM = 'sum', 'Sum the rows'
    COUNT = 'count', 'Count the rows'
    AVG = 'avg', 'Average'
    MIN = 'min', 'Minimum'
    MAX = 'max', 'Maximum'
    LAST = 'last', 'Last value'


class Accumulation(models.TextChoices):
    """Flow vs stock — does a period stand alone or carry forward?"""
    PERIOD = 'period', "This period's own figure"
    CUMULATIVE = 'cumulative', 'Running total'


# A key is the expression variable, the CSV header and the form field name all
# at once, so it has to be a valid identifier.
KEY_VALIDATOR = RegexValidator(
    regex=r'^[a-z][a-z0-9_]*$',
    message=(
        'Use lower-case letters, digits and underscores, starting with a '
        'letter — it becomes a variable in the formula and a CSV column '
        "header (e.g. 'total_exits')."
    ),
)


# ---------------------------------------------------------------------------
# 1–2 · The adoptable KPI library
# ---------------------------------------------------------------------------


class KpiPreset(models.Model):
    """A known KPI, offered to managers for one-click adoption.

    The ~80 KPIs currently hard-coded in the LOB views land here. Adopting one
    COPIES it into a `KpiDefinition`; editing that copy never touches the
    preset, and the preset carries a *suggested* target the manager overrides.
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    suggested_category = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)

    expression = models.CharField(
        max_length=255,
        help_text="e.g. 'a / b * 100' — operands are this preset's inputs.",
    )
    display_format = models.CharField(
        max_length=12, choices=DisplayFormat.choices, default=DisplayFormat.PERCENT
    )
    unit = models.CharField(max_length=16, blank=True, help_text="Display suffix: ' days', '×', '₱'.")
    direction = models.CharField(max_length=4, choices=Direction.choices, default=Direction.UP)
    frequency = models.CharField(
        max_length=12, choices=Frequency.choices, default=Frequency.MONTHLY
    )

    suggested_target_min = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True
    )
    suggested_target_max = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True
    )

    applies_to_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='kpi_presets',
        help_text='Leave empty to offer this preset to every team.',
    )
    is_seeded = models.BooleanField(
        default=False,
        help_text='Auto-installed into every team (Attrition Rate, Billable Hours).',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'kpi_preset'
        ordering = ['suggested_category', 'name']
        verbose_name = 'KPI preset'

    def __str__(self):
        return self.name


class KpiPresetInput(models.Model):
    """One operand of a preset's formula — copied into `KpiInput` on adoption."""

    preset = models.ForeignKey(KpiPreset, on_delete=models.CASCADE, related_name='inputs')
    key = models.CharField(max_length=60, validators=[KEY_VALIDATOR])
    label = models.CharField(max_length=120)
    placeholder = models.CharField(max_length=60, blank=True)
    data_type = models.CharField(max_length=10, choices=DataType.choices, default=DataType.NUMBER)
    aggregation = models.CharField(
        max_length=8, choices=Aggregation.choices, default=Aggregation.NONE
    )
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = 'kpi_preset_input'
        ordering = ['position']
        constraints = [
            models.UniqueConstraint(fields=['preset', 'key'], name='kpi_preset_input_unique_key'),
        ]
        verbose_name = 'KPI preset input'

    def __str__(self):
        return f'{self.preset.name} · {self.key}'


# ---------------------------------------------------------------------------
# 3–4 · Team structure
# ---------------------------------------------------------------------------


class KpiBranch(models.Model):
    """A sub-team within a team (Sales → SEO / Lead Gen / Transitions).

    As data rather than a hard-coded list, a fourth branch is a row instead of
    a deploy.
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, help_text='Matches the URL segment, e.g. "seo".')
    order = models.PositiveSmallIntegerField(default=0, help_text='Sidebar sort order.')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'kpi_branch'
        ordering = ['team', 'order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['team', 'slug'], name='kpi_branch_unique_slug'),
        ]
        verbose_name = 'KPI branch'
        verbose_name_plural = 'KPI branches'

    def __str__(self):
        return f'{self.team.name} · {self.name}'


class KpiCategory(models.Model):
    """A grouping of KPIs within one team ("Client Impact", "Payroll").

    A table rather than a free-text field so the Add-KPI dropdown grows without
    a deploy and a typo can't silently spawn a new category.
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='kpi_categories')
    name = models.CharField(max_length=80)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'kpi_category'
        ordering = ['team', 'order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['team', 'name'], name='kpi_category_unique_name'),
        ]
        verbose_name = 'KPI category'
        verbose_name_plural = 'KPI categories'

    def __str__(self):
        return f'{self.team.name} · {self.name}'


# ---------------------------------------------------------------------------
# 5–6 · The KPI itself, and its operands
# ---------------------------------------------------------------------------


class KpiDefinition(models.Model):
    """One team's KPI: what it measures, how it is calculated, what it aims at.

    `expression` is the real content — a formula over this KPI's own
    `inputs`, evaluated by a whitelisted AST walk (never `eval()`).
    `formula_text` is the readable sentence the KPI Definitions screen shows,
    RENDERED from the expression on save rather than typed, so the two can
    never disagree.
    """

    team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        related_name='kpis',
        help_text='Owning team. Never empty — this is what access control keys off.',
    )
    branch = models.ForeignKey(
        KpiBranch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='kpis',
        help_text='Leave empty for a team-level KPI.',
    )
    category = models.ForeignKey(
        KpiCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='kpis'
    )
    preset = models.ForeignKey(
        KpiPreset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adoptions',
        help_text='Where it came from, if adopted from the library.',
    )

    name = models.CharField(max_length=120)
    slug = models.SlugField(
        max_length=120,
        help_text='Stable — the CSV template binds to this. Renaming breaks old templates.',
    )
    description = models.TextField(blank=True)

    expression = models.CharField(
        max_length=255,
        help_text="The formula, e.g. 'total_exits / average_headcount * 100'.",
    )
    score_expression = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            'Only when the graded number differs from the shown one — e.g. '
            "'abs(value)' so a −3.2% variance is graded as 3.2."
        ),
    )
    formula_text = models.CharField(
        max_length=255,
        blank=True,
        help_text='Human-readable rendering of the expression. Generated, not typed.',
    )

    display_format = models.CharField(
        max_length=12, choices=DisplayFormat.choices, default=DisplayFormat.PERCENT
    )
    unit = models.CharField(max_length=16, blank=True)
    precision = models.PositiveSmallIntegerField(default=1, help_text='Decimal places.')

    accumulation = models.CharField(
        max_length=10, choices=Accumulation.choices, default=Accumulation.PERIOD
    )
    baseline_value = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Required when cumulative — the running total starts here.',
    )

    direction = models.CharField(max_length=4, choices=Direction.choices, default=Direction.UP)
    frequency = models.CharField(
        max_length=12, choices=Frequency.choices, default=Frequency.MONTHLY
    )

    # Targets are always bands: a single target is a band of width zero, and
    # both empty means tracked but not scored ("No Target").
    target_min = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    target_max = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    target_display = models.CharField(
        max_length=60, blank=True, help_text='"≥95%", "40–80 / month", "Threshold 3.5%".'
    )

    template_version = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            'Bumped on every formula or input change, so a CSV filled against '
            'an older formula is rejected instead of silently misread.'
        ),
    )
    is_active = models.BooleanField(default=True, help_text='Delete a KPI.')
    sort_order = models.PositiveSmallIntegerField(default=0, help_text='Card order on the scorecard.')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kpis_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kpi_definition'
        ordering = ['team', 'sort_order', 'name']
        indexes = [
            models.Index(fields=['team', 'is_active'], name='kpi_definition_team_active'),
        ]
        constraints = [
            # nulls_distinct=False so two TEAM-LEVEL KPIs (branch = NULL)
            # can't share a slug — Postgres would otherwise treat each NULL as
            # unique and let the duplicate through. Needs Postgres 15+.
            models.UniqueConstraint(
                fields=['team', 'branch', 'slug'],
                name='kpi_definition_unique_slug',
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(target_min__isnull=True)
                    | models.Q(target_max__isnull=True)
                    | models.Q(target_min__lte=models.F('target_max'))
                ),
                name='kpi_definition_target_band_ordered',
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(accumulation=Accumulation.CUMULATIVE)
                    | models.Q(baseline_value__isnull=False)
                ),
                name='kpi_definition_cumulative_needs_baseline',
            ),
        ]
        verbose_name = 'KPI definition'

    def __str__(self):
        return f'{self.team.name} · {self.name}'

    @property
    def is_scored(self):
        """False when no target is set — the KPI is tracked but not graded."""
        return self.target_min is not None or self.target_max is not None


class KpiInput(models.Model):
    """One operand of a KPI's formula — and therefore one CSV column.

    The keystone of the design: `key` is simultaneously the variable name in
    `KpiDefinition.expression`, the column header in the generated CSV, and the
    field name in the Add-Record form. One identifier, three jobs.
    """

    kpi = models.ForeignKey(KpiDefinition, on_delete=models.CASCADE, related_name='inputs')
    key = models.CharField(
        max_length=60,
        validators=[KEY_VALIDATOR],
        help_text="Formula variable AND CSV column header, e.g. 'total_exits'.",
    )
    label = models.CharField(max_length=120, help_text='Shown on the form, e.g. "Total exits".')
    placeholder = models.CharField(max_length=60, blank=True, help_text='e.g. "e.g. 12".')
    data_type = models.CharField(max_length=10, choices=DataType.choices, default=DataType.NUMBER)
    aggregation = models.CharField(
        max_length=8,
        choices=Aggregation.choices,
        default=Aggregation.NONE,
        help_text='How this column collapses when a period has several rows.',
    )
    position = models.PositiveSmallIntegerField(
        default=1, help_text='Order in the form and in the CSV.'
    )
    help_text = models.CharField(
        max_length=160, blank=True, help_text="Guidance in the CSV's instruction block."
    )
    is_required = models.BooleanField(
        default=True, help_text='When false, a blank cell counts as 0 instead of an error.'
    )

    class Meta:
        db_table = 'kpi_input'
        ordering = ['kpi', 'position']
        constraints = [
            models.UniqueConstraint(fields=['kpi', 'key'], name='kpi_input_unique_key'),
        ]
        verbose_name = 'KPI input'

    def __str__(self):
        return f'{self.kpi.name} · {self.key}'


# ---------------------------------------------------------------------------
# 7–8 · The actuals
# ---------------------------------------------------------------------------


class KpiRecord(models.Model):
    """One actual value, for one KPI, for one reporting period.

    This is what the dashboards read. `attainment` and `status` are CACHED so
    charts don't recompute per page load — they are always re-derivable from
    the record plus the KPI's target.

    One KPI has exactly one row per period, which is also what makes
    re-uploading a corrected file safe: the parser upserts on
    (kpi, period_start) and fixes the month rather than duplicating it.
    """

    class Status(models.TextChoices):
        ON_TRACK = 'on_track', 'On Track'
        AT_RISK = 'at_risk', 'At Risk'
        BELOW = 'below', 'Below Target'
        MONITORED = 'monitored', 'No Target'

    class Source(models.TextChoices):
        MANUAL = 'manual', 'Manual entry'
        IMPORT = 'import', 'CSV import'
        API = 'api', 'API'

    kpi = models.ForeignKey(KpiDefinition, on_delete=models.CASCADE, related_name='records')
    period_start = models.DateField(help_text='First day of the reporting period.')
    period_end = models.DateField(help_text="Derived from the KPI's frequency when saved.")

    value = models.DecimalField(
        max_digits=14, decimal_places=4, help_text="The expression's result."
    )
    score = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Only when the graded number differs from the shown one.',
    )
    value_display = models.CharField(
        max_length=40, blank=True, help_text='"3.1%", "8.6 days", "₱1,240".'
    )
    attainment = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Cached % of target. Empty when the KPI has no target.',
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.MONITORED
    )

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    import_batch = models.ForeignKey(
        'kpi.KpiImportBatch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='records',
        help_text='Which upload produced this, if any.',
    )
    remarks = models.TextField(blank=True)

    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kpi_records_entered',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kpi_record'
        ordering = ['-period_start']
        indexes = [
            # Every scorecard query is "latest period for this KPI".
            models.Index(fields=['kpi', '-period_start'], name='kpi_record_latest'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['kpi', 'period_start'], name='kpi_record_unique_period'),
        ]
        verbose_name = 'KPI record'

    def __str__(self):
        return f'{self.kpi.name} · {self.period_start} · {self.value_display or self.value}'


class KpiRecordInput(models.Model):
    """The raw number behind a record — one row per operand.

    The record stores `3.1%`; these store `12` and `380`. Without them "why is
    this 3.1%?" is unanswerable, and a corrected formula could never re-derive
    history.
    """

    record = models.ForeignKey(KpiRecord, on_delete=models.CASCADE, related_name='input_values')
    input = models.ForeignKey(KpiInput, on_delete=models.PROTECT, related_name='record_values')
    value_number = models.DecimalField(
        max_digits=16, decimal_places=4, null=True, blank=True
    )
    value_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'kpi_record_input'
        constraints = [
            models.UniqueConstraint(
                fields=['record', 'input'], name='kpi_record_input_unique_operand'
            ),
            # Exactly one of the two value columns is filled.
            models.CheckConstraint(
                condition=(
                    models.Q(value_number__isnull=False, value_date__isnull=True)
                    | models.Q(value_number__isnull=True, value_date__isnull=False)
                ),
                name='kpi_record_input_one_value',
            ),
        ]
        verbose_name = 'KPI record input'

    def __str__(self):
        return f'{self.input.key} = {self.value_number if self.value_date is None else self.value_date}'


# ---------------------------------------------------------------------------
# 9–10 · Imports
# ---------------------------------------------------------------------------


class KpiImportBatch(models.Model):
    """One upload — what feeds the "Recent Import History" panel.

    The file itself is NOT in Postgres: these three `storage_*` columns are a
    pointer into the Cloudflare R2 bucket (see `apps.core.storage`).
    """

    class Provider(models.TextChoices):
        R2 = 'r2', 'Cloudflare R2'
        S3 = 's3', 'Amazon S3'
        LOCAL = 'local', 'Local disk'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPLIED = 'applied', 'Applied'
        PARTIAL = 'partial', 'Partially applied'
        FAILED = 'failed', 'Failed'

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='kpi_imports')
    branch = models.ForeignKey(
        KpiBranch, on_delete=models.PROTECT, null=True, blank=True, related_name='kpi_imports'
    )
    kpi = models.ForeignKey(
        KpiDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='imports',
        help_text='Set when the file targets one KPI.',
    )

    file_name = models.CharField(max_length=255, help_text='As uploaded, for display.')
    storage_provider = models.CharField(
        max_length=20, choices=Provider.choices, default=Provider.R2
    )
    storage_bucket = models.CharField(max_length=100)
    storage_path = models.CharField(
        max_length=500, help_text='Object key, e.g. "operations/2026/08/attrition-<uuid>.csv".'
    )
    file_size = models.PositiveIntegerField(default=0, help_text='Bytes.')
    file_hash = models.CharField(
        max_length=64, blank=True, help_text='sha256 — warns on an accidental duplicate upload.'
    )
    content_type = models.CharField(max_length=60, blank=True)

    template_version = models.PositiveSmallIntegerField(
        default=1, help_text="From the file header; compared against the KPI's current version."
    )
    template_generated_at = models.DateTimeField(
        null=True, blank=True, help_text='From the file\'s "generated=" header.'
    )

    uploaded_at = models.DateTimeField(help_text='When the file arrived.')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    row_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kpi_imports',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True, blank=True, help_text='Kept separate from uploaded_at so a stuck import shows.'
    )

    class Meta:
        db_table = 'kpi_import_batch'
        ordering = ['-uploaded_at']
        constraints = [
            models.UniqueConstraint(
                fields=['storage_provider', 'storage_bucket', 'storage_path'],
                name='kpi_import_batch_unique_object',
            ),
        ]
        verbose_name = 'KPI import batch'
        verbose_name_plural = 'KPI import batches'

    def __str__(self):
        return f'{self.file_name} · {self.team.name}'


class KpiImportIssue(models.Model):
    """One rejected (or flagged) row from an upload.

    Without this the user is told "1 row failed" with no way to find out which,
    or why.
    """

    class Severity(models.TextChoices):
        ERROR = 'error', 'Error (row skipped)'
        WARNING = 'warning', 'Warning (row applied)'

    batch = models.ForeignKey(KpiImportBatch, on_delete=models.CASCADE, related_name='issues')
    row_number = models.PositiveIntegerField(help_text='1-based, as the user sees it in Excel.')
    column_key = models.CharField(max_length=60, blank=True)
    raw_value = models.CharField(max_length=255, blank=True, help_text='What was actually typed.')
    severity = models.CharField(max_length=8, choices=Severity.choices, default=Severity.ERROR)
    message = models.CharField(max_length=255, help_text='"\'n/a\' is not a number".')

    class Meta:
        db_table = 'kpi_import_issue'
        ordering = ['batch', 'row_number']
        verbose_name = 'KPI import issue'

    def __str__(self):
        return f'Row {self.row_number}: {self.message}'


# ---------------------------------------------------------------------------
# 11–12 · History — append-only, never rewritten
# ---------------------------------------------------------------------------


class KpiTargetHistory(models.Model):
    """Every target a KPI has ever had.

    Changing a target silently rewrites how every past period reads: a July
    that was "On Track" becomes "Below Target" with no record of why.
    """

    kpi = models.ForeignKey(
        KpiDefinition, on_delete=models.CASCADE, related_name='target_history'
    )
    target_min = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    target_max = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    target_display = models.CharField(max_length=60, blank=True)
    effective_from = models.DateField()
    reason = models.CharField(max_length=255, blank=True, help_text='"FY27 goal reset".')

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kpi_target_changes',
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kpi_target_history'
        ordering = ['-effective_from']
        indexes = [
            models.Index(fields=['kpi', '-effective_from'], name='kpi_target_history_recent'),
        ]
        verbose_name = 'KPI target history'
        verbose_name_plural = 'KPI target history'

    def __str__(self):
        return f'{self.kpi.name} · from {self.effective_from}'


class KpiFormulaHistory(models.Model):
    """Every formula a KPI has ever had.

    A target change moves the goalposts; a formula change redefines the number
    itself — the same 12 exits and 380 headcount can mean something different
    after an edit. Paired with `KpiRecordInput`, any past period can be
    recomputed under either the old or the new formula.
    """

    kpi = models.ForeignKey(
        KpiDefinition, on_delete=models.CASCADE, related_name='formula_history'
    )
    expression = models.CharField(max_length=255)
    score_expression = models.CharField(max_length=255, blank=True)
    formula_text = models.CharField(max_length=255, blank=True)
    template_version = models.PositiveSmallIntegerField(
        help_text='The CSV template version this formula produced.'
    )
    effective_from = models.DateField()
    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text='"Denominator changed to average, not opening, headcount".',
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kpi_formula_changes',
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kpi_formula_history'
        ordering = ['-effective_from']
        indexes = [
            models.Index(fields=['kpi', '-effective_from'], name='kpi_formula_history_recent'),
        ]
        verbose_name = 'KPI formula history'
        verbose_name_plural = 'KPI formula history'

    def __str__(self):
        return f'{self.kpi.name} · v{self.template_version} from {self.effective_from}'
