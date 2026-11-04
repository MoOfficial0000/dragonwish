from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.forms import BaseInlineFormSet

from .models import Dragon, DragonBall, Relic


class DragonBallFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen: set[int] = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            ball = form.cleaned_data.get("ball")
            if ball is None:
                continue
            if ball.pk == self.instance.ball_id:
                raise ValidationError("The dragon itself cannot also be one of its dragon balls.")
            if ball.pk in seen:
                raise ValidationError(f"{ball} is listed more than once.")
            seen.add(ball.pk)


class DragonBallInline(admin.TabularInline):
    model = DragonBall
    formset = DragonBallFormSet
    extra = 1
    fields = ("position", "ball", "emoji")
    autocomplete_fields = ("ball",)


@admin.register(Dragon)
class DragonAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "set_name",
        "ball_count",
        "reward_count",
        "relic_count",
        "shiny_chance",
        "mythical_chance",
        "position",
        "enabled",
    )
    list_editable = ("position", "enabled")
    list_filter = ("enabled",)
    list_select_related = ("ball",)
    search_fields = ("ball__country", "set_name")
    autocomplete_fields = ("ball",)
    inlines = (DragonBallInline,)
    fieldsets = (
        (None, {"fields": ("ball", "enabled", "position")}),
        ("Display", {"fields": ("emoji", "set_name", "set_emoji")}),
        ("Rewards", {"fields": ("reward_count", "relic_count", "shiny_chance", "mythical_chance")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_ball_count=Count("dragon_balls"))

    @admin.display(description="Dragon balls", ordering="_ball_count")
    def ball_count(self, obj: Dragon) -> int:
        return obj._ball_count  # type: ignore


@admin.register(Relic)
class RelicAdmin(admin.ModelAdmin):
    list_display = ("__str__", "ball_id")
    list_select_related = ("ball",)
    search_fields = ("ball__country",)
    autocomplete_fields = ("ball",)
