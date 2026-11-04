"""Procedural generation: structural guarantees checked over many seeds."""

import random
from collections import deque

import pytest

from roguegame.dungeon import DIRS8, DungeonMap
from roguegame.mapgen import STYLES, GENERATORS, door_candidates, generate_caves, generate_map, generate_rooms
from roguegame.tiles import DEEP_WATER, DOOR_CLOSED, DOOR_OPEN, FLOOR, TILES, WALL, WATER

from conftest import parse_map

SEEDS = range(25)
W, H = 70, 45


def reachable(m: DungeonMap, start) -> set:
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in DIRS8:
            n = (x + dx, y + dy)
            if n not in seen and m.pathable(*n):
                seen.add(n)
                queue.append(n)
    return seen


def passable_tiles(m: DungeonMap) -> set:
    return {(x, y) for x, y in m.cells() if m.pathable(x, y)}


@pytest.mark.parametrize("style", sorted(GENERATORS))
@pytest.mark.parametrize("seed", SEEDS)
def test_generated_maps_are_sound(style, seed):
    m = GENERATORS[style](W, H, random.Random(seed))
    assert m.style == style
    assert (m.width, m.height) == (W, H)
    # Solid border: nothing can walk (or see) off the edge of the map.
    for x in range(W):
        assert m.tiles[0][x] == WALL and m.tiles[H - 1][x] == WALL
    for y in range(H):
        assert m.tiles[y][0] == WALL and m.tiles[y][W - 1] == WALL
    # Single connected region (doors count as passable).
    tiles = passable_tiles(m)
    assert tiles
    assert reachable(m, next(iter(tiles))) == tiles
    # Only terrain the generator is supposed to emit.
    assert {t for row in m.tiles for t in row} <= {WALL, FLOOR, DOOR_CLOSED, DOOR_OPEN, WATER, DEEP_WATER}
    # Nothing starts explored.
    assert not any(any(row) for row in m.explored)


@pytest.mark.parametrize("seed", SEEDS)
def test_room_maps(seed):
    m = generate_rooms(W, H, random.Random(seed))
    assert len(m.rooms) >= 6
    for i, a in enumerate(m.rooms):
        assert m.tile(*a.center) == FLOOR
        for b in m.rooms[i + 1:]:
            assert not a.intersects(b, pad=0), "rooms must not overlap"
    ratio = len(passable_tiles(m)) / (W * H)
    assert 0.15 < ratio < 0.6


@pytest.mark.parametrize("seed", SEEDS)
def test_doors_sit_in_doorways(seed):
    m = generate_rooms(W, H, random.Random(seed))
    doors = m.find_tiles(DOOR_CLOSED) + m.find_tiles(DOOR_OPEN)
    for x, y in doors:
        horizontal_walls = m.tile(x - 1, y) == WALL and m.tile(x + 1, y) == WALL
        vertical_walls = m.tile(x, y - 1) == WALL and m.tile(x, y + 1) == WALL
        assert horizontal_walls or vertical_walls, f"door at {(x, y)} is not in a 1-wide gap"
        assert not any(r.contains(x, y) for r in m.rooms), "doors are never inside rooms"
        for dx, dy in DIRS8:
            assert m.tile(x + dx, y + dy) not in (DOOR_CLOSED, DOOR_OPEN), "no double doors"


def test_doors_appear_across_seeds():
    total = sum(len(generate_rooms(W, H, random.Random(s)).find_tiles(DOOR_CLOSED)) for s in SEEDS)
    assert total > len(SEEDS), "doors should be common"


def test_door_chance_zero_gives_no_doors():
    m = generate_rooms(W, H, random.Random(1), door_chance=0.0)
    assert not m.find_tiles(DOOR_CLOSED) and not m.find_tiles(DOOR_OPEN)


