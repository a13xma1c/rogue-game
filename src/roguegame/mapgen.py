"""Procedural map generators.

Layout styles:

* ``rooms``   - rectangular rooms scattered at random, joined by L-shaped
  corridors, with a few extra corridors to create loops.
* ``bsp``     - binary space partitioning: the map is split recursively into
  leaves, each holding one room; sibling subtrees are joined by corridors,
  giving an evenly spread, well-structured floor.
* ``caves``   - organic caverns grown with a cellular automaton; only the
  largest connected cave is kept. Some caves hold lakes (shallow water
  with deep, uncrossable middles).
* ``hybrid``  - caverns on one side, BSP rooms on the other, stitched
  together.

Every generator guarantees a solid outer border and that all walkable tiles
form one connected region (doors count as passable). Rooms and BSP maps get
doors where corridors meet rooms.
"""

from __future__ import annotations

import random
from collections import deque

from .dungeon import DIRS4, DIRS8, DungeonMap, Pos, Room
from .tiles import DEEP_WATER, DOOR_CLOSED, DOOR_OPEN, FLOOR, WALL, WATER

STYLES = ("rooms", "bsp", "caves", "hybrid")
STYLE_WEIGHTS = (3, 3, 2, 2)


def generate_map(width: int, height: int, depth: int, rng: random.Random) -> DungeonMap:
    """Pick a layout style for ``depth`` and generate it. The first floor is
    always built from rooms (classic or BSP) to ease you in."""
    if depth == 1:
        style = rng.choice(("rooms", "bsp"))
    else:
        style = rng.choices(STYLES, weights=STYLE_WEIGHTS)[0]
    return GENERATORS[style](width, height, rng)


# ---------------------------------------------------------------- rooms
def generate_rooms(
    width: int, height: int, rng: random.Random, max_rooms: int = 16, door_chance: float = 0.7
) -> DungeonMap:
    m = DungeonMap(width, height)
    m.style = "rooms"
    # Scale the number of rooms with the map's area (16 rooms on a 70x45 map).
    max_rooms = max(4, round(max_rooms * width * height / (70 * 45)))
    for _ in range(max_rooms * 6):
        if len(m.rooms) >= max_rooms:
            break
        w, h = rng.randint(5, 11), rng.randint(4, 8)
        x = rng.randint(1, width - w - 2)
        y = rng.randint(1, height - h - 2)
        room = Room(x, y, w, h)
        if any(room.intersects(r) for r in m.rooms):
            continue
        _carve_room(m, room)
        if m.rooms:
            _connect(m, m.rooms[-1].center, room.center, rng)
        m.rooms.append(room)

    # A few extra corridors between random rooms create loops, so the level
    # is not a strict chain and the player can outmanoeuvre monsters.
    if len(m.rooms) > 3:
        for _ in range(rng.randint(1, 3)):
            a, b = rng.sample(m.rooms, 2)
            _connect(m, a.center, b.center, rng)

    _place_doors(m, rng, door_chance)
    return m


def _carve_room(m: DungeonMap, room: Room) -> None:
    for yy in range(room.y, room.y + room.h):
        for xx in range(room.x, room.x + room.w):
            m.tiles[yy][xx] = FLOOR


def _connect(m: DungeonMap, a: Pos, b: Pos, rng: random.Random) -> None:
    (x1, y1), (x2, y2) = a, b
    if rng.random() < 0.5:
        _h_tunnel(m, x1, x2, y1)
        _v_tunnel(m, y1, y2, x2)
    else:
        _v_tunnel(m, y1, y2, x1)
        _h_tunnel(m, x1, x2, y2)


def _h_tunnel(m: DungeonMap, x1: int, x2: int, y: int) -> None:
    for x in range(min(x1, x2), max(x1, x2) + 1):
        m.tiles[y][x] = FLOOR


def _v_tunnel(m: DungeonMap, y1: int, y2: int, x: int) -> None:
    for y in range(min(y1, y2), max(y1, y2) + 1):
        m.tiles[y][x] = FLOOR


def door_candidates(m: DungeonMap) -> list[Pos]:
    """Tiles just outside a room where a one-wide corridor enters it.

    A candidate is floor on the room's outer ring, flanked by wall on both
    sides along the ring, and not inside any room.
    """
    found: set[Pos] = set()
    for r in m.rooms:
        ring: list[tuple[Pos, tuple[Pos, Pos]]] = []
        for x in range(r.x, r.x + r.w):
            for y in (r.y - 1, r.y + r.h):
                ring.append(((x, y), ((x - 1, y), (x + 1, y))))
        for y in range(r.y, r.y + r.h):
            for x in (r.x - 1, r.x + r.w):
                ring.append(((x, y), ((x, y - 1), (x, y + 1))))
        for (x, y), (s1, s2) in ring:
            if m.tile(x, y) != FLOOR or any(room.contains(x, y) for room in m.rooms):
                continue
            if m.tile(*s1) == WALL and m.tile(*s2) == WALL:
                found.add((x, y))
    return sorted(found)


