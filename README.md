# Dragon wish for Ballsdex 3

Gather dragon balls, activate a dragon with `/wish start`, and get rewarded. Everything is configured from the admin
panel (section "Dragon wish"):

- **Wishes**: a name, the emoji and title of the set, how many characters and relics it gives.
  - **Activation countryballs**: any one of them activates the wish, it is not consumed.
  - **Dragon balls**: the list of accepted countryballs, each with an optional emoji. Set *Required count* to ask for
    only some of them (for example 4 for "any 4 different of these 8"), leave it empty to require all of them.
  - **Reward countryballs**: limit the random rewards to these countryballs, with a relative weight. Leave empty to
    reward any enabled countryball (except dragon balls).
  - **Special chances**: any number of specials, each with its percentage. Their catch phrase is shown with the reward.
- **Relics**: the countryballs counting as relics.
- **Wish settings**: the words used everywhere (dragon, dragon ball(s), relic(s), relicborne), the special given by
  relic crafting, and an optional list restricting what relic crafting can give.

Without an emoji, the emoji of the countryball is used.

## Installation

Add the package to your `config/extra.toml` (the `location` is a pip requirement, here a git URL as an example):

```toml
[[ballsdex.packages]]
location = "git+https://github.com/MoOfficial0000/dragonwish.git"
path = "dragonwish"
enabled = true
```

Rebuild and run the migrations as usual. A new install is filled with the dragons, emojis and relics of the v2 package,
looking countryballs up by name (relics by ID 321 to 324). Whatever cannot be found is skipped.

Staff members need the `dragonwish` permissions to see the new sections in the admin panel.

## Things to know

- Consumed countryballs (dragon balls, relics) are soft deleted: they stay in the database, flagged as deleted.
- Chances of specials are overall percentages, tried in order, and cannot add up to more than 100.
- Command names (`/wish`, `/wish craft relics`...) cannot be renamed from the admin panel, only the words in messages.
- Newly added wishes and relics can take up to 30 seconds to show up in the command autocompletion.
- Wishes in progress only live in memory. Restarting the bot loses them, and the locked countryballs unlock by
  themselves after 30 minutes. Reloading the package unlocks them right away.
