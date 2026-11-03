# Diablo III (Xbox 360, 2013) save editor for Rehydrated

An item, affix, gem, follower, gold, level, quest, artisan and Paragon editor for the saves of **the original Xbox 360 release of Diablo III**
(September 2013, before Reaper of Souls) when it runs in **Rehydrated**, the PC recompilation of that game.

| Works with | Does not work with |
| --- | --- |
| Diablo III for Xbox 360 (2013 base game, save version 903), played through Rehydrated | Diablo III for PC (any version) |
| The unpacked saves Rehydrated writes (`...\rehydrated\<profile>\<title>\00000001\d3save`) | Reaper of Souls / Ultimate Evil Edition (Xbox 360, Xbox One, PS3, PS4, Switch) |
| | Xbox 360 saves still inside their console package (`PARAM.PFD` / STFS) |

Items with stats from later versions of the game (Reaper of Souls and up) do not exist in this version; the editor only
offers what the 2013 console game itself contains.

## Start

Needs Windows 10 or 11 and [Python](https://www.python.org/downloads/) 3.10 or newer (the python.org installer
includes Tkinter, which the editor uses). Close the game, then double-click **`Save Editor.bat`** (or run
`pythonw editor.py`).

The editor opens the most recently played save in `Documents\rehydrated` (also when Windows moved Documents, e.g. to
OneDrive). If you start Rehydrated with another `--user_data_root`, use **Open folder...** and pick that folder or the
`d3save` folder inside it; the editor remembers it.

## What it does

- Lists the shared stashes (normal and hardcore) and every hero's backpack, equipment and follower gear, with each
  item's stats in the game's own words ("+46-56 Strength", "Critical Hit damage increased by 105-140%").
- **Add item**: any normal, magic, rare or legendary item of this version, by name or type, into the backpack, straight
  into an equipment slot (the old item moves to the backpack), onto the Templar, Scoundrel or Enchantress, or into the
  stash. Magic and rare items get random
  affixes that fit the item; legendaries get the affixes the console rolls for that legendary (best tier). You can
  change them afterwards. Items that exist only in the PC version are not offered: the console game deletes them.
- **Affixes**: add, remove or randomize affixes. Normally you get the affixes the game can roll on that item type,
  one per family. Tick **Show all affixes (modded)** to add any affix to any item, as many copies as you like:
  copies stack, so a dagger with four times the top damage affix really does four times that damage.
  An item can hold at most **32 affixes**; with more the game disconnects you when the item loads.
- **Sockets and gems**: give any item up to **3 sockets**, also items that normally get fewer (a dagger with three
  Radiant Star Rubies works in game), and fill them with any gem, up to the console's Radiant Star gems. More than 3
  is not possible: the game client only handles 0-3 sockets and disconnects with more gems.
- **Rare names**: rares get a name like the game gives them ("Worthy Shell"), built from the item type and its
  affixes; pick another from the list of names that item can have.
- **Followers**: unlock the Templar, Scoundrel and Enchantress for a hero and equip their main hand, off-hand,
  special item, neck and rings.
- **Hero level** (1-60): sets the level, the base Strength, Dexterity, Intelligence and Vitality the hero would
  have at that level (a level 60 Wizard: 67 / 67 / 187 / 127) and an empty experience bar for that level.
- **Quests and difficulty**: unlock every act and story quest up to Normal, Nightmare, Hell or Inferno (all waypoints
  too), and choose where the next game starts: difficulty, act, quest and checkpoint, by the game's own quest names
  ("Siegebreaker", "Kill the Siegebreaker Assault Beast..."). In PC proxy mode this is how you pick the quest: the
  console side starts the game with "Continue".
