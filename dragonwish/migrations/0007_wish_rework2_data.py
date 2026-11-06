"""
Emojis are now configured with their ID. Convert the emojis saved as text (like <:DB1:1355509169565859929>) to
their ID. Text that is not a custom emoji (like a unicode emoji) cannot be converted and is cleared: the emoji of
the countryball (or of the special) is used instead.
"""

import logging
import re

from django.db import migrations

log = logging.getLogger("dragonwish.migrations")

CUSTOM_EMOJI = re.compile(r"<a?:[^:>]+:(\d+)>")


def to_id(value: str) -> int | None:
    value = (value or "").strip()
    if value.isdigit():
        return int(value)
    match = CUSTOM_EMOJI.fullmatch(value)
    return int(match.group(1)) if match else None


def forwards(apps, schema_editor):
    targets = [
        ("Dragon", "emoji", "emoji_id"),
        ("Dragon", "set_emoji", "set_emoji_id"),
        ("ActivationBall", "emoji", "emoji_id"),
        ("DragonBall", "emoji", "emoji_id"),
        ("DragonSpecial", "emoji", "emoji_id"),
    ]
    for model_name, old, new in targets:
        Model = apps.get_model("dragonwish", model_name)
        changed = []
        for obj in Model.objects.exclude(**{old: ""}):
            value = to_id(getattr(obj, old))
            if value is None and model_name != "DragonSpecial":
                log.warning(f"{model_name} {obj.pk}: {getattr(obj, old)!r} is not a custom emoji, cleared")
            setattr(obj, new, value)
            changed.append(obj)
        Model.objects.bulk_update(changed, [new])


class Migration(migrations.Migration):
    dependencies = [("dragonwish", "0006_wish_rework2_add")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
