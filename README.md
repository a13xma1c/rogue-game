# Rogue Game

A 2D turn-based roguelike built with Python and Pygame (pygame-ce), managed with [uv](https://docs.astral.sh/uv/).

## Run

```sh
uv sync
uv run roguegame        # or: uv run python -m roguegame
```

The game opens on a title screen where you pick the **mode**, **difficulty**, **class** and optionally a **seed**, or load a saved game (Up/Down to choose a row, Left/Right to change it, Enter to start). You can also skip the menu from the command line:

```sh
uv run roguegame --endless --difficulty hard --class mage
uv run roguegame --classic -d easy -c warrior --seed 1234   # a fixed seed replays the same dungeon
```

## Seeds and sharing

Every dungeon comes from a seed. The same seed always builds the same floors, with the same layouts, loot, monsters, quests, and potion and scroll appearances. The class doesn't change the map, so friends can race the same dungeon as different classes.

- The seed is shown in the HUD, in the pause menu (which can also copy it to the clipboard) and on the end screen, together with the exact command to replay the run:

  ```sh
  roguegame --classic -d normal -c mage --seed 2848209897
  ```

- On the title screen, select **Seed** and type a number, or any word or phrase ("dragon" is a fine seed). A typed seed is remembered for your next run from the title screen, while **R** after a run always rolls a fresh dungeon.

## Saving and loading

Press **Esc** to open the pause menu, which has Resume, Save game, Load game, Copy seed, Quit to title and Quit.

- There are three save slots. The load menu shows each save's class, level, floor, turn, mode, difficulty and seed. You can also load from the title screen.
- A saved game resumes *exactly* where it was, including the random number generator: what happens after loading is identical to what would have happened without saving.
- **File format:**
  - one line of JSON (version, summary and a SHA-256 checksum) followed by the compressed game state;
  - writes are atomic, so a crash mid-save can't destroy the old save;
  - damaged files, files that aren't saves, and saves from incompatible versions are rejected with a clear message.
- **Where saves live:** `<data dir>/saves/slot1.sav` ... `slot3.sav`, next to `scores.json` (see Scores).
- The game state is stored with Python's pickle, so only load save files you trust (your own).

## Modes

- **Classic.** Descend through 5 procedurally generated floors, defeat the orc warlord who seals floor 3, then slay the lich on floor 5 and take the Amulet of Yendor (`*`) it carries.
- **Endless.** There is no Amulet and no bottom. Floors 1-5 play exactly as in classic mode, except that the lich guards a hoard instead of the Amulet. After that:
  - The boss pattern repeats every five floors (warlord on 3, 8, 13...; lich on 5, 10, 15...).
  - Below floor 5, every monster's health and power compound per floor (+9% and +7%). This outpaces your own levelling, so every run meets its match eventually.
  - From floor 10 on, floors hold no more monsters than before, but each one is deadlier.
  - Slain bosses leave a hoard of gold and deep loot.

  The goal is to get as deep as you can. In testing, a simple bot's runs ended on floor 15 or 20, at the lich's third or fourth appearance.

## Difficulty

| | Easy | Normal | Hard |
| --- | --- | --- | --- |
| Your starting HP / potions / arrows (before class adjustments) | 40 / 3 / 15 | 30 / 1 / 10 | 25 / 0 / 6 |
| How fast you get hungry | x0.75 | x1 | x1.25 |
| Natural regeneration | 1 HP every 6 turns | every 10 | every 15 |
| Rest on reaching a new floor | 50% HP | 25% | none |
| Monster health | x0.8 | x1 | x1.25 |
| Monster power / accuracy | -1 / -5% | +0 | +1 / +5% |
| Monsters per floor | x0.75 | x1 | x1.3 |
| Trap damage | x0.5 | x1 | x1.5 |
| Score multiplier | x0.5 | x1 | x1.5 |

A floor's layout depends only on the seed, not the difficulty: the same seed gives the same map on every difficulty, with different inhabitants. In testing (20 seeds each, as an Adventurer), a bot that explores whole floors, fights, loots, eats, manages its pack and uses its skills won classic mode 20 times on Easy, 17 times on Normal and 6 times on Hard.

## Classes

| Class | Strengths | Starts with | Skill branches |
| --- | --- | --- | --- |
| Adventurer | A bit of everything | shortbow, 10 arrows | Survivor (toughness, evasion, foraging, second wind) / Dabbler (steady aim, magic missile, blink, meditation) |
| Warrior | Most HP, armor, melee | sword, leather armor | Weapon Master (brawn, power strike, cleave, executioner) / Juggernaut (toughness, iron skin, second wind, unstoppable) |
| Ranger | Accuracy, evasion, crits | longbow, 25 arrows, dagger | Marksman (steady aim, aimed shot, volley, eagle eye) / Survivalist (evasion, forager, trap sense, poison arrow) |
| Mage | Mana and spell power | dagger, 2 mana potions, Magic Missile | Evocation (magic missile, frost bolt, fireball, arcane power) / Arcana (meditation, blink, mend, mana shield) |

Everyone also starts with a ration and the difficulty's healing potions.

- **Skill points.** You get one skill point to start and one per level. Spend them in the character screen (C).
- **Tree structure.** Each skill needs the one above it in its branch, and the tiers open at character levels 1, 2, 4 and 6.
- **Passive skills** add stats, for example +8 max HP per rank of Toughness. Unstoppable makes you immune to stuns and slows.
- **Active skills** unlock an ability or spell, and further ranks make it stronger.

In testing (16-20 classic games each on Normal), the explore-and-fight bot won every game as a Ranger or Mage, 94% as a Warrior and 85% as an Adventurer.

## Scores

Every finished run is scored. Depth counts the most, then kills, level and gold, with a bonus for a classic victory, all multiplied by the difficulty's score multiplier. The best 10 runs are kept separately for each mode and difficulty, and shown on the title screen. Scores are stored in `scores.json` under your user data directory (`~/.local/share/roguegame/` on Linux, `~/Library/Application Support/roguegame/` on macOS, `%APPDATA%\roguegame\` on Windows), or under `$ROGUEGAME_DATA` if set.

## Controls

| Key | Action |
| --- | --- |
| Arrows / WASD / hjkl / yubn / numpad | Move (8 directions); walk into things to attack, talk, open doors, drink from fountains, open chests |
| Space / `.` / numpad 5 | Wait a turn and search nearby for hidden traps |
| Enter (or `>` / `<`) | Take the stairs you are standing on |
| T / F | Aim your bow: the cursor starts on the best target, Tab cycles targets, T / Enter / click fires, Esc cancels |
| I | Inventory: pick an item by letter, then `u` to use / equip / take off, `d` to drop |
| Q (or P) / R / E | Quaff a potion / read a scroll or tome / eat, from a menu of just those items |
| Z | Cast a spell or ability (targeted ones use the same aiming as the bow) |
| C | Character sheet and skill tree (Enter spends a skill point) |
| X | Look mode: move the cursor to inspect anything; Tab / Shift+Tab cycles through targets |
| Mouse | Click the map, minimap or full map to inspect a tile; hover while looking or aiming |
| M | Full-screen map |
| G | Toggle sprites / classic ASCII glyphs |
| 1-9 | Pick a dialogue option when talking to an NPC |
| ? | Help |
| J (Shift+j) | Quest journal |
| R / Enter | After a run ends: play again with the same settings / go back to the title screen |
| Esc | Close the current panel; in the main view, open the pause menu (save, load, seed, quit); on the title screen, quit |

## Features

- **Procedural floors.** Floors are 100x64 tiles, built in one of four layout styles:
  - **Rooms.** Rooms scattered at random, joined by corridors, with extra loops.
  - **BSP.** The map is split recursively (binary space partitioning) into a tree of leaves, each holding a room, and sibling branches are joined by corridors. This gives evenly spread, well-structured floors.
  - **Caverns.** Grown with a cellular automaton, often with lakes: wadeable shallows around deep, uncrossable middles.
  - **Hybrid.** Caverns on one side and BSP rooms on the other, stitched together.

  Floor 1 is always rooms or BSP.

  Every floor is fully connected. The way onwards is placed among the tiles farthest from where you arrive. Each floor is generated from its own seed, so a floor's layout depends only on the game seed and its depth, not on what you did before reaching it.
- **Persistent floors with stairs up and down.** Floors are kept exactly as you left them. You only get the rest bonus (+25% HP) the first time you reach a floor. If a monster is standing on the stairs when you arrive, it's shoved aside.
- **Vaults and special rooms.** Rooms are stamped into solid rock, each joined to the floor by a short tunnel:
  - **Vaults** hold rare loot behind either a *locked door* (an iron key lies elsewhere on the floor) or a *portcullis* you can see through (a lever elsewhere on the floor raises it).
  - **Secret rooms** hide behind a *secret door* that looks exactly like wall. A dead-end corridor is the tell: search next to it (Space) to find the door. Magic mapping and sages reveal secret doors too.
  - **Treasure rooms** hold heaps of gold and good gear, with guards.
  - **Libraries** have bookshelves to search for scrolls and tomes.

  Keys and levers are always reachable without getting into the vault they open, and none of these rooms ever blocks the way onwards.
- **Quests.** On about half the floors a **guild envoy** (a yellow `@`) offers a job:
  - slay a named *champion* (a tougher monster with a gold outline);
  - recover a lost relic, often tucked away in a secret room or vault;
  - cull a kind of monster on that floor.

  The reward (gold, experience and a named magic item) is shown when the envoy offers the job, and you get it by reporting back. Shift+J shows your quest journal.
- **Boss floors.**
  - Floor 3 is ruled by the **orc warlord**. He calls goblin reinforcements with war cries and enrages (faster, stronger) at half health.
  - Floor 5 belongs to the **lich**, who carries the Amulet. It hurls fire bolts that can set you alight, blinks away when cornered, and raises skeletons once wounded.

  Each boss waits in a pillared hall with its guards. The stairs down stay sealed until the boss falls. A health bar appears at the top of the screen once a boss is aware of you. A boss's summons crumble when it dies.
- **Combat: accuracy, dodging and critical hits.** Every attack, melee or ranged, rolls to hit (your accuracy minus the target's evasion, clamped to 5-95%; shots lose accuracy with distance).
  - A failed roll is a *dodge* if the target's evasion made the difference, otherwise a *miss*.
  - Hits can be critical, for double damage. Warhammers, ogres and the warlord stun on a critical hit.
  - Gear has traits:
    - daggers: accurate and crit-prone;
    - warhammers: stun on a critical hit;
    - plate armour: hurts your evasion;
    - dragon scale: improves your evasion;
    - crossbows: accurate.
  - Damage numbers, misses and dodges float over their targets, and projectiles fly across the screen.
- **Ranged attacks.**
  - Adventurers start with a shortbow and Rangers with a longbow (see Classes). Better bows drop as loot, and merchants sell arrows.
  - Arrows stop at the first creature in their path and won't fly through friendly NPCs.
  - Fired arrows can often be picked up again.
  - The aiming preview shows the line of fire, hit and crit chance, and damage before you commit.
  - Goblin archers, shamans and the lich shoot back.
- **Status effects.**
  - Poisoned: damage over time.
  - Burning: damage over time, and stops troll regeneration.
  - Slowed: half speed, worse evasion.
  - Stunned: lose your turns, can't dodge.
  - Blinded: sight shrinks to 2 tiles, terrible aim.

  They apply to you and to monsters. Some monsters are immune (skeletons and the lich don't care about poison). Stuns never stack, and you shrug off new stuns briefly after one ends, so there are no stun-locks. Cures:
  - potions cure poison and burning;
  - fountains and healers cure everything.

  Coloured pips over a creature show its statuses.
- **Distinct monster behaviours.** Monsters act according to their speed (fast bats and jackals sometimes act twice; lumbering ogres skip beats):

  | Monster | Behaviour |
  | --- | --- |
  | rat | Flees when badly hurt; fights when cornered |
  | goblin, orc, skeleton | Charge straight in |
  | troll | Charges in; regenerates unless burning |
  | bat | Flits erratically; hard to hit |
  | jackal | Pack hunter: hangs back when alone, howls to wake its pack, swarms with friends |
  | goblin archer | Keeps its distance and shoots; backs away when you close in |
  | goblin shaman | Heals wounded allies; hexes you with poison, slowness or blindness |
  | cave spider | Ambusher: sits motionless until you come within 3 tiles; venomous |
  | ogre | Slow brute whose critical hits stun |
  | mimic | Waits disguised as a chest |
- **Inventory and equipment.** Items go into a 20-slot pack, and potions, scrolls, food and tomes stack. You have four equipment slots: weapon, armor, bow and ring. Arrows go into a quiver and gold into your purse. Nothing is equipped automatically, since it might be cursed. The inventory screen (I) shows every item with its sprite and what you know about it.
- **Item identification.**
  - Potions and scrolls look different in every run ("ruby potion", "scroll labelled ZELGO MER"), until you learn what they are.
  - You learn a potion or scroll by using it, reading a scroll of identify, buying one from a merchant, or paying a merchant to identify everything you carry.
  - Magic gear keeps its affixes, and any curse, hidden until you equip it or identify it.
  - The look and inventory panels never reveal what you don't know.
- **Consumables.**
  - Potions: healing, greater healing, mana, haste (every other action is free), regeneration, might (permanent +1 attack). Potions of poison and blindness are the bad ones.
  - Scrolls: fire, identify, teleportation, magic mapping, enchant weapon, enchant armor, remove curse. Aggravation is the bad one: it wakes the whole floor, which then hunts you.
  - Food: apples, bread and rations.
  - Tomes: any class can read one to learn its spell.
- **Rarity and affixes.** Gear is common (white), magic (blue, 1 affix), rare (yellow, 2-3 affixes) or legendary (orange, 3-4 stronger affixes and a name of its own). Deeper floors roll rarer gear. Magic items glow with their rarity colour on the map.
  - **Affixes** include:
    - Keen, Heavy, Accurate;
    - Flaming, Venomous and Frozen (chance to burn, poison or slow on hit);
    - Vampiric (life steal);
    - Sturdy, Nimble, Arcane;
    - of the Bear (+HP), of the Magi (+mana), of Wizardry, of Regeneration, of Sustenance, of Precision, of Slaying.
  - **Curses.** From floor 2 down, about 1 in 8 magic items is cursed: it carries a harmful affix (Rusty, Clumsy, of Frailty, of Hunger, of Brittleness) and can't be removed once equipped. A scroll of remove curse or a healer fixes that.
- **Hunger.** You get hungrier every turn; the rate depends on difficulty, the Forager skill and Sustenance gear.
  - **Hungry:** a warning.
  - **Weak:** -10% accuracy, and no natural healing.
  - **Fainting:** you sometimes lose turns.
  - **Starving:** you lose HP every turn.

  Every floor has at least one piece of food, and merchants sell rations.
- **Mana and spells.** You have a mana pool that grows with level, gear and skills, and regenerates at your class's pace. Spells:
  - **Magic Missile** never misses.
  - **Frost Bolt** slows its target, but can be dodged.
  - **Fireball** hits a 3x3 area; the aiming preview shows the blast and who's in it.
  - **Blink**, **Mend** and **Mana Shield** (damage drains mana before HP).

  Class abilities use mana too:
  - Warrior: Power Strike, Cleave, Second Wind.
  - Ranger: Aimed Shot, Volley, Poison Arrow.
- **Sprites.**
  - Every character (each class, NPCs, monsters, bosses) and every item has 12x12 pixel-art sprite art, drawn in code, auto-outlined and scaled to the tile.
  - Potions are tinted with their appearance, tomes and rings with their colour, and magic gear is outlined in its rarity colour.
  - Press G for classic ASCII glyphs.
  - To use your own art, drop PNGs named after the sprite (`goblin_archer.png`, `lich.png`, `longbow.png`, ...) into `src/roguegame/assets/sprites/`.
  - `uv run python -m roguegame.sprites DIR [SCALE]` exports the built-in sprites as a starting point.
- **Interactive tiles.**
  - Doors `+` block sight. Monsters open them too. Locked doors need a key; monsters can't get through them.
  - A portcullis `#` can be seen through but not passed until its lever `/` is pulled. Pulling the lever again lowers it, but never onto someone.
  - Shrines `_` give a blessing once: restored mana, regeneration, haste, a mana shield, or the lifting of every curse.
  - Bookshelves `|` can be searched once, often yielding a scroll or a tome.
  - Shallow water `~` puts out flames (yours or a monster's). Deep water can't be crossed.
  - Fountains `{` heal once and cure afflictions.
  - Chests `&` hold gold and loot. From floor 2 down, some are mimics.
  - Hidden traps `^`:
    - Spike traps hurt you.
    - Alarm traps wake nearby monsters.
    - Teleport traps move you elsewhere on the floor, but never into a boss's hall.

  You sometimes spot a trap when you pass next to it, and waiting makes spotting much more likely. Once you know about a spike or alarm trap, you step around it. Teleport runes always fire.
- **NPCs.** Friendly characters who never fight and never block corridors:
  - Merchants sell healing potions, fire and identify scrolls, rations and arrows, and will identify everything you carry for a fee.
  - Healers restore HP, cure afflictions and lift curses, for gold.
  - Sages reveal the floor layout once and point you to the way onwards.
  - Lost adventurers share rumours (gameplay hints) and a one-time gift.
- **Minimap and full map.** Both show only what you know. Unexplored areas are blank, remembered areas are dimmed, and monsters appear only while in view.
- **Look/inspect heuristics.**
  - **Monsters:** a threat rating (harmless to deadly) from the expected number of actions each side needs to win. It accounts for hit chance, dodging, criticals, ranged attacks, your arrows and the monster's speed. Look also shows:
    - your and its hit chance;
    - its behaviour, speed and range;
    - its venom, regeneration and immunities;
    - its current statuses and health;
    - whether it is a boss or carries the Amulet.
  - **Items:** whether gear is an upgrade, including its traits.
  - **Features:** how far away things are over explored ground.
  - **Fair information:** hidden traps look like floor.
  - **Look mode starting point:** the cursor starts on the most important target in view.

## Code layout

| Module | Purpose |
| --- | --- |
| `tiles.py` | Tile types: walkability, transparency, glyphs and descriptions all come from one table |
| `dungeon.py` | `DungeonMap`: tiles, traps, field of view, path finding, distance maps |
| `mapgen.py` | Layout generators (`rooms`, `bsp`, `caves` with lakes, `hybrid`) and connectivity helpers |
| `setpieces.py` | Vaults, secret rooms, treasure rooms, libraries, quest champions |
| `quests.py` | Quest model (slay / fetch / cull) |
| `difficulty.py` | Game modes, difficulty levels (every tuning knob in one table), `GameOptions` |
| `level.py` | `Level` (one persistent floor), boss lairs and the boss cycle, and `build_level` |
| `entities.py` | Player (stats from class, gear, skills and statuses; pack; mana; hunger), monster kinds, NPCs |
| `items.py` | Items, consumable tables, gear bases, rarity, affixes, loot generation, identification |
| `classes.py` | Character classes, skills and skill trees |
| `spells.py` | Spells and abilities: numbers, targeting, effects |
| `combat.py` | Hit/dodge/crit resolution, expected-damage maths, lines of fire (pure functions) |
| `status.py` | Status effect definitions |
| `ai.py` | Monster behaviours (one function each) |
| `game.py` | Game rules and the round-based clock (no pygame) |
| `game_items.py` | Player item actions: use, equip, drop, identify, hunger (mixed into `Game`) |
| `game_magic.py` | Casting, mana regeneration and learning skills (mixed into `Game`) |
| `game_world.py` | Locks and keys, levers, secret doors, shrines, bookshelves, water, quest dialogue (mixed into `Game`) |
| `saves.py` | Save slots: header + checksum + compressed game state |
| `fonts.py` | Robust monospace font lookup (works even when pygame's font scan times out) |
| `look.py` | Look/inspect descriptions and heuristics, target ranking |
| `minimap.py` | Minimap model: what to draw per cell (no pygame) |
| `sprites.py` | Pixel-art sprites, PNG overrides, export |
| `scores.py` | High-score table (JSON, per mode and difficulty) |
| `ui.py` | `App` (title menu, input, modes, aiming, animations, score recording), `Renderer`, main loop |
| `__init__.py` | Command-line options and entry point |

## Performance

The game only recomputes or redraws what actually changed:

- **Field of view** is cached on the map. It's recomputed only when the origin, the radius or a tile within the radius changes. The tiles are compared directly, so the cache stays correct however a tile changes. Recomputing only clears the cells that were lit before, not the whole map. Standing still costs no FOV work at all; moving costs one computation per turn.
- **Drawing** uses cached layers:
  - the map view (tiles, items, actors), the HUD and the minimap are redrawn only when the game changes or the view moves;
  - cursors, aim lines, animations and panels are drawn on top each frame;
  - the minimap model is built once per change and shared by the HUD minimap and the full map.
- **How the cache knows something changed:** `Game.revision` goes up with every turn, message, level change and dialogue choice. Code that changes something visible without going through those should call `game.touch()`.

Measured on the development machine:

| | Before | After |
| --- | --- | --- |
| Idle frame | 13 ms | 0.6-1 ms |
| Full map (M) frame | 27 ms | 3 ms |
| Game turn | 1.1 ms | 0.3 ms |

Every UI mode now renders in 3 ms or less, well within the 16.7 ms a 60 FPS frame allows.

## Tests

```sh
uv run pytest                 # everything (~2.5 min)
uv run pytest -m "not slow"   # skip the long randomized simulations (~1 min)
```

The suite has no display requirement: it uses SDL's dummy video driver. It covers:

- tile rules, FOV and path finding;
- generator guarantees over many seeds;
- level population and boss lairs;
- combat odds (formulas checked exactly, dice checked statistically);
- difficulty knobs, endless mode (boss cycle, scaling, hoards) and the score table (including corrupt or unwritable files);
- the item model (stacking, identification, rarity, affixes, curses);
- every potion and scroll, equipment and curses, shops;
- hunger;
- map generators (BSP, hybrids, lakes, connectivity);
- set pieces and their tiles (keys, levers, secret doors, shrines, bookshelves, water);
- quests;
- save/load, including a saved game continuing *identically* to an unsaved one, and damaged or incompatible files;
- seeds (the same seed gives the same dungeon, typing seeds, sharing);
- classes and every skill;
- every spell and ability;
- status effects and the round-based clock;
- every monster behaviour and boss ability;
- the bow and the aiming UI;
- interactive tiles, NPCs and floor persistence;
- look heuristics and the minimap's knowledge rules;
- caching (the FOV, map view, HUD and minimap are reused when nothing changed, redrawn when something did, and never shown stale);
- sprites (data integrity, every character *and every possible item* has one, tints and rarity outlines, overrides, export);
- input and rendering in every UI mode: inventory and item prompts, character sheet, spell menu and spell targeting, the title menu, the main loop and the command line.

Fixtures in `tests/conftest.py` take the dice out of combat when a test is about *what* a hit does: `sure_hits`, `sure_crits`, `sure_misses`.

`tests/test_simulation.py` fuzzes random play (moving, shooting, drinking, taking stairs) while checking game invariants after every action. The fuzzer covers every mode, difficulty and class, uses items, skills and spells at random, and saves and reloads mid-run. A goal-seeking bot must beat both bosses and win classic mode on every seed, and must reach floor 15 in endless mode.

Tests never touch your real score or save files: an autouse fixture points `ROGUEGAME_DATA` at a temporary directory. `tests/conftest.py` also has an `arena` fixture that builds a game from ASCII art, so tests can set up exact situations:

```python
def test_bumping_a_door_opens_it(arena):
    g = arena("""
        ########
        #..@+..#
        ########
    """)
    g.player_move(1, 0)
```