- **Hardcore**: unlock hardcore heroes for the account, and **revive** a dead hardcore hero.
- **Artisans**: set the Blacksmith and Jeweler level (0-10), normal and hardcore.
- **Stash tabs**: 1-3 tabs (70 squares each, the game's maximum is 210) for the normal and hardcore stash.
- **Bulk add**: every legendary (or only weapons, armor, jewelry, one item type), the best gem of each kind, crafting
  materials or dyes, into the stash or backpack until it is full.
- **Copy to** another hero or stash, and **item presets**: save an item you built (affixes, sockets, gems, rare name)
  as a `.d3item` file and load it onto any hero or stash, also in another save or on another PC.
- **Paragon level** (0-100) for normal and hardcore heroes (on console it is shared by all heroes of the account);
  the bonus stats follow from it in game.
- Duplicate and delete items, change stack sizes and durability, set gold for normal and hardcore.
- **Safe saving**: the editor refuses to save while Rehydrated runs (the game would overwrite the files), and copies the
  whole save folder to `d3save-backup-<date>` next to it before every save.

Tested in game: items in the backpack, equipment slots and stash; legendaries; magic and rare items with affixes
(stats apply when equipped); legendaries with their rolled affixes; 29 stacked affixes on one weapon; hero level 60 with
its stats; Paragon 50 (shown as "60 (50)" with the bonus stats); a socketed Radiant Star Ruby (damage jumps); the Templar
wearing items in all six follower slots; a rare's name and an item in the hardcore stash surviving a save.

Tested in game (PC proxy): everything unlocked up to Inferno and a level 35 hero starting in New Tristram on Hell at
"A Shattered Crown"; the hero list showing a dead hardcore hero as "Dead" and a revived one as playable; stash tabs,
artisan levels and quest progress kept when the game saves again; starting in Act II (Normal), Act III (Hell) and Act IV
(Normal). The game numbers acts 0, 100, 200 and 300; editor versions before this fix wrote 1-3, which made the game
exit with a fatal error on entering Act II-IV (open the hero and pick the quest again to fix such a save). Nightmare,
Hell and Inferno through the PC proxy need a Rehydrated.Bnet that offers a game factory per difficulty. Bulk add, copies and
presets are checked with the editor's own test on a save copy.

Not supported: typing exact stat numbers (stats come from the game's affix tables; stack affixes instead) and a
bigger backpack (the game window only shows 60 squares). Rare names are written the way the game stores them, but the
in-game tooltip showing them has not been checked.

## How it works

- Saves are protobuf messages XOR'd with a running key (`d3save.py`); the message definitions (`D3.Hero`,
  `D3.Items`) are the ones embedded in the game.
- Hero file field 6 is the item list; account field 20 holds partitions (0 normal, 1 hardcore), whose field 3 is the
  shared stash and gold and field 2 the account attributes: Paragon level (key `0x1FF9`) and the experience to the next
  Paragon level (`0x1FFB`, from the console's table: 7,200,000 at Paragon 0 up to 322,560,000 at 99).
- Saved attribute keys are not the game's attribute numbers but a short list of their own (hero: Level `0x1F5F`,
  Experience_Next `0x1F7F`, Strength `0x1EFB`, ...); they were mapped by loading saves with probe values and reading
  the attributes the server sends.
- An item is `D3.Items.SavedItem`: the slot is `(inventory slot + 17) * 16` (sint32), the square is the grid index
  `y * width + x` (sint32), and the generator holds the seed, the item gbid (sfixed32), the affix gbids (repeated
  sfixed32), the rare name (word list SNO and indexes), durability, stack size, quality (sint32; 3-5 magic, 6-8 rare,
  9 legendary) and socketed gems. A gem is also saved as its own item in slot 47 pointing at the socketed item.
  Follower gear has the hireling class (1 Templar, 2 Scoundrel, 3 Enchantress) and slots 64-69.
- Console affixes are named `1xx_<name>` and their gbid is the hash of that full name, so PC affix ids do not work
  on console. `data/affixes.json` is the console's own affix table (3227 affixes).
- The hero level is the digest (hero list) plus the saved `Level` attribute (key `0x1F5F`) the game reads in play.
  Base stats are saved float attributes the game raises at each level-up: Strength `0x1EFB`, Dexterity `0x1EF7`,
  Intelligence `0x1EF3`, Vitality `0x1EDF` (level 1: 10 in the class's main stat, 9 Vitality, 8 in the others; per
  level +3 main stat, +2 Vitality, +1 others).
- Hero progress is in the digest: highest unlocked act (10) and difficulty (12), highest completed difficulty (16),
  last played act, difficulty, quest and step (9, 11, 13, 14), and the quest history (8: quest SNO, difficulty,
  highest step played). Story quests, their order per act and their checkpoints (the steps with a Battle.net text) come
  from the PC client's Act and Quest files (`data/quests.json`). Step uids are sint32.
- Hero `player_flags` (digest 6): 1 hardcore, 2 female, 8 dead; the console data's killer name is cleared on revive.
  The account digest flag 1 unlocks hardcore heroes.
- Account partitions hold the artisans (field 4: one `CrafterData` per artisan, level in field 3) and the stash size
  (`Shared_Stash_Slots`, attribute key `0x1FFF`, bounded 0-210 in the game).
- Console legendaries were reworked: each lists up to 6 affix families (item record offset 1224) with a highest affix
  level (1248) and rolls one affix from each when it drops. Legendary-only affixes name the group `0xA14D315D` and rule
  item types out through their exclusion list.
- Affix stats are the console's own formulas (small stack programs: push numbers, random range, divide), turned into
  text with the PC client's attribute descriptions.

## Rebuilding the data files

- `data/items.json`, `data/quests.json` and `data/text.json` (stat descriptions, rare name words):
  `python tools\gen_gamedata.py "<Diablo III 1.0.8 PC client folder>" data` (item names and ids are the same on PC
  1.0.8 and on console).
- `data/affixes.json` and the console parts of `items.json` (legendary affix rolls, rare name lists, which items
  exist on console):
  start Rehydrated, wait for the main menu, then `python tools\console_affixes.py`; it reads them from the running game.
  Run it after `gen_gamedata.py`.
- `tools\ingame_test.py` prepares a copy of a save folder with test items (`basic`, `affix`, `crazy`, `legend`,
  `extras`, `progress`) to check in game; `tools\ui_test.py` and `tools\ui_test2.py` run the editor's own actions on a
  copy without showing the window.

## Disclaimer

Unofficial fan tool, not affiliated with or endorsed by Blizzard Entertainment. Diablo is a trademark of Blizzard
Entertainment. Use it on your own offline saves only. It contains no game files; `data/` holds item and affix ids and
names, needed to show and create items.

MIT licensed, see `LICENSE`.
