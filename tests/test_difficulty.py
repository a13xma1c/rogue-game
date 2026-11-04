"""Difficulty levels and game options."""

import pytest

from roguegame.difficulty import (
    CLASSIC,
    DIFFICULTIES,
    DIFFICULTY_NAMES,
    ENDLESS,
    MODE_DESCRIPTIONS,
    MODES,
    GameOptions,
)
from roguegame.entities import Monster
from roguegame.game import Game, State
from roguegame.level import build_level, level_rng

from conftest import add_monster, slay_boss

EASY, NORMAL, HARD = (DIFFICULTIES[n] for n in ("easy", "normal", "hard"))


# ---------------------------------------------------------------- options
def test_defaults_are_classic_normal():
    o = GameOptions()
    assert (o.mode, o.difficulty) == (CLASSIC, "normal")
    assert not o.endless and o.rules is NORMAL and o.label == "Classic - Normal"
    assert Game(seed=1).options == o


def test_invalid_options_are_rejected():
    with pytest.raises(ValueError, match="mode"):
        GameOptions("speedrun")
    with pytest.raises(ValueError, match="difficulty"):
        GameOptions(CLASSIC, "nightmare")


def test_every_mode_is_described():
    assert set(MODE_DESCRIPTIONS) == set(MODES) == {CLASSIC, ENDLESS}
    assert DIFFICULTY_NAMES == ("easy", "normal", "hard")
    assert all(d.description for d in DIFFICULTIES.values())


def test_difficulties_are_ordered():
    """Every knob moves in the same direction from easy to hard."""
    for easier, harder in ((EASY, NORMAL), (NORMAL, HARD)):
        assert easier.player_hp > harder.player_hp
        assert easier.start_potions > harder.start_potions
        assert easier.start_arrows > harder.start_arrows
        assert easier.regen_interval < harder.regen_interval
        assert easier.rest_fraction > harder.rest_fraction
        assert easier.monster_hp < harder.monster_hp
        assert easier.monster_power < harder.monster_power
        assert easier.monster_accuracy < harder.monster_accuracy
        assert easier.monster_count < harder.monster_count
        assert easier.trap_damage < harder.trap_damage
        assert easier.score_mult < harder.score_mult


def test_normal_is_neutral():
    """Normal must leave monsters exactly as designed."""
    m = Monster(0, 0, "orc", 3)
    before = (m.max_hp, m.hp, m.power, m.accuracy, m.ranged_power)
    NORMAL.adjust(m)
    assert (m.max_hp, m.hp, m.power, m.accuracy, m.ranged_power) == before
    assert NORMAL.spawn_count(10) == 10


# ------------------------------------------------------------- the player
@pytest.mark.parametrize("name", DIFFICULTY_NAMES)
def test_starting_kit(name):
    g = Game(seed=1, options=GameOptions(CLASSIC, name))
    rules = DIFFICULTIES[name]
    p = g.player
    assert p.max_hp == p.hp == rules.player_hp
    assert p.potions == rules.start_potions and p.arrows == rules.start_arrows


@pytest.mark.parametrize("name", DIFFICULTY_NAMES)
def test_rest_on_a_new_floor(name):
    g = Game(seed=2, options=GameOptions(CLASSIC, name))
    g.player.hp = 5
    g.player.x, g.player.y = g.level.down_stairs
    g.use_stairs()
    assert g.player.hp == 5 + int(g.player.max_hp * DIFFICULTIES[name].rest_fraction)


@pytest.mark.parametrize("name", DIFFICULTY_NAMES)
def test_natural_regeneration_rate(arena, name):
    g = arena("""
        #####
        #.@.#
        #####
    """)
    g.options = GameOptions(CLASSIC, name)
    g.player.hp = 5
    for _ in range(30):
        g.wait()
    assert g.player.hp == 5 + 30 // DIFFICULTIES[name].regen_interval


@pytest.mark.parametrize("name, damage", [("easy", 2), ("normal", 4), ("hard", 6)])
def test_trap_damage(arena, name, damage):
    g = arena("""
        ######
        #@.^.#
        ######
    """)
    g.options = GameOptions(CLASSIC, name)
    g.player_move(1, 0)
    g.player_move(1, 0)
    assert g.player.max_hp - g.player.hp == damage


# ------------------------------------------------------------ the monsters
def test_adjust_scales_monsters():
    m = HARD.adjust(Monster(0, 0, "goblin archer", 2))
    base = Monster(0, 0, "goblin archer", 2)
    assert m.max_hp == m.hp == round(base.max_hp * HARD.monster_hp)
    assert m.power == base.power + 1 and m.ranged_power == base.ranged_power + 1
    assert m.accuracy == base.accuracy + 5
    weak = EASY.adjust(Monster(0, 0, "rat", 1))
    assert weak.power >= 1 and weak.hp >= 1


def test_spawn_count():
    assert EASY.spawn_count(10) < NORMAL.spawn_count(10) < HARD.spawn_count(10)
    assert EASY.spawn_count(1) == 1, "never zero"


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_same_seed_same_map_whatever_the_difficulty(depth):
    levels = [build_level(depth, level_rng(7, depth), difficulty=d) for d in (EASY, NORMAL, HARD)]
    assert levels[0].map.tiles == levels[1].map.tiles == levels[2].map.tiles
    assert [(n.role, n.x, n.y) for n in levels[0].npcs] == [(n.role, n.x, n.y) for n in levels[2].npcs]
    counts = [len(lvl.monsters) for lvl in levels]
    assert counts[0] < counts[1] < counts[2]


def test_bosses_feel_the_difficulty_too():
    easy = build_level(3, level_rng(7, 3), difficulty=EASY).boss
    hard = build_level(3, level_rng(7, 3), difficulty=HARD).boss
    assert easy.max_hp < hard.max_hp and easy.power < hard.power


def test_summons_and_mimics_are_adjusted(arena):
    g = arena("""
        ##########
        #@.&.....#
        #........#
        ##########
    """, depth=3)
    g.options = GameOptions(CLASSIC, "hard")
    boss = add_monster(g, "orc warlord", 7, 2)
    minion = g.summon(boss, "goblin")
    assert minion.max_hp == round(Monster(0, 0, "goblin", 3).max_hp * HARD.monster_hp)
    g.level.mimics.add((3, 1))
    g.player_move(1, 0)
    g.player_move(1, 0)
    mimic = g.monster_at(3, 1)
    assert mimic.name == "mimic" and mimic.max_hp == round(Monster(0, 0, "mimic", 3).max_hp * HARD.monster_hp)


# ------------------------------------------------------------------ score
def test_score_rewards_depth_and_scales_with_difficulty():
    def run(name):
        g = Game(seed=4, options=GameOptions(CLASSIC, name))
        for _ in range(2):
            slay_boss(g)
            g.player.x, g.player.y = g.level.down_stairs
            g.use_stairs()
        g.player.kills, g.player.gold, g.player.level = 10, 0, 1
        return g

    normal = run("normal")
    assert normal.deepest == 3
    assert normal.score == 2 * 250 + 10 * 10 + 25
    assert run("hard").score == round(normal.score * HARD.score_mult)
    assert run("easy").score == round(normal.score * EASY.score_mult)


def test_victory_bonus():
    g = Game(seed=4)
    before = g.score
    g.state = State.WON
    assert g.score == before + 2000
