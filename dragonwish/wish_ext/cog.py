import asyncio
import enum
import logging
import random
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Container, Section, Separator, TextDisplay, Thumbnail, button
from django.db.models import Count

from ballsdex.core.discord import LayoutView, View
from ballsdex.core.utils import checks
from ballsdex.core.utils.menus import ListSource, Menu, TextFormatter
from ballsdex.core.utils.transformers import BallInstanceTransform, SpecialEnabledTransform, TTLModelTransformer
from ballsdex.core.utils.utils import inventory_privacy, is_staff
from bd_models.models import Ball, BallInstance, Player, balls
from settings.models import settings

from ..models import ActivationBall, Dragon, DragonBall, DragonSpecial, Relic, RewardBall, WishSettings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.wish")


class DragonTransformer(TTLModelTransformer[Dragon]):
    name = "dragon"
    model = Dragon
    ttl = 30

    def key(self, model: Dragon) -> str:
        return model.name

    def get_queryset(self):
        return Dragon.objects.filter(enabled=True, **self.filters)

    async def get_from_text(self, value: str) -> Dragon:
        return await self.get_queryset().aget(name__iexact=value)


class RelicTransformer(TTLModelTransformer[Relic]):
    name = "relic"
    model = Relic
    ttl = 30

    def key(self, model: Relic) -> str:
        return model.ball.country

    def get_queryset(self):
        return Relic.objects.filter(**self.filters).select_related("ball")

    async def get_from_text(self, value: str) -> Relic:
        return await self.get_queryset().aget(ball__country__iexact=value)


DragonTransform = app_commands.Transform[Dragon, DragonTransformer]
RelicTransform = app_commands.Transform[Relic, RelicTransformer]


@dataclass(frozen=True)
class Words:
    """
    The words configured in the admin panel, used in every message.
    """

    dragon: str
    activation: str
    ball: str
    balls: str
    relic: str
    relics: str
    relicborne: str

    @classmethod
    def from_settings(cls, wish_settings: WishSettings) -> "Words":
        return cls(
            dragon=wish_settings.dragon_name,
            activation=f"Activation {wish_settings.dragon_name}",
            ball=wish_settings.dragon_ball_name,
            balls=wish_settings.dragon_ball_name_plural,
            relic=wish_settings.relic_name,
            relics=wish_settings.relic_name_plural,
            relicborne=wish_settings.relicborne_name,
        )


class AddResult(enum.Enum):
    ADDED = enum.auto()
    DUPLICATE = enum.auto()
    NOT_NEEDED = enum.auto()
    ACTIVATION_FULL = enum.auto()
    BALLS_FULL = enum.auto()


@dataclass(eq=False)
class WishSession:
    """
    A wish being prepared by a user. This only lives in memory, it is lost if the bot restarts (the countryballs
    locked by the wish unlock by themselves after 30 minutes).
    """

    interaction: discord.Interaction["BallsDexBot"]
    user: discord.User | discord.Member
    dragon: Dragon
    words: Words
    activation_balls: list[ActivationBall]
    dragon_balls: list[DragonBall]
    special_chances: list[DragonSpecial]
    dragon_instance: BallInstance | None = None
    ball_instances: list[BallInstance] = field(default_factory=list)

    @property
    def required(self) -> int:
        """
        How many different dragon balls are needed.
        """
        total = len(self.dragon_balls)
        return min(self.dragon.required_count, total) if self.dragon.required_count else total

    @property
    def all_instances(self) -> list[BallInstance]:
        return ([self.dragon_instance] if self.dragon_instance else []) + self.ball_instances


async def soft_delete(instance: BallInstance):
    """
    Mark a countryball as deleted. It stays in the database and can be restored.
    """
    instance.deleted = True
    await instance.asave(update_fields=("deleted",))


def pick_random_ball(exclude: set[int] | None = None) -> Ball | None:
    """
    Pick an enabled countryball, taking rarity into account, like a natural spawn would.
    """
    population = [x for x in balls.values() if x.enabled and x.pk not in (exclude or ())]
    if not population:
        return None
    weights = [x.rarity for x in population]
    if sum(weights) <= 0:
        return random.choice(population)
    return random.choices(population, weights)[0]


async def pick_reward_ball(dragon: Dragon) -> Ball | None:
    """
    Pick the countryball rewarded by a wish: from its reward list if it has one, otherwise any enabled countryball
    except the dragon balls.
    """
    entries = [x async for x in RewardBall.objects.filter(dragon=dragon).select_related("ball")]
    if entries:
        return random.choices([x.ball for x in entries], [x.weight for x in entries])[0]
    excluded = {x async for x in DragonBall.objects.values_list("ball_id", flat=True)}
    return pick_random_ball(excluded)


