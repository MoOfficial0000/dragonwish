from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from bd_models.models import Ball, Special


class WishSettings(models.Model):
    """
    Words and options shared by every wish. There is only one entry.
    """

    dragon_name = models.CharField(
        max_length=32,
        default="Dragon",
        help_text="The word for a dragon. The item that starts a wish is called 'Activation <this word>'.",
    )
    dragon_ball_name = models.CharField(max_length=32, default="Dragon Ball", help_text="The word for one dragon ball.")
    dragon_ball_name_plural = models.CharField(
        max_length=32, default="Dragon Balls", help_text="The word for several dragon balls."
    )
    relic_name = models.CharField(max_length=32, default="Relic", help_text="The word for one relic.")
    relic_name_plural = models.CharField(max_length=32, default="Relics", help_text="The word for several relics.")
    relicborne_name = models.CharField(
        max_length=32,
        default="Relicborne",
        help_text="The word for what relic crafting gives, as in 'a Relicborne character'.",
    )
    relicborne_special = models.ForeignKey(
        Special,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The special given to the character obtained by crafting relics. "
        "Its catch phrase is shown when crafting.",
    )
    craft_pool = models.ManyToManyField(
        Ball,
        blank=True,
        related_name="+",
        help_text="The only countryballs that relic crafting can give. Leave empty to allow any enabled countryball.",
    )

    class Meta:
        verbose_name = "wish settings"
        verbose_name_plural = "wish settings"

    def __str__(self) -> str:
        return "Wish settings"

    @classmethod
    async def aload(cls) -> "WishSettings":
        """
        Fetch the settings, creating them with the default words if they don't exist yet.
        """
        await cls.objects.aget_or_create(pk=1)
        return await cls.objects.select_related("relicborne_special").aget(pk=1)


class Dragon(models.Model):
    """
    A wish that can be made: the countryballs activating it, the dragon balls it needs, and what it gives.
    """

    name = models.CharField(
        max_length=64, unique=True, help_text="Name of this wish, shown when choosing it in `/wish start`."
    )
    emoji = models.CharField(
        max_length=100,
        blank=True,
        help_text="Emoji of the wish, shown in its title, for example <:Shenron:1358300433441099948>. "
        "Leave empty to use the emoji of the first activation countryball.",
    )
    set_name = models.CharField(
        max_length=64,
        blank=True,
        help_text="Title of this set in the completion command, for example 'Earth Dragon Balls'. "
        "Leave empty to use '<name> <dragon balls word>'.",
    )
    set_emoji = models.CharField(
        max_length=100,
        blank=True,
        help_text="Emoji of the whole set, shown in the wish title next to the dragon. "
        "Leave empty to use the emoji of the first dragon ball.",
    )
    required_count = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="How many different countryballs of the dragon balls list are needed, for example 4 for "
        "'any 4 of these 8'. Leave empty to require all of them.",
    )
    reward_count = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)], help_text="How many random characters one wish gives."
    )
    relic_count = models.PositiveSmallIntegerField(default=0, help_text="How many random relics one wish gives.")
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower values are listed first.")
    enabled = models.BooleanField(default=True, help_text="Disabled wishes cannot be started.")

    class Meta:
        ordering = ("position", "id")

    def __str__(self) -> str:
        return self.name


class ActivationBall(models.Model):
    """
    A countryball that can activate a wish. Only one of them is needed, and it is not consumed.
    """

    dragon = models.ForeignKey(Dragon, on_delete=models.CASCADE, related_name="activation_balls")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="+")
    emoji = models.CharField(
        max_length=100,
        blank=True,
        help_text="Emoji shown for this countryball. Leave empty to use the emoji of the countryball.",
    )
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower values are listed first.")

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("dragon", "ball"), name="dragonwish_unique_activation_per_dragon")
        ]

    def __str__(self) -> str:
        return str(self.ball)


class DragonBall(models.Model):
    """
    A countryball that can be used as a dragon ball for a wish. The wish needs a number of different ones of its
    list, they are consumed.
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


class RewardBall(models.Model):
    """
    A countryball that a wish can give as a random reward. If a wish has none, any enabled countryball can be given.
    """

    dragon = models.ForeignKey(Dragon, on_delete=models.CASCADE, related_name="reward_balls")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="+")
    weight = models.FloatField(
        default=1,
        validators=[MinValueValidator(0.0001)],
        help_text="Relative chance of this countryball. The same value everywhere means equal chances, "
        "2 is twice as likely as 1.",
    )

    class Meta:
        ordering = ("id",)
        constraints = [models.UniqueConstraint(fields=("dragon", "ball"), name="dragonwish_unique_reward_per_dragon")]

    def __str__(self) -> str:
        return str(self.ball)


class DragonSpecial(models.Model):
    """
    A special that each rewarded character may get, with its chance.
    """

    dragon = models.ForeignKey(Dragon, on_delete=models.CASCADE, related_name="special_chances")
    special = models.ForeignKey(Special, on_delete=models.CASCADE, related_name="+")
    chance = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Chance in percent that each rewarded character gets this special. "
        "All the chances of a wish cannot add up to more than 100.",
    )
    emoji = models.CharField(
        max_length=100,
        blank=True,
        help_text="Emoji shown next to the chance. Leave empty to use the emoji of the special.",
    )
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower values are listed first.")

    class Meta:
        ordering = ("position", "id")
        verbose_name = "special chance"
        constraints = [
            models.UniqueConstraint(fields=("dragon", "special"), name="dragonwish_unique_special_per_dragon")
        ]

    def __str__(self) -> str:
        return f"{self.special} ({self.chance:g}%)"


class Relic(models.Model):
    """
    A countryball that counts as a relic, for relic crafting and as a wish reward.
    """

    ball = models.OneToOneField(Ball, on_delete=models.CASCADE, related_name="wish_relic")

    class Meta:
        ordering = ("ball_id",)

    def __str__(self) -> str:
        return str(self.ball)