def _place_doors(m: DungeonMap, rng: random.Random, chance: float) -> None:
    placed: set[Pos] = set()
    for x, y in door_candidates(m):
        if rng.random() >= chance:
            continue
        # Never put two doors side by side.
        if any((x + dx, y + dy) in placed for dx, dy in DIRS8):
            continue
        m.tiles[y][x] = DOOR_CLOSED if rng.random() < 0.75 else DOOR_OPEN
        placed.add((x, y))


# ---------------------------------------------------------------- caves
def generate_caves(
    width: int,
    height: int,
    rng: random.Random,
    fill: float = 0.45,
    steps: int = 5,
    min_floor_ratio: float = 0.30,
) -> DungeonMap:
    for _attempt in range(20):
        grid = [
            [
                WALL if x in (0, width - 1) or y in (0, height - 1) or rng.random() < fill else FLOOR
                for x in range(width)
            ]
            for y in range(height)
        ]
        for step in range(steps):
            grid = _automaton_step(grid, width, height, sparse_fill=step < 3)
        region = _largest_region(grid, width, height)
        if len(region) >= min_floor_ratio * width * height:
            break
    m = DungeonMap(width, height)
    m.style = "caves"
    for x, y in region:
        m.tiles[y][x] = FLOOR
    return m


def _automaton_step(grid: list[list[int]], width: int, height: int, sparse_fill: bool) -> list[list[int]]:
    """One round of the classic 4-5 cave rule.

    R1 counts walls in the 3x3 block around a cell (including itself), R2 in
    the 5x5 block (clipped to the map). A cell becomes wall if R1 >= 5;
    during the early ``sparse_fill`` rounds it also becomes wall if R2 <= 2,
    which seeds pillars in the middle of large open areas.
    """
    # Summed-area table: sat[y][x] = walls in grid[0:y][0:x]. Any window
    # count is then four lookups instead of 9 or 25 cell reads.
    sat = [[0] * (width + 1) for _ in range(height + 1)]
    for y in range(height):
        row_sum = 0
        above, cur, src = sat[y], sat[y + 1], grid[y]
        for x in range(width):
            row_sum += src[x] == WALL
            cur[x + 1] = above[x + 1] + row_sum

    def walls(x0: int, y0: int, x1: int, y1: int) -> int:  # inclusive box, clipped
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width - 1, x1), min(height - 1, y1)
        return sat[y1 + 1][x1 + 1] - sat[y0][x1 + 1] - sat[y1 + 1][x0] + sat[y0][x0]

    new = [row[:] for row in grid]
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            wall = walls(x - 1, y - 1, x + 1, y + 1) >= 5
            if sparse_fill and not wall:
                wall = walls(x - 2, y - 2, x + 2, y + 2) <= 2
            new[y][x] = WALL if wall else FLOOR
    return new


def _largest_region(grid: list[list[int]], width: int, height: int) -> set[Pos]:
    seen: set[Pos] = set()
    best: set[Pos] = set()
    for y in range(height):
        for x in range(width):
            if grid[y][x] != FLOOR or (x, y) in seen:
                continue
            region = {(x, y)}
            queue = deque([(x, y)])
            seen.add((x, y))
            while queue:
                cx, cy = queue.popleft()
                # 4-connectivity keeps caves from being joined only through
                # diagonal pinholes.
                for dx, dy in DIRS4:
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] == FLOOR and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        region.add((nx, ny))
                        queue.append((nx, ny))
            if len(region) > len(best):
                best = region
    return best


# ------------------------------------------------------------------ bsp
MIN_LEAF = 10  # smallest partition (width or height) that can still be split


def generate_bsp(width: int, height: int, rng: random.Random, door_chance: float = 0.7) -> DungeonMap:
    m = DungeonMap(width, height)
    m.style = "bsp"
    root = Room(1, 1, width - 2, height - 2)
    _bsp_split(m, root, rng, depth=0)
    # A few extra links between random rooms make loops.
    if len(m.rooms) > 3:
        for _ in range(rng.randint(1, 3)):
            a, b = rng.sample(m.rooms, 2)
            _connect(m, a.center, b.center, rng)
    _place_doors(m, rng, door_chance)
    return m


