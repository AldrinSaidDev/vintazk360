"""The Create- and Edit-KPI forms behind the Operations KPI Management screen.

Operations is the reference implementation: once this is right it gets lifted
into a shared place and reused by every other LOB, so the forms deliberately
enforce the whole of `db_schema.txt` rather than just filling a table:

  * the FORMULA is validated by whitelisted AST walk (`apps.kpi.formula`),
  * the INPUTS come with it — they are the operands, the CSV columns and the
    form fields all at once (§6), so a KPI without them is unusable,
  * creating writes the `KpiFormulaHistory` row the KPI shipped with (§E.3),
  * editing a target appends a `KpiTargetHistory` row (§11) — otherwise a July
    that read "On Track" silently becomes "Below Target" with no record of why.

Audit entries are written by the view, which is the thing that holds the
request.
"""

import datetime as dt
import json
from decimal import Decimal

from django import forms
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.kpi import formula as formula_engine
from apps.kpi import importer, periods, records
from apps.kpi.models import (
    KEY_VALIDATOR,
    REMARKS_MAX_LENGTH,
    Aggregation,
    DataType,
    KpiCategory,
    KpiDefinition,
    KpiEntryInput,
    KpiFormulaHistory,
    KpiInput,
    KpiRecord,
    KpiTargetHistory,
)


TAILWIND_INPUT = (
    "w-full rounded-lg border border-slate-300 px-3 py-2.5 "
    "text-sm focus:border-brand focus:outline-none "
    "focus:ring-2 focus:ring-brand/20"
)

# Both forms carry the same fields, `expression` included — the formula builder
# is available when editing too. What differs is the consequence: on an edit, a
# changed formula appends history and bumps `template_version` (§A.6).
_SHARED_FIELDS = [
    "name",
    "category",
    "description",
    "frequency",
    "direction",
    "display_format",
    "unit",
    "target_min",
    "target_max",
    "target_display",
    "expression",
]


class CategorySelect(forms.Select):
    """The category dropdown, with one extra option meaning "make a new one".

    Keeping it in the same control is what lets the text box stay hidden until
    it is wanted (see `.category-picker` in static/src/input.css) — an
    always-visible "or type a new one" field reads as a second required
    question on a form that already has plenty.
    """

    NEW = "__new__"
    NEW_LABEL = "+ Create new category…"

    def optgroups(self, name, value, attrs=None):
        groups = super().optgroups(name, value, attrs)
        index = len(groups)
        selected = self.NEW in [str(v) for v in value if v is not None]
        groups.append(
            (
                None,
                [self.create_option(name, self.NEW, self.NEW_LABEL, selected, index)],
                index,
            )
        )
        return groups


class CategoryChoiceField(forms.ModelChoiceField):
    """A category picker whose "create new" sentinel is not a validation error.

    `__new__` means *no existing category* — the `new_category` text box
    supplies the name instead, and the form's `clean()` insists it is filled.
    """

    widget = CategorySelect

    def to_python(self, value):
        if value == CategorySelect.NEW:
            return None
        return super().to_python(value)

    def label_from_instance(self, obj):
        """The category's own name, without `KpiCategory.__str__`'s team prefix.

        Two reasons, and the second one was measured. It reads better: the
        queryset is already scoped to one team, so every option said
        "Operations · " and the only part that varied came after it. And it is
        the whole of a performance bug — the default label calls `str(obj)`,
        which reaches through `obj.team` for that prefix, and neither the
        category nor its team is select_related in a ModelChoiceField's own
        iteration. KPI Management renders eleven of these pickers (the create
        form plus one Edit modal per row), so the page was issuing a
        `core_team` SELECT per option per form: 26 identical queries for one
        team's name.
        """
        return obj.name


_SHARED_WIDGETS = {
    "name": forms.TextInput(
        attrs={"class": TAILWIND_INPUT, "placeholder": "e.g. Attrition Rate"}
    ),
    "description": forms.Textarea(
        attrs={
            "class": TAILWIND_INPUT,
            "rows": 3,
            'maxlength': 500,
            "placeholder": "Describe what this KPI measures...",
        }
    ),
    "frequency": forms.Select(attrs={"class": TAILWIND_INPUT}),
    "direction": forms.Select(attrs={"class": TAILWIND_INPUT}),
    "display_format": forms.Select(attrs={"class": TAILWIND_INPUT}),
    "unit": forms.TextInput(
        attrs={"class": TAILWIND_INPUT, "placeholder": "e.g. ' days', '×', '₱'"}
    ),
    "target_min": forms.NumberInput(attrs={"class": TAILWIND_INPUT, "step": "0.01"}),
    "target_max": forms.NumberInput(attrs={"class": TAILWIND_INPUT, "step": "0.01"}),
    "target_display": forms.TextInput(
        attrs={"class": TAILWIND_INPUT, "placeholder": "e.g. ≥95%"}
    ),
    # Written by the builder, not typed — the visible control is the canvas.
    "expression": forms.HiddenInput(),
}

