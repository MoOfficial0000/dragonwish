from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from bd_models.models import Ball, Special

EMOJI_HELP = (
    "ID of the emoji: the number at the end of <:name:ID>, or right click the emoji and choose Copy ID "
    "(developer mode). Leave empty to use the emoji of the countryball."
)


def emoji_id_field(help_text: str = EMOJI_HELP) -> models.PositiveBigIntegerField:
    return models.PositiveBigIntegerField(null=True, blank=True, help_text=help_text)


class WishSettings(models.Model):
    """
    Words and options shared by every wish. There is only one entry.
    """

    class CompletionLayout(models.TextChoices):
        BY_DRAGON = "by_dragon", "Each dragon followed by its own dragon balls"
        BY_BALLS = "by_balls", "All dragons, then all dragon balls by name (a shared dragon ball is listed once)"

    dragon_name = models.CharField(
        max_length=32,
        default="Dragon",
        help_text="The word for a dragon. The item that starts a wish is called 'Activation <this word>'.",
    )
    dragon_name_plural = models.CharField(max_length=32, default="Dragons", help_text="The word for several dragons.")
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
    reward_text = models.CharField(
        max_length=64,
        default="Wild Character Drop!",
        help_text="Text of each random character reward, shown in the rewards of a wish.",
    )
    wish_timeout_minutes = models.PositiveSmallIntegerField(
        default=15,
        validators=[MinValueValidator(1)],
        help_text="A wish is cancelled after this many minutes without any action (adding, removing, "
        "pressing a button). Every action resets the timer.",
    )
    completion_layout = models.CharField(
        max_length=16,
        choices=CompletionLayout,
        default=CompletionLayout.BY_DRAGON,
        help_text="How the dragon ball completion command is laid out.",
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
    emoji_id = emoji_id_field(
        "ID of the emoji of the wish, shown in its title. Leave empty to use the emoji of the first activation "
        "countryball."
    )
    set_name = models.CharField(
        max_length=64,
        blank=True,
        help_text="Title of this set in the completion command, for example 'Earth Dragon Balls'. "
        "Leave empty to use '<name> <dragon balls word>'.",
    )
    set_emoji_id = emoji_id_field(
        "ID of the emoji of the whole set, shown in the wish title next to the dragon. Leave empty to use the "
        "emoji of the first dragon ball."
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
    emoji_id = emoji_id_field()
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower values are listed first.")

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("dragon", "ball"), name="dragonwish_unique_activation_per_dragon")
        ]

    def __str__(self) -> str:
        return str(self.ball)


class ExtraRequirement(models.Model):
    """
    An additional countryball a wish requires, next to the activation countryball and the dragon balls.
    """

    dragon = models.ForeignKey(Dragon, on_delete=models.CASCADE, related_name="extra_requirements")
    name = models.CharField(max_length=32, help_text="Name shown to players, for example 'Energy Piece'.")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="+")
    consumed = models.BooleanField(
        default=False, help_text="Whether it is deleted by the wish. If not, the player keeps it."
    )
    emoji_id = emoji_id_field()
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower values are listed first.")

    class Meta:
        ordering = ("position", "id")
        constraints = [models.UniqueConstraint(fields=("dragon", "ball"), name="dragonwish_unique_extra_per_dragon")]

    def __str__(self) -> str:
        return self.name


class DragonBall(models.Model):
    """
    A countryball that can be used as a dragon ball for a wish. The wish needs a number of different ones of its
    list, they are consumed.
    """

    dragon = models.ForeignKey(Dragon, on_delete=models.CASCADE, related_name="dragon_balls")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="+")
    emoji_id = emoji_id_field()
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
    emoji_id = emoji_id_field("ID of the emoji shown next to the chance. Leave empty to use the emoji of the special.")
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