async def pick_craft_ball(wish_settings: WishSettings) -> Ball | None:
    """
    Pick the countryball obtained by crafting relics, from the configured list if there is one.
    """
    pool = [x async for x in wish_settings.craft_pool.all()]
    if pool:
        return random.choice(pool)
    return pick_random_ball()


def roll_special(chances: list[DragonSpecial]):
    """
    Roll which special a rewarded character gets, if any. The chances are overall percentages, tried in order.
    """
    roll = random.uniform(0, 100)
    cumulative = 0.0
    for entry in chances:
        cumulative += entry.chance
        if roll < cumulative:
            return entry.special
    return None


def catch_phrase_text(special) -> str:
    """
    The catch phrase of a special, formatted like in the catch message, to add at the end of a line.
    """
    return f"\n*{special.catch_phrase}*" if special and special.catch_phrase else ""


def emoji_or_default(bot: "BallsDexBot", custom: str, ball: Ball) -> str:
    """
    The emoji configured in the admin panel, or the countryball's own emoji if none was configured.
    """
    if custom:
        return custom
    emoji = bot.get_emoji(int(ball.emoji_id))
    return str(emoji) if emoji else ""


def render_deck(lines: list[str], total: int) -> str:
    """
    Join lines for an embed field (1024 characters max), with a total if they had to be truncated.
    """
    if not lines:
        return "Empty"
    deck = "\n".join(lines)
    if len(deck) <= 1024:
        return deck

    suffix = f"\nTotal: {total}"
    truncated = ""
    for line in lines:
        candidate = f"{truncated}\n{line}" if truncated else line
        if len(candidate) > 1024 - len(suffix):
            break
        truncated = candidate
    return truncated + suffix


def add_chunked_field(embed: discord.Embed, name: str, text: str):
    """
    Add a field to an embed, splitting it across several fields if it exceeds the 1024 characters limit.
    """
    chunk = ""
    first = True
    for line in text.split("\n"):
        if chunk and len(chunk) + len(line) + 1 > 1024:
            embed.add_field(name=name if first else "\u200b", value=chunk, inline=False)
            first = False
            chunk = ""
        chunk = f"{chunk}\n{line}" if chunk else line
    if chunk.strip():
        embed.add_field(name=name if first else "\u200b", value=chunk, inline=False)


def reward_lines(dragon: Dragon, chances: list[DragonSpecial], words: Words) -> str:
    parts = []
    for entry in chances:
        if entry.chance <= 0:
            continue
        label = entry.emoji or entry.special.emoji
        parts.append(f"{label}{entry.chance:g}%" if label else f"{entry.special.name} {entry.chance:g}%")
    suffix = f" ( {' | '.join(parts)} )" if parts else ""
    lines = [f"- **Wild Character Drop!{suffix}**"] * dragon.reward_count
    if dragon.relic_count:
        plural = "" if dragon.relic_count == 1 else "s"
        lines.append(f"- -# **{dragon.relic_count}× {words.relic} Drop{plural}!**")
    return "\n".join(lines)


