"""
Fill the dragons, dragon balls, emojis and relics that were hardcoded in the v2 wish package.

Countryballs are looked up by name, anything that cannot be found is skipped (so nothing is added on a dex
without these countryballs). Nothing happens if
dragons already exist. Everything can be edited afterwards in the admin panel.
"""

import logging

from django.db import migrations

log = logging.getLogger("dragonwish.migrations")

# (name of the dragon countryball, emoji of the dragon, title of the set, emoji of the set,
#  [(name of a dragon ball countryball, emoji of that dragon ball), ...],
#  characters rewarded, relics rewarded, shiny chance, mythical chance)
DRAGONS = [
    (
        "Shenron",
        "<:Shenron:1358300433441099948>",
        "Earth Dragon Balls",
        "<:EarthDragonBalls:1355736004530536559>",
        [
            ("Earth Dragon Ball (1 Star)", "<:DB1:1355509169565859929>"),
            ("Earth Dragon Ball (2 Star)", "<:DB2:1355509172233441473>"),
            ("Earth Dragon Ball (3 Star)", "<:DB3:1355509175089893396>"),
            ("Earth Dragon Ball (4 Star)", "<:DB4:1355509186871427112>"),
            ("Earth Dragon Ball (5 Star)", "<:DB5:1355509178176897174>"),
            ("Earth Dragon Ball (6 Star)", "<:DB6:1355509181150662766>"),
            ("Earth Dragon Ball (7 Star)", "<:DB7:1355509183964774420>"),
        ],
        7,
        1,
        0,
        0,
    ),
    (
        "Super Shenron",
        "<:SuperShenron:1311798650246271016>",
        "Super Dragon Balls",
        "<:SuperDragonBalls:1355736009018445854>",
        [
            ("Super Dragon Ball (1 Star)", "<:SuperDB1:1355509197126762498>"),
            ("Super Dragon Ball (2 Star)", "<:SuperDB2:1355509198875791420>"),
            ("Super Dragon Ball (3 Star)", "<:SuperDB3:1355509200939126914>"),
            ("Super Dragon Ball (4 Star)", "<:SuperDB4:1355509203380207869>"),
            ("Super Dragon Ball (5 Star)", "<:SuperDB5:1355509205242744903>"),
            ("Super Dragon Ball (6 Star)", "<:SuperDB6:1355509207331504168>"),
            ("Super Dragon Ball (7 Star)", "<:SuperDB7:1355509209411878933>"),
        ],
        1,
        4,
        60,
        12,
    ),
    (
        "Porunga",
        "<:Porunga:1325953103031439410>",
        "Namekian Dragon Balls",
        "<:NamekianDragonBalls:1355736002135588974>",
        [
            ("Namekian Dragon Ball (1 Star)", "<:NamekDB1:1355509351615565934>"),
            ("Namekian Dragon Ball (2 Star)", "<:NamekDB2:1355509354811625634>"),
            ("Namekian Dragon Ball (3 Star)", "<:NamekDB3:1355509357776863302>"),
            ("Namekian Dragon Ball (4 Star)", "<:NamekDB4:1355509369399152782>"),
            ("Namekian Dragon Ball (5 Star)", "<:NamekDB5:1355509360041787412>"),
            ("Namekian Dragon Ball (6 Star)", "<:NamekDB6:1355509362927341678>"),
            ("Namekian Dragon Ball (7 Star)", "<:NamekDB7:1355509365553106975>"),
        ],
        7,
        1,
        0,
        0,
    ),
    (
        "Porunga (Daima)",
        "<:PorungaDaima:1340039668137463941>",
        "Demon Realm Dragon Balls",
        "<:DemonRealmDragonBalls:1355736006782881993>",
        [
            ("Demon Realm Dragon Ball (1 Star)", "<:DemonRealmDB1:1355509715248877638>"),
            ("Demon Realm Dragon Ball (2 Star)", "<:DemonRealmDB2:1355509710744191134>"),
            ("Demon Realm Dragon Ball (3 Star)", "<:DemonRealmDB3:1355509713323819059>"),
        ],
        3,
        2,
        2,
        0.4,
    ),
    (
        "Toronbo",
        "<:Toronbo:1322958774088106077>",
        "Cerealian Dragon Balls",
        "<:CerealianDragonBalls:1355735779875229867>",
        [
            ("Cerealian Dragon Ball (1 Star)", "<:CerealianDB1:1355508560284614737>"),
            ("Cerealian Dragon Ball (2 Star)", "<:CerealianDB2:1355508557537218791>"),
        ],
        2,
        2,
        3,
        0.6,
    ),
    (
        "Ultimate Shenron",
        "<:UltimateShenron:1437982333507735743>",
        "Black Star Dragon Balls",
        "<:BlackStarDragonBalls:1439034304180260997>",
        [
            ("Black Star Dragon Ball (1 Star)", "<:OneStarBlackStarDragonball:1439035486357422194>"),
            ("Black Star Dragon Ball (2 Star)", "<:TwoStarBlackStarDragonball:1439035463137755357>"),
            ("Black Star Dragon Ball (3 Star)", "<:ThreeStarBlackStarDragonball:1439035445328613386>"),
            ("Black Star Dragon Ball (4 Star)", "<:FourStarBlackStarDragonball:1439035525905387660>"),
            ("Black Star Dragon Ball (5 Star)", "<:FiveStarBlackStarDragonball:1439035398159335424>"),
            ("Black Star Dragon Ball (6 Star)", "<:SixStarBlackStarDragonball:1439035506724962304>"),
            ("Black Star Dragon Ball (7 Star)", "<:SevenStarBlackStarDragonball:1439035426747842660>"),
        ],
        7,
        2,
        1,
        0.2,
    ),
]

RELIC_NAMES = ["Relic of Tyranny", "Relic of Destruction", "Relic of Monarchy", "Relic of Divinity"]


def seed(apps, schema_editor):
    Ball = apps.get_model("bd_models", "Ball")
    Dragon = apps.get_model("dragonwish", "Dragon")
    DragonBall = apps.get_model("dragonwish", "DragonBall")
    Relic = apps.get_model("dragonwish", "Relic")

    if Dragon.objects.exists():
        return

    for position, (name, emoji, set_name, set_emoji, dragon_balls, rewards, relics, shiny, mythical) in enumerate(
        DRAGONS, start=1
    ):
        dragon_ball = Ball.objects.filter(country=name).first()
        if dragon_ball is None:
            log.info(f"Skipping dragon {name!r}: no countryball with this name")
            continue
        found = []
        for index, (ball_name, ball_emoji) in enumerate(dragon_balls, start=1):
            ball = Ball.objects.filter(country=ball_name).first()
            if ball is None:
                log.info(f"Skipping dragon ball {ball_name!r} of {name!r}: no countryball with this name")
                continue
            found.append((index, ball, ball_emoji))
        if not found:
            log.info(f"Skipping dragon {name!r}: none of its dragon balls exist")
            continue

        dragon = Dragon.objects.create(
            ball=dragon_ball,
            emoji=emoji,
            set_name=set_name,
            set_emoji=set_emoji,
            reward_count=rewards,
            relic_count=relics,
            shiny_chance=shiny,
            mythical_chance=mythical,
            position=position,
        )
        for index, ball, ball_emoji in found:
            DragonBall.objects.create(dragon=dragon, ball=ball, emoji=ball_emoji, position=index)

    for ball in Ball.objects.filter(country__in=RELIC_NAMES):
        Relic.objects.create(ball=ball)


class Migration(migrations.Migration):
    dependencies = [("dragonwish", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