def test_door_candidates_on_handmade_map():
    from roguegame.dungeon import Room

    m, _ = parse_map("""
        ###########
        #....#....#
        #@...#....#
        #.........#
        #....#....#
        ###########
    """)
    m.rooms = [Room(1, 1, 4, 4), Room(6, 1, 4, 4)]
    assert door_candidates(m) == [(5, 3)]


@pytest.mark.parametrize("seed", SEEDS)
def test_cave_maps(seed):
    m = generate_caves(W, H, random.Random(seed))
    assert m.rooms == []
    ratio = len(passable_tiles(m)) / (W * H)
    assert 0.3 <= ratio < 0.8, "caves should be roomy but not one big hall"
    # The cellular automaton should leave some interior pillars/walls.
    interior_walls = sum(m.tiles[y][x] == WALL for y in range(2, H - 2) for x in range(2, W - 2))
    assert interior_walls > 100


@pytest.mark.parametrize("style", sorted(GENERATORS))
def test_generation_is_deterministic(style):
    a = GENERATORS[style](W, H, random.Random(42))
    b = GENERATORS[style](W, H, random.Random(42))
    c = GENERATORS[style](W, H, random.Random(43))
    assert a.tiles == b.tiles
    assert a.tiles != c.tiles


def test_first_floor_is_always_built_from_rooms():
    styles = {generate_map(W, H, 1, random.Random(seed)).style for seed in SEEDS}
    assert styles == {"rooms", "bsp"}


def test_deeper_floors_use_every_style():
    styles = {generate_map(W, H, depth, random.Random(seed)).style for seed in range(20) for depth in (2, 3)}
    assert styles == set(STYLES)


def test_every_style_uses_only_known_tiles():
    for style, gen in GENERATORS.items():
        m = gen(W, H, random.Random(0))
        assert all(t in TILES for row in m.tiles for t in row), style


# ------------------------------------------------------------ bsp, hybrid, lakes
@pytest.mark.parametrize("seed", range(10))
def test_bsp_rooms_are_separate_and_spread_out(seed):
    from roguegame.mapgen import generate_bsp

    m = generate_bsp(100, 64, random.Random(seed))
    assert len(m.rooms) >= 12
    for i, a in enumerate(m.rooms):
        for b in m.rooms[i + 1:]:
            assert not a.intersects(b, pad=0)
    # Partitioning spreads rooms over the whole map: every quadrant has one.
    quads = {(r.center[0] >= 50, r.center[1] >= 32) for r in m.rooms}
    assert len(quads) == 4


def test_hybrid_maps_have_rooms_and_caves():
    from roguegame.mapgen import generate_hybrid

    for seed in range(4):
        m = generate_hybrid(100, 64, random.Random(seed))
        assert m.style == "hybrid" and m.rooms, "the BSP half keeps its rooms"
        # Caves are ragged: lots of floor tiles with wall neighbours on odd sides.
        ragged = sum(1 for x, y in m.cells() if m.tiles[y][x] == FLOOR
                     and sum(m.tile(x + dx, y + dy) == WALL for dx, dy in DIRS8) in (1, 2, 5))
        assert ragged > 100


@pytest.mark.parametrize("seed", range(15))
def test_lakes_never_disconnect_the_map(seed):
    from roguegame.mapgen import add_lakes, generate_caves, regions

    m = generate_caves(100, 64, random.Random(seed))
    add_lakes(m, random.Random(seed), 4)
    assert len(regions(m)) == 1
    for x, y in m.find_tiles(DEEP_WATER):
        assert all(m.tile(x + dx, y + dy) in (WATER, DEEP_WATER, WALL) for dx, dy in DIRS8), \
            "deep water is always ringed by shallows"


def test_connect_regions_joins_everything():
    from roguegame.mapgen import connect_regions, regions

    m = DungeonMap(40, 20)
    for x0 in (3, 15, 30):  # three separate boxes
        for y in range(3, 8):
            for x in range(x0, x0 + 4):
                m.tiles[y][x] = FLOOR
    assert len(regions(m)) == 3
    connect_regions(m, random.Random(1))
    assert len(regions(m)) == 1
