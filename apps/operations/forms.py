"""The Create-KPI form behind the Operations KPI Management modal.

Operations is the reference implementation: once this is right it gets lifted
into a shared place and reused by every other LOB, so the form deliberately
enforces the whole of `db_schema.txt` rather than just filling a table:

  * the FORMULA is validated by whitelisted AST walk (`apps.kpi.formula`),
  * the INPUTS come with it — they are the operands, the CSV columns and the
    form fields all at once (§6), so a KPI without them is unusable,
  * saving also writes the `KpiFormulaHistory` row the KPI shipped with (§E.3).

The audit entry is written by the view, which is the thing that holds the
request.
"""

import json

from django import forms
from django.db import transaction
from django.utils.text import slugify

from apps.kpi import formula as formula_engine
from apps.kpi.models import (
    KEY_VALIDATOR,
    DataType,
    KpiCategory,
    KpiDefinition,
    KpiFormulaHistory,
    KpiInput,
)


TAILWIND_INPUT = (
    "w-full rounded-lg border border-slate-300 px-3 py-2.5 "
    "text-sm focus:border-brand focus:outline-none "
    "focus:ring-2 focus:ring-brand/20"
)


class CreateKpiForm(forms.ModelForm):
    """Create one KPI, its inputs, and its first formula-history row."""

    # The formula builder's inputs, serialised by static/js/formula_builder.js.
    # A list of {key, label}, in canvas order.
    inputs_json = forms.CharField(
        required=False, widget=forms.HiddenInput(), label="Inputs"
    )

    # Categories are per-team rows (§4) and the table starts empty, so the
    # dropdown alone would be unusable. This lets a manager name a new one.
    new_category = forms.CharField(
        required=False,
        max_length=80,
        label="Or add a new category",
        widget=forms.TextInput(
            attrs={"class": TAILWIND_INPUT, "placeholder": "e.g. Client Impact"}
        ),
    )

    class Meta:
        model = KpiDefinition

        fields = [
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

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": TAILWIND_INPUT,
                    "placeholder": "e.g. Attrition Rate",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": TAILWIND_INPUT,
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": TAILWIND_INPUT,
                    "rows": 3,
                    "placeholder": "Describe what this KPI measures...",
                }
            ),
            "frequency": forms.Select(
                attrs={
                    "class": TAILWIND_INPUT,
                }
            ),
            "direction": forms.Select(
                attrs={
                    "class": TAILWIND_INPUT,
                }
            ),
            "display_format": forms.Select(
                attrs={
                    "class": TAILWIND_INPUT,
                }
            ),
            "unit": forms.TextInput(
                attrs={
                    "class": TAILWIND_INPUT,
                    "placeholder": "e.g. ' days', '×', '₱'",
                }
            ),
            "target_min": forms.NumberInput(
                attrs={
                    "class": TAILWIND_INPUT,
                    "step": "0.01",
                }
            ),
            "target_max": forms.NumberInput(
                attrs={
                    "class": TAILWIND_INPUT,
                    "step": "0.01",
                }
            ),
            "target_display": forms.TextInput(
                attrs={
                    "class": TAILWIND_INPUT,
                    "placeholder": "e.g. ≥95%",
                }
            ),
            "expression": forms.TextInput(
                attrs={
                    "class": TAILWIND_INPUT + " font-mono",
                    "placeholder": "e.g. total_exits / average_headcount * 100",
                }
            ),
        }

        labels = {
            "target_min": "Minimum Target",
            "target_max": "Maximum Target",
            "target_display": "Target Display",
            "display_format": "Display Format",
            "unit": "Unit Suffix",
            "expression": "Formula",
        }

    def __init__(self, *args, team=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.team = team

        # Categories belong to ONE team (§4) — without this scoping an
        # Operations manager could file a KPI under an HR category.
        self.fields["category"].queryset = KpiCategory.objects.filter(team=team)
        self.fields["category"].empty_label = "— No category —"
        self.fields["category"].required = False

        self.fields["name"].required = True
        self.fields["expression"].required = True

    # --- field-level ------------------------------------------------------

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

            inputs.append(
                {
                    "key": key,
                    "label": label[:120],
                    "placeholder": str(item.get("placeholder", ""))[:60],
                    "data_type": (
                        item.get("data_type")
                        if item.get("data_type") in DataType.values
                        else DataType.NUMBER
                    ),
                    "position": position,
                }
            )

        return inputs

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not slugify(name):
            raise forms.ValidationError(
                "Give the KPI a name with at least one letter or number."
            )
        return name

    # --- cross-field ------------------------------------------------------

    def clean(self):
        cleaned = super().clean()

        inputs = cleaned.get("inputs_json") or []
        expression = (cleaned.get("expression") or "").strip()

        # An expression on its own is not a KPI: without inputs there are no
        # CSV columns, no form fields and nothing to store in kpi_record_input.
        if expression and not inputs:
            self.add_error(
                "expression",
                "Add at least one input — the inputs are what the formula is "
                "calculated from and what the CSV template's columns become.",
            )
        elif expression:
            try:
                cleaned["expression"] = formula_engine.validate(
                    expression, [item["key"] for item in inputs]
                )
            except formula_engine.FormulaError as error:
                self.add_error("expression", str(error))

        # Targets are always bands; a single figure is a band of width zero
        # (§ design principle 4), so filling only one side means both.
        minimum, maximum = cleaned.get("target_min"), cleaned.get("target_max")
        if minimum is None and maximum is not None:
            cleaned["target_min"] = maximum
        elif maximum is None and minimum is not None:
            cleaned["target_max"] = minimum
        elif minimum is not None and maximum is not None and minimum > maximum:
            self.add_error(
                "target_max", "The maximum target must be at least the minimum."
            )

        return cleaned

    # --- persistence ------------------------------------------------------

    def _unique_slug(self, name):
        """A stable slug that does not collide within this team.

        The CSV template binds to the slug, so it is generated once and then
        left alone. `(team, branch, slug)` is unique with `nulls_distinct=False`,
        which without this would surface as a 500 the second time anyone reuses
        a KPI name.
        """
        base = slugify(name)[:110] or "kpi"
        candidate, counter = base, 2
        existing = KpiDefinition.objects.filter(team=self.team, branch=None)
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
        kpi.slug = self._unique_slug(kpi.name)
        kpi.created_by = user if user and user.is_authenticated else None
        kpi.template_version = 1

        inputs = self.cleaned_data.get("inputs_json") or []
        labels = {item["key"]: item["label"] for item in inputs}

        # Rendered, never typed, so the sentence on the Definitions screen can
        # never disagree with the maths (§5).
        kpi.formula_text = formula_engine.render_text(kpi.expression, labels)[:255]

        # A category typed into the free-text box wins over the dropdown.
        typed = (self.cleaned_data.get("new_category") or "").strip()
        if typed:
            kpi.category, _ = KpiCategory.objects.get_or_create(
                team=self.team, name=typed
            )

        kpi.save()

        KpiInput.objects.bulk_create(
            KpiInput(
                kpi=kpi,
                key=item["key"],
                label=item["label"],
                placeholder=item["placeholder"],
                data_type=item["data_type"],
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
