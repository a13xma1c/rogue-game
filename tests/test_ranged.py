"""The player's bow: planning shots, firing, arrows and bows as loot."""

import pytest

from roguegame import game as game_mod
from roguegame.entities import make_launcher

HALL = """
    ####################
    #..................#
    #..@...............#
    #..................#
    ####################
"""


def test_shot_plan_at_a_monster(arena, spawn):
    g = arena(HALL)
    orc = spawn(g, "orc", 7, 2)
    g._update_fov()
    plan = g.plan_shot(7, 2)
    assert plan.ok and plan.target is orc and plan.dist == 4
    assert plan.path[-1] == (7, 2) and len(plan.path) == 4
    assert 0.05 <= plan.hit <= 0.95 and plan.crit == 0.05
    assert plan.damage == (max(1, g.player.ranged_power - orc.defense - 1), g.player.ranged_power - orc.defense + 2)


@pytest.mark.parametrize(
    "setup, target, reason",
    [
        (lambda g: setattr(g.player, "launcher", None), (7, 2), "nothing to shoot with"),
        (lambda g: setattr(g.player, "arrows", 0), (7, 2), "out of arrows"),
        (lambda g: None, (3, 2), "shoot yourself"),
        (lambda g: None, (10, 2), "Out of range"),  # visible (7 tiles) but the bow reaches 6
        (lambda g: g.map.visible[2].__setitem__(7, False), (7, 2), "can't see"),
    ],
)
def test_shots_that_cannot_be_taken(arena, setup, target, reason):
    g = arena(HALL)
    setup(g)
    plan = g.plan_shot(*target)
    assert not plan.ok and reason in plan.reason
    arrows = g.player.arrows
    assert g.shoot(*target) is False
    assert g.turns == 0 and g.player.arrows == arrows, "a refused shot costs nothing"


def test_walls_block_shots(arena):
    g = arena("""
        ##########
        #..@.#...#
        #........#
        ##########
    """)
    g.map.visible[1][7] = True  # pretend we can see past the corner
    plan = g.plan_shot(7, 1)
    assert not plan.ok and "clear shot" in plan.reason


def test_friendly_npcs_block_shots(arena, npc, spawn):
    g = arena(HALL)
    npc(g, "merchant", 5, 2)
    spawn(g, "orc", 8, 2)
    g._update_fov()
    plan = g.plan_shot(8, 2)
    assert not plan.ok and "in the way" in plan.reason


def test_arrows_stop_at_the_first_monster(arena, spawn):
    g = arena(HALL)
    front = spawn(g, "goblin", 5, 2)
    spawn(g, "orc", 8, 2)
    g._update_fov()
    plan = g.plan_shot(8, 2)
    assert plan.ok and plan.target is front and plan.path[-1] == (5, 2)


def test_shooting_hits_and_takes_a_turn(arena, spawn, sure_hits):
    g = arena(HALL)
    orc = spawn(g, "orc", 7, 2, hp=100, max_hp=100)
    g._update_fov()
    arrows = g.player.arrows
    assert g.shoot(7, 2)
    assert orc.hp < 100 and g.player.arrows == arrows - 1 and g.turns == 1
    assert any(fx.kind == "shot" and fx.path[-1] == (7, 2) for fx in g.fx)
    assert any("Your arrow hits the orc" in m for m, _ in g.log)


def test_shooting_can_kill(arena, spawn, sure_hits):
    g = arena(HALL)
    rat = spawn(g, "rat", 7, 2, hp=1)
    g._update_fov()
    g.shoot(7, 2)
    assert rat not in g.monsters and g.player.kills == 1


def test_missing(arena, spawn, sure_misses):
    g = arena(HALL)
    orc = spawn(g, "orc", 7, 2)
    g._update_fov()
    g.shoot(7, 2)
    assert orc.hp == orc.max_hp
    assert any("misses the orc" in m or "dodges" in m for m, _ in g.log)


def test_shooting_at_the_floor(arena):
    g = arena(HALL)
    plan = g.plan_shot(7, 2)
    assert plan.ok and plan.target is None
    assert g.shoot(7, 2) and g.turns == 1


def test_arrows_can_be_recovered_and_stack(arena, spawn, monkeypatch):
    monkeypatch.setattr(game_mod, "ARROW_RECOVERY_MISS", 1.0)
    g = arena(HALL)
    start = g.player.arrows
    g.shoot(7, 2)
    g.shoot(7, 2)
    pile = g.item_at(7, 2)
    assert pile is not None and pile.kind == "ammo" and pile.value == 2 and pile.name == "2 arrows"
    for _ in range(4):
        g.player_move(1, 0)
    assert g.player.arrows == start and g.item_at(7, 2) is None


def test_arrows_never_land_in_walls(arena, monkeypatch):
    monkeypatch.setattr(game_mod, "ARROW_RECOVERY_MISS", 1.0)
    g = arena(HALL)
    g._drop_arrow((0, 0))
    assert not g.items


def test_better_launchers_can_be_equipped(arena, item):
    g = arena(HALL)
    longbow = make_launcher(4, 2, "longbow", 2, 8, 0)
    g.items.append(longbow)
    g.player_move(1, 0)
    assert longbow in g.player.pack
    old = g.player.launcher
    g.equip(longbow)
    assert g.player.launcher is longbow and g.player.shot_range == 8 and old in g.player.pack


def test_monster_projectiles_stop_at_whoever_is_in_the_way(arena, spawn):
    g = arena(HALL)
    archer = spawn(g, "goblin archer", 9, 2)
    spawn(g, "orc", 6, 2)
    assert g.ranged_attack(archer, g.player) is None, "the orc took the arrow's path"
    assert g.player.hp == g.player.max_hp
