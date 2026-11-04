"""DungeonMap queries, field of view and path finding."""

import pytest

from roguegame.dungeon import DungeonMap, Room, compass
from roguegame.tiles import DOOR_CLOSED, DOOR_OPEN, FLOOR, WALL

from conftest import parse_map


def open_map(w=15, h=15) -> DungeonMap:
    m = DungeonMap(w, h)
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            m.tiles[y][x] = FLOOR
    return m


# ----------------------------------------------------------------- queries
def test_out_of_bounds_is_solid_wall():
    m = open_map()
    assert m.tile(-1, 0) == WALL and m.tile(99, 99) == WALL
    assert not m.walkable(-1, 3) and not m.pathable(3, 99)
    assert m.blocks_sight(-1, -1)


def test_new_map_is_all_unexplored_wall():
    m = DungeonMap(5, 4)
    assert all(t == WALL for row in m.tiles for t in row)
    assert not any(any(row) for row in m.explored)
    assert (m.width, m.height) == (5, 4)


def test_find_tiles_and_cells():
    m, _ = parse_map("""
        #####
        #.>@#
        #####
    """)
    assert len(list(m.cells())) == 15
    assert m.find_tiles(FLOOR) == [(1, 1), (3, 1)]


def test_open_spot_requires_all_neighbours_floor():
    m, _ = parse_map("""
        #######
        #.....#
        #..@..#
        #.....#
        #######
    """)
    assert m.is_open_spot(3, 2)
    assert not m.is_open_spot(1, 1)  # touches walls
    m.tiles[1][3] = DOOR_OPEN
    assert not m.is_open_spot(3, 2)  # a doorway next to it
    assert not m.is_open_spot(3, 1)  # not plain floor itself


def test_room_geometry():
    a = Room(2, 2, 4, 3)
    assert a.center == (4, 3)
    assert a.contains(2, 2) and a.contains(5, 4) and not a.contains(6, 4)
    assert a.intersects(Room(6, 2, 3, 3))  # touching counts (pad=1)
    assert not a.intersects(Room(9, 2, 3, 3))


@pytest.mark.parametrize(
    "dx, dy, expected",
    [
        (0, 0, "right here"), (0, -5, "north"), (0, 5, "south"), (5, 0, "east"), (-5, 0, "west"),
        (4, -4, "north-east"), (-4, 4, "south-west"), (10, 1, "east"), (-1, -10, "north"),
    ],
)
def test_compass(dx, dy, expected):
    assert compass(dx, dy) == expected


# --------------------------------------------------------------------- FOV
def test_fov_marks_visible_and_explored():
    m = open_map()
    m.compute_fov(7, 7, 4)
    assert m.visible[7][7] and m.explored[7][7]
    assert m.visible[7][10]
    assert not m.visible[1][1]  # beyond the radius


def test_walls_block_sight():
    m, p = parse_map("""
        #########
        #@..#...#
        #########
    """)
    m.compute_fov(*p, 8)
    assert m.visible[1][3]
    assert m.visible[1][4], "the wall itself is seen"
    assert not m.visible[1][5], "but not what is behind it"


def test_closed_doors_block_sight_and_open_doors_do_not():
    m, p = parse_map("""
        #########
        #@..+...#
        #########
    """)
    m.compute_fov(*p, 8)
    assert m.visible[1][4] and not m.visible[1][6]
    m.tiles[1][4] = DOOR_OPEN
    m.compute_fov(*p, 8)
    assert m.visible[1][6]


def test_visibility_resets_but_exploration_is_remembered():
    m = open_map(30, 5)
    m.compute_fov(2, 2, 3)
    assert m.visible[2][4]
    m.compute_fov(25, 2, 3)
    assert not m.visible[2][4]
    assert m.explored[2][4]


def test_reveal_maps_floor_and_bordering_walls_only():
    m, _ = parse_map("""
        ########
        #..#####
        ########
        ########
    """)
    m.reveal()
    assert m.explored[1][1] and m.explored[0][0] and m.explored[1][3]
    assert not m.explored[3][6], "solid rock far from any floor stays unknown"
    assert not any(any(row) for row in m.visible), "reveal does not grant sight"


# ---------------------------------------------------------------- pathing
def test_next_step_is_on_a_shortest_path():
    m = open_map()
    step = m.next_step((2, 2), (6, 2), set())
    # 8-way moves allow several equally short routes; any of them will do.
    assert max(abs(step[0] - 2), abs(step[1] - 2)) == 1
    assert max(abs(step[0] - 6), abs(step[1] - 2)) == 3


def test_next_step_same_tile_is_none():
    m = open_map()
    assert m.next_step((2, 2), (2, 2), set()) is None


def test_next_step_goes_around_walls():
    m, _ = parse_map("""
        #######
        #.....#
        #.###.#
        #.#@#.#
        #######
    """)
    # From (1,3) to (5,3) the only way is over the top.
    assert m.next_step((1, 3), (5, 3), set()) == (1, 2)


def test_next_step_avoids_blocked_tiles_but_can_enter_goal():
    m, _ = parse_map("""
        #####
        #...#
        #####
    """)
    assert m.next_step((1, 1), (3, 1), {(2, 1)}) is None
    assert m.next_step((1, 1), (2, 1), {(2, 1)}) == (2, 1), "the goal itself may be 'blocked' (it's the target)"


def test_next_step_unreachable_returns_none():
    m, _ = parse_map("""
        #######
        #..#..#
        #######
    """)
    assert m.next_step((1, 1), (5, 1), set()) is None


def test_next_step_routes_through_closed_doors():
    m, _ = parse_map("""
        #######
        #..+..#
        #######
    """)
    assert m.tile(3, 1) == DOOR_CLOSED
    assert m.next_step((2, 1), (5, 1), set()) == (3, 1)


def test_distance_map_counts_diagonal_steps():
    m = open_map()
    d = m.distance_map((1, 1))
    assert d[(1, 1)] == 0 and d[(4, 4)] == 3 and d[(13, 1)] == 12


def test_distance_map_known_only_stays_in_explored_area():
    m = open_map(20, 5)
    for x in range(1, 6):
        m.explored[2][x] = True
    d = m.distance_map((1, 2), known_only=True)
    assert set(d) == {(x, 2) for x in range(1, 6)}
