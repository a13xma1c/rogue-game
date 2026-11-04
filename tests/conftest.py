"""Shared fixtures.

The ``arena`` fixture builds a Game on a hand-drawn map so tests can set up
exact situations instead of hunting through random levels:

    game = arena('''
        #######
        #@.+.>#
        #######
    ''')

Legend: ``#`` wall, ``.`` floor, ``@`` player (on floor), ``>``/``<`` stairs,
``+`` closed door, ``'`` open door, ``{`` fountain, ``&`` chest, and
``^`` a hidden spike trap (change ``game.map.traps[pos]`` for other kinds).
"""

from __future__ import annotations

import os

# Must be set before pygame is imported anywhere.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import functools
import textwrap

import pytest

from roguegame.dungeon import DungeonMap, Trap
from roguegame import combat
from roguegame.entities import MONSTER_KINDS, NPC, Item, Monster  # noqa: F401
from roguegame.game import Game
from roguegame.level import Level
from roguegame.tiles import (
    CHEST,
    DOOR_CLOSED,
    DOOR_OPEN,
    FLOOR,
    FOUNTAIN,
    STAIRS_DOWN,
    STAIRS_UP,
    TRAP,
    WALL,
)

LEGEND = {
    "#": WALL, ".": FLOOR, "@": FLOOR, ">": STAIRS_DOWN, "<": STAIRS_UP,
    "+": DOOR_CLOSED, "'": DOOR_OPEN, "{": FOUNTAIN, "&": CHEST, "^": TRAP,
}


def parse_map(art: str) -> tuple[DungeonMap, tuple[int, int] | None]:
    rows = [r for r in textwrap.dedent(art).strip("\n").splitlines()]
    width = max(len(r) for r in rows)
    m = DungeonMap(width, len(rows))
    m.style = "arena"
    player = None
    for y, row in enumerate(rows):
        for x, ch in enumerate(row.ljust(width, "#")):
            m.tiles[y][x] = LEGEND[ch]
            if ch == "@":
                player = (x, y)
            if ch == "^":
                m.traps[(x, y)] = Trap("spike")
    return m, player


def build_arena(art: str, depth: int = 1, seed: int = 0) -> Game:
    m, player = parse_map(art)
    assert player is not None, "arena needs an @"
    ups, downs = m.find_tiles(STAIRS_UP), m.find_tiles(STAIRS_DOWN)
    level = Level(depth, m, player, ups[0] if ups else None, downs[0] if downs else None)
    game = Game(seed=seed, first_level=level)  # no random floor 1 gets generated
    game.levels = {depth: level}
    game.depth = depth
    game.player.x, game.player.y = player
    game.log.clear()
    game._update_fov()
    return game


@pytest.fixture(autouse=True)
def isolated_scores(tmp_path, monkeypatch):
    """Never read or write the real high-score file from tests."""
    monkeypatch.setenv("ROGUEGAME_DATA", str(tmp_path / "data"))


@pytest.fixture
def arena():
    return build_arena


def add_monster(game: Game, name: str, x: int, y: int, **overrides) -> Monster:
    assert name in MONSTER_KINDS, name
    m = Monster(x, y, name, game.depth)
    for k, v in overrides.items():
        setattr(m, k, v)
    game.monsters.append(m)
    return m


def add_npc(game: Game, role: str, x: int, y: int) -> NPC:
    import random

    npc = NPC(x, y, role, random.Random(0))
    game.npcs.append(npc)
    return npc


def add_item(game: Game, kind: str, x: int, y: int, value: int = 0, name: str | None = None,
             subtype: str | None = None) -> Item:
    """Put a real item of ``kind`` on the floor at (x, y).

    Consumables default to the classic subtype (healing potion, fire scroll,
    ration); gear gets ``value`` as its bonus and ``name`` as its label."""
    from roguegame import items as I

    if kind == "gold":
        it = I.make_gold(x, y, value)
    elif kind == "ammo":
        it = I.make_ammo(x, y, value or 1)
    elif kind == "amulet":
        it = I.make_amulet(x, y)
    elif kind in ("potion", "scroll", "food", "book"):
        default = {"potion": "healing", "scroll": "fire", "food": "ration", "book": "fireball"}[kind]
        it = I.make_consumable(x, y, kind, subtype or default)
    elif kind == "weapon":
        it = I.make_weapon(x, y, value or 1, base=subtype)
    elif kind == "armor":
        it = I.make_armor(x, y, value or 1, base=subtype)
    elif kind == "launcher":
        base = subtype or "shortbow"
        _, _, reach, acc = next(b for b in I.LAUNCHERS if b[0] == base)
        it = I.make_launcher(x, y, base, value or 1, reach, acc)
    elif kind == "ring":
        import random

        it = I.make_ring(x, y, 1, random.Random(value))
    else:
        raise ValueError(kind)
    if name is not None and it.is_gear:
        it.name = name
    game.items.append(it)
    game._update_fov()
    return it


@pytest.fixture
def spawn():
    return add_monster


@pytest.fixture
def npc():
    return add_npc


@pytest.fixture
def item():
    return add_item


@pytest.fixture
def sure_hits(monkeypatch):
    """Take the dice out of combat: every attack hits, nothing crits.

    For tests about *what happens* on a hit rather than about the odds."""
    monkeypatch.setattr(combat, "hit_chance", lambda *a, **k: 1.0)
    monkeypatch.setattr(combat, "crit_chance", lambda *a, **k: 0.0)


@pytest.fixture
def sure_crits(monkeypatch):
    monkeypatch.setattr(combat, "hit_chance", lambda *a, **k: 1.0)
    monkeypatch.setattr(combat, "crit_chance", lambda *a, **k: 1.0)


@pytest.fixture
def sure_misses(monkeypatch):
    monkeypatch.setattr(combat, "hit_chance", lambda *a, **k: 0.0)


def slay_boss(game: Game) -> None:
    """Remove the current floor's boss (unsealing the stairs) via the normal kill path."""
    boss = game.level.boss
    if boss is not None and boss in game.monsters:
        game._kill(boss)


def openable(m, x: int, y: int) -> bool:
    """Passable for a player who can open things (doors, locks, portcullises,
    secret doors). Used for 'is everything reachable?' checks."""
    from roguegame.tiles import OPENABLE_IDS

    return m.pathable(x, y) or m.tile(x, y) in OPENABLE_IDS


def reachable(m, start) -> set:
    """Tiles a determined player could eventually reach from ``start``."""
    from collections import deque

    from roguegame.dungeon import DIRS8

    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in DIRS8:
            n = (x + dx, y + dy)
            if n not in seen and openable(m, *n):
                seen.add(n)
                queue.append(n)
    return seen


def all_openable(m) -> set:
    return {(x, y) for x, y in m.cells() if openable(m, x, y)}


@functools.lru_cache(maxsize=None)
def cached_level(seed: int, depth: int):
    """A generated floor, shared between tests that only *read* levels
    (generation is deterministic, so this is just a speed-up)."""
    from roguegame.level import build_level, level_rng

    return build_level(depth, level_rng(seed, depth))
