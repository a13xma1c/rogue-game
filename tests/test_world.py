"""Set pieces (vaults, secret rooms, treasure rooms, libraries) and the
interactive tiles that come with them."""

import random

import pytest

from roguegame import game_world
from roguegame.dungeon import DIRS8, DungeonMap
from roguegame.items import make_key
from roguegame.level import build_level, level_rng
from roguegame.look import describe
from roguegame.setpieces import stamp_room
from roguegame.tiles import (
    BOOKSHELF,
    BOOKSHELF_EMPTY,
    DEEP_WATER,
    DOOR_CLOSED,
    DOOR_LOCKED,
    DOOR_OPEN,
    FLOOR,
    LEVER,
    LEVER_PULLED,
    PORTCULLIS,
    PORTCULLIS_OPEN,
    SECRET_DOOR,
    SHRINE,
    SHRINE_USED,
    WALL,
    WATER,
)

from conftest import cached_level, reachable


@pytest.fixture(scope="module")
def floors():
    return [cached_level(seed, depth) for seed in range(16) for depth in (1, 2, 3, 4)]


# ------------------------------------------------------------ stamping
def test_stamp_room_carves_into_rock_with_a_tunnel():
    m = DungeonMap(40, 30)
    for x in range(2, 38):
        m.tiles[15][x] = FLOOR  # one long corridor
    rng = random.Random(1)
    room, door = stamp_room(m, rng, 5, 3)
    assert all(m.tiles[y][x] == FLOOR for x in range(room.x, room.x + room.w) for y in range(room.y, room.y + room.h))
    assert m.tile(*door) == WALL, "the doorway is left for the caller to fill in"
    m.tiles[door[1]][door[0]] = DOOR_CLOSED
    assert (room.center in reachable(m, (2, 15)))


def test_stamp_room_avoids_other_rooms_interiors():
    m = DungeonMap(40, 30)
    for x in range(2, 38):
        m.tiles[15][x] = FLOOR
    avoid = {(x, 15) for x in range(2, 38)}
    assert stamp_room(m, random.Random(1), 5, 3, avoid=avoid, tries=200) is None, "nothing else to join"


# ---------------------------------------------------------- generation
def test_vaults(floors):
    vaults = [(lvl, pc) for lvl in floors for pc in lvl.pieces if pc.kind == "vault"]
    assert {pc.lock for _, pc in vaults} == {"key", "lever"}
    for lvl, pc in vaults:
        m = lvl.map
        assert m.tile(*pc.door) == (DOOR_LOCKED if pc.lock == "key" else PORTCULLIS)
        loot = [it for it in lvl.items if pc.room.contains(it.x, it.y)]
        gear = [it for it in loot if it.is_gear]
        assert len(gear) >= 1 and any(it.kind == "gold" for it in loot)
        assert not any(pc.room.contains(mo.x, mo.y) for mo in lvl.monsters), "vaults aren't monster pens"
        # The way in is elsewhere, and reachable without getting into the vault.
        outside = reachable_without(m, lvl.start, pc.door)
        if pc.lock == "key":
            keys = [it for it in lvl.items if it.kind == "key"]
            assert keys and any((k.x, k.y) in outside for k in keys)
        else:
            levers = m.find_tiles(LEVER)
            assert levers and any(any((lx + dx, ly + dy) in outside for dx, dy in DIRS8) for lx, ly in levers)


def reachable_without(m, start, blocked):
    saved = m.tiles[blocked[1]][blocked[0]]
    m.tiles[blocked[1]][blocked[0]] = WALL
    try:
        return reachable(m, start)
    finally:
        m.tiles[blocked[1]][blocked[0]] = saved


def test_secret_rooms(floors):
    secrets = [(lvl, pc) for lvl in floors for pc in lvl.pieces if pc.kind == "secret"]
    assert secrets
    for lvl, pc in secrets:
        assert lvl.map.tile(*pc.door) == SECRET_DOOR
        treasure = [lvl.map.tile(x, y) for x, y in pc.interior()]
        assert any(t != FLOOR for t in treasure), "a chest or a shrine waits inside"
        assert any(pc.room.contains(it.x, it.y) for it in lvl.items)


def test_treasure_rooms(floors):
    rooms = [(lvl, pc) for lvl in floors for pc in lvl.pieces if pc.kind == "treasure"]
    assert rooms
    for lvl, pc in rooms:
        gold = [it for it in lvl.items if it.kind == "gold" and pc.room.contains(it.x, it.y)]
        guards = [mo for mo in lvl.monsters if pc.room.contains(mo.x, mo.y)]
        assert len(gold) >= 1 and len(guards) >= 1


def test_libraries(floors):
    libs = [(lvl, pc) for lvl in floors for pc in lvl.pieces if pc.kind == "library"]
    assert libs
    for lvl, pc in libs:
        shelves = [p for p in pc.interior() if lvl.map.tile(*p) == BOOKSHELF]
        assert 1 <= len(shelves) <= 4


def test_lakes_exist_somewhere():
    tiles = set()
    for seed in range(40):
        lvl = cached_level(seed, 3)
        tiles |= {t for row in lvl.map.tiles for t in row}
    assert {WATER, DEEP_WATER} <= tiles


# -------------------------------------------------------------- playing
WORLD = """
    ###############
    #.............#
    #.@...........#
    #.............#
    ###############
"""


