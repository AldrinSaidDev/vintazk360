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
    """How one input collapses when a period has several entries.

    THE most consequential setting on a KPI, and the one thing a manager has to
    get right per input. Cadence decides the reporting period; this decides what
    "the period's figure" means once somebody has reported into it twice.

    Additive events take SUM: hires, exits, tickets, revenue. A snapshot or a
    DIVISOR takes LAST or AVG — adding up "average headcount" over three
    uploads gives 1,140 people and an attrition rate a third of the truth. The
    seeder's defaults are derived from the formula itself (an operand under a
    `/` is never auto-summed), and this field is the override for what the
    formula cannot know.

    THREE options, and that is deliberate. A figure somebody types into a
    template is either something that accumulates (SUM), something measured
    repeatedly whose readings average (AVG), or a snapshot whose newest reading
    stands (LAST). `COUNT`, `MIN` and `MAX` were dropped: COUNT ignored the
    number in the cell and counted rows, so the column the uploader filled in
    stopped mattering, and MIN/MAX answered a question about the entries rather
    than about the period. Nothing on the database held any of the three. There
    is no "replace" setting either: it collapsed exactly as `LAST` does, so it
    was one label too many for one behaviour, and it was the misleading one.
    Nothing here overwrites a period.
    """
    SUM = 'sum', 'Add them up'
    AVG = 'avg', 'Average'
    LAST = 'last', 'Most recent wins'


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
        max_length=8, choices=Aggregation.choices, default=Aggregation.SUM
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
DESCRIPTION_MAX_LENGTH = 500

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
    description = models.TextField(blank=True, max_length=DESCRIPTION_MAX_LENGTH)

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
        default=Aggregation.SUM,
        help_text=(
            'How this figure collapses when a period has several entries. '
            'Additive events add up. A snapshot or a divisor should not.'
        ),
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

# How long a record's note may be. Defined once and imported by the form, the
# importer and the field below, so the modal, an uploaded file and the database
# cannot disagree about what fits. Remarks are context for one figure, not a
# report: past a few sentences it belongs in the KPI's description.
REMARKS_MAX_LENGTH = 400


