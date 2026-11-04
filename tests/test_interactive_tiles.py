"""Doors, fountains, chests (and mimics) and traps."""

import pytest

from roguegame import game as game_mod
from roguegame.dungeon import Trap
from roguegame.game import State
from roguegame.tiles import CHEST_OPEN, DOOR_OPEN, FLOOR, FOUNTAIN, FOUNTAIN_DRY


# These tests are about what attacks *do*; test_combat.py covers the odds.
pytestmark = pytest.mark.usefixtures("sure_hits")

# ------------------------------------------------------------------ doors
DOOR = """
    ###########
    #...@+....#
    ###########
"""


def test_bumping_a_door_opens_it_and_takes_a_turn(arena):
    g = arena(DOOR)
    assert not g.map.visible[1][7]
    g.player_move(1, 0)
    assert g.map.tile(5, 1) == DOOR_OPEN
    assert (g.player.x, g.player.y) == (4, 1), "opening does not move you"
    assert g.turns == 1
    assert g.map.visible[1][7], "you can see through the open doorway"
    g.player_move(1, 0)
    assert (g.player.x, g.player.y) == (5, 1)


def test_monsters_open_doors_to_reach_you(arena, spawn):
    g = arena(DOOR)
    orc = spawn(g, "orc", 7, 1, alert=True)
    g.wait()
    assert (orc.x, orc.y) == (6, 1)
    g.wait()
    assert g.map.tile(5, 1) == DOOR_OPEN and (orc.x, orc.y) == (6, 1), "opening costs its move"
    g.wait()
    assert (orc.x, orc.y) == (5, 1)


# -------------------------------------------------------------- fountains
FOUNTAIN_ROOM = """
    #######
    #.....#
    #.@{..#
    #.....#
    #######
"""


def test_fountain_heals_once(arena):
    g = arena(FOUNTAIN_ROOM)
    g.player.hp = 5
    g.player_move(1, 0)
    assert g.player.hp == 5 + 15 and g.map.tile(3, 2) == FOUNTAIN_DRY and g.turns == 1
    g.player_move(1, 0)
    assert g.player.hp == 20 and g.turns == 1, "a dry fountain is just in the way"


def test_fountain_heal_is_capped_and_at_least_ten(arena):
    g = arena(FOUNTAIN_ROOM)
    g.player.hp = 29
    g.player_move(1, 0)
    assert g.player.hp == 30


def test_fountain_is_saved_at_full_health(arena):
    g = arena(FOUNTAIN_ROOM)
    g.player_move(1, 0)
    assert g.map.tile(3, 2) == FOUNTAIN and g.turns == 0
    assert "full health" in g.log[-1][0]


def test_fountains_block_movement(arena):
    g = arena(FOUNTAIN_ROOM)
    g.map.tiles[2][3] = FOUNTAIN_DRY
    g.player_move(1, 0)
    assert (g.player.x, g.player.y) == (2, 2)


# ----------------------------------------------------------------- chests
CHEST_ROOM = """
    #######
    #.....#
    #.@&..#
    #.....#
    #######
"""


def test_chest_gives_gold_and_maybe_an_item(arena):
    for seed in range(15):
        g = arena(CHEST_ROOM, seed=seed)
        g.player_move(1, 0)
        assert g.map.tile(3, 2) == CHEST_OPEN and g.turns == 1
        assert g.player.gold > 0
        loot = g.item_at(3, 2)
        if loot:
            assert loot.seen and loot.kind != "gold"
            g.player_move(1, 0)  # open chests can be walked onto to grab the loot
            assert (g.player.x, g.player.y) == (3, 2)
            assert g.item_at(3, 2) is None or loot.kind in ("weapon", "armor")


def test_open_chests_are_not_reopened(arena):
    g = arena(CHEST_ROOM)
    g.player_move(1, 0)
    gold = g.player.gold
    g.items.clear()
    g.player_move(1, 0)
    g.player_move(-1, 0)
    g.player_move(1, 0)
    assert g.player.gold == gold


