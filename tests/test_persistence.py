"""Persistent floors connected by up and down staircases."""

from roguegame import settings as S
from roguegame.dungeon import DIRS8
from roguegame.game import Game, State
from roguegame.level import build_level, level_rng
from roguegame.tiles import STAIRS_DOWN, STAIRS_UP

from conftest import slay_boss


def stand_on(g: Game, pos) -> None:
    g.player.x, g.player.y = pos
    g._update_fov()


def go_down(g: Game) -> None:
    slay_boss(g)  # boss floors stay sealed until the boss is dead
    stand_on(g, g.level.down_stairs)
    g.use_stairs()


def go_up(g: Game) -> None:
    stand_on(g, g.level.up_stairs)
    g.use_stairs()


def test_descending_arrives_on_the_up_stairs():
    g = Game(seed=1)
    go_down(g)
    assert g.depth == 2 and set(g.levels) == {1, 2}
    assert (g.player.x, g.player.y) == g.level.up_stairs
    assert g.map.tile(g.player.x, g.player.y) == STAIRS_UP
    assert g.map.visible[g.player.y][g.player.x]


def test_ascending_arrives_on_the_down_stairs():
    g = Game(seed=1)
    go_down(g)
    go_up(g)
    assert g.depth == 1
    assert (g.player.x, g.player.y) == g.level.down_stairs
    assert g.map.tile(g.player.x, g.player.y) == STAIRS_DOWN


def test_floors_are_kept_not_regenerated():
    g = Game(seed=2)
    first = g.level
    go_down(g)
    second = g.level
    go_up(g)
    assert g.level is first
    go_down(g)
    assert g.level is second
    assert set(g.levels) == {1, 2}


def test_exploration_monsters_and_items_persist():
    g = Game(seed=3)
    explored = [row[:] for row in g.map.explored]
    victim = g.monsters[0]
    g.monsters.remove(victim)
    loot = g.items[0]
    g.items.remove(loot)
    g.map.tiles[1][1] = STAIRS_UP  # a mark we can recognise later
    survivors = [(m.name, m.x, m.y, m.hp) for m in g.monsters]
    go_down(g)
    go_up(g)
    assert victim not in g.monsters and loot not in g.items
    assert [(m.name, m.x, m.y, m.hp) for m in g.monsters] == survivors
    assert g.map.tiles[1][1] == STAIRS_UP
    for y, row in enumerate(explored):
        for x, was in enumerate(row):
            assert g.map.explored[y][x] or not was, "explored tiles are never forgotten"


def test_only_the_first_arrival_heals():
    g = Game(seed=4)
    g.player.hp = 10
    go_down(g)
    assert g.player.hp == 10 + g.player.max_hp // 4
    g.player.hp = 10
    go_up(g)
    go_down(g)
    assert g.player.hp == 10, "no healing by stair-dancing"


def test_floor_layout_does_not_depend_on_history():
    """Floor 3 looks the same however (and whenever) you get there."""
    g = Game(seed=5)
    for _ in range(5):
        g.wait()
    go_down(g)
    go_down(g)
    fresh = build_level(3, level_rng(5, 3))
    assert g.map.tiles == fresh.map.tiles


def test_stairs_needed():
    g = Game(seed=6)
    g.use_stairs()
    assert g.depth == 1 and "no stairs" in g.log[-1][0]
    g.ascend()
    assert g.depth == 1 and "no stairs up" in g.log[-1][0]
    g.descend()
    assert g.depth == 1 and "no stairs down" in g.log[-1][0]


def test_floor_one_has_no_way_up_and_last_floor_no_way_down():
    g = Game(seed=7)
    assert g.level.up_stairs is None
    for _ in range(S.MAX_DEPTH - 1):
        go_down(g)
    assert g.depth == S.MAX_DEPTH
    assert g.level.down_stairs is None
    assert g.level.boss is not None and g.level.boss.carries_amulet


def test_full_round_trip():
    g = Game(seed=8)
    for depth in range(2, S.MAX_DEPTH + 1):
        go_down(g)
        assert g.depth == depth
    for depth in range(S.MAX_DEPTH - 1, 0, -1):
        go_up(g)
        assert g.depth == depth
    assert set(g.levels) == set(range(1, S.MAX_DEPTH + 1))
    assert g.state is State.PLAYING


def test_arriving_shoves_a_monster_off_the_stairs():
    g = Game(seed=9)
    go_down(g)
    up = g.level.up_stairs
    camper = g.monsters[0]
    go_up(g)
    camper.x, camper.y = up  # a monster wandered onto the stairs while we were away
    go_down(g)
    assert (g.player.x, g.player.y) == up
    assert (camper.x, camper.y) != up
    assert g.map.walkable(camper.x, camper.y)
    assert max(abs(camper.x - up[0]), abs(camper.y - up[1])) <= 2


def test_the_amulet_can_be_reached_and_wins():
    g = Game(seed=10)
    for _ in range(S.MAX_DEPTH - 1):
        go_down(g)
    assert not [it for it in g.items if it.kind == "amulet"]
    slay_boss(g)  # the lich drops the Amulet
    amulet = next(it for it in g.items if it.kind == "amulet")
    beside = next(
        (amulet.x + dx, amulet.y + dy) for dx, dy in DIRS8 if g.map.walkable(amulet.x + dx, amulet.y + dy)
    )
    stand_on(g, beside)
    g.monsters.clear()
    g.player_move(amulet.x - g.player.x, amulet.y - g.player.y)
    assert g.state is State.WON


def test_stairs_keys_via_descend_and_ascend():
    g = Game(seed=12)
    stand_on(g, g.level.down_stairs)
    g.ascend()
    assert g.depth == 1
    g.descend()
    assert g.depth == 2
    stand_on(g, g.level.up_stairs)
    g.descend()
    assert g.depth == 2
    g.ascend()
    assert g.depth == 1
