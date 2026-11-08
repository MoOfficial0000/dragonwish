from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.forms import BaseInlineFormSet

from .models import ActivationBall, Dragon, DragonBall, DragonSpecial, ExtraRequirement, Relic, RewardBall, WishSettings


class UniqueEntriesFormSet(BaseInlineFormSet):
    """
    Inline entries pointing to a countryball (or special): no duplicates, with an optional minimum.
    """

    target = "ball"
    minimum = 0
    minimum_message = ""

    def clean(self):
        super().clean()
        seen: set[int] = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            entry = form.cleaned_data.get(self.target)
            if entry is None:
                continue
            if entry.pk in seen:
                raise ValidationError(f"{entry} is listed more than once.")
            seen.add(entry.pk)
        if len(seen) < self.minimum:
            raise ValidationError(self.minimum_message)
        self.clean_entries(form_data=[x.cleaned_data for x in self.forms if self._is_kept(x)])

    @staticmethod
    def _is_kept(form) -> bool:
        return hasattr(form, "cleaned_data") and not form.cleaned_data.get("DELETE") and bool(form.cleaned_data)

    def clean_entries(self, form_data: list[dict]):
        pass


class ActivationBallFormSet(UniqueEntriesFormSet):
    minimum = 1
    minimum_message = "A wish needs at least one activation countryball."


class DragonBallFormSet(UniqueEntriesFormSet):
    minimum = 1
    minimum_message = "A wish needs at least one dragon ball."

    def clean_entries(self, form_data: list[dict]):
        total = len([x for x in form_data if x.get("ball")])
        required = self.instance.required_count
        if required and required > total:
            raise ValidationError(
                f"The wish requires {required} different dragon balls but only {total} are listed. "
                "Add more dragon balls or lower the required amount."
            )


class RewardBallFormSet(UniqueEntriesFormSet):
    pass


class SpecialChanceFormSet(UniqueEntriesFormSet):
    target = "special"

    def clean_entries(self, form_data: list[dict]):
        total = sum(x.get("chance") or 0 for x in form_data if x.get("special"))
        if total > 100:
            raise ValidationError(f"The chances add up to {total:g}%, they cannot exceed 100%.")


class ActivationBallInline(admin.TabularInline):
    model = ActivationBall
    formset = ActivationBallFormSet
    extra = 1
    fields = ("position", "ball", "emoji_id")
    autocomplete_fields = ("ball",)
    verbose_name = "activation countryball"
    verbose_name_plural = "activation countryballs (any one of them activates the wish)"


class ExtraRequirementFormSet(UniqueEntriesFormSet):
    # every part of the wish screen is a few components and Discord limits a message to 40 of them
    maximum = 4

    def clean_entries(self, form_data: list[dict]):
        total = len([x for x in form_data if x.get("ball")])
        if total > self.maximum:
            raise ValidationError(f"A wish supports at most {self.maximum} extra required countryballs, not {total}.")


class ExtraRequirementInline(admin.TabularInline):
    model = ExtraRequirement
    formset = ExtraRequirementFormSet
    extra = 0
    fields = ("position", "name", "ball", "consumed", "emoji_id")
    autocomplete_fields = ("ball",)
    verbose_name = "extra required countryball"
    verbose_name_plural = (
        "extra required countryballs (each one is required next to the activation countryball and the dragon balls)"
    )


class DragonBallInline(admin.TabularInline):
    model = DragonBall
    formset = DragonBallFormSet
    extra = 1
    fields = ("position", "ball", "emoji_id")
    autocomplete_fields = ("ball",)
    verbose_name = "dragon ball"
    verbose_name_plural = "dragon balls (the wish needs the amount set in 'Required count', all of them if empty)"


class RewardBallInline(admin.TabularInline):
    model = RewardBall
    formset = RewardBallFormSet
    extra = 0
    fields = ("ball", "weight")
    autocomplete_fields = ("ball",)
    verbose_name = "reward countryball"
    verbose_name_plural = "reward countryballs (leave empty to reward any enabled countryball)"


class DragonSpecialInline(admin.TabularInline):
    model = DragonSpecial
    formset = SpecialChanceFormSet
    extra = 0
    fields = ("position", "special", "chance", "emoji_id")
    autocomplete_fields = ("special",)
    verbose_name = "special chance"
    verbose_name_plural = "special chances (each rewarded character may get one of these specials)"


@admin.register(Dragon)
class DragonAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "set_name",
        "activation_count",
        "ball_count",
        "required_count",
        "reward_count",
        "relic_count",
        "position",
        "enabled",
    )
    list_editable = ("position", "enabled")
    list_filter = ("enabled",)
    search_fields = ("name", "set_name")
    inlines = (ActivationBallInline, ExtraRequirementInline, DragonBallInline, RewardBallInline, DragonSpecialInline)
    fieldsets = (
        (None, {"fields": ("name", "enabled", "position")}),
        ("Display", {"fields": ("emoji_id", "set_name", "set_emoji_id")}),
        ("Requirements", {"fields": ("required_count",)}),
        ("Rewards", {"fields": ("reward_count", "relic_count")}),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _activation_count=Count("activation_balls", distinct=True),
                _ball_count=Count("dragon_balls", distinct=True),
            )
        )

    @admin.display(description="Activation countryballs", ordering="_activation_count")
    def activation_count(self, obj: Dragon) -> int:
        return obj._activation_count  # type: ignore

    @admin.display(description="Dragon balls", ordering="_ball_count")
    def ball_count(self, obj: Dragon) -> int:
        return obj._ball_count  # type: ignore


@admin.register(Relic)
class RelicAdmin(admin.ModelAdmin):
    list_display = ("__str__", "ball_id")
    list_select_related = ("ball",)
    search_fields = ("ball__country",)
    autocomplete_fields = ("ball",)


@admin.register(WishSettings)
class WishSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "dragon_name", "dragon_ball_name_plural", "relic_name_plural", "completion_layout")
    autocomplete_fields = ("relicborne_special", "craft_pool")
    fieldsets = (
        ("Dragons", {"fields": ("dragon_name", "dragon_name_plural", "dragon_ball_name", "dragon_ball_name_plural")}),
        ("Relics", {"fields": ("relic_name", "relic_name_plural", "relicborne_name", "relicborne_special")}),
        ("Messages", {"fields": ("reward_text", "wish_timeout_minutes")}),
        ("Completion command", {"fields": ("completion_layout",)}),
        ("Relic crafting", {"fields": ("craft_pool",)}),
    )

    def has_add_permission(self, request):
        # there is only one entry, it is created by the migration (or on first use)
        return not WishSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
