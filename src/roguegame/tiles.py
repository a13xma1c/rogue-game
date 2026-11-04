"""Tile types.

Tiles are stored in the map as small integers; everything else about a tile
(whether it can be walked on, whether it blocks sight, how it is drawn and
described) lives in the ``TILES`` table so that game logic, rendering, the
minimap and the look command all agree.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import settings as S

WALL = 0
FLOOR = 1
STAIRS_DOWN = 2
STAIRS_UP = 3
DOOR_CLOSED = 4
DOOR_OPEN = 5
TRAP = 6  # the trap itself (kind, hidden/known) lives in DungeonMap.traps
FOUNTAIN = 7
FOUNTAIN_DRY = 8
CHEST = 9
CHEST_OPEN = 10
DOOR_LOCKED = 11  # opened with a key
PORTCULLIS = 12  # iron bars: see through, can't pass; raised by a lever
PORTCULLIS_OPEN = 13
LEVER = 14
LEVER_PULLED = 15
SECRET_DOOR = 16  # looks exactly like wall until found; then becomes a closed door
SHRINE = 17
SHRINE_USED = 18
BOOKSHELF = 19
BOOKSHELF_EMPTY = 20
WATER = 21  # shallow: wade through, puts out fire
DEEP_WATER = 22  # can't cross, can see across

STAIRS = STAIRS_DOWN  # backwards-compatible alias


@dataclass(frozen=True)
class TileType:
    name: str
    walkable: bool  # an actor may stand here
    transparent: bool  # light / line of sight passes through
    glyph: str | None  # drawn on top of the floor colour; None = plain
    color: tuple[int, int, int]
    description: str
    pathable: bool | None = None  # monsters may route through (defaults to walkable)
    interactive: bool = False  # bumping into it does something

    @property
    def can_path(self) -> bool:
        return self.walkable if self.pathable is None else self.pathable


TILES: dict[int, TileType] = {
    WALL: TileType("wall", False, False, None, S.WALL_LIT, "A solid stone wall."),
    FLOOR: TileType("floor", True, True, None, S.FLOOR_LIT, "Bare stone floor."),
    STAIRS_DOWN: TileType("stairs down", True, True, ">", S.CYAN,
                          "A staircase leading down. Press Enter to descend."),
    STAIRS_UP: TileType("stairs up", True, True, "<", S.CYAN,
                        "A staircase leading up. Press Enter to climb."),
    DOOR_CLOSED: TileType("closed door", False, False, "+", (205, 150, 90),
                          "A closed wooden door. Walk into it to open it.",
                          pathable=True, interactive=True),
    DOOR_OPEN: TileType("open door", True, True, "'", S.BROWN, "An open wooden door."),
    TRAP: TileType("trap", True, True, "^", S.RED, "A trap."),
    FOUNTAIN: TileType("fountain", False, True, "{", S.BLUE,
                       "A fountain of clear, glowing water. Walk into it to drink.",
                       interactive=True),
    FOUNTAIN_DRY: TileType("dry fountain", False, True, "{", S.DARK_GREY,
                           "A dry fountain. Its magic is spent."),
    CHEST: TileType("chest", False, True, "&", S.AMBER,
                    "A closed chest. Walk into it to open it.", interactive=True),
    CHEST_OPEN: TileType("open chest", True, True, "&", S.DARK_GREY, "An empty, opened chest."),
    DOOR_LOCKED: TileType("locked door", False, False, "+", S.YELLOW,
                          "A heavy door with a brass lock. A key would open it.", pathable=False, interactive=True),
    PORTCULLIS: TileType("portcullis", False, True, "#", (170, 170, 185),
                         "An iron portcullis. You can see through it, but not pass. A lever must raise it.",
                         pathable=False, interactive=True),
    PORTCULLIS_OPEN: TileType("raised portcullis", True, True, "'", (170, 170, 185),
                              "A raised portcullis. The way is open."),
    LEVER: TileType("lever", False, True, "/", (200, 200, 210),
                    "A heavy iron lever set into the floor. Walk into it to pull it.", interactive=True),
    LEVER_PULLED: TileType("pulled lever", False, True, "\\", S.DARK_GREY,
                           "A lever, already pulled. Walk into it to push it back.", interactive=True),
    SECRET_DOOR: TileType("wall", False, False, None, S.WALL_LIT, "A solid stone wall.", pathable=False),
    SHRINE: TileType("shrine", False, True, "_", S.CYAN,
                     "A shrine humming with old power. Walk into it to pray.", interactive=True),
    SHRINE_USED: TileType("silent shrine", False, True, "_", S.DARK_GREY, "A shrine. Its power is spent."),
    BOOKSHELF: TileType("bookshelf", False, True, "|", S.BROWN,
                        "Dusty shelves of old books. Walk into it to search them.", interactive=True),
    BOOKSHELF_EMPTY: TileType("bare bookshelf", False, True, "|", S.DARK_GREY,
                              "Shelves you've already searched."),
    WATER: TileType("shallow water", True, True, "~", (80, 140, 230),
                    "Knee-deep water. Wading through it puts out flames."),
    DEEP_WATER: TileType("deep water", False, True, "~", (40, 70, 160),
                         "Dark, deep water. You can see across it, but not cross.", pathable=False),
}

# Tiles the player can get through one way or another (for connectivity checks).
OPENABLE_IDS = frozenset({DOOR_CLOSED, DOOR_LOCKED, PORTCULLIS, SECRET_DOOR})

# Trap kinds: name, glyph colour, description
TRAP_KINDS: dict[str, tuple[str, tuple[int, int, int], str]] = {
    "spike": ("spike trap", S.RED, "Hidden spikes. You can now step around it safely."),
    "alarm": ("alarm trap", S.YELLOW, "A tripwire bell. You can now step around it safely."),
    "teleport": ("teleport trap", S.PURPLE,
                 "A shimmering rune. Stepping on it will teleport you elsewhere on this floor."),
}


# Precomputed id sets for the hot paths (FOV and path finding run every turn).
WALKABLE_IDS = frozenset(t for t, tt in TILES.items() if tt.walkable)
PATHABLE_IDS = frozenset(t for t, tt in TILES.items() if tt.can_path)
OPAQUE_IDS = frozenset(t for t, tt in TILES.items() if not tt.transparent)


def tile_type(tile: int) -> TileType:
    return TILES[tile]
