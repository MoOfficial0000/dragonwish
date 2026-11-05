"""
Move the existing wish configuration to the reworked models:

- every dragon becomes a named wish with its countryball as the first activation countryball
- the shiny and mythical chances become special chances, using the specials named "Shiny" and "Mythical"
- the settings are created, using the special named "Relicborne" for relic crafting

Nothing is lost silently: whatever cannot be moved is logged.
"""

import logging

from django.db import migrations

log = logging.getLogger("dragonwish.migrations")


def forwards(apps, schema_editor):
    Dragon = apps.get_model("dragonwish", "Dragon")
    ActivationBall = apps.get_model("dragonwish", "ActivationBall")
    DragonSpecial = apps.get_model("dragonwish", "DragonSpecial")
    WishSettings = apps.get_model("dragonwish", "WishSettings")
    Special = apps.get_model("bd_models", "Special")

    used: set[str] = set()
    for dragon in Dragon.objects.select_related("ball").order_by("position", "id"):
        name = base = dragon.ball.country
        number = 2
        while name in used:
            name = f"{base} ({number})"
            number += 1
        used.add(name)
        dragon.name = name
        dragon.save(update_fields=["name"])

        ActivationBall.objects.create(dragon=dragon, ball=dragon.ball, emoji=dragon.emoji, position=1)

        for position, (chance, special_name, emoji) in enumerate(
            ((dragon.shiny_chance, "Shiny", "✨"), (dragon.mythical_chance, "Mythical", "🌌")), start=1
        ):
            if chance <= 0:
                continue
            special = Special.objects.filter(name__iexact=special_name).first()
            if special is None:
                log.warning(f"{name}: a {chance:g}% chance of {special_name!r} was not moved, no such special exists")
                continue
            DragonSpecial.objects.create(dragon=dragon, special=special, chance=chance, emoji=emoji, position=position)

    relicborne = Special.objects.filter(name__iexact="Relicborne").first()
    WishSettings.objects.get_or_create(pk=1, defaults={"relicborne_special": relicborne})


class Migration(migrations.Migration):
    dependencies = [("dragonwish", "0003_wish_rework_add")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