class WishView(View):
    def __init__(self, cog: "Wish", user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.restrict_author(user_id)

    @button(style=discord.ButtonStyle.success, emoji="✔", label="Wish")
    async def wish(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        await self.cog.start_wish(interaction)

    @button(style=discord.ButtonStyle.danger, emoji="✖", label="Cancel")
    async def cancel(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        await self.cog.cancel_wish(interaction)


class RelicCraftView(View):
    def __init__(self, cog: "Wish", user_id: int, *, disabled: bool = False):
        super().__init__(timeout=60)
        self.cog = cog
        self.restrict_author(user_id)
        self.craft.disabled = disabled

    @button(style=discord.ButtonStyle.primary, emoji="🌠", label="Craft")
    async def craft(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        await self.cog.craft_relics(interaction)


class Wish(commands.GroupCog):
    """
    Wish your Dragon Balls!
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.sessions: dict[int, WishSession] = {}
        self.crafting: set[int] = set()

    admin = app_commands.Group(name="admin", description="Admin commands for wish")
    dbz = app_commands.Group(name=settings.balls_slash_name, description="Completion commands for wish")
    craft = app_commands.Group(name="craft", description="Relic crafting commands for wish")
    bulk = app_commands.Group(name="bulk", description="Bulk commands for wish")

    async def cog_load(self):
        # slash command parameter names cannot contain spaces or capitals, they are derived from the dragon word
        wish_settings = await WishSettings.aload()
        start = self.app_command.get_command("start")
        if start is None:
            return
        name = re.sub(r"[^\w-]+", "_", wish_settings.dragon_name.strip().lower()).strip("_")[:32] or "dragon"
        try:
            app_commands.rename(dragon=name)(start)
        except ValueError:
            log.warning(f"{name!r} is not a valid command parameter name, using 'dragon'")
            app_commands.rename(dragon="dragon")(start)

    async def cog_unload(self):
        # unlock what pending wishes were holding, since they cannot be resumed
        for session in list(self.sessions.values()):
            await self._unlock_all(session.all_instances)
        self.sessions.clear()

    # ----------------------------------------------------------------------------------------------------------
    # helpers
    # ----------------------------------------------------------------------------------------------------------

    @staticmethod
    async def _unlock_all(instances: list[BallInstance]):
        for instance in instances:
            try:
                await instance.unlock()
            except Exception:
                log.exception(f"Failed to unlock {instance.pk}")

    @staticmethod
    async def _words() -> tuple[WishSettings, Words]:
        wish_settings = await WishSettings.aload()
        return wish_settings, Words.from_settings(wish_settings)

    async def _session_for(self, interaction: discord.Interaction["BallsDexBot"]) -> WishSession | None:
        """
        Fetch the wish of the user, or reply with the reason why there is none usable from this interaction.
        """
        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        session = self.sessions.get(interaction.user.id)
        if session is None:
            await send("You aren't wishing!", ephemeral=True)
            return None
        if interaction.guild_id != session.interaction.guild_id:
            await send("You must be in the same server as your wish to use commands.", ephemeral=True)
            return None
        return session

    @staticmethod
    def _try_add(session: WishSession, instance: BallInstance) -> AddResult:
        if instance.ball_id in {x.ball_id for x in session.activation_balls}:
            if session.dragon_instance is None:
                session.dragon_instance = instance
                return AddResult.ADDED
            if session.dragon_instance.ball_id == instance.ball_id:
                return AddResult.DUPLICATE
            return AddResult.ACTIVATION_FULL
        if instance.ball_id in {x.ball_id for x in session.dragon_balls}:
            if any(x.ball_id == instance.ball_id for x in session.ball_instances):
                return AddResult.DUPLICATE
            if len(session.ball_instances) >= session.required:
                return AddResult.BALLS_FULL
            session.ball_instances.append(instance)
            return AddResult.ADDED
        return AddResult.NOT_NEEDED

    @staticmethod
    def _try_remove(session: WishSession, instance: BallInstance) -> bool:
        if session.dragon_instance is not None and session.dragon_instance.pk == instance.pk:
            session.dragon_instance = None
            return True
        for index, existing in enumerate(session.ball_instances):
            if existing.pk == instance.pk:
                del session.ball_instances[index]
                return True
        return False

    @staticmethod
    def _add_failure(session: WishSession, result: AddResult) -> str:
        words = session.words
        match result:
            case AddResult.DUPLICATE:
                return "You have already added this!"
            case AddResult.ACTIVATION_FULL:
                return f"Your wish already has its {words.activation}."
            case AddResult.BALLS_FULL:
                return f"You already added all the {words.balls} needed."
            case _:
                return (
                    "That is not needed for the wish you have chosen!\n"
                    f"Please make sure to use the correct {words.dragon} and {words.balls} for this wish!"
                )

    def _wish_emoji(self, session: WishSession) -> str:
        if session.dragon.emoji:
            return session.dragon.emoji
        if session.activation_balls:
            first = session.activation_balls[0]
            return emoji_or_default(self.bot, first.emoji, first.ball)
        return ""

    def _set_emoji(self, session: WishSession) -> str:
        if session.dragon.set_emoji:
            return session.dragon.set_emoji
        if session.dragon_balls:
            first = session.dragon_balls[0]
            return emoji_or_default(self.bot, first.emoji, first.ball)
        return ""

    def _setup_embed(self, session: WishSession) -> discord.Embed:
        words = session.words
        total = len(session.dragon_balls)
        required = session.required
        activation_emojis = {x.ball_id: emoji_or_default(self.bot, x.emoji, x.ball) for x in session.activation_balls}
        ball_emojis = {x.ball_id: emoji_or_default(self.bot, x.emoji, x.ball) for x in session.dragon_balls}

        if len(session.activation_balls) > 1:
            activation_need = f"Any one {words.activation} out of the {len(session.activation_balls)} accepted ones"
        else:
            activation_need = words.activation
        if required < total:
            balls_need = f"Any {required} different {words.balls} out of the {total} accepted ones"
        else:
            balls_need = words.balls

        embed = discord.Embed(
            title=f"{settings.collectible_name.title()} Wishing {self._wish_emoji(session)} {self._set_emoji(session)}",
            description=(
                "Use `/wish add`, `/wish remove` or `/wish bulk add` to add/remove requirements.\n"
                "Requires:\n"
                f"- {activation_need} (Will **__not be deleted__** after the wish)\n"
                f"- {balls_need} (obtainable from `/hourly`)\n"
                f"{words.balls} **__will be deleted__** after the wish\n"
                "Click the tick button when ready.\n-------\n"
                "Rewards:\n"
                f"{reward_lines(session.dragon, session.special_chances, words)}\n"
            ),
            color=discord.Colour.from_rgb(255, 255, 255),
        )

        activation_lines = []
        if session.dragon_instance:
            emoji = activation_emojis.get(session.dragon_instance.ball_id, "")
            line = session.dragon_instance.short_description(is_trade=True)
            activation_lines.append(f"- {emoji} {line}" if emoji else f"- {line}")
        ball_lines = []
        for instance in session.ball_instances:
            emoji = ball_emojis.get(instance.ball_id, "")
            line = instance.short_description(is_trade=True)
            ball_lines.append(f"- {emoji} {line}" if emoji else f"- {line}")

        progress = f" ({len(session.ball_instances)}/{required})" if required < total else ""
        embed.add_field(name=f"{words.activation}:", value=render_deck(activation_lines, 1), inline=True)
        embed.add_field(
            name=f"{words.balls}{progress}:", value=render_deck(ball_lines, len(session.ball_instances)), inline=True
        )

        # when there is a choice, tell what can be used
        if len(session.activation_balls) > 1:
            accepted = "\n".join(
                f"- {activation_emojis[x.ball_id]} {x.ball.country}".replace("-  ", "- ")
                for x in session.activation_balls
            )
            add_chunked_field(embed, f"Accepted {words.activation}:", accepted)
        if required < total:
            accepted = "\n".join(
                f"- {ball_emojis[x.ball_id]} {x.ball.country}".replace("-  ", "- ") for x in session.dragon_balls
            )
            add_chunked_field(embed, f"Accepted {words.balls}:", accepted)
        return embed

    @staticmethod
    def _result_embed(
        color: discord.Colour,
        *,
        words: Words,
        description: str,
        dragon_text: str,
        balls_text: str,
        reward_text: str | None = None,
        cancelled: bool = False,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"{settings.collectible_name.title()} Wishing", description=description, color=color
        )
        prefix = ":no_entry_sign: " if cancelled else ""
        embed.add_field(name=f"{prefix}{words.activation}:", value=dragon_text, inline=True)
        embed.add_field(name=f"{prefix}{words.balls}:", value=balls_text, inline=True)
        if reward_text:
            add_chunked_field(embed, "Reward:", reward_text)
        return embed

    def _cancelled_embed(self, words: Words) -> discord.Embed:
        return self._result_embed(
            discord.Color.red(),
            words=words,
            description="The wish has been cancelled.",
            dragon_text="Cancelled",
            balls_text="Cancelled",
            cancelled=True,
        )

    async def _refresh(self, session: WishSession):
        try:
            await session.interaction.edit_original_response(embed=self._setup_embed(session))
        except discord.HTTPException:
            log.warning("Could not refresh the wish message, it may be too old.", exc_info=True)

    # ----------------------------------------------------------------------------------------------------------
    # starting, cancelling and finishing a wish
    # ----------------------------------------------------------------------------------------------------------

    @app_commands.command()
    async def start(self, interaction: discord.Interaction["BallsDexBot"], dragon: DragonTransform):
        """
        Start a wish!

        Parameters
        ----------
        dragon: Dragon
            The type of wish you would like to make.
        """
        if interaction.user.id in self.sessions:
            await interaction.response.send_message(
                "You are already wishing. You may use `/wish cancel` to cancel it.", ephemeral=True
            )
            return
        _, words = await self._words()
        activation_balls = [x async for x in ActivationBall.objects.filter(dragon=dragon).select_related("ball")]
        dragon_balls = [x async for x in DragonBall.objects.filter(dragon=dragon).select_related("ball")]
        special_chances = [x async for x in DragonSpecial.objects.filter(dragon=dragon).select_related("special")]
        if not activation_balls or not dragon_balls:
            await interaction.response.send_message("This wish is not configured yet.", ephemeral=True)
            return
        # checked again since the queries above yielded, a concurrent invocation may have registered a wish
        if interaction.user.id in self.sessions:
            await interaction.response.send_message(
                "You are already wishing. You may use `/wish cancel` to cancel it.", ephemeral=True
            )
            return

        session = WishSession(
            interaction, interaction.user, dragon, words, activation_balls, dragon_balls, special_chances
        )
        self.sessions[interaction.user.id] = session
        await interaction.response.send_message(
            embed=self._setup_embed(session), view=WishView(self, interaction.user.id)
        )

    async def cancel_wish(self, interaction: discord.Interaction["BallsDexBot"]):
        session = self.sessions.pop(interaction.user.id, None)
        if session is None:
            await interaction.response.send_message("This wish doesn't belong to you.", ephemeral=True)
            return
        await interaction.response.defer()
        await self._unlock_all(session.all_instances)
        await interaction.edit_original_response(embed=self._cancelled_embed(session.words), view=None)

    @app_commands.command()
    async def cancel(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Cancels the wish you are in.
        """
        session = self.sessions.pop(interaction.user.id, None)
        if session is None:
            await interaction.response.send_message("You aren't wishing!", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._unlock_all(session.all_instances)
        try:
            await session.interaction.edit_original_response(embed=self._cancelled_embed(session.words), view=None)
        except discord.HTTPException:
            pass
        await interaction.followup.send("Your current wish has been frozen and cancelled.", ephemeral=True)

    async def start_wish(self, interaction: discord.Interaction["BallsDexBot"]):
        await interaction.response.defer()
        session = self.sessions.get(interaction.user.id)
        if session is None:
            await interaction.followup.send("This wish doesn't belong to you.", ephemeral=True)
            return
        if session.dragon_instance is None or len(session.ball_instances) != session.required:
            await interaction.followup.send("Insufficient Materials!", ephemeral=True)
            return

        # take the wish out right away, so that a double click cannot grant the rewards twice
        del self.sessions[interaction.user.id]
        instances = session.all_instances
        try:
            embed = await self._grant_wish(session, instances)
        except Exception:
            log.exception(f"Wish of {interaction.user.id} failed")
            await self._unlock_all(instances)
            await interaction.followup.send("Something went wrong, your wish was cancelled.", ephemeral=True)
            return
        await interaction.edit_original_response(
            content=f"{interaction.user.mention}'s reward(s)", embed=embed, view=None
        )

    async def _grant_wish(self, session: WishSession, instances: list[BallInstance]) -> discord.Embed:
        user = session.user
        dragon = session.dragon
        words = session.words
        assert session.dragon_instance

        # everything must still belong to the user, the locks expire after 30 minutes
        owned = await BallInstance.objects.filter(pk__in=[x.pk for x in instances], player__discord_id=user.id).acount()
        if owned != len(instances):
            await self._unlock_all(instances)
            return self._result_embed(
                discord.Color.dark_orange(),
                words=words,
                description=f"Wishing of {user.mention}",
                dragon_text="Cancelled",
                balls_text="Cancelled",
                reward_text=f"⚠️ One or more {words.balls} do not belong to you.\nThis wish has been cancelled.",
                cancelled=True,
            )

        # rendered now, a deleted countryball is displayed differently
        activation = next((x for x in session.activation_balls if x.ball_id == session.dragon_instance.ball_id), None)
        activation_emoji = emoji_or_default(
            self.bot,
            activation.emoji if activation else "",
            activation.ball if activation else session.dragon_instance.ball,
        )
        activation_line = session.dragon_instance.short_description(is_trade=True)
        dragon_text = f"- {activation_emoji} {activation_line}" if activation_emoji else f"- {activation_line}"
        balls_text = render_deck(
            [f"- ⛔ {x.short_description(is_trade=True)}" for x in session.ball_instances], len(session.ball_instances)
        )

        for instance in session.ball_instances:
            await soft_delete(instance)
        await session.dragon_instance.unlock()

        player, _ = await Player.objects.aget_or_create(discord_id=user.id)
        reward_text = ""

        for _ in range(dragon.reward_count):
            ball = await pick_reward_ball(dragon)
            if ball is None:
                log.error("There is no countryball available to give as a wish reward")
                break
            attack = random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
            health = random.randint(-settings.max_health_bonus, settings.max_health_bonus)
            special = roll_special(session.special_chances)
            await BallInstance.objects.acreate(
                ball=ball, player=player, special=special, attack_bonus=attack, health_bonus=health
            )
            emoji = emoji_or_default(self.bot, "", ball)
            reward_text += f"{emoji} {ball.country}\n`{attack:+d}ATK/{health:+d}HP`{catch_phrase_text(special)}\n\n"

        if dragon.relic_count:
            relics = [x async for x in Relic.objects.select_related("ball")]
            if not relics:
                log.warning("This wish gives relics but no relic is configured")
            for _ in range(dragon.relic_count if relics else 0):
                relic = random.choice(relics)
                await BallInstance.objects.acreate(
                    ball=relic.ball, player=player, special=None, attack_bonus=0, health_bonus=0
                )
                reward_text += f"{emoji_or_default(self.bot, '', relic.ball)} {relic.ball.country}\n"

        return self._result_embed(
            discord.Color.green(),
            words=words,
            description=f"Wishing of {user.mention}",
            dragon_text=dragon_text,
            balls_text=balls_text,
            reward_text=reward_text or "Nothing.",
        )

    # ----------------------------------------------------------------------------------------------------------
    # adding and removing materials
    # ----------------------------------------------------------------------------------------------------------

    @app_commands.command()
    async def add(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Adds a countryball to a wish.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to add.
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        session = await self._session_for(interaction)
        if session is None:
            return
        if not countryball.is_tradeable:
            await interaction.response.send_message("You cannot use this.", ephemeral=True)
            return
        if await countryball.is_locked():
            await interaction.response.send_message(
                f"This {settings.collectible_name} is currently locked for a trade. Please try again later.",
                ephemeral=True,
            )
            return

        result = self._try_add(session, countryball)
        if result is not AddResult.ADDED:
            await interaction.response.send_message(self._add_failure(session, result), ephemeral=True)
            return

        await countryball.lock_for_trade()
        await interaction.response.send_message(
            f"Added `{countryball.description(short=True, include_emoji=False, bot=self.bot)}`!", ephemeral=True
        )
        await self._refresh(session)

    @app_commands.command()
    async def remove(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Removes a countryball from wish.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to remove.
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        session = await self._session_for(interaction)
        if session is None:
            return
        if not self._try_remove(session, countryball):
            await interaction.response.send_message("You cannot remove what is not in your wish!", ephemeral=True)
            return

        await countryball.unlock()
        await interaction.response.send_message(
            f"Removed `{countryball.description(short=True, include_emoji=False, bot=self.bot)}`!", ephemeral=True
        )
        await self._refresh(session)

    @bulk.command(name="add")
    async def bulk_add(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Bulk add what's needed to a wish.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await self._session_for(interaction)
        if session is None:
            return
        words = session.words

        activation_ids = [x.ball_id for x in session.activation_balls]
        ball_ids = [x.ball_id for x in session.dragon_balls]
        candidates: dict[int, BallInstance] = {}
        async for instance in BallInstance.objects.filter(
            player__discord_id=interaction.user.id, ball_id__in=activation_ids + ball_ids
        ).order_by("pk"):
            if instance.ball_id in candidates or not instance.is_tradeable:
                continue
            # the instance was just fetched, there is no need to refresh its lock
            if await instance.is_locked(refresh=False):
                continue
            candidates[instance.ball_id] = instance

        dragon_added = False
        if session.dragon_instance is None:
            for ball_id in activation_ids:
                instance = candidates.get(ball_id)
                if instance is not None and self._try_add(session, instance) is AddResult.ADDED:
                    await instance.lock_for_trade()
                    dragon_added = True
                    break

        number_added = 0
        for ball_id in ball_ids:
            if len(session.ball_instances) >= session.required:
                break
            instance = candidates.get(ball_id)
            if instance is not None and self._try_add(session, instance) is AddResult.ADDED:
                await instance.lock_for_trade()
                number_added += 1

        if dragon_added:
            if number_added > 0:
                text = f"Bulk added {number_added} {words.balls} + {words.activation}."
            else:
                text = f"Added {words.activation}."
        elif number_added > 0:
            text = f"Bulk added {number_added} {words.balls}"
        else:
            text = "There is nothing else to add!"
        await interaction.followup.send(text, ephemeral=True)
        if dragon_added or number_added:
            await self._refresh(session)

    # ----------------------------------------------------------------------------------------------------------
    # completion
    # ----------------------------------------------------------------------------------------------------------

    @dbz.command(name="completion")
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def completion(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User | None = None):
        """
        Show your dragon ball completion for wishing

        Parameters
        ----------
        user: discord.User
            The user whose completion you want to view, if not yours.
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)
        if user is not None:
            try:
                player = await Player.objects.aget(discord_id=user_obj.id)
            except Player.DoesNotExist:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any {settings.plural_collectible_name} yet."
                )
                return

            interaction_player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
            blocked = await player.is_blocked(interaction_player)
            if blocked and not await is_staff(interaction):
                await interaction.followup.send(
                    "You cannot view the completion of a user that has blocked you.", ephemeral=True
                )
                return

            if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
                return

        _, words = await self._words()
        dragons = [
            x
            async for x in Dragon.objects.filter(enabled=True).prefetch_related(
                "activation_balls__ball", "dragon_balls__ball"
            )
        ]
        if not dragons:
            await interaction.followup.send("No wish is configured yet.", ephemeral=True)
            return

        all_ids = {
            x.ball_id for dragon in dragons for x in [*dragon.activation_balls.all(), *dragon.dragon_balls.all()]
        }
        owned = {
            x
            async for x in BallInstance.objects.filter(player__discord_id=user_obj.id, ball_id__in=all_ids)
            .distinct()
            .values_list("ball_id", flat=True)
        }

        def line(ball_id: int, emoji: str, label: str) -> str:
            mark = ":white_check_mark:" if ball_id in owned else ":x:"
            return f"- {mark}{emoji}{label}"

        sections = []
        for dragon in dragons:
            title = dragon.set_name or f"{dragon.name} {words.balls}"
            activation_balls = list(dragon.activation_balls.all())
            dragon_balls = list(dragon.dragon_balls.all())
            required = min(dragon.required_count, len(dragon_balls)) if dragon.required_count else len(dragon_balls)

            lines = []
            if required < len(dragon_balls):
                lines.append(f"-# Any {required} different out of these {len(dragon_balls)}")
            for activation in activation_balls:
                emoji = emoji_or_default(self.bot, activation.emoji, activation.ball)
                lines.append(line(activation.ball_id, emoji, activation.ball.country))
            for index, dragon_ball in enumerate(dragon_balls, start=1):
                emoji = emoji_or_default(self.bot, dragon_ball.emoji, dragon_ball.ball)
                lines.append(line(dragon_ball.ball_id, emoji, f"#{index}"))
            sections.append(f"**{title}:**\n" + "\n".join(lines))

        # two wishes per page
        pages = ["\n\n".join(sections[i : i + 2]) for i in range(0, len(sections), 2)]

        view = LayoutView()
        container = Container(accent_colour=discord.Colour.from_rgb(0, 0, 255))
        container.add_item(
            Section(
                TextDisplay(
                    f"**{words.ball} completion of {user_obj.mention}**\n"
                    f"-# {words.balls} are obtainable from `/hourly`.\n"
                    f"-# Use `/{settings.balls_slash_name} completion` for the full dex completion."
                ),
                accessory=Thumbnail(user_obj.display_avatar.url),
            )
        )
        container.add_item(Separator())
        display = TextDisplay("")
        container.add_item(display)
        view.add_item(container)
        menu = Menu(self.bot, view, ListSource(pages), TextFormatter(display))
        await menu.init()
        await interaction.followup.send(view=view)

    # ----------------------------------------------------------------------------------------------------------
    # relics
    # ----------------------------------------------------------------------------------------------------------

    @staticmethod
    async def _relic_counts(user_id: int, relics: list[Relic]) -> dict[int, int]:
        return {
            row["ball_id"]: row["total"]
            async for row in BallInstance.objects.filter(
                player__discord_id=user_id, ball_id__in=[x.ball_id for x in relics]
            )
            .values("ball_id")
            .annotate(total=Count("id"))
        }

    def _relic_embed(
        self,
        user: discord.User | discord.Member,
        relics: list[Relic],
        counts: dict[int, int],
        words: Words,
        wish_settings: WishSettings,
    ) -> discord.Embed:
        special = wish_settings.relicborne_special
        special_emoji = (special.emoji or "") if special else ""
        embed = discord.Embed(
            title=f"{words.relic} Crafting",
            description=(
                f"Craft the {len(relics)} {words.relics.lower()} to receive "
                f"a random {special_emoji}{words.relicborne} character!\n"
                f"{words.relics} are obtainable from `/wish start` or `/daily`."
            ),
            color=discord.Colour.from_rgb(82, 92, 145),
        )
        embed.set_author(name=user.name, icon_url=user.display_avatar.url)
        embed.set_footer(text=f"Incomplete {words.relic.lower()} set? Use `/wish craft relics_2`.")
        for relic in relics:
            embed.add_field(
                name=f"{emoji_or_default(self.bot, '', relic.ball)} {relic.ball.country}",
                value=f"Count: {counts.get(relic.ball_id, 0)}",
                inline=True,
            )
        return embed

    @craft.command(name="relics")
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def relics(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Craft the relics!
        """
        await interaction.response.defer(thinking=True)
        wish_settings, words = await self._words()
        relics = [x async for x in Relic.objects.select_related("ball")]
        if not relics:
            await interaction.followup.send(f"No {words.relic.lower()} is configured yet.", ephemeral=True)
            return
        counts = await self._relic_counts(interaction.user.id, relics)
        view = RelicCraftView(self, interaction.user.id)
        view.original_message = await interaction.followup.send(
            embed=self._relic_embed(interaction.user, relics, counts, words, wish_settings), view=view, wait=True
        )

    async def craft_relics(self, interaction: discord.Interaction["BallsDexBot"]):
        user = interaction.user
        if user.id in self.crafting:
            await interaction.response.send_message("You are already crafting!", ephemeral=True)
            return
        wish_settings, words = await self._words()
        not_enough = f"You don't have enough {words.relics.lower()} to craft!"
        relics = [x async for x in Relic.objects.select_related("ball")]
        counts = await self._relic_counts(user.id, relics)
        if not relics or any(counts.get(x.ball_id, 0) < 1 for x in relics):
            await interaction.response.send_message(not_enough, ephemeral=True)
            return

        self.crafting.add(user.id)
        try:
            await interaction.response.defer()
            await interaction.edit_original_response(view=RelicCraftView(self, user.id, disabled=True))

            # gather everything first, so nothing is consumed if one of the relics vanished meanwhile
            consumed: list[BallInstance] = []
            for relic in relics:
                instance = (
                    await BallInstance.objects.filter(player__discord_id=user.id, ball_id=relic.ball_id)
                    .order_by("pk")
                    .afirst()
                )
                if instance is None:
                    await interaction.followup.send(not_enough, ephemeral=True)
                    await interaction.edit_original_response(view=RelicCraftView(self, user.id))
                    return
                consumed.append(instance)

            ball = await pick_craft_ball(wish_settings)
            if ball is None:
                await interaction.followup.send("There is no countryball available to craft.", ephemeral=True)
                await interaction.edit_original_response(view=RelicCraftView(self, user.id))
                return
            for instance in consumed:
                await soft_delete(instance)
            counts = {x.ball_id: counts.get(x.ball_id, 1) - 1 for x in relics}

            attack = random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
            health = random.randint(-settings.max_health_bonus, settings.max_health_bonus)
            player, _ = await Player.objects.aget_or_create(discord_id=user.id)
            special = wish_settings.relicborne_special
            await BallInstance.objects.acreate(
                ball=ball, player=player, special=special, attack_bonus=attack, health_bonus=health
            )
            text = f"{user.mention} You crafted **{ball.country}**! `({attack:+d}ATK/{health:+d}HP)`"
            if special:
                phrase = special.catch_phrase or f"It's a {words.relicborne} character!"
                text += f"\n\n***{phrase}***"
            await interaction.followup.send(text)
            await interaction.edit_original_response(
                embed=self._relic_embed(user, relics, counts, words, wish_settings)
            )

            await asyncio.sleep(5)
            new_view = RelicCraftView(self, user.id)
            new_view.original_message = interaction.message
            await interaction.edit_original_response(view=new_view)
        finally:
            self.crafting.discard(user.id)

    @craft.command(name="relics_2")
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def specificrelic(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        owned_relic1: BallInstanceTransform,
        owned_relic2: BallInstanceTransform,
        chosen_relic: RelicTransform,
    ):
        """
        Fuse two relics to form a chosen relic.

        Parameters
        ----------
        owned_relic1: BallInstance
            Select the first relic you own for fusion.
        owned_relic2: BallInstance
            Select the second relic you own for fusion.
        chosen_relic: Relic
            The relic you want to create from the fusion.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        _, words = await self._words()
        relic_word = words.relic.lower()
        relic_ids = {x async for x in Relic.objects.values_list("ball_id", flat=True)}
        if owned_relic1.ball_id not in relic_ids or owned_relic2.ball_id not in relic_ids:
            await interaction.followup.send(f"You must select valid {words.relics.lower()}!", ephemeral=True)
            return
        if owned_relic1.pk == owned_relic2.pk:
            await interaction.followup.send(
                f"You cannot select {relic_word} with the same (Character #ID) twice.", ephemeral=True
            )
            return
        if chosen_relic.ball_id in (owned_relic1.ball_id, owned_relic2.ball_id):
            await interaction.followup.send(
                f"The chosen {relic_word} must be different from the {words.relics.lower()} you are using!",
                ephemeral=True,
            )
            return

        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        # described now, a deleted countryball is displayed differently
        first = owned_relic1.description(short=True, include_emoji=False, bot=self.bot)
        second = owned_relic2.description(short=True, include_emoji=False, bot=self.bot)
        for relic in (owned_relic1, owned_relic2):
            await soft_delete(relic)
        await BallInstance.objects.acreate(
            ball=chosen_relic.ball, player=player, special=None, attack_bonus=0, health_bonus=0
        )
        await interaction.followup.send(
            f"You successfully fused {first} and {second} to create {chosen_relic.ball.country}!", ephemeral=True
        )

    # ----------------------------------------------------------------------------------------------------------
    # admin
    # ----------------------------------------------------------------------------------------------------------

    @admin.command(name="clear")
    @checks.app_check(checks.is_staff())
    async def clear(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Cancels all wishes.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        sessions = list(self.sessions.values())
        self.sessions.clear()
        for session in sessions:
            await self._unlock_all(session.all_instances)
        await interaction.followup.send("All wishes have been reset.", ephemeral=True)
