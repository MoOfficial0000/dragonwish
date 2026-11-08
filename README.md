# Dragon wish for Ballsdex 3

Gather dragon balls, activate a dragon with `/wish start`, and get rewarded. Everything is configured from the admin
panel (section "Dragon wish"):

- **Wishes**: a name, the emoji and title of the set, how many characters and relics it gives.
  - **Activation countryballs**: any one of them activates the wish, it is not consumed.
  - **Extra required countryballs**: each one is required next to the activation countryball and the dragon balls,
    with its own name (shown as its own field), and a setting for whether the wish deletes it.
  - **Dragon balls**: the list of accepted countryballs. Set *Required count* to ask for only some of them (for
    example 4 for "any 4 different of these 8"), leave it empty to require all of them.
  - **Reward countryballs**: limit the random rewards to these countryballs, with a relative weight. Leave empty to
    reward any enabled countryball (except dragon balls).
  - **Special chances**: any number of specials, each with its percentage. Their catch phrase is shown with the reward.
- **Relics**: the countryballs counting as relics.
- **Wish settings**: the words used everywhere (dragon, dragon ball(s), relic(s), relicborne), the text of a random
  character reward, how long a wish can stay inactive before it cancels itself, the layout of the completion command,
  the special given by relic crafting, and an optional list restricting what relic crafting can give.

Every emoji is configured with its **ID** (the number at the end of `<:name:ID>`, or right click the emoji and choose
Copy ID). Without an emoji, the emoji of the countryball is used.

## Installation

Add the package to your `config/extra.toml` (the `location` is a pip requirement, here a git URL as an example):

```toml
[[ballsdex.packages]]
location = "git+https://github.com/MoOfficial0000/dragonwish.git"
path = "dragonwish"
enabled = true
```

Rebuild and run the migrations as usual. A new install is filled with the dragons, emojis and relics of the v2 package,
looking countryballs up by name (including the four "Relic of ..." ones). Whatever cannot be found is skipped,
so on another dex the package simply starts empty and you configure everything in the admin panel.

Staff members need the `dragonwish` permissions to see the new sections in the admin panel.

## Things to know

- Consumed countryballs (dragon balls, relics) are soft deleted: they stay in the database, flagged as deleted.
- Chances of specials are overall percentages, tried in order, and cannot add up to more than 100.
- The wish screen has Wish, Cancel and Clear buttons. Cancel and Clear ask for confirmation first. Clear releases
  everything that was added but keeps the wish open.
- A list that is too long for one embed field (many dragon balls) continues in a second field, nothing is cut off.
- `/wish remove` only suggests the countryballs that were added to the wish.
- Rewards show the ID and bonuses of what was given, like `(#1A2B, +5ATK%/-3HP%)`.
- The completion command shows how many of each countryball the player has.
- The wish and completion messages say that dragon balls come from `/hourly` and extra required countryballs from
  `/daily`. Those two commands are constants at the top of `dragonwish/wish_ext/cog.py`.
- `/wish bulk add` chooses the dragon balls the player has the most copies of, picking randomly between equal
  amounts (in order when every dragon ball is required anyway), and takes the activation and extra required
  countryballs too.
- A wish cancels itself (and unlocks its countryballs) after the configured number of minutes without an action.
  Adding, removing, bulk adding or pressing a button resets the countdown.
- Command names (`/wish`, `/wish craft relics`...) cannot be renamed from the admin panel, only the words in messages.
  Two exceptions: the completion command is `/wish <balls command name> completion`, using the name of your balls
  command, and the `/wish start` parameter is named after your dragon word. Changes to these apply after restarting
  the bot, which syncs its slash commands at startup (run `b.reloadtree` only if startup syncing is skipped).
- Newly added wishes and relics can take up to 30 seconds to show up in the command autocompletion.
- Wishes in progress only live in memory. Restarting the bot loses them, and the locked countryballs unlock by
  themselves after 30 minutes. Reloading the package unlocks them right away.
