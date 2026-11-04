"""The dungeon map: tiles, traps, field of view and path finding.

Map *generation* lives in :mod:`roguegame.mapgen`; this module only knows how
to store and query a map.
"""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass

from .tiles import (  # noqa: F401  (re-exported for convenience)
    CHEST,
    CHEST_OPEN,
    DOOR_CLOSED,
    DOOR_OPEN,
    FLOOR,
    FOUNTAIN,
    FOUNTAIN_DRY,
    OPAQUE_IDS,
    SECRET_DOOR,
    PATHABLE_IDS,
    STAIRS,
    STAIRS_DOWN,
    STAIRS_UP,
    TILES,
    TRAP,
    WALKABLE_IDS,
    WALL,
)

DIRS8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
DIRS4 = [(0, -1), (-1, 0), (1, 0), (0, 1)]

Pos = tuple[int, int]


class Room:
    def __init__(self, x: int, y: int, w: int, h: int) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h

    @property
    def center(self) -> Pos:
        return self.x + self.w // 2, self.y + self.h // 2

    def intersects(self, other: Room, pad: int = 1) -> bool:
        return (
            self.x - pad <= other.x + other.w
            and self.x + self.w + pad >= other.x
            and self.y - pad <= other.y + other.h
            and self.y + self.h + pad >= other.y
        )

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def random_point(self, rng: random.Random) -> Pos:
        return rng.randint(self.x, self.x + self.w - 1), rng.randint(self.y, self.y + self.h - 1)


@dataclass
class Trap:
    kind: str  # spike | alarm | teleport  (see tiles.TRAP_KINDS)
    known: bool = False