def _bsp_split(m: DungeonMap, leaf: Room, rng: random.Random, depth: int) -> Room:
    """Split ``leaf`` recursively; returns a room inside it (for connecting)."""
    can_h = leaf.h >= 2 * MIN_LEAF
    can_v = leaf.w >= 2 * MIN_LEAF
    # Stop splitting at random once leaves are smallish, so room sizes vary.
    if (can_h or can_v) and not (depth > 3 and leaf.w < 24 and leaf.h < 18 and rng.random() < 0.3):
        vertical = can_v and (not can_h or leaf.w / leaf.h > 1.25 or (leaf.h / leaf.w <= 1.25 and rng.random() < 0.5))
        if vertical:
            cut = rng.randint(MIN_LEAF, leaf.w - MIN_LEAF)
            a, b = Room(leaf.x, leaf.y, cut, leaf.h), Room(leaf.x + cut, leaf.y, leaf.w - cut, leaf.h)
        else:
            cut = rng.randint(MIN_LEAF, leaf.h - MIN_LEAF)
            a, b = Room(leaf.x, leaf.y, leaf.w, cut), Room(leaf.x, leaf.y + cut, leaf.w, leaf.h - cut)
        room_a = _bsp_split(m, a, rng, depth + 1)
        room_b = _bsp_split(m, b, rng, depth + 1)
        _connect(m, room_a.center, room_b.center, rng)
        return rng.choice((room_a, room_b))
    # A leaf: put a room in it, leaving a wall margin so rooms never touch.
    w = rng.randint(max(4, leaf.w // 2), max(4, leaf.w - 2))
    h = rng.randint(max(3, leaf.h // 2), max(3, leaf.h - 2))
    x = rng.randint(leaf.x + 1, leaf.x + leaf.w - w - 1)
    y = rng.randint(leaf.y + 1, leaf.y + leaf.h - h - 1)
    room = Room(x, y, w, h)
    _carve_room(m, room)
    m.rooms.append(room)
    return room


# ---------------------------------------------------------------- lakes
def add_lakes(m: DungeonMap, rng: random.Random, count: int) -> None:
    """Flood a few spots with water: shallow at the edges, deep in the middle.

    Deep water is impassable, so any deep tile whose loss would cut the map
    in two is turned back into shallow water.
    """
    floors = [(x, y) for x, y in m.cells() if m.tiles[y][x] == FLOOR]
    if not floors:
        return
    for _ in range(count):
        cx, cy = rng.choice(floors)
        radius = rng.randint(3, 6)
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if not m.in_bounds(x, y) or m.tiles[y][x] != FLOOR:
                    continue
                # A wobbly disc.
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius + rng.randint(-radius, radius):
                    m.tiles[y][x] = WATER
    for x, y in m.cells():
        if m.tiles[y][x] == WATER and all(m.tile(x + dx, y + dy) in (WATER, DEEP_WATER) for dx, dy in DIRS8):
            m.tiles[y][x] = DEEP_WATER
    # Keep everything reachable: undo deep water that disconnects the map.
    while True:
        parts = regions(m)
        if len(parts) <= 1:
            break
        main = max(parts, key=len)
        stranded = set().union(*(p for p in parts if p is not main))
        fixed = False
        for x, y in list(m.cells()):
            if m.tiles[y][x] == DEEP_WATER and any((x + dx, y + dy) in stranded for dx, dy in DIRS8):
                m.tiles[y][x] = WATER
                fixed = True
        if not fixed:  # pragma: no cover - defensive
            connect_regions(m, rng)
            break


# ----------------------------------------------------------- connectivity
def regions(m: DungeonMap) -> list[set[Pos]]:
    """Connected groups of passable tiles (8-way; doors count as passable)."""
    seen: set[Pos] = set()
    out: list[set[Pos]] = []
    for start in m.cells():
        if start in seen or not m.pathable(*start):
            continue
        group = {start}
        queue = deque([start])
        seen.add(start)
        while queue:
            x, y = queue.popleft()
            for dx, dy in DIRS8:
                n = (x + dx, y + dy)
                if n not in seen and m.pathable(*n):
                    seen.add(n)
                    group.add(n)
                    queue.append(n)
        out.append(group)
    return out


def connect_regions(m: DungeonMap, rng: random.Random) -> None:
    """Tunnel between separate regions until the whole map is one region."""
    while True:
        parts = regions(m)
        if len(parts) <= 1:
            return
        parts.sort(key=len, reverse=True)
        main, other = parts[0], parts[1]
        # Join the closest pair of tiles (sampled, to keep this cheap).
        sample_a = rng.sample(sorted(main), min(len(main), 200))
        sample_b = rng.sample(sorted(other), min(len(other), 200))
        a, b = min(((p, q) for p in sample_a for q in sample_b),
                   key=lambda pq: abs(pq[0][0] - pq[1][0]) + abs(pq[0][1] - pq[1][1]))
        _connect(m, a, b, rng)


# --------------------------------------------------------------- hybrid
def generate_hybrid(width: int, height: int, rng: random.Random) -> DungeonMap:
    caves = generate_caves(width, height, rng)
    bsp = generate_bsp(width, height, rng)
    split = rng.randint(width * 2 // 5, width * 3 // 5)
    caves_left = rng.random() < 0.5
    m = DungeonMap(width, height)
    m.style = "hybrid"
    for x, y in m.cells():
        src = caves if (x < split) == caves_left else bsp
        m.tiles[y][x] = src.tiles[y][x]
    # The seam cuts some rooms, corridors and doorways; keep what still makes sense.
    m.rooms = [r for r in bsp.rooms if all(((x < split) != caves_left) for x in (r.x, r.x + r.w - 1))]
    from .level import fix_doors

    fix_doors(m)
    connect_regions(m, rng)
    return m


def generate_caves_with_lakes(width: int, height: int, rng: random.Random) -> DungeonMap:
    m = generate_caves(width, height, rng)
    if rng.random() < 0.6:
        add_lakes(m, rng, rng.randint(1, 3))
    return m


GENERATORS = {
    "rooms": generate_rooms,
    "bsp": generate_bsp,
    "caves": generate_caves_with_lakes,
    "hybrid": generate_hybrid,
}