def test_locked_doors_need_keys(arena):
    g = arena(WORLD)
    g.map.tiles[2][3] = DOOR_LOCKED
    g.player_move(1, 0)
    assert g.map.tile(3, 2) == DOOR_LOCKED and g.turns == 0 and "need a key" in g.log[-1][0]
    assert "You have no key" in describe(g, 3, 2).text
    g.player.add_to_pack(make_key(0, 0))
    assert "You have 1 key" in describe(g, 3, 2).text
    g.player_move(1, 0)
    assert g.map.tile(3, 2) == DOOR_OPEN and g.player.count("key", "key") == 0 and g.turns == 1


def test_keys_stack(arena):
    g = arena(WORLD)
    g.player.add_to_pack(make_key(0, 0))
    g.player.add_to_pack(make_key(0, 0))
    assert g.player.count("key", "key") == 2 and g.item_name(g.player.find("key")) == "2 iron keys"


def test_levers_raise_and_lower_every_portcullis(arena):
    g = arena(WORLD)
    g.map.tiles[1][8] = PORTCULLIS
    g.map.tiles[3][12] = PORTCULLIS
    g.map.tiles[2][3] = LEVER
    g.player_move(1, 0)
    assert "won't budge" not in g.log[-1][0]
    assert g.map.tile(3, 2) == LEVER_PULLED
    assert g.map.tile(8, 1) == PORTCULLIS_OPEN and g.map.tile(12, 3) == PORTCULLIS_OPEN
    g.player_move(1, 0)
    assert g.map.tile(3, 2) == LEVER and g.map.tile(8, 1) == PORTCULLIS


def test_portcullis_never_drops_on_anyone(arena, spawn):
    g = arena(WORLD)
    g.map.tiles[1][8] = PORTCULLIS_OPEN
    g.map.tiles[2][3] = LEVER_PULLED
    spawn(g, "rat", 8, 1)
    g.player_move(1, 0)
    assert g.map.tile(8, 1) == PORTCULLIS_OPEN


def test_portcullis_blocks_but_lets_you_see(arena):
    g = arena(WORLD)
    g.map.tiles[2][5] = PORTCULLIS
    g._update_fov()
    assert g.map.visible[2][7], "you can see through the bars"
    g.player.x = 4
    g.player_move(1, 0)
    assert g.player.x == 4 and "lever" in g.log[-1][0]


def test_monsters_cannot_pass_locks_or_gates(arena, spawn):
    g = arena(WORLD)
    for y in (1, 2, 3):
        g.map.tiles[y][6] = WALL
    g.map.tiles[2][6] = DOOR_LOCKED
    orc = spawn(g, "orc", 10, 2, alert=True)
    for _ in range(6):
        g.wait()
    assert orc.x > 6
    g.map.tiles[2][6] = PORTCULLIS
    for _ in range(4):
        g.wait()
    assert orc.x > 6


def test_secret_doors_are_found_by_searching(arena, monkeypatch):
    g = arena(WORLD)
    g.map.tiles[1][3] = SECRET_DOOR
    assert describe(g, 3, 1).title == "Wall", "indistinguishable from wall"
    monkeypatch.setattr(game_world, "SECRET_SPOT_CHANCE", 1.0)
    g.wait()
    assert g.map.tile(3, 1) == DOOR_CLOSED and "secret door" in g.log[-1][0]


def test_magic_mapping_reveals_secret_doors(arena):
    from roguegame import items as I

    g = arena(WORLD)
    g.map.tiles[1][10] = SECRET_DOOR
    g.read(g.player.add_to_pack(I.make_scroll(0, 0, "magic mapping")))
    assert g.map.tile(10, 1) == DOOR_CLOSED


def test_shrines_bless_once(arena):
    g = arena(WORLD)
    g.map.tiles[2][3] = SHRINE
    g.player.mana = 0
    g.rng = random.Random(0)
    g.player_move(1, 0)
    p = g.player
    assert g.map.tile(3, 2) == SHRINE_USED
    assert p.mana > 0 or p.statuses or "cleansed" in " ".join(m for m, _ in g.log)
    turns = g.turns
    g.player_move(1, 0)
    assert g.turns == turns, "a silent shrine is just in the way"


def test_bookshelves_are_searched_once(arena, monkeypatch):
    monkeypatch.setattr(game_world, "BOOKSHELF_FIND_CHANCE", 1.0)
    g = arena(WORLD)
    g.map.tiles[2][3] = BOOKSHELF
    pack = len(g.player.pack)
    g.player_move(1, 0)
    assert g.map.tile(3, 2) == BOOKSHELF_EMPTY and len(g.player.pack) == pack + 1
    g.player_move(1, 0)
    assert len(g.player.pack) == pack + 1


def test_water_puts_out_fire(arena, spawn):
    g = arena(WORLD)
    g.map.tiles[2][3] = WATER
    g.player.add_status("burning", 5, 2)
    g.player_move(1, 0)
    assert not g.player.has("burning") and "hisses" in " ".join(m for m, _ in g.log)
    rat = spawn(g, "rat", 5, 2, alert=True)
    rat.add_status("burning", 5)
    g.map.tiles[2][4] = WATER
    g.try_move(rat, 4, 2)
    assert not rat.has("burning")


def test_deep_water_is_impassable(arena):
    g = arena(WORLD)
    g.map.tiles[2][3] = DEEP_WATER
    g.player_move(1, 0)
    assert g.player.x == 2 and g.turns == 0


def test_teleports_never_land_in_sealed_rooms():
    from roguegame.game import Game

    def has_sealed_room(s):
        return any(pc.kind in ("vault", "secret") for pc in build_level(1, level_rng(s, 1)).pieces)

    seed = next(s for s in range(100) if has_sealed_room(s))
    g = Game(seed=seed)
    sealed = set().union(*(pc.interior() for pc in g.level.pieces if pc.kind in ("vault", "secret")))
    for _ in range(40):
        assert g._random_teleport_destination() not in sealed
