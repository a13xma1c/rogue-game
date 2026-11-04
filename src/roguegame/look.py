"""Look / inspect: describe what the player knows about a tile.

Only information the player could actually have is reported:

* tiles never seen are "unexplored";
* explored tiles out of view are described from memory (terrain and items
  the player has seen - monsters move, so they are never remembered);
* hidden traps look exactly like floor.

On top of plain descriptions a few heuristics help the player decide what to
do: a threat estimate for monsters, gear comparison for items, and a
walking-distance estimate over known territory. ``interesting_targets``
ranks what is in view so the look cursor can jump straight to what matters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import settings as S
from .combat import expected_attack, expected_damage, hit_chance  # noqa: F401  (expected_damage re-exported)
from .dungeon import DIRS8, Pos
from .entities import NPC, Actor, Item, Monster, Player
from .items import AFFIXES, affix_text
from .tiles import (
    SECRET_DOOR,
    DOOR_LOCKED,
    CHEST,
    FLOOR,
    FOUNTAIN,
    STAIRS_DOWN,
    STAIRS_UP,
    TILES,
    TRAP,
    TRAP_KINDS,
    WALL,
)

if TYPE_CHECKING:
    from .game import Game

Color = tuple[int, int, int]

VISIBLE, REMEMBERED, UNKNOWN = "visible", "remembered", "unknown"


@dataclass
class Inspection:
    title: str
    color: Color
    lines: list[tuple[str, Color]] = field(default_factory=list)

    def add(self, text: str, color: Color = S.WHITE) -> None:
        self.lines.append((text, color))

    @property
    def text(self) -> str:
        """Plain text of the whole inspection (handy for tests and logs)."""
        return "\n".join([self.title, *(t for t, _ in self.lines)])


# ------------------------------------------------------------------ threat
@dataclass(frozen=True)
class Threat:
    label: str
    color: Color
    hits_to_kill: int  # your expected hits to kill it
    hits_to_die: int  # its expected hits to kill you
    ratio: float  # hits_to_die / hits_to_kill; > 1 means you win the race


THREAT_LEVELS: list[tuple[float, str, Color]] = [
    # (minimum ratio, label, colour) - checked top to bottom
    (4.0, "harmless", S.GREEN),
    (2.0, "easy", S.GREEN),
    (1.2, "fair fight", S.YELLOW),
    (0.8, "dangerous", S.ORANGE),
    (0.0, "deadly", S.RED),
]


def best_attack(attacker: Actor, defender: Actor) -> float:
    """Expected damage per action of the attacker's better option (melee or
    shooting from range), counting misses, dodges and criticals."""
    from .combat import distance

    options = [expected_attack(attacker, defender)]
    can_shoot = attacker.shot_range > 0 and (not isinstance(attacker, Player) or attacker.arrows > 0)
    if can_shoot:
        d = max(2, distance((attacker.x, attacker.y), (defender.x, defender.y)))
        options.append(expected_attack(attacker, defender, ranged=True, dist=min(d, attacker.shot_range)))
    return max(options)


def assess_threat(player: Actor, monster: Actor) -> Threat:
    """Compare how many actions each side needs to finish the other.

    Uses expected damage per action (hit chance x damage x crit bonus), and
    scales the monster's side by its speed: a fast monster acts more often.
    """
    per_round = best_attack(monster, player) * getattr(monster, "speed", 100) / 100
    hits_to_kill = max(1, math.ceil(monster.hp / max(0.01, best_attack(player, monster))))
    hits_to_die = max(1, math.ceil(max(1, player.hp) / max(0.01, per_round)))
    ratio = hits_to_die / hits_to_kill
    for minimum, label, color in THREAT_LEVELS:
        if ratio >= minimum:
            return Threat(label, color, hits_to_kill, hits_to_die, ratio)
    raise AssertionError("unreachable")  # pragma: no cover


def health_word(actor: Actor) -> str:
    frac = actor.hp / actor.max_hp
    if frac >= 1:
        return "unhurt"
    if frac >= 0.6:
        return "lightly wounded"
    if frac >= 0.3:
        return "badly wounded"
    return "almost dead"


# ------------------------------------------------------------------ items
def item_advice(player: Player, item: Item, depth: int, ident=None) -> tuple[str, Color]:
    """One-line verdict on an item. ``ident`` (the game's Identification)
    hides what the player doesn't know yet; without it, everything is known."""
    from .items import CONSUMABLES, FOODS

    known = ident is None or ident.is_known(item)
    if item.kind == "gold":
        return f"{item.value} gold coins. Merchants will want these.", S.YELLOW
    if item.kind in ("potion", "scroll") and not known:
        verb = "Drink" if item.kind == "potion" else "Read"
        return f"Unknown. {verb} it to find out - or identify it first.", S.GREY
    if item.kind == "potion":
        if item.subtype == "healing":
            return f"Heals up to {15 + depth * 3} HP. You carry {player.potions}.", S.GREEN
        spec = CONSUMABLES["potion"][item.subtype]
        return spec.description, S.RED if spec.harmful else S.GREEN
    if item.kind == "scroll":
        if item.subtype == "fire":
            return f"Burns every foe in sight for {8 + depth * 3}. You carry {player.scrolls}.", S.ORANGE
        spec = CONSUMABLES["scroll"][item.subtype]
        return spec.description, S.RED if spec.harmful else S.ORANGE
    if item.kind == "food":
        state = player.hunger_state or "not hungry"
        return f"Food: +{FOODS[item.subtype].nutrition} nourishment. You are {state.lower()}.", (200, 160, 90)
    if item.kind == "book":
        from .spells import SPELLS, describe

        spell = SPELLS[item.subtype]
        if player.spells.get(item.subtype):
            return f"You already know {spell.name}.", S.GREY
        return f"Teaches {spell.name} ({spell.cost} mana): {describe(item.subtype, 1, player.spell_power)}", S.PURPLE
    if item.kind == "ammo":
        return f"{item.value} arrow{'s' if item.value != 1 else ''}. You carry {player.arrows}.", S.WHITE
    if item.kind == "ring":
        if not known:
            return "A magic ring of unknown power. Wear it or identify it to learn more.", S.GREY
        return "A magic ring: " + "; ".join(affix_text(k, v) for k, v in item.affixes) + ".", S.CYAN
    if item.kind in ("weapon", "armor", "launcher"):
        current = {"weapon": player.weapon, "armor": player.armor, "launcher": player.launcher}[item.kind]
        if current is item:
            return "You have it equipped.", S.CYAN
        stat = {"weapon": "ATK", "armor": "DEF", "launcher": "ranged ATK"}[item.kind]
        have = current.value if current else 0
        have_name = current.name if current else {"weapon": "bare fists", "armor": "no armor",
                                                  "launcher": "no bow"}[item.kind]
        diff = item.value - have
        traits = gear_traits(item)
        if diff > 0:
            return f"Upgrade: +{diff} {stat} over your {have_name}.{traits}", S.GREEN
        return f"No better than your {have_name}.{traits}", S.GREY
    if item.kind == "amulet":
        return "The object of your quest! Pick it up to win.", S.PURPLE
    return "", S.WHITE


def item_lines(game: Game, item: Item) -> list[tuple[str, Color]]:
    """Everything the player knows about ``item``, for the look panel and the
    inventory screen."""
    from .items import RARITIES

    known = game.ident.is_known(item)
    lines = [item_advice(game.player, item, game.depth, game.ident)]
    if item.is_gear:
        rarity = RARITIES[item.rarity]
        if item.rarity != "common":
            lines.append((f"{item.rarity.capitalize()} item.", rarity.color))
        if known and item.affixes and item.kind != "ring":
            for key, value in item.affixes:
                color = S.RED if AFFIXES[key].curse else S.CYAN
                lines.append((f"  {AFFIXES[key].label}: {affix_text(key, value)}", color))
        elif not known:
            lines.append(("Unidentified: its magic - and any curse - is hidden until you wear it "
                          "or identify it.", S.GREY))
        if known and item.cursed:
            lines.append(("Cursed: once equipped it can't be removed.", S.RED))
    return lines


def gear_traits(item: Item) -> str:
    """Secondary stats of a piece of gear, e.g. ' (accuracy +5%, crit +10%)'."""
    parts = []
    if item.accuracy:
        parts.append(f"accuracy {item.accuracy:+d}%")
    if item.evasion:
        parts.append(f"evasion {item.evasion:+d}%")
    if item.crit:
        parts.append(f"crit {item.crit:+d}%")
    if item.effect == "stun":
        parts.append("criticals stun")
    if item.range:
        parts.append(f"range {item.range}")
    return f" ({', '.join(parts)})" if parts else ""


def status_summary(actor: Actor) -> str:
    return ", ".join(f"{name} ({st.turns})" for name, st in actor.statuses.items())


# -------------------------------------------------------------- knowledge
def knowledge(game: Game, x: int, y: int) -> str:
    m = game.map
    if not m.in_bounds(x, y) or not m.explored[y][x]:
        return UNKNOWN
    return VISIBLE if m.visible[y][x] else REMEMBERED


def apparent_tile(game: Game, x: int, y: int) -> int:
    """The tile as the player believes it to be (hidden traps look like floor)."""
    tile = game.map.tile(x, y)
    if tile == TRAP and not game.map.known_trap(x, y):
        return FLOOR
    if tile == SECRET_DOOR:
        return WALL
    return tile


def tile_description(game: Game, x: int, y: int) -> tuple[str, str, Color]:
    """(name, description, colour) of the apparent terrain at (x, y)."""
    tile = apparent_tile(game, x, y)
    tt = TILES[tile]
    if tile == TRAP:
        trap = game.map.traps[(x, y)]
        name, color, desc = TRAP_KINDS[trap.kind]
        return name, desc, color
    name, desc = tt.name, tt.description
    if tile == STAIRS_DOWN:
        target = game.depth + 1
        seen = "visited" if target in game.levels else "unexplored"
        desc = f"Stairs down to floor {target} ({seen}). Press Enter to descend."
        if game.level.sealed and game.level.boss:
            desc = f"Stairs down to floor {target}, sealed by dark magic until the {game.level.boss.name} falls."
    elif tile == STAIRS_UP:
        desc = f"Stairs up to floor {game.depth - 1}. Press Enter to climb."
    elif tile == FOUNTAIN:
        p = game.player
        if p.hp < p.max_hp:
            heal = min(p.max_hp - p.hp, max(10, p.max_hp // 2))
            desc += f" Drinking now would restore {heal} HP."
        else:
            desc += " You're at full health - save it for later."
    elif tile == CHEST and game.depth >= 2:
        desc += " At this depth, some chests are mimics."
    elif tile == DOOR_LOCKED:
        keys = game.player.count("key", "key")
        desc += f" You have {keys} key{'s' if keys != 1 else ''}." if keys else " You have no key."
    return name, desc, tt.color if tt.glyph else S.GREY


def route_length(game: Game, x: int, y: int, dist: dict[Pos, int] | None = None) -> int | None:
    """Steps needed to reach (x, y) - or to stand next to it, if it cannot be
    entered - walking only over explored territory."""
    p = game.player
    if dist is None:
        dist = game.map.distance_map((p.x, p.y), known_only=True)
    if (x, y) in dist:
        return dist[(x, y)]
    around = [dist[(x + dx, y + dy)] for dx, dy in DIRS8 if (x + dx, y + dy) in dist]
    return min(around) + 1 if around else None


# --------------------------------------------------------------- describe
def describe(game: Game, x: int, y: int, dist: dict[Pos, int] | None = None) -> Inspection:
    """Describe tile (x, y) from the player's point of view.

    ``dist`` may be a precomputed ``distance_map(player, known_only=True)``
    to avoid repeating the search when describing many tiles.
    """
    seen = knowledge(game, x, y)
    if seen == UNKNOWN:
        return Inspection("Unexplored", S.GREY, [("You haven't seen this place yet.", S.GREY)])

    p = game.player
    tname, tdesc, tcolor = tile_description(game, x, y)

    if (x, y) == (p.x, p.y):
        insp = Inspection("You", S.YELLOW)
        insp.add(f"HP {p.hp}/{p.max_hp}, ATK {p.power}, DEF {p.defense}, level {p.level}.")
        insp.add(f"Accuracy {p.accuracy}%, evasion {p.evasion}%, crit {p.crit_chance}%.", S.GREY)
        if p.statuses:
            insp.add(f"You are {status_summary(p)}.", S.ORANGE)
        if tname != "floor":
            insp.add(f"You are standing on: {tname}.", tcolor)
            insp.add(tdesc, S.GREY)
        underfoot = game.item_at(x, y)
        if underfoot:
            advice, color = item_advice(p, underfoot, game.depth, game.ident)
            insp.add(f"There is a {game.item_name(underfoot)} here. {advice}", color)
        return insp

    if seen == VISIBLE:
        monster = game.monster_at(x, y)
        if monster:
            return _describe_monster(game, monster, tname, dist)
        npc = game.npc_at(x, y)
        if npc:
            return _describe_npc(game, npc, dist)

    item = game.item_at(x, y)
    if item and item.seen:
        name = game.item_name(item)
        insp = Inspection(name[:1].upper() + name[1:], game.item_color(item))
        if seen == REMEMBERED:
            insp.add("(remembered - out of sight)", S.DARK_GREY)
        for text, color in item_lines(game, item):
            insp.add(text, color)
        if tname != "floor":
            insp.add(f"Lying on: {tname}.", S.GREY)
    else:
        insp = Inspection(tname.capitalize(), tcolor)
        if seen == REMEMBERED:
            insp.add("(remembered - out of sight)", S.DARK_GREY)
        insp.add(tdesc, S.GREY)

    if apparent_tile(game, x, y) != WALL:
        _add_route(game, insp, x, y, dist)
    return insp


def _add_route(game: Game, insp: Inspection, x: int, y: int, dist: dict[Pos, int] | None) -> None:
    steps = route_length(game, x, y, dist)
    if steps is None:
        insp.add("No known route there yet.", S.DARK_GREY)
    else:
        insp.add(f"About {steps} step{'s' if steps != 1 else ''} away.", S.DARK_GREY)


def _describe_monster(game: Game, m: Monster, tname: str, dist: dict[Pos, int] | None) -> Inspection:
    from .ai import DESCRIPTIONS

    p = game.player
    threat = assess_threat(p, m)
    boss = "BOSS: " if m.is_boss else ""
    insp = Inspection(f"{boss}{m.name.capitalize()} - {threat.label}", threat.color)
    awareness = "hunting you" if m.alert else "unaware of you"
    insp.add(f"HP {m.hp}/{m.max_hp} ({health_word(m)}), {awareness}.")
    insp.add(
        f"You need ~{threat.hits_to_kill} attack{'s' if threat.hits_to_kill != 1 else ''}; "
        f"it needs ~{threat.hits_to_die} to kill you.",
        threat.color,
    )
    mine = hit_chance(p, m)
    theirs = hit_chance(m, p, ranged=m.shot_range > 0, dist=2 if m.shot_range else 1)
    insp.add(f"Your hit chance {mine:.0%}; its hit chance {theirs:.0%}.", S.GREY)
    traits = [DESCRIPTIONS.get(m.ai, "")]
    if m.speed > 100:
        traits.append("Fast.")
    elif m.speed < 100:
        traits.append("Slow.")
    if m.shot_range:
        traits.append(f"Attacks from up to {m.shot_range} tiles.")
    if m.kind.on_hit:
        traits.append(f"Its attacks can leave you {m.kind.on_hit[0]}.")
    if m.kind.regen:
        traits.append("Regenerates unless burning.")
    if m.immune:
        traits.append(f"Immune to: {', '.join(sorted(m.immune))}.")
    insp.add(" ".join(t for t in traits if t), S.CYAN)
    if m.statuses:
        insp.add(f"It is {status_summary(m)}.", S.ORANGE)
    if m.carries_amulet:
        insp.add("It carries the Amulet of Yendor!", S.PURPLE)
    others = [o for o in game.monsters if o is not m and o.alive and game.visible(o.x, o.y)]
    if others:
        insp.add(f"{len(others)} other foe{'s' if len(others) != 1 else ''} in view.", S.ORANGE)
    if tname != "floor":
        insp.add(f"It stands on: {tname}.", S.GREY)
    _add_route(game, insp, m.x, m.y, dist)
    return insp


NPC_BLURBS = {
    "merchant": "Sells potions and scrolls.",
    "healer": "Will heal your wounds for a donation.",
    "sage": "Knows the layout of this floor.",
    "wanderer": "Might share a rumour or two.",
}


def _describe_npc(game: Game, npc: NPC, dist: dict[Pos, int] | None) -> Inspection:
    insp = Inspection(npc.display_name, npc.color)
    insp.add(f"Friendly. {NPC_BLURBS.get(npc.role, '')} Walk into them to talk.", S.GREEN)
    if npc.role in ("merchant", "healer"):
        insp.add(f"You have {game.player.gold} gold.", S.YELLOW)
    if npc.role == "sage" and npc.used:
        insp.add("They have already shared their map.", S.GREY)
    _add_route(game, insp, npc.x, npc.y, dist)
    return insp


# ---------------------------------------------------------------- targets
def interesting_targets(game: Game) -> list[Pos]:
    """Positions worth looking at, most important first.

    Order: visible monsters (most dangerous & closest first), friendly NPCs,
    items, notable features in view, then remembered stairs.
    """
    p = game.player
    m = game.map

    def cheb(x: int, y: int) -> int:
        return max(abs(x - p.x), abs(y - p.y))

    def monster_priority(mon: Monster) -> float:
        threat = assess_threat(p, mon)
        danger = 1 / threat.ratio
        if mon.alert:
            danger *= 1.5
        return -danger * 10 / (1 + cheb(mon.x, mon.y))

    monsters = sorted(
        (mon for mon in game.monsters if mon.alive and m.visible[mon.y][mon.x]), key=monster_priority
    )
    npcs = sorted((n for n in game.npcs if m.visible[n.y][n.x]), key=lambda n: cheb(n.x, n.y))
    items = sorted(
        (it for it in game.items if m.visible[it.y][it.x]),
        key=lambda it: (it.kind != "amulet", cheb(it.x, it.y)),
    )
    notable = {STAIRS_DOWN, STAIRS_UP, FOUNTAIN, CHEST, TRAP}
    features: list[Pos] = []
    remembered_stairs: list[Pos] = []
    for x, y in m.cells():
        if not m.explored[y][x] or (x, y) == (p.x, p.y):
            continue
        tile = apparent_tile(game, x, y)
        if tile not in notable:
            continue
        if m.visible[y][x]:
            features.append((x, y))
        elif tile in (STAIRS_DOWN, STAIRS_UP):
            remembered_stairs.append((x, y))
    features.sort(key=lambda q: cheb(*q))
    remembered_stairs.sort(key=lambda q: cheb(*q))

    out: list[Pos] = []
    for pos in [
        *((a.x, a.y) for a in monsters),
        *((n.x, n.y) for n in npcs),
        *((it.x, it.y) for it in items),
        *features,
        *remembered_stairs,
    ]:
        if pos not in out:
            out.append(pos)
    return out


def shootable_targets(game: Game) -> list[Pos]:
    """Monsters you could hit with an arrow right now, best target first.

    Uses the same danger/proximity ordering as ``interesting_targets`` and
    keeps only monsters the arrow would actually reach (in range, nothing in
    the way)."""
    out = []
    for pos in interesting_targets(game):
        mon = game.monster_at(*pos)
        if mon is None:
            continue
        plan = game.plan_shot(*pos)
        if plan.ok and plan.target is mon:
            out.append(pos)
    return out
