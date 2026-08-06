from django import forms

from apps.kpi.models import KpiDefinition


TAILWIND_INPUT = (
    "w-full rounded-lg border border-slate-300 px-3 py-2.5 "
    "text-sm focus:border-brand focus:outline-none "
    "focus:ring-2 focus:ring-brand/20"
)


class CreateKpiForm(forms.ModelForm):
    class Meta:
        model = KpiDefinition

        fields = [
            "name",
            "category",
            "description",
            "frequency",
            "direction",
            "display_format",
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
            "expression": "Formula",
        }