class DungeonMap:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.tiles = [[WALL] * width for _ in range(height)]
        self.visible = [[False] * width for _ in range(height)]
        self.explored = [[False] * width for _ in range(height)]
        self.rooms: list[Room] = []
        self.traps: dict[Pos, Trap] = {}
        self.style = "blank"
        # Field-of-view cache: what it was computed from, and which cells it lit.
        self._fov_key: tuple | None = None
        self._fov_window: list[list[int]] | None = None
        self._fov_lit: list[Pos] = []
        self.fov_computations = 0  # how many times FOV was actually recomputed (for tests/profiling)

    # --------------------------------------------------------------- queries
    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def tile(self, x: int, y: int) -> int:
        return self.tiles[y][x] if self.in_bounds(x, y) else WALL

    def walkable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and self.tiles[y][x] in WALKABLE_IDS

    def pathable(self, x: int, y: int) -> bool:
        """Like walkable, but closed doors count as passable (they can be opened)."""
        return 0 <= x < self.width and 0 <= y < self.height and self.tiles[y][x] in PATHABLE_IDS

    def blocks_sight(self, x: int, y: int) -> bool:
        return not (0 <= x < self.width and 0 <= y < self.height) or self.tiles[y][x] in OPAQUE_IDS

    def is_plain_floor(self, x: int, y: int) -> bool:
        return self.tile(x, y) == FLOOR

    def is_open_spot(self, x: int, y: int) -> bool:
        """Plain floor whose 8 neighbours are all walkable floor.

        Something standing on such a tile can never block a corridor or
        doorway, which makes these safe spots for NPCs and furniture.
        """
        if not (0 < x < self.width - 1 and 0 < y < self.height - 1):
            return False  # border tiles are never floor
        tiles = self.tiles
        if tiles[y][x] != FLOOR:
            return False
        for row in (tiles[y - 1], tiles[y], tiles[y + 1]):
            for t in (row[x - 1], row[x], row[x + 1]):
                if t != FLOOR and t != TRAP:
                    return False
        return True

    def cells(self) -> Iterator[Pos]:
        for y in range(self.height):
            for x in range(self.width):
                yield x, y

    def find_tiles(self, tile: int) -> list[Pos]:
        return [(x, y) for x, y in self.cells() if self.tiles[y][x] == tile]

    def known_trap(self, x: int, y: int) -> Trap | None:
        trap = self.traps.get((x, y))
        return trap if trap and trap.known else None

    # ------------------------------------------------------------------- FOV
    def compute_fov(self, ox: int, oy: int, radius: int) -> bool:
        """Ray-cast field of view from (ox, oy); updates ``visible`` and
        ``explored``. Returns True if it had to be recomputed.

        The result is cached: it only depends on the origin, the radius and
        the tiles within the radius, so if none of those changed since the
        last call the previous result still stands. The tiles are compared
        directly (a small window of the map), so the cache stays correct no
        matter how a tile was changed.
        """
        x0, x1 = max(0, ox - radius), min(self.width, ox + radius + 1)
        y0, y1 = max(0, oy - radius), min(self.height, oy + radius + 1)
        window = [row[x0:x1] for row in self.tiles[y0:y1]]
        key = (ox, oy, radius)
        if key == self._fov_key and window == self._fov_window:
            return False
        # Only the cells lit last time need clearing - not the whole map.
        visible = self.visible
        for x, y in self._fov_lit:
            visible[y][x] = False
        self._fov_lit = []
        self._mark(ox, oy)
        for tx in range(ox - radius, ox + radius + 1):
            self._cast(ox, oy, tx, oy - radius, radius)
            self._cast(ox, oy, tx, oy + radius, radius)
        for ty in range(oy - radius, oy + radius + 1):
            self._cast(ox, oy, ox - radius, ty, radius)
            self._cast(ox, oy, ox + radius, ty, radius)
        self._fov_key, self._fov_window = key, window
        self.fov_computations += 1
        return True

    def invalidate_fov(self) -> None:
        """Forget the cached field of view (the next compute_fov recomputes)."""
        self._fov_key = None

    def _mark(self, x: int, y: int) -> None:
        if self.in_bounds(x, y):
            if not self.visible[y][x]:
                self.visible[y][x] = True
                self._fov_lit.append((x, y))
            self.explored[y][x] = True

    def _cast(self, x0: int, y0: int, x1: int, y1: int, radius: int) -> None:
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while (x, y) != (x1, y1):
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
            if (x - x0) ** 2 + (y - y0) ** 2 > radius * radius + radius:
                return
            self._mark(x, y)
            if self.blocks_sight(x, y):
                return

    def reveal(self, find_secrets: bool = False) -> None:
        """Magic mapping: mark every non-wall tile (and the walls around them)
        explored. With ``find_secrets``, secret doors are exposed too."""
        if find_secrets:
            for x, y in self.find_tiles(SECRET_DOOR):
                self.tiles[y][x] = DOOR_CLOSED
        for x, y in self.cells():
            if self.tiles[y][x] != WALL or any(
                self.in_bounds(x + dx, y + dy) and self.tiles[y + dy][x + dx] != WALL
                for dx, dy in DIRS8
            ):
                self.explored[y][x] = True

    # ------------------------------------------------------------ path finding
    def next_step(
        self,
        start: Pos,
        goal: Pos,
        blocked: set[Pos],
        max_nodes: int = 600,
    ) -> Pos | None:
        """BFS from start to goal; returns the first step to take, if any.

        Closed doors are treated as passable (the mover opens them).
        """
        if start == goal:
            return None
        prev: dict[Pos, Pos | None] = {start: None}
        queue = deque([start])
        nodes = 0
        while queue and nodes < max_nodes:
            cur = queue.popleft()
            nodes += 1
            for dx, dy in DIRS8:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt in prev or not self.pathable(*nxt):
                    continue
                if nxt != goal and nxt in blocked:
                    continue
                prev[nxt] = cur
                if nxt == goal:
                    step = nxt
                    while prev[step] != start:
                        step = prev[step]  # type: ignore[assignment]
                    return step
                queue.append(nxt)
        return None

    def distance_map(self, start: Pos, known_only: bool = False) -> dict[Pos, int]:
        """BFS step distances (8-way) from start over pathable tiles.

        With ``known_only`` only explored tiles are traversed, which is what
        the player can reason about. (Written for speed: this runs several
        times per floor generation and for look/AI queries.)
        """
        width, height = self.width, self.height
        tiles, explored = self.tiles, self.explored
        pathable = PATHABLE_IDS
        dist = {start: 0}
        frontier = [start]
        d = 0
        while frontier:
            d += 1
            nxt_frontier = []
            for cx, cy in frontier:
                for ny in (cy - 1, cy, cy + 1):
                    if not 0 <= ny < height:
                        continue
                    row = tiles[ny]
                    seen_row = explored[ny]
                    for nx in (cx - 1, cx, cx + 1):
                        if not 0 <= nx < width or row[nx] not in pathable:
                            continue
                        if known_only and not seen_row[nx]:
                            continue
                        key = (nx, ny)
                        if key not in dist:
                            dist[key] = d
                            nxt_frontier.append(key)
            frontier = nxt_frontier
        return dist

def compass(dx: int, dy: int) -> str:
    """Rough compass direction of the vector (dx, dy); y grows southwards."""
    if dx == 0 and dy == 0:
        return "right here"
    ns = "north" if dy < 0 else "south"
    ew = "west" if dx < 0 else "east"
    # Only call it diagonal if neither axis dominates by more than ~2.4x.
    if abs(dy) > 2.4 * abs(dx):
        return ns
    if abs(dx) > 2.4 * abs(dy):
        return ew
    return f"{ns}-{ew}"
