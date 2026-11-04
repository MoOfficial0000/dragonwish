# Dragon wish for Ballsdex 3

Gather dragon balls, summon a dragon with `/wish start`, and get rewarded. Everything that used to be hardcoded in
the v2 package is now configured from the admin panel:

- **Dragons**: the activation dragon (a countryball dropdown), its title, emoji, and what a wish gives (number of
  characters, number of relics, shiny and mythical chances).
- **Dragon balls**: added under each dragon with a countryball dropdown, in order, each with an optional emoji.
  Without an emoji, the emoji of the countryball is used.
- **Relics**: the countryballs counting as relics, for `/wish craft relics`, `/wish craft relics_2` and as wish rewards.

## Installation

Add the package to your `config/extra.toml` (the `location` is a pip requirement, here a git URL as an example):

```toml
[[ballsdex.packages]]
location = "git+https://github.com/<you>/ballsdex-dragonwish.git"
path = "dragonwish"
enabled = true
```

Rebuild and run the migrations as usual. The first migration creates the tables, the second one fills them with the
dragons, emojis and relics of the v2 package, looking countryballs up by name (relics by ID 321 to 324). Whatever
cannot be found is skipped, and the migration does nothing if dragons already exist.

Staff members need the `dragonwish` permissions to see the new sections in the admin panel.

## Things to know

- Specials given as rewards are looked up by name: `Shiny`, `Mythical` and `Relicborne`. They are constants at the
  top of `dragonwish/wish_ext/cog.py`, as is the player receiving the relics consumed by `/wish craft relics_2`.
- Shiny and mythical chances are the *overall* chances displayed to players. Shiny is rolled first, so the two cannot
  add up to more than 100.
- Newly added dragons and relics can take up to 30 seconds to show up in the command autocompletion.
- Wishes in progress only live in memory. Restarting the bot loses them, and the locked countryballs unlock by
  themselves after 30 minutes. Reloading the package unlocks them right away.