def test_mimic_chest(arena):
    g = arena(CHEST_ROOM, depth=3)
    g.level.mimics.add((3, 2))
    hp = g.player.hp
    g.player_move(1, 0)
    mimic = g.monster_at(3, 2)
    assert mimic is not None and mimic.name == "mimic" and mimic.alert
    assert g.map.tile(3, 2) == FLOOR and not g.level.mimics
    assert g.player.hp < hp, "the mimic bites straight away"
    assert g.player.gold == 0


# ------------------------------------------------------------------ traps
TRAP_HALL = """
    ###########
    #@.^......#
    ###########
"""


def test_hidden_spike_trap_hurts_and_is_revealed(arena):
    g = arena(TRAP_HALL)
    g.player_move(1, 0)
    g.player_move(1, 0)
    assert g.player.hp == 30 - 4
    assert g.map.traps[(3, 1)].known


def test_known_spike_trap_is_avoided(arena):
    g = arena(TRAP_HALL)
    g.map.traps[(3, 1)].known = True
    g.player_move(1, 0)
    g.player_move(1, 0)
    assert g.player.hp == 30 and "carefully" in g.log[-1][0]


def test_spike_trap_can_kill(arena):
    g = arena(TRAP_HALL, depth=4)
    g.player.hp = 3
    g.player_move(1, 0)
    g.player_move(1, 0)
    assert g.state is State.DEAD and "spike trap" in g.death_cause


def test_alarm_trap_alerts_monsters(arena, spawn):
    g = arena(TRAP_HALL)
    g.map.traps[(3, 1)] = Trap("alarm")
    sleeper = spawn(g, "orc", 9, 1)
    g.map.tiles[1][8] = 0  # wall it off so it can't just see you
    g.player_move(1, 0)
    g.player_move(1, 0)
    assert sleeper.alert


@pytest.mark.parametrize("known", [False, True])
def test_teleport_trap_always_fires(arena, known):
    art = "#" * 40 + "\n#@.^" + "." * 35 + "#\n" + "#" * 40
    g = arena(art, depth=2)
    g.map.traps[(3, 1)] = Trap("teleport", known=known)
    g.player_move(1, 0)
    g.player_move(1, 0)
    p = g.player
    assert g.map.tile(p.x, p.y) == FLOOR
    assert abs(p.x - 3) > 8, "teleports land out of sight"
    assert g.map.traps[(3, 1)].known


def test_monsters_ignore_traps(arena, spawn):
    g = arena("""
        ###########
        #@..^.....#
        ###########
    """)
    orc = spawn(g, "orc", 6, 1, alert=True)
    g.wait()
    g.wait()
    assert (orc.x, orc.y) == (4, 1), "the orc walked onto the trap"
    assert orc.hp == orc.max_hp, "traps don't hurt monsters"
    assert not g.map.traps[(4, 1)].known, "and it stays hidden"


def test_searching_reveals_adjacent_traps(arena, monkeypatch):
    g = arena(TRAP_HALL)
    g.player.x = 2
    monkeypatch.setattr(game_mod, "TRAP_SEARCH_CHANCE", 1.0)
    g.wait()
    assert g.map.traps[(3, 1)].known
    assert "spot" in g.log[-1][0]


def test_walking_past_traps_can_reveal_them(arena, monkeypatch):
    g = arena(TRAP_HALL)
    monkeypatch.setattr(game_mod, "TRAP_SPOT_CHANCE", 1.0)
    g.player_move(1, 0)
    assert g.map.traps[(3, 1)].known


def test_traps_are_not_spotted_from_afar(arena, monkeypatch):
    g = arena(TRAP_HALL)
    monkeypatch.setattr(game_mod, "TRAP_SEARCH_CHANCE", 1.0)
    g.wait()
    assert not g.map.traps[(3, 1)].known


def test_fountain_message_reports_actual_healing(arena):
    g = arena(FOUNTAIN_ROOM)
    g.player.hp = 27
    g.player_move(1, 0)
    assert "recover 3 HP" in g.log[-1][0]
