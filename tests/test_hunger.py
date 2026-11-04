"""Hunger and food."""

import pytest

from roguegame import game_items
from roguegame.difficulty import CLASSIC, GameOptions
from roguegame.entities import HUNGER_MAX, HUNGER_START, Player
from roguegame.game import State
from roguegame.items import FOODS, make_food
from roguegame.level import build_level, level_rng

ROOM = """
    ##########
    #........#
    #...@....#
    #........#
    ##########
"""


@pytest.mark.parametrize("satiation, state", [
    (HUNGER_MAX, "Satiated"), (1800, "Satiated"), (1300, ""), (800, "Hungry"), (300, "Weak"),
    (100, "Fainting"), (10, "Starving"), (0, "Starving"),
])
def test_hunger_states(satiation, state):
    p = Player(0, 0)
    p.satiation = satiation
    assert p.hunger_state == state


def test_you_start_fed_with_a_ration():
    p = Player(0, 0)
    assert p.satiation == HUNGER_START and p.hunger_state == "" and p.count("food", "ration") == 1


def test_hunger_ticks_each_turn(arena):
    g = arena(ROOM)
    for _ in range(10):
        g.wait()
    assert g.player.satiation == HUNGER_START - 10


@pytest.mark.parametrize("difficulty, expected", [("easy", 7), ("normal", 10), ("hard", 12)])
def test_difficulty_changes_the_hunger_rate(arena, difficulty, expected):
    g = arena(ROOM)
    g.options = GameOptions(CLASSIC, difficulty)
    for _ in range(10):
        g.wait()
    assert HUNGER_START - g.player.satiation == pytest.approx(expected, abs=1)


def test_forager_and_gear_slow_hunger(arena):
    g = arena(ROOM)
    g.player.skills["forager"] = 2
    assert g.player.hunger_rate == pytest.approx(0.5)
    for _ in range(10):
        g.wait()
    assert g.player.satiation == HUNGER_START - 5


def test_warnings_on_each_threshold(arena):
    g = arena(ROOM)
    g.player.satiation = 901
    g.wait()
    g.wait()
    assert "getting hungry" in " ".join(m for m, _ in g.log)
    g.player.satiation = 401
    g.wait()
    g.wait()
    assert "weak with hunger" in " ".join(m for m, _ in g.log)


def test_weakness_hurts_aim_and_stops_healing(arena):
    g = arena(ROOM)
    acc = g.player.accuracy
    g.player.satiation = 300
    assert g.player.accuracy == acc - 10
    g.player.hp = 10
    for _ in range(20):
        g.wait()
    assert g.player.hp == 10


def test_fainting_costs_rounds(arena, spawn, monkeypatch):
    monkeypatch.setattr(game_items, "FAINT_CHANCE", 1.0)
    g = arena(ROOM)
    g.player.satiation = 100
    orc = spawn(g, "orc", 8, 2, alert=True)
    g.wait()
    assert orc.x == 5, "you lay there for two extra rounds while it closed in"
    assert "faint" in " ".join(m for m, _ in g.log)


def test_starvation_kills(arena):
    g = arena(ROOM)
    g.player.satiation = 0
    g.player.hp = 2
    g.wait()
    g.wait()
    assert g.state is State.DEAD and g.death_cause == "starved to death"


def test_eating(arena):
    g = arena(ROOM)
    g.player.satiation = 500
    assert g.eat(g.player.find("food", "ration"))
    assert g.player.satiation == 500 + FOODS["ration"].nutrition - 1 and g.turns == 1
    assert g.player.count("food", "ration") == 0


def test_you_cannot_overeat(arena):
    g = arena(ROOM)
    g.player.satiation = HUNGER_MAX - 100
    assert not g.eat(g.player.find("food", "ration"))
    assert g.turns == 0 and "too full" in g.log[-1][0]


def test_food_caps_at_the_maximum(arena):
    g = arena(ROOM)
    g.player.satiation = HUNGER_MAX - 300
    g.player.add_to_pack(make_food(0, 0, "ration"))
    g.eat(g.player.find("food", "ration"))
    assert g.player.satiation <= HUNGER_MAX


@pytest.mark.parametrize("depth", [1, 3, 5])
def test_every_floor_has_food(depth):
    for seed in range(6):
        lvl = build_level(depth, level_rng(seed, depth))
        assert any(it.kind == "food" for it in lvl.items)
