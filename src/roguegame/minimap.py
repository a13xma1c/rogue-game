"""Minimap model: what to draw for each map cell, from the player's knowledge.

This module is pure data (no pygame) so it can be tested directly; the
renderer just paints the colours it returns. It follows the same knowledge
rules as the look command: unexplored cells are blank, hidden traps look like
floor, monsters and NPCs appear only while in view, and items only once seen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import settings as S
from .look import apparent_tile
from .tiles import (
    BOOKSHELF,
    BOOKSHELF_EMPTY,
    CHEST,
    CHEST_OPEN,
    DEEP_WATER,
    DOOR_LOCKED,
    LEVER,
    LEVER_PULLED,
    PORTCULLIS,
    PORTCULLIS_OPEN,
    SECRET_DOOR,
    SHRINE,
    SHRINE_USED,
    WATER,
    DOOR_CLOSED,
    DOOR_OPEN,
    FLOOR,
    FOUNTAIN,
    FOUNTAIN_DRY,
    STAIRS_DOWN,
    STAIRS_UP,
    TRAP,
    WALL,
)

if TYPE_CHECKING:
    from .game import Game

Color = tuple[int, int, int]
Pos = tuple[int, int]

# (lit colour, remembered colour) for terrain
TERRAIN_COLORS: dict[int, tuple[Color, Color]] = {
    WALL: ((92, 86, 120), (52, 49, 68)),
    FLOOR: ((120, 110, 95), (64, 60, 54)),
    DOOR_CLOSED: (S.BROWN, (95, 65, 35)),
    DOOR_OPEN: (S.BROWN, (95, 65, 35)),
    STAIRS_DOWN: (S.CYAN, S.CYAN),  # stairs stay bright: they're landmarks
    STAIRS_UP: (S.CYAN, S.CYAN),
    TRAP: (S.RED, (150, 45, 45)),
    FOUNTAIN: (S.BLUE, (55, 95, 155)),
    FOUNTAIN_DRY: ((100, 100, 110), (70, 70, 78)),
    CHEST: (S.AMBER, (160, 112, 50)),
    CHEST_OPEN: ((100, 100, 110), (70, 70, 78)),
    DOOR_LOCKED: (S.YELLOW, (150, 130, 50)),
    PORTCULLIS: ((170, 170, 185), (110, 110, 120)),
    PORTCULLIS_OPEN: ((120, 110, 95), (64, 60, 54)),
    LEVER: ((220, 220, 230), (140, 140, 150)),
    LEVER_PULLED: ((140, 140, 150), (90, 90, 100)),
    SECRET_DOOR: ((92, 86, 120), (52, 49, 68)),  # indistinguishable from wall
    SHRINE: (S.CYAN, (60, 140, 150)),
    SHRINE_USED: ((100, 100, 110), (70, 70, 78)),
    BOOKSHELF: (S.BROWN, (95, 65, 35)),
    BOOKSHELF_EMPTY: ((100, 80, 60), (70, 55, 40)),
    WATER: ((80, 140, 230), (45, 80, 130)),
    DEEP_WATER: ((40, 70, 160), (25, 40, 90)),
}

PLAYER_COLOR = S.YELLOW
MONSTER_COLOR = S.RED
NPC_COLOR = S.GREEN


@dataclass
class Minimap:
    width: int
    height: int
    cells: list[list[Color | None]]  # None = unexplored
    markers: list[tuple[Pos, Color]]  # actors, drawn on top (player last)


def build_minimap(game: Game) -> Minimap:
    m = game.map
    cells: list[list[Color | None]] = [[None] * m.width for _ in range(m.height)]
    for y in range(m.height):
        row = cells[y]
        for x in range(m.width):
            if not m.explored[y][x]:
                continue
            lit, dim = TERRAIN_COLORS[apparent_tile(game, x, y)]
            row[x] = lit if m.visible[y][x] else dim

    for it in game.items:
        if it.seen and m.explored[it.y][it.x]:
            cells[it.y][it.x] = it.color

    markers: list[tuple[Pos, Color]] = []
    for npc in game.npcs:
        if m.visible[npc.y][npc.x]:
            markers.append(((npc.x, npc.y), NPC_COLOR))
    for mon in game.monsters:
        if mon.alive and m.visible[mon.y][mon.x]:
            markers.append(((mon.x, mon.y), MONSTER_COLOR))
    markers.append(((game.player.x, game.player.y), PLAYER_COLOR))
    return Minimap(m.width, m.height, cells, markers)