class KpiRecord(models.Model):
    """One actual value, for one KPI, for one reporting period.

    This is what the dashboards read. `attainment` and `status` are CACHED so
    charts don't recompute per page load — they are always re-derivable from
    the record plus the KPI's target.

    One KPI has exactly one row per period. It is now DERIVED rather than
    written directly: `kpi_entry` holds each act of reporting and
    `records.rebuild_period()` collapses that period's entries, re-runs the
    formula and upserts this row. So a month can be topped up any number of
    times and this stays the single figure every chart reads.

    Nothing should write this table except `records.rebuild_period()`. Writing a
    value here directly would be overwritten by the next entry against the same
    period, silently.
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
    # How many entries collapsed into this figure. Cached from kpi_entry so the
    # records table can say "3 entries" without a count per row, and so a
    # reader can tell one submission from a month that has been topped up.
    entry_count = models.PositiveIntegerField(default=0)
    # True while `period_end` is still in the future: the period is open and
    # more entries are expected. The status is still scored against the FULL
    # target, deliberately — pro-rating a target would be a guess about how
    # evenly work lands across a month, and would quietly rewrite what the
    # target means. This flag is what stops a part-filled month reading as
    # failure instead of as unfinished.
    is_in_progress = models.BooleanField(default=False)

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    import_batch = models.ForeignKey(
        'kpi.KpiImportBatch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='records',
        help_text='Which upload produced this, if any.',
    )
    remarks = models.TextField(
        blank=True,
        max_length=REMARKS_MAX_LENGTH,
        help_text=f'Context for this figure. Up to {REMARKS_MAX_LENGTH} characters.',
    )

    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kpi_records_entered',
    )
    # SOFT delete, same as kpi_definition (design principle 7). A figure entered
    # against the wrong period is the one mistake a re-upload cannot fix: the
    # upsert key is (kpi, period_start), so a corrected file writes the right
    # period and leaves the wrong one behind. This is how that row leaves the
    # table without destroying it or its operands.
    #
    # NOTE: the unique constraint on (kpi, period_start) still counts a deleted
    # row, which is deliberate. Re-entering that period REVIVES this row rather
    # than failing on the constraint. See records.save_record().
    is_active = models.BooleanField(
        default=True, help_text='Cleared when the record is deleted.'
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
# 8b · Entries — what was actually submitted, one row per act of reporting
# ---------------------------------------------------------------------------


class KpiEntry(models.Model):
    """One submission: the figures somebody entered or uploaded on one date.

    `kpi_record` holds one row per reporting PERIOD and is what every dashboard
    reads. This holds one row per ACT OF REPORTING, and the record is derived
    from it. The two answer different questions:

        kpi_entry   "on 21 July somebody added 5 hires"
        kpi_record  "July's total is 23 hires, 92% of target"

    Cadence decides the period, never how often you may report. A monthly KPI
    can be topped up every day of the month; each top-up is an entry, they
    collapse into that month's one record, and the month can be watched filling
    in instead of only being readable once it has ended.

    Accumulation happens on the OPERANDS, per `kpi_input.aggregation`, never on
    the finished figure: 3% attrition plus 4% attrition is not 7%. Summing the
    operands and re-running the formula is correct at every KPI shape, and it is
    why a divisor is left on `last` rather than being added up.

    Deliberately NOT unique on (kpi, entry_date): two uploads on one day are two
    entries, which is the whole point of the table.
    """

    kpi = models.ForeignKey(KpiDefinition, on_delete=models.CASCADE, related_name='entries')

    entry_date = models.DateField(
        help_text='The date this figure is for, e.g. 2026-07-21.'
    )
    # Derived from `entry_date` through the KPI's frequency and stored, so that
    # grouping a period's entries is an indexed lookup rather than a date
    # calculation repeated per row. `records.add_entry()` is what keeps it true.
    period_start = models.DateField(help_text="First day of the period `entry_date` falls in.")
    period_end = models.DateField(help_text='Last day of that period.')

    # This entry's own figure, so the history log can show what each submission
    # contributed. The PERIOD's figure lives on kpi_record and is NOT these
    # summed — it is the collapsed operands re-run through the formula.
    value = models.DecimalField(
        max_digits=14, decimal_places=4, help_text="This entry's own result."
    )
    value_display = models.CharField(max_length=40, blank=True)

    source = models.CharField(
        max_length=10, choices=KpiRecord.Source.choices, default=KpiRecord.Source.MANUAL
    )
    import_batch = models.ForeignKey(
        'kpi.KpiImportBatch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entries',
        help_text='Which upload produced this, if any.',
    )
    remarks = models.TextField(blank=True, max_length=REMARKS_MAX_LENGTH)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kpi_entries_entered',
    )
    # Soft, like everything else here. Removing one entry re-collapses the
    # period rather than deleting the record, so a mistyped top-up can be taken
    # back without losing the rest of the month.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kpi_entry'
        ordering = ['-entry_date', '-created_at']
        indexes = [
            # The one query that matters: every entry of one period, to collapse.
            models.Index(fields=['kpi', 'period_start'], name='kpi_entry_period'),
        ]
        verbose_name = 'KPI entry'
        verbose_name_plural = 'KPI entries'

    def __str__(self):
        return f'{self.kpi.name} · {self.entry_date} · {self.value_display or self.value}'


class KpiEntryInput(models.Model):
    """The raw operands of one entry — one row per input.

    The same job `kpi_record_input` does for a period, one level down. Both
    exist: these are what get collapsed, those are the collapsed result, and
    keeping the collapsed copy means a dashboard never has to re-aggregate to
    answer "why is the month this number?".
    """

    entry = models.ForeignKey(KpiEntry, on_delete=models.CASCADE, related_name='input_values')
    input = models.ForeignKey(KpiInput, on_delete=models.PROTECT, related_name='entry_values')
    value_number = models.DecimalField(
        max_digits=16, decimal_places=4, null=True, blank=True
    )
    value_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'kpi_entry_input'
        constraints = [
            models.UniqueConstraint(
                fields=['entry', 'input'], name='kpi_entry_input_unique_operand'
            ),
            # Exactly one of the two value columns is filled.
            models.CheckConstraint(
                condition=(
                    models.Q(value_number__isnull=False, value_date__isnull=True)
                    | models.Q(value_number__isnull=True, value_date__isnull=False)
                ),
                name='kpi_entry_input_one_value',
            ),
        ]
        verbose_name = 'KPI entry input'

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
    # SOFT delete, same as kpi_record and kpi_definition (design principle 7).
    # An upload made by mistake has to leave Recent Import History, but what it
    # did — its counts, its rejected rows, the object it points at — is the
    # audit trail of that mistake and is exactly what nobody should destroy.
    # The records it wrote are soft-deleted with it; see KpiScreens._import_data.
    is_active = models.BooleanField(
        default=True,
        help_text='Cleared when the import is deleted. The row and its issues survive.',
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
