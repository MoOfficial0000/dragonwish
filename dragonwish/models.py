from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from bd_models.models import Ball


class Dragon(models.Model):
    """
    An activation dragon, the dragon balls it needs, and what a wish with it gives.
    """

    ball = models.OneToOneField(
        Ball,
        on_delete=models.CASCADE,
        related_name="wish_dragon",
        help_text="The countryball acting as the activation dragon. It is not consumed by the wish.",
    )
    emoji = models.CharField(
        max_length=100,
        blank=True,
        help_text="Emoji shown for the dragon, for example <:Shenron:1358300433441099948>. "
        "Leave empty to use the emoji of the countryball.",
    )
    set_name = models.CharField(
        max_length=64,
        blank=True,
        help_text="Title of this dragon ball set in the completion command, for example 'Earth Dragon Balls'. "
        "Leave empty to use '<dragon> Dragon Balls'.",
    )
    set_emoji = models.CharField(
        max_length=100,
        blank=True,
        help_text="Emoji of the whole set, shown in the wish title next to the dragon. "
        "Leave empty to use the emoji of the first dragon ball.",
    )
    reward_count = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)], help_text="How many random characters one wish gives."
    )
    relic_count = models.PositiveSmallIntegerField(default=0, help_text="How many random relics one wish gives.")
    shiny_chance = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Chance in percent that each rewarded character is a Shiny.",
    )
    mythical_chance = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Overall chance in percent that each rewarded character is a Mythical. "
        "Shiny is rolled first, so the shiny and mythical chances cannot add up to more than 100.",
    )
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower values are listed first.")
    enabled = models.BooleanField(default=True, help_text="Disabled dragons cannot be used to start a wish.")

    class Meta:
        ordering = ("position", "id")

    def __str__(self) -> str:
        return str(self.ball)

    def clean(self):
        if self.shiny_chance + self.mythical_chance > 100:
            raise ValidationError("The shiny and mythical chances cannot add up to more than 100%.")


class DragonBall(models.Model):
    """
    A countryball required to summon a dragon. They are consumed by the wish.
    """

    dragon = models.ForeignKey(Dragon, on_delete=models.CASCADE, related_name="dragon_balls")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="+")
    emoji = models.CharField(
        max_length=100,
        blank=True,
        help_text="Emoji shown for this dragon ball, for example <:DB1:1355509169565859929>. "
        "Leave empty to use the emoji of the countryball.",
    )
    position = models.PositiveSmallIntegerField(
        default=0, help_text="Order inside the set, the first dragon ball (1 star) should have the lowest value."
    )

    class Meta:
        ordering = ("position", "id")
        constraints = [models.UniqueConstraint(fields=("dragon", "ball"), name="dragonwish_unique_ball_per_dragon")]

    def __str__(self) -> str:
        return str(self.ball)


class Relic(models.Model):
    """
    A countryball that counts as a relic, for relic crafting and as a wish reward.
    """

    ball = models.OneToOneField(Ball, on_delete=models.CASCADE, related_name="wish_relic")

    class Meta:
        ordering = ("ball_id",)

    def __str__(self) -> str:
        return str(self.ball)