_SHARED_LABELS = {
    "target_min": "Minimum Target",
    "target_max": "Maximum Target",
    "target_display": "Target Display",
    "display_format": "Display Format",
    "unit": "Unit Suffix",
    "expression": "Formula",
}


class BaseKpiForm(forms.ModelForm):
    """Everything create and edit agree on: the widgets, the team-scoped
    category picker, and the rule that a target is always a band."""

    @property
    def aggregation_choices(self):
        """`Aggregation.choices` as JSON, for the builder's per-input picker.

        Emitted onto the fieldset rather than written out in `formula_builder.js`
        for the same reason `data-all-team-roles` is: the model stays the one
        place that decides what the options are, so adding one cannot leave the
        form offering a stale list. Same shape the template already uses for a
        `<select>`: `[[value, label], ...]`.
        """
        return json.dumps(list(Aggregation.choices))

    # Categories are per-team rows (§4) and the table starts empty, so the
    # dropdown alone would be unusable. This names a new one; it stays hidden
    # until the dropdown's "Create new category" option is chosen.
    category = CategoryChoiceField(
        queryset=KpiCategory.objects.none(),
        required=False,
        empty_label="No category",
        widget=CategorySelect(attrs={"class": TAILWIND_INPUT}),
    )
    new_category = forms.CharField(
        required=False,
        max_length=80,
        label="New category name",
        widget=forms.TextInput(
            attrs={"class": TAILWIND_INPUT, "placeholder": "e.g. Client Impact"}
        ),
    )

    # The formula builder's operands, serialised by static/js/formula_builder.js
    # as a list of {key, label} in canvas order. They travel WITH the expression
    # — a formula whose operands aren't stored has no CSV columns (§6).
    inputs_json = forms.CharField(
        required=False, widget=forms.HiddenInput(), label="Inputs"
    )

    def __init__(self, *args, team=None, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        if team is None and self.instance.pk:
            team = self.instance.team
        # A branch KPI belongs to the branch it was authored on. Falling back to
        # the instance matters on edit: the branch is not a form field, so
        # without this a saved KPI would quietly become team-level.
        if branch is None and self.instance.pk:
            branch = self.instance.branch
        self.team = team
        self.branch = branch

        # Without this scoping an Operations manager could file a KPI under an
        # HR category.
        self.fields["category"].queryset = KpiCategory.objects.filter(team=self.team)
        self.fields["name"].required = True

    def wants_new_category(self):
        """True when the dropdown is on "Create new category".

        Also true when a failed POST comes back with the box filled, so the
        re-rendered form keeps the sentinel selected and the CSS keeps the box
        open rather than swallowing what the manager typed.
        """
        if not self.is_bound:
            return False
        return bool(
            self.data.get(self.add_prefix("category")) == CategorySelect.NEW
            or (self.data.get(self.add_prefix("new_category")) or "").strip()
        )

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not slugify(name):
            raise forms.ValidationError(
                "Give the KPI a name with at least one letter or number."
            )
        return name

    def clean(self):
        cleaned = super().clean()

        # "Create new category" with nothing typed would silently file the KPI
        # as uncategorised, so it is an error rather than a shrug.
        if (
            self.data.get(self.add_prefix("category")) == CategorySelect.NEW
            and not (cleaned.get("new_category") or "").strip()
        ):
            self.add_error("new_category", "Name the new category, or pick an existing one.")

        inputs = cleaned.get("inputs_json") or []
        expression = (cleaned.get("expression") or "").strip()

        # An expression on its own is not a KPI: without inputs there are no
        # CSV columns, no form fields and nothing to store in kpi_record_input.
        if expression and not inputs:
            self.add_error(
                "expression",
                "Add at least one input. The inputs are what the formula is "
                "calculated from and what the CSV template's columns become.",
            )
        elif expression:
            try:
                cleaned["expression"] = self.instance.expression = (
                    formula_engine.validate(
                        expression, [item["key"] for item in inputs]
                    )
                )
            except formula_engine.FormulaError as error:
                self.add_error("expression", str(error))

        # Targets are always bands; a single figure is a band of width zero
        # (design principle 4), so filling only one side means both.
        minimum, maximum = cleaned.get("target_min"), cleaned.get("target_max")
        if minimum is None and maximum is not None:
            cleaned["target_min"] = self.instance.target_min = maximum
        elif maximum is None and minimum is not None:
            cleaned["target_max"] = self.instance.target_max = minimum
        elif minimum is not None and maximum is not None and minimum > maximum:
            self.add_error(
                "target_max", "The maximum target must be at least the minimum."
            )

        return cleaned

    def _apply_category(self, kpi):
        """A category typed into the free-text box wins over the dropdown."""
        typed = (self.cleaned_data.get("new_category") or "").strip()
        if typed:
            kpi.category, _ = KpiCategory.objects.get_or_create(
                team=self.team, name=typed
            )

    def clean_inputs_json(self):
        """Turn the builder's JSON into a checked list of operand dicts."""
        raw = (self.cleaned_data.get("inputs_json") or "").strip()
        if not raw:
            return []

        try:
            parsed = json.loads(raw)
        except ValueError:
            raise forms.ValidationError("The formula inputs could not be read.")

        if not isinstance(parsed, list):
            raise forms.ValidationError("The formula inputs could not be read.")

        inputs, seen = [], set()
        for position, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                raise forms.ValidationError("The formula inputs could not be read.")

            key = str(item.get("key", "")).strip()
            label = str(item.get("label", "")).strip() or key.replace("_", " ").title()

            # `key` is the expression variable, the CSV header and the form
            # field name at once, so it has to be a valid identifier (§6).
            KEY_VALIDATOR(key)

            if key in seen:
                raise forms.ValidationError(f'"{key}" is used by more than one input.')
            seen.add(key)

            data_type = (
                item.get("data_type")
                if item.get("data_type") in DataType.values
                else DataType.NUMBER
            )
            inputs.append(
                {
                    "key": key,
                    "label": label[:120],
                    "placeholder": str(item.get("placeholder", ""))[:60],
                    "data_type": data_type,
                    "aggregation": (
                        item.get("aggregation")
                        if item.get("aggregation") in Aggregation.values
                        else None  # filled in by _default_aggregations()
                    ),
                    "position": position,
                }
            )

        return inputs

    def _default_aggregations(self, inputs, expression):
        """Fill in any operand the builder did not choose an aggregation for.

        The setting decides whether a second entry against a period ADDS to it
        or replaces it, so leaving it unset is not an option — there is no
        neutral answer. The formula gives most of it away: an operand under a
        `/` is a denominator, and adding three uploads of "average headcount"
        together gives a population nobody has. Dates cannot be summed at all.
        Everything else is an additive event.

        A default, not a rule: a numerator can be a snapshot too, and the picker
        on this form is where that gets said.
        """
        try:
            denominators = formula_engine.divisors(expression or "")
        except formula_engine.FormulaError:
            # The expression is validated separately and will report itself.
            # Additive is the safer guess meanwhile: a wrong total is visible on
            # the dashboard, a silent replace is not.
            denominators = set()

        for item in inputs:
            if item.get("aggregation"):
                continue
            item["aggregation"] = (
                Aggregation.LAST
                if item["data_type"] == DataType.DATE or item["key"] in denominators
                else Aggregation.SUM
            )
        return inputs

    def _sync_inputs(self, kpi, inputs):
        """Make `kpi_input` match the builder exactly: add, update, remove.

        Removal is why this is not just delete-and-recreate: `KpiRecordInput`
        protects the inputs it points at, so an operand that already has data
        behind it cannot be dropped. `clean()` catches that first, with a
        message; this is the write.
        """
        existing = {row.key: row for row in kpi.inputs.all()}
        wanted = {item["key"] for item in inputs}

        for key, row in existing.items():
            if key not in wanted:
                row.delete()

        for item in inputs:
            row = existing.get(item["key"])
            if row is None:
                KpiInput.objects.create(kpi=kpi, **item)
                continue
            row.label = item["label"]
            row.placeholder = item["placeholder"]
            row.data_type = item["data_type"]
            row.aggregation = item["aggregation"]
            row.position = item["position"]
            row.save(update_fields=[
                "label", "placeholder", "data_type", "aggregation", "position"
            ])


class CreateKpiForm(BaseKpiForm):
    """Create one KPI, its inputs, and its first formula-history row."""

    class Meta:
        model = KpiDefinition
        fields = _SHARED_FIELDS
        widgets = _SHARED_WIDGETS
        labels = _SHARED_LABELS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expression"].required = True

    def _unique_slug(self, name):
        """A stable slug that does not collide within this team.

        The CSV template binds to the slug, so it is generated once and then
        left alone. `(team, branch, slug)` is unique with `nulls_distinct=False`,
        which without this would surface as a 500 the second time anyone reuses
        a KPI name.
        """
        base = slugify(name)[:110] or "kpi"
        candidate, counter = base, 2
        existing = KpiDefinition.objects.filter(team=self.team, branch=self.branch)
        while existing.filter(slug=candidate).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    # Always commits: a KPI without its `kpi_input` rows and its first
    # formula-history row is not a valid KPI, so they are written together.
    @transaction.atomic
    def save(self, user=None):
        kpi = super().save(commit=False)

        kpi.team = self.team
        kpi.branch = self.branch
        kpi.slug = self._unique_slug(kpi.name)
        kpi.created_by = user if user and user.is_authenticated else None
        kpi.template_version = 1

        inputs = self._default_aggregations(
            self.cleaned_data.get("inputs_json") or [], kpi.expression
        )
        labels = {item["key"]: item["label"] for item in inputs}

        # Rendered, never typed, so the sentence on the Definitions screen can
        # never disagree with the maths (§5).
        kpi.formula_text = formula_engine.render_text(kpi.expression, labels)[:255]

        self._apply_category(kpi)
        kpi.save()

        KpiInput.objects.bulk_create(
            KpiInput(
                kpi=kpi,
                key=item["key"],
                label=item["label"],
                placeholder=item["placeholder"],
                data_type=item["data_type"],
                aggregation=item["aggregation"],
                position=item["position"],
            )
            for item in inputs
        )

        # The formula this KPI shipped with, so the first period is as
        # explainable as every later one (§12, §E.3).
        KpiFormulaHistory.objects.create(
            kpi=kpi,
            expression=kpi.expression,
            score_expression=kpi.score_expression,
            formula_text=kpi.formula_text,
            template_version=kpi.template_version,
            effective_from=kpi.created_at.date(),
            reason="Initial formula",
            changed_by=kpi.created_by,
        )

        return kpi


class EditKpiForm(BaseKpiForm):
    """Edit an existing KPI — including its formula.

    The formula builder is here too, because a manager who can author a formula
    can also get one wrong. What editing cannot change is the `slug`: a
    downloaded CSV binds to it, so renaming the KPI is fine but its address is
    stable.

    Changing the formula (or the input set) is not a quiet edit. Per §A.6 it:
      * bumps `template_version`, so a CSV filled against the old columns is
        rejected rather than silently misread,
      * appends a `KpiFormulaHistory` row, so "which formula produced July?"
        stays answerable,
      * and audits as `formula_changed`, not `updated`.
    Renaming an operand's *label* is cosmetic and does none of that.
    """

    # §11/§12: "FY27 goal reset" — why the goalposts (or the maths) moved.
    change_reason = forms.CharField(
        required=False,
        max_length=255,
        label="Reason for the change",
        widget=forms.TextInput(
            attrs={"class": TAILWIND_INPUT, "placeholder": "e.g. FY27 goal reset"}
        ),
    )

    # What the audit entry and the history checks compare against.
    TRACKED = [*_SHARED_FIELDS]

    class Meta:
        model = KpiDefinition
        fields = _SHARED_FIELDS
        widgets = _SHARED_WIDGETS
        labels = _SHARED_LABELS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Snapshot before anything is bound onto the instance, so `save()` can
        # tell what actually changed.
        self._original = {field: self._display(field) for field in self.TRACKED}
        self._original_keys = [row.key for row in self.instance.inputs.all()]
        self._original_inputs = [
            f"{row.key} ({row.label})" for row in self.instance.inputs.all()
        ]

        # Feed the builder this KPI's own operands so it opens on the real
        # formula rather than an empty canvas.
        # `aggregation` rides along so re-saving an untouched formula does not
        # quietly reset every operand to the derived default. The builder is
        # what the form believes, so anything it does not send is lost.
        self.fields["inputs_json"].initial = json.dumps(
            [
                {
                    "key": row.key,
                    "label": row.label,
                    "data_type": row.data_type,
                    "aggregation": row.aggregation,
                }
                for row in self.instance.inputs.all()
            ]
        )

    @property
    def formula_changed(self):
        """True when the maths changed — not when only a label was reworded.

        §A.6: an edit to the expression, or to the input SET (adding, removing,
        renaming or reordering a key), bumps the template version. Cosmetic
        edits do not.
        """
        keys = [item["key"] for item in (self.cleaned_data.get("inputs_json") or [])]
        return (
            self._original["expression"] != self._display("expression")
            or keys != self._original_keys
        )

    @property
    def _submitted_inputs(self):
        return [
            f"{item['key']} ({item['label']})"
            for item in (self.cleaned_data.get("inputs_json") or [])
        ]

    @property
    def inputs_changed(self):
        """True for ANY input edit, a reworded label included.

        Distinct from `formula_changed`: a relabel is cosmetic — it does not
        bump the template version — but it does rewrite `formula_text`, so it
        is still a change and should not be reported as "nothing happened".
        """
        return self._submitted_inputs != self._original_inputs

    def clean(self):
        cleaned = super().clean()

        # An operand that already has recorded values behind it cannot be
        # dropped — `KpiRecordInput` and `KpiEntryInput` both protect it. Better
        # a clear message here than a ProtectedError from the middle of save().
        # BOTH have to be asked: an entry whose period was later emptied still
        # holds its operands, so the record side alone would miss it and the
        # save would die halfway through.
        keys = {item["key"] for item in (cleaned.get("inputs_json") or [])}
        blocked = [
            row.key
            for row in self.instance.inputs.all()
            if row.key not in keys
            and (row.record_values.exists() or row.entry_values.exists())
        ]
        if blocked:
            self.add_error(
                "inputs_json",
                "These inputs already have recorded data and cannot be removed: "
                + ", ".join(blocked)
                + ". Delete the KPI and create a new one instead.",
            )

        return cleaned

    def _display(self, field):
        """One comparable, readable string per tracked field.

        Decimals are normalised first: the database hands back
        `Decimal('3.5000')` where the form cleans `Decimal('3.5')`, and a naive
        `str()` comparison would call that a change — writing a spurious
        `KpiTargetHistory` row every time someone edited a description.
        """
        if field == "category":
            return self.instance.category.name if self.instance.category_id else None

        value = getattr(self.instance, field, None)
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value.normalize(), "f")
        return str(value)

    @property
    def targets_changed(self):
        return any(
            self._original[field] != self._display(field)
            for field in ("target_min", "target_max", "target_display")
        )

    @transaction.atomic
    def save(self, user=None):
        actor = user if user and user.is_authenticated else None
        reason = (self.cleaned_data.get("change_reason") or "").strip()
        today = timezone.localdate()

        # Read both BEFORE the instance is written, while `_original` still has
        # something to compare against.
        targets_changed = self.targets_changed
        formula_changed = self.formula_changed
        inputs_changed = self.inputs_changed
        submitted_inputs = self._submitted_inputs

        kpi = super().save(commit=False)
        inputs = self._default_aggregations(
            self.cleaned_data.get("inputs_json") or [], kpi.expression
        )
        labels = {item["key"]: item["label"] for item in inputs}

        # Regenerated on every save — a reworded operand label changes the
        # sentence even when the maths is untouched (§5).
        kpi.formula_text = formula_engine.render_text(kpi.expression, labels)[:255]

        if formula_changed:
            # A stale CSV must be rejected rather than misread (§A.6 rule 3).
            kpi.template_version += 1

        self._apply_category(kpi)
        kpi.save()
        self._sync_inputs(kpi, inputs)

        self.changes = {
            field: {"from": self._original[field], "to": self._display(field)}
            for field in self.TRACKED
            if self._original[field] != self._display(field)
        }
        if inputs_changed:
            self.changes["inputs"] = {
                "from": self._original_inputs,
                "to": submitted_inputs,
            }

        # A target change rewrites how every past period reads, so it is
        # recorded rather than silently applied (§11).
        if targets_changed:
            KpiTargetHistory.objects.create(
                kpi=kpi,
                target_min=kpi.target_min,
                target_max=kpi.target_max,
                target_display=kpi.target_display,
                effective_from=today,
                reason=reason,
                changed_by=actor,
            )

        # A formula change redefines the number itself, so the same operands
        # can mean something different afterwards (§12). Each row records the
        # formula in force FROM its `effective_from` — the previous formula is
        # preserved as the earlier row, which is also how target history reads.
        if formula_changed:
            KpiFormulaHistory.objects.create(
                kpi=kpi,
                expression=kpi.expression,
                score_expression=kpi.score_expression,
                formula_text=kpi.formula_text,
                template_version=kpi.template_version,
                effective_from=today,
                reason=reason,
                changed_by=actor,
            )

        return kpi


