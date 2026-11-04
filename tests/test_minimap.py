"""The minimap model shows only what the player knows."""

from roguegame import settings as S
from roguegame.game import Game
from roguegame.minimap import MONSTER_COLOR, NPC_COLOR, PLAYER_COLOR, TERRAIN_COLORS, build_minimap
from roguegame.tiles import FLOOR, STAIRS_DOWN, TRAP, WALL

SPLIT = """
    ####################
    #@.......#......>..#
    #........+.........#
    ####################
"""


def markers(mm):
    return dict(mm.markers)


def test_dimensions_match_the_map():
    g = Game(seed=1)
    mm = build_minimap(g)
    assert (mm.width, mm.height) == (S.MAP_W, S.MAP_H)
    assert len(mm.cells) == S.MAP_H and all(len(r) == S.MAP_W for r in mm.cells)


def test_unexplored_is_blank_and_lit_differs_from_remembered(arena):
    g = arena(SPLIT)
    mm = build_minimap(g)
    assert mm.cells[1][15] is None
    assert mm.cells[1][2] == TERRAIN_COLORS[FLOOR][0]
    assert mm.cells[0][0] == TERRAIN_COLORS[WALL][0]
    g.map.explored[1][12] = True
    assert build_minimap(g).cells[1][12] == TERRAIN_COLORS[FLOOR][1]


def test_remembered_stairs_stay_bright(arena):
    g = arena(SPLIT)
    g.map.explored[1][16] = True
    assert build_minimap(g).cells[1][16] == TERRAIN_COLORS[STAIRS_DOWN][1] == S.CYAN


def test_player_marker_is_drawn_last(arena, spawn, npc):
    g = arena(SPLIT)
    spawn(g, "rat", 3, 1)
    npc(g, "sage", 4, 2)
    g._update_fov()
    mm = build_minimap(g)
    assert mm.markers[-1] == ((1, 1), PLAYER_COLOR)
    assert markers(mm)[(3, 1)] == MONSTER_COLOR
    assert markers(mm)[(4, 2)] == NPC_COLOR


def test_unseen_actors_are_not_marked(arena, spawn, npc):
    g = arena(SPLIT)
    spawn(g, "troll", 14, 1)
    npc(g, "sage", 13, 2)
    g.map.explored[1][14] = g.map.explored[2][13] = True
    assert set(markers(build_minimap(g))) == {(1, 1)}


def test_hidden_traps_look_like_floor(arena):
    g = arena("""
        #######
        #@.^..#
        #######
    """)
    assert build_minimap(g).cells[1][3] == TERRAIN_COLORS[FLOOR][0]
    g.map.traps[(3, 1)].known = True
    assert build_minimap(g).cells[1][3] == TERRAIN_COLORS[TRAP][0]


def test_items_appear_once_seen(arena, item):
    g = arena(SPLIT)
    near = item(g, "potion", 3, 1)
    far = item(g, "gold", 12, 1)
    g.map.explored[1][12] = True
    mm = build_minimap(g)
    assert mm.cells[1][3] == near.color
    assert mm.cells[1][12] == TERRAIN_COLORS[FLOOR][1], "never-seen item isn't shown"
    assert not far.seen


def test_every_tile_type_has_minimap_colors():
    from roguegame.tiles import TILES

    assert set(TERRAIN_COLORS) == set(TILES)
