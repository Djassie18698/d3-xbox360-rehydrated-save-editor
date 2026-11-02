# Diablo III (Xbox 360, 2013) save editor for Rehydrated

An item, affix, gold and hero level editor for the saves of **the original Xbox 360 release of Diablo III**
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

- Lists the shared stash and every hero's backpack and equipment.
- **Add item**: any normal, magic, rare or legendary item of this version, by name or type, into the backpack, straight
  into an equipment slot (the old item moves to the backpack) or into the stash. Magic and rare items get random
  affixes that fit the item; legendaries get the affixes the console rolls for that legendary (best tier). You can
  change them afterwards. Items that exist only in the PC version are not offered: the console game deletes them.
- **Affixes**: add, remove or randomize affixes. Normally you get the affixes the game can roll on that item type,
  one per family. Tick **Show all affixes (modded)** to add any affix to any item, as many copies as you like:
  copies stack, so a dagger with four times the top damage affix really does four times that damage.
  An item can hold at most **32 affixes**; with more the game disconnects you when the item loads.
- **Hero level** (1-60): sets the level and the base Strength, Dexterity, Intelligence and Vitality the hero would
  have at that level (a level 60 Wizard: 67 / 67 / 187 / 127).
- Duplicate and delete items, change stack sizes and durability, set gold.
- **Safe saving**: the editor refuses to save while Rehydrated runs (the game would overwrite the files), and copies the
  whole save folder to `d3save-backup-<date>` next to it before every save.

Tested in game: items in the backpack, equipment slots and stash; legendaries; magic and rare items with affixes
(stats apply when equipped); legendaries with their rolled affixes; 29 stacked affixes on one weapon; hero level 60 with
its stats. All of it survives the game saving the hero again.

Not supported: custom names for rare items (they use the game's default), typing exact stat numbers (stats come from
the game's affix tables; stack affixes instead), experience and Paragon levels.

## How it works

- Saves are protobuf messages XOR'd with a running key (`d3save.py`); the message definitions (`D3.Hero`,
  `D3.Items`) are the ones embedded in the game.
- Hero file field 6 is the item list; account field 20 holds partitions, whose field 3 is the shared stash and gold.
- An item is `D3.Items.SavedItem`: the slot is `(inventory slot + 17) * 16` (sint32), the square is the grid index
  `y * width + x` (sint32), and the generator holds the seed, the item gbid (sfixed32), the affix gbids (repeated
  sfixed32), durability, stack size and quality (sint32; 3-5 magic, 6-8 rare, 9 legendary).
- Console affixes are named `1xx_<name>` and their gbid is the hash of that full name, so PC affix ids do not work
  on console. `data/affixes.json` is the console's own affix table (3227 affixes).
- The hero level is the digest (hero list) plus the saved `Level` attribute (key `0x1F5F`) the game reads in play.
  Base stats are saved float attributes the game raises at each level-up: Strength `0x1EFB`, Dexterity `0x1EF7`,
  Intelligence `0x1EF3`, Vitality `0x1EDF` (level 1: 10 in the class's main stat, 9 Vitality, 8 in the others; per
  level +3 main stat, +2 Vitality, +1 others).
- Console legendaries were reworked: each lists up to 6 affix families (item record offset 1224) with a highest affix
  level (1248) and rolls one affix from each when it drops. Legendary-only affixes name the group `0xA14D315D` and rule
  item types out through their exclusion list.

## Rebuilding the data files

- `data/items.json`: `python tools\gen_gamedata.py "<Diablo III 1.0.8 PC client folder>" data` (item names and ids
  are the same on PC 1.0.8 and on console).
- `data/affixes.json` and the console parts of `items.json` (legendary affix rolls, which items exist on console):
  start Rehydrated, wait for the main menu, then `python tools\console_affixes.py`; it reads them from the running game.
  Run it after `gen_gamedata.py`.
- `tools\ingame_test.py` prepares a copy of a save folder with test items (`basic`, `affix`, `crazy`, `legend`) to check in game.

## Disclaimer

Unofficial fan tool, not affiliated with or endorsed by Blizzard Entertainment. Diablo is a trademark of Blizzard
Entertainment. Use it on your own offline saves only. It contains no game files; `data/` holds item and affix ids and
names, needed to show and create items.

MIT licensed, see `LICENSE`.