# ---------------------------------------------------------------------------
# Import Data screen
# ---------------------------------------------------------------------------


class KpiChoiceField(forms.ModelChoiceField):
    """A KPI dropdown labelled by name alone.

    `KpiDefinition.__str__` is "<team> · <name>", so the default label reaches
    through `obj.team` for every option and the Add-Record dropdown cost one
    `core_team` SELECT per KPI. Exactly the trap `CategoryChoiceField` below
    documents, on a different picker.

    It reads better too: the queryset is already scoped to one team, so naming
    that team on every row of its own dropdown says nothing.
    """

    def label_from_instance(self, obj):
        return obj.name


class AddRecordForm(forms.Form):
    """Manual entry of one actual, from the Add Performance Record modal.

    The operand fields cannot be declared up front: they are whatever the
    chosen KPI's `kpi_input` rows say they are. So the template renders one
    field group per KPI (all but the selected one disabled, so only one set is
    ever submitted) and `clean()` reads them by key.

    **It asks for a DATE, not a reporting period**, and that is the whole change
    in how figures are entered. The date is what the person knows: "these are
    today's numbers". Which period it belongs to follows from the KPI's cadence,
    so the form derives it and shows it back rather than asking someone to write
    `2026-Q3` correctly. It also means the field's meaning no longer changes
    shape when the KPI dropdown changes — only the period it resolves to does.

    Adding a figure to a period that already has one ADDS to it. There is no
    overwrite here and no "this period already exists" refusal: reporting twice
    in a month is the normal case, not a mistake to be caught.
    """

    INPUT_PREFIX = "input__"

    kpi = KpiChoiceField(
        queryset=KpiDefinition.objects.none(),
        empty_label="Select KPI…",
        widget=forms.Select(attrs={"class": TAILWIND_INPUT, "data-record-kpi": True}),
    )
    entry_date = forms.DateField(
        label="Date",
        widget=forms.DateInput(
            attrs={"class": TAILWIND_INPUT, "type": "date", "data-record-date": True},
            format="%Y-%m-%d",
        ),
        help_text="The date these figures are for.",
    )
    remarks = forms.CharField(
        required=False,
        # Server-side limit AND a browser `maxlength`, from the one constant the
        # model and the importer also read. The attribute is set explicitly
        # rather than left to Django, so the cap is visible in this file.
        max_length=REMARKS_MAX_LENGTH,
        widget=forms.Textarea(
            attrs={
                "class": TAILWIND_INPUT,
                "rows": 3,
                "maxlength": REMARKS_MAX_LENGTH,
                "placeholder": "Add any context for this record…",
            }
        ),
        help_text=f"Optional. Up to {REMARKS_MAX_LENGTH} characters.",
    )

    def __init__(self, *args, team=None, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.team = team
        self.branch = branch
        self.fields["kpi"].queryset = (
            KpiDefinition.objects.filter(team=team, branch=branch, is_active=True)
            .prefetch_related("inputs")
            .order_by("sort_order", "name")
        )
        # Today, in Manila. `timezone.localdate()` and not `date.today()`: the
        # server runs on UTC and for eight hours a day those are different days,
        # which would default the figure into yesterday.
        self.fields["entry_date"].initial = timezone.localdate()

    def clean(self):
        cleaned = super().clean()
        kpi = cleaned.get("kpi")
        entry_date = cleaned.get("entry_date")
        if not kpi or not entry_date:
            return cleaned

        # The cadence turns the date into a period. Nothing to validate: every
        # date falls in exactly one period at every cadence, which is precisely
        # why the form asks for a date instead of asking someone to spell
        # "2026-Q3".
        cleaned["period_start"], _ = periods.parse(
            periods.label(entry_date, kpi.frequency), kpi.frequency
        )

        values = {}
        for row in kpi.inputs.all():
            raw = self.data.get(f"{self.INPUT_PREFIX}{row.key}")
            try:
                values[row.key] = records.coerce(raw, row)
            except records.RecordError as error:
                self.add_error(None, str(error))
        cleaned["values"] = values

        if not self.errors:
            # Catch a division by zero here rather than at save time, so it
            # lands on the form instead of as a 500.
            try:
                records.evaluate(kpi, values)
            except records.RecordError as error:
                self.add_error(None, str(error))

        return cleaned

    def save(self, user=None):
        """Add one entry. Returns `(entry, record)` — the record is the period.

        The period is re-derived inside `add_entry`, so what comes back is the
        accumulated figure and not just what was typed. That is what the flash
        message should report: "August is now 45 hires", not "you added 5".
        """
        return records.add_entry(
            self.cleaned_data["kpi"],
            self.cleaned_data["entry_date"],
            self.cleaned_data["values"],
            source=KpiRecord.Source.MANUAL,
            user=user,
            remarks=self.cleaned_data.get("remarks", ""),
        )


class EditRecordForm(forms.Form):
    """Correcting one ENTRY: its date, its raw operands and its remarks.

    It edits a submission, not a period. A period's figure is derived from every
    entry inside it, so there is nothing there to edit directly — correcting the
    month means correcting the entry that got it wrong, and `rebuild_period()`
    re-collapses the rest around it.

    **The date IS editable, and that is new.** It used to be the record's
    identity, so a figure filed against the wrong month could only be deleted
    and re-entered. An entry's date is just a fact about that entry now, so
    moving it is a correction like any other: `save()` rebuilds the period it
    left as well as the one it arrives in, which is what stops the old month
    keeping a figure that is no longer in it.

    The KPI is still fixed. Moving an entry between KPIs would mean its operands
    landing in inputs of a different formula, which is a re-entry wearing a
    correction's clothes.

    Unlike `AddRecordForm`, the operand fields are declared for real, because
    there is exactly one KPI in play. Each form is prefixed with its entry's
    pk: the screen renders one modal per row and every field name would
    otherwise repeat down the page.
    """

    INPUT_PREFIX = "input__"

    entry_date = forms.DateField(
        label="Date",
        widget=forms.DateInput(
            attrs={"class": TAILWIND_INPUT, "type": "date"}, format="%Y-%m-%d"
        ),
        help_text="The date these figures are for.",
    )
    remarks = forms.CharField(
        required=False,
        max_length=REMARKS_MAX_LENGTH,
        widget=forms.Textarea(
            attrs={
                "class": TAILWIND_INPUT,
                "rows": 3,
                "maxlength": REMARKS_MAX_LENGTH,
                "placeholder": "Add any context for this record…",
            }
        ),
        help_text=f"Optional. Up to {REMARKS_MAX_LENGTH} characters.",
    )
    change_reason = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": TAILWIND_INPUT,
                "placeholder": "e.g. Corrected the headcount figure",
            }
        ),
        help_text="Optional. Shown on the activity log entry for this edit.",
    )

    def __init__(self, *args, entry=None, **kwargs):
        # The prefix is derived, not passed, so a caller cannot accidentally
        # bind one entry's POST data to another entry's form.
        kwargs.setdefault("prefix", self.prefix_for(entry))
        super().__init__(*args, **kwargs)
        self.entry = entry
        self.kpi = entry.kpi

        stored = {value.input_id: value for value in entry.input_values.all()}
        for row in self.kpi.inputs.all():
            self.fields[f"{self.INPUT_PREFIX}{row.key}"] = self._input_field(
                row, stored.get(row.pk)
            )

        self.fields["entry_date"].initial = entry.entry_date
        self.fields["remarks"].initial = entry.remarks

    @staticmethod
    def prefix_for(entry):
        return f"entry{entry.pk}"

    @property
    def operand_fields(self):
        """The operand fields in CSV column order, for the template to loop.

        Declared fields come first on a Django form and these are added in
        `__init__`, so iterating the form itself would put Remarks above the
        figures it is a remark about.
        """
        return [
            self[f"{self.INPUT_PREFIX}{row.key}"] for row in self.kpi.inputs.all()
        ]

    def _input_field(self, row, stored):
        """One operand field, pre-filled with what is currently stored.

        `required=False` here on purpose: emptiness is `records.coerce()`'s
        question, not the widget's, so a blank cell gets the KPI's own message
        ("Total exits is required") rather than the browser's generic one, and
        an optional input still counts as 0.
        """
        attrs = {"class": TAILWIND_INPUT}
        if row.data_type == DataType.DATE:
            attrs["type"] = "date"
            initial = stored.value_date if stored else None
            widget = forms.DateInput(attrs=attrs, format="%Y-%m-%d")
        else:
            attrs["inputmode"] = "decimal"
            attrs["placeholder"] = row.placeholder
            initial = self._number(stored.value_number) if stored else None
            widget = forms.TextInput(attrs=attrs)

        return forms.CharField(
            label=row.label,
            required=False,
            initial=initial,
            widget=widget,
            help_text=row.help_text,
        )

    @staticmethod
    def _number(value):
        """A stored Decimal as a person typed it: `12`, not `12.0000`."""
        if value is None:
            return None
        return format(value.normalize(), "f")

    def clean(self):
        cleaned = super().clean()

        values = {}
        for row in self.kpi.inputs.all():
            field = f"{self.INPUT_PREFIX}{row.key}"
            try:
                values[row.key] = records.coerce(cleaned.get(field), row)
            except records.RecordError as error:
                self.add_error(field, str(error))
        cleaned["values"] = values

        if not self.errors:
            # Same reason as `AddRecordForm`: a division by zero belongs on the
            # form, not in a 500 at save time.
            try:
                records.evaluate(self.kpi, values)
            except records.RecordError as error:
                self.add_error(None, str(error))

        return cleaned

    @transaction.atomic
    def save(self, user=None):
        """Rewrite the entry, then re-derive every period it touches.

        The source becomes MANUAL and the entry stops pointing at the import
        batch, because after this the figure is no longer what the file said.
        That also keeps "delete this import" honest: it removes the entries the
        upload is still the source of, and this one no longer is.

        Two periods can need rebuilding, not one. If the date moved across a
        month boundary the period it LEFT has to be re-collapsed too, or it goes
        on showing a total that includes a figure no longer filed against it.
        """
        entry = self.entry
        was = entry.period_start
        values = self.cleaned_data["values"]

        entry.entry_date = self.cleaned_data["entry_date"]
        entry.period_start, entry.period_end = records._period_of(
            self.kpi, entry.entry_date
        )
        entry.value = Decimal(str(round(records.evaluate(self.kpi, values), 4)))
        entry.value_display = records.format_value(self.kpi, float(entry.value))
        entry.source = KpiRecord.Source.MANUAL
        entry.import_batch = None
        entry.remarks = self.cleaned_data.get("remarks", "")
        entry.entered_by = user if user and user.is_authenticated else None
        entry.save()

        # Replace rather than merge, same rule as the first write: the operand
        # set is whatever this edit says it is.
        entry.input_values.all().delete()
        KpiEntryInput.objects.bulk_create(
            KpiEntryInput(
                entry=entry,
                input=row,
                value_number=None if isinstance(values.get(row.key), dt.date) else values.get(row.key),
                value_date=values.get(row.key) if isinstance(values.get(row.key), dt.date) else None,
            )
            for row in self.kpi.inputs.all()
            if values.get(row.key) is not None
        )

        if was != entry.period_start:
            records.rebuild_period(self.kpi, was)
        return records.rebuild_period(self.kpi, entry.period_start)


class ImportRecordsForm(forms.Form):
    """Upload one filled-in CSV template.

    Deliberately thin: the file identifies its own KPI from the header the
    template generated, so there is nothing else to ask for.
    """

    file = forms.FileField(
        label="Template file",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".xlsx,.csv,text/csv",
                "class": "sr-only",
                "data-import-file": True,
            }
        ),
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > importer.MAX_BYTES:
            raise forms.ValidationError("That file is larger than 5 MB.")
        # .xlsx is the team workbook (a sheet per KPI); .csv is the older
        # per-KPI template. The view picks the reader off the extension.
        if not upload.name.lower().endswith((".csv", ".xlsx")):
            raise forms.ValidationError(
                "Upload the .xlsx workbook or a .csv template. If you have an "
                'older .xls file, open it in Excel and "Save As" .xlsx.'
            )
        return upload
