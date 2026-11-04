"""Special rooms stamped into a generated floor.

* **Vault** - a sealed room of rare loot. Its only door is either *locked*
  (the key lies somewhere else on the floor) or a *portcullis* (raised by a
  lever somewhere else on the floor).
* **Secret room** - a small room behind a secret door (it looks like wall
  until you search next to it). A dead-end corridor is the tell.
* **Treasure room** - heaps of gold and good loot... and its guards.
* **Library** - bookshelves you can search for scrolls and tomes.
* **Shrine** - pray once for a blessing.

``stamp_room`` carves a new room into solid rock with a short tunnel to the
existing map, so it works with every layout style; carving only ever adds
floor, so the floor stays connected.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .dungeon import DungeonMap, Pos, Room
from .entities import Monster, random_monster
from .items import make_gold, make_key, random_gear
from .tiles import BOOKSHELF, CHEST, DOOR_CLOSED, DOOR_LOCKED, FLOOR, LEVER, PORTCULLIS, SECRET_DOOR, SHRINE, WALL

MAX_TUNNEL = 10


@dataclass
class SetPiece:
    kind: str  # vault | secret | treasure | library
    room: Room
    door: Pos | None = None
    lock: str = ""  # vaults: "key" or "lever"

    def interior(self) -> set[Pos]:
        r = self.room
        return {(x, y) for x in range(r.x, r.x + r.w) for y in range(r.y, r.y + r.h)}


def stamp_room(
    m: DungeonMap, rng: random.Random, w: int, h: int, avoid: set[Pos] | frozenset = frozenset(), tries: int = 400
) -> tuple[Room, Pos] | None:
    """Carve a w x h room into solid rock, joined to existing floor by a
    straight tunnel. Returns (room, doorway tile) - the doorway is left as
    wall for the caller to turn into a door of its choosing.

    The tunnel never joins a tile in ``avoid`` (the inside of other special
    rooms), so a new room is always reachable from the main floor."""
    for _ in range(tries):
        x = rng.randint(2, m.width - w - 3)
        y = rng.randint(2, m.height - h - 3)
        if any(m.tiles[yy][xx] != WALL for yy in range(y - 1, y + h + 1) for xx in range(x - 1, x + w + 1)):
            continue
        sides = [
            ((0, -1), [(xx, y - 1) for xx in range(x + 1, x + w - 1)]),
            ((0, 1), [(xx, y + h) for xx in range(x + 1, x + w - 1)]),
            ((-1, 0), [(x - 1, yy) for yy in range(y + 1, y + h - 1)]),
            ((1, 0), [(x + w, yy) for yy in range(y + 1, y + h - 1)]),
        ]
        rng.shuffle(sides)
        for (dx, dy), doors in sides:
            if not doors:
                continue
            door = rng.choice(doors)
            tunnel: list[Pos] = []
            cx, cy = door
            for _step in range(MAX_TUNNEL):
                cx, cy = cx + dx, cy + dy
                if not (1 <= cx < m.width - 1 and 1 <= cy < m.height - 1):
                    break
                tile = m.tiles[cy][cx]
                if tile == FLOOR and (cx, cy) in avoid:
                    break
                if tile == FLOOR:
                    room = Room(x, y, w, h)
                    for yy in range(y, y + h):
                        for xx in range(x, x + w):
                            m.tiles[yy][xx] = FLOOR
                    for tx, ty in tunnel:
                        m.tiles[ty][tx] = FLOOR
                    return room, door
                if tile != WALL:
                    break
                tunnel.append((cx, cy))
    return None


def _interior_spots(piece: SetPiece, rng: random.Random) -> list[Pos]:
    spots = sorted(piece.interior())
    rng.shuffle(spots)
    return spots


def taken_by_pieces(level) -> set[Pos]:
    out: set[Pos] = set()
    for pc in level.pieces:
        out |= pc.interior()
    return out


def add_vault(level, rng: random.Random, depth: int, main_spot) -> SetPiece | None:
    """A sealed room of rare loot, opened by a key or a lever found elsewhere."""
    m = level.map
    stamped = stamp_room(m, rng, rng.randint(4, 6), rng.randint(3, 4), taken_by_pieces(level))
    if stamped is None:
        return None
    room, door = stamped
    lock = rng.choice(("key", "lever"))
    m.tiles[door[1]][door[0]] = DOOR_LOCKED if lock == "key" else PORTCULLIS
    piece = SetPiece("vault", room, door, lock)
    spots = _interior_spots(piece, rng)
    for _ in range(rng.randint(1, 2)):
        x, y = spots.pop()
        gear = random_gear(x, y, depth + 1, rng)
        if gear.rarity in ("common", "magic"):
            gear = random_gear(x, y, depth + 4, rng)  # vaults hold the good stuff
        level.items.append(gear)
    for _ in range(rng.randint(1, 2)):
        x, y = spots.pop()
        level.items.append(make_gold(x, y, rng.randint(20, 40) * depth))
    # The key (or lever) goes somewhere in the main part of the floor.
    if lock == "key":
        spot = main_spot(open_only=False)
        if spot:
            level.items.append(make_key(*spot))
    else:
        spot = main_spot(open_only=True)
        if spot:
            m.tiles[spot[1]][spot[0]] = LEVER
    return piece


def add_secret_room(level, rng: random.Random, depth: int) -> SetPiece | None:
    m = level.map
    stamped = stamp_room(m, rng, rng.randint(3, 4), 3, taken_by_pieces(level))
    if stamped is None:
        return None
    room, door = stamped
    m.tiles[door[1]][door[0]] = SECRET_DOOR
    piece = SetPiece("secret", room, door)
    cx, cy = room.center
    if rng.random() < 0.6:
        m.tiles[cy][cx] = CHEST
    else:
        m.tiles[cy][cx] = SHRINE
    spots = [p for p in _interior_spots(piece, rng) if p != (cx, cy)]
    x, y = spots.pop()
    level.items.append(random_gear(x, y, depth + 2, rng))
    return piece


def add_treasure_room(level, rng: random.Random, depth: int, candidates: list[Room], prepare) -> SetPiece | None:
    """Gold and loot under guard - in an existing room if one fits, else a new one."""
    m = level.map
    if candidates:
        room = rng.choice(candidates)
        door = None
    else:
        stamped = stamp_room(m, rng, rng.randint(4, 6), rng.randint(3, 4), taken_by_pieces(level))
        if stamped is None:
            return None
        room, door = stamped
        m.tiles[door[1]][door[0]] = DOOR_CLOSED
    piece = SetPiece("treasure", room, door)
    spots = [p for p in _interior_spots(piece, rng) if m.tiles[p[1]][p[0]] == FLOOR]
    for _ in range(min(len(spots) // 3, rng.randint(3, 5))):
        x, y = spots.pop()
        level.items.append(make_gold(x, y, rng.randint(10, 25) * depth))
    if spots:
        x, y = spots.pop()
        level.items.append(random_gear(x, y, depth + 2, rng))
    for _ in range(rng.randint(2, 3)):
        if spots:
            x, y = spots.pop()
            level.monsters.append(prepare(random_monster(x, y, depth, rng)))
    return piece


def add_library(level, rng: random.Random, candidates: list[Room]) -> SetPiece | None:
    """Fill a room with bookshelves - only on open spots, so nothing gets blocked."""
    m = level.map
    for room in rng.sample(candidates, len(candidates)):
        piece = SetPiece("library", room)
        spots = [p for p in _interior_spots(piece, rng) if m.is_open_spot(*p)]
        if len(spots) < 2:
            continue
        placed = 0
        for x, y in spots:
            if placed >= rng.randint(2, 4):
                break
            if m.is_open_spot(x, y):  # re-check: a neighbouring shelf may have taken the room
                m.tiles[y][x] = BOOKSHELF
                placed += 1
        if placed:
            return piece
    return None


def place_champion(level, rng: random.Random, depth: int, spot: Pos, prepare) -> Monster:
    """A named, tougher version of a floor monster, for slaying quests."""
    from .quests import champion_name

    m = prepare(random_monster(spot[0], spot[1], depth, rng))
    m.max_hp = m.hp = m.max_hp * 2
    m.base_power += 2
    m.xp_value *= 3
    m.title = champion_name(m.name, rng)
    level.monsters.append(m)
    return m
