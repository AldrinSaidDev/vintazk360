"""
Admin for the KPI tables.

Enough to create, inspect and correct rows by hand while the real screens are
being built — a KPI is only meaningful together with its inputs, so those are
inlines rather than separate pages. The history tables and import issues are
read-only: they are append-only records, and editing one would defeat the point
of keeping it.
"""

from django.contrib import admin

from .models import (
    KpiBranch,
    KpiCategory,
    KpiDefinition,
    KpiFormulaHistory,
    KpiImportBatch,
    KpiImportIssue,
    KpiInput,
    KpiPreset,
    KpiPresetInput,
    KpiRecord,
    KpiRecordInput,
    KpiTargetHistory,
)


class KpiPresetInputInline(admin.TabularInline):
    model = KpiPresetInput
    extra = 1


@admin.register(KpiPreset)
class KpiPresetAdmin(admin.ModelAdmin):
    list_display = ('name', 'suggested_category', 'expression', 'direction', 'is_seeded', 'is_active')
    list_filter = ('is_seeded', 'is_active', 'direction', 'frequency', 'applies_to_team')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = (KpiPresetInputInline,)


@admin.register(KpiBranch)
class KpiBranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'team', 'slug', 'order', 'is_active')
    list_filter = ('team', 'is_active')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(KpiCategory)
class KpiCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'team', 'order')
    list_filter = ('team',)


class KpiInputInline(admin.TabularInline):
    model = KpiInput
    extra = 1
    fields = ('position', 'key', 'label', 'data_type', 'aggregation', 'is_required', 'placeholder')


@admin.register(KpiDefinition)
class KpiDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'team', 'branch', 'category', 'target_display',
        'frequency', 'template_version', 'is_active',
    )
    list_filter = ('team', 'branch', 'category', 'is_active', 'frequency', 'direction')
    search_fields = ('name', 'slug', 'description', 'expression')
    prepopulated_fields = {'slug': ('name',)}
    inlines = (KpiInputInline,)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('team', 'branch', 'category', 'preset', 'name', 'slug', 'description')}),
        ('Formula', {
            'fields': ('expression', 'score_expression', 'formula_text', 'template_version'),
            'description': 'Operands are the inputs below. formula_text is generated, not typed.',
        }),
        ('Display', {'fields': ('display_format', 'unit', 'precision')}),
        ('Target', {'fields': ('direction', 'target_min', 'target_max', 'target_display', 'frequency')}),
        ('Accumulation', {'fields': ('accumulation', 'baseline_value'), 'classes': ('collapse',)}),
        ('Housekeeping', {'fields': ('is_active', 'sort_order', 'created_by', 'created_at', 'updated_at')}),
    )


class KpiRecordInputInline(admin.TabularInline):
    model = KpiRecordInput
    extra = 0


@admin.register(KpiRecord)
class KpiRecordAdmin(admin.ModelAdmin):
    # `is_active` is listed and filterable because admin is the only place a
    # soft-deleted record can be brought back without re-entering its period.
    list_display = (
        'kpi', 'period_start', 'value_display', 'attainment', 'status', 'source',
        'is_active',
    )
    list_filter = ('is_active', 'status', 'source', 'kpi__team', 'period_start')
    search_fields = ('kpi__name', 'remarks')
    date_hierarchy = 'period_start'
    inlines = (KpiRecordInputInline,)
    readonly_fields = ('created_at', 'updated_at')


class KpiImportIssueInline(admin.TabularInline):
    model = KpiImportIssue
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(KpiImportBatch)
class KpiImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        'file_name', 'team', 'kpi', 'status', 'row_count',
        'created_count', 'updated_count', 'error_count', 'uploaded_at',
    )
    list_filter = ('status', 'team', 'storage_provider')
    search_fields = ('file_name', 'storage_path', 'file_hash')
    date_hierarchy = 'uploaded_at'
    inlines = (KpiImportIssueInline,)
    readonly_fields = ('created_at',)


class _AppendOnlyAdmin(admin.ModelAdmin):
    """History is written by the app, never edited here."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(KpiTargetHistory)
class KpiTargetHistoryAdmin(_AppendOnlyAdmin):
    list_display = ('kpi', 'effective_from', 'target_display', 'reason', 'changed_by', 'changed_at')
    list_filter = ('kpi__team',)
    date_hierarchy = 'effective_from'


@admin.register(KpiFormulaHistory)
class KpiFormulaHistoryAdmin(_AppendOnlyAdmin):
    list_display = ('kpi', 'effective_from', 'template_version', 'expression', 'changed_by', 'changed_at')
    list_filter = ('kpi__team',)
    date_hierarchy = 'effective_from'
