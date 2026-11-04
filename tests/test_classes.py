"""Character classes and skill trees."""

import pytest

from roguegame import game as game_mod
from roguegame.classes import CLASS_NAMES, CLASSES, SKILLS, TIER_LEVELS, can_learn
from roguegame.difficulty import CLASSIC, GameOptions
from roguegame.dungeon import Trap
from roguegame.entities import Player
from roguegame.game import Game
from roguegame.spells import SPELLS

ROOM = """
    ##############
    #............#
    #...@........#
    #............#
    ##############
"""


def game_as(cls: str, seed: int = 1) -> Game:
    return Game(seed=seed, options=GameOptions(CLASSIC, "normal", cls))


# --------------------------------------------------------------- tables
def test_four_classes():
    assert CLASS_NAMES == ("adventurer", "warrior", "ranger", "mage")


@pytest.mark.parametrize("name", CLASS_NAMES)
def test_every_class_has_a_full_tree(name):
    cls = CLASSES[name]
    assert len(cls.branches) == 2
    for _, branch in cls.branches:
        assert len(branch) == len(TIER_LEVELS) == 4
        assert all(k in SKILLS for k in branch)
    keys = [k for _, b in cls.branches for k in b]
    assert len(keys) == len(set(keys))


def test_every_skill_is_used_and_actives_cast_real_spells():
    used = {k for c in CLASSES.values() for _, b in c.branches for k in b}
    assert used == set(SKILLS)
    for skill in SKILLS.values():
        assert skill.spell is None or skill.spell in SPELLS
        assert skill.max_rank >= 1 and skill.description
        assert skill.spell or skill.stats or skill.immune, f"{skill.key} does nothing"


def test_class_kits_and_stats():
    war, ran, mag, adv = (game_as(c).player for c in ("warrior", "ranger", "mage", "adventurer"))
    assert war.max_hp > adv.max_hp > mag.max_hp
    assert war.weapon.subtype == "sword" and war.armor is not None and war.launcher is None
    assert ran.launcher.subtype == "longbow" and ran.arrows == 10 + 15
    assert mag.max_mana > adv.max_mana and mag.spell_power == 2 and mag.spells == {"magic missile": 1}
    assert mag.count("potion", "mana") == 2 and mag.launcher is None and mag.arrows == 0
    assert adv.launcher.subtype == "shortbow" and adv.arrows == 10
    for p in (war, ran, mag, adv):
        assert p.potions == 1 and p.count("food", "ration") == 1 and p.skill_points == 1


def test_the_adventurer_matches_the_old_default_character():
    p = game_as("adventurer").player
    assert (p.max_hp, p.power, p.defense, p.accuracy, p.evasion, p.crit_chance) == (30, 4, 0, 80, 10, 5)


# ------------------------------------------------------------- learning
def test_learning_rules():
    cls = CLASSES["warrior"]
    assert can_learn(cls, {}, 1, "brawn") == (True, "")
    ok, why = can_learn(cls, {}, 2, "power strike")
    assert not ok and "Brawn" in why, "needs the skill above it"
    ok, why = can_learn(cls, {"brawn": 1}, 1, "power strike")
    assert not ok and "level 2" in why
    assert can_learn(cls, {"brawn": 1}, 2, "power strike")[0]
    ok, why = can_learn(cls, {"brawn": 3}, 9, "brawn")
    assert not ok and "highest rank" in why
    ok, why = can_learn(cls, {}, 9, "fireball")
    assert not ok and "Not in your skill tree" in why


def test_spending_points(arena):
    g = game_as("warrior")
    p = g.player
    assert g.learn_skill("brawn") and p.skills["brawn"] == 1 and p.skill_points == 0
    assert not g.learn_skill("brawn") and "No skill points" in g.log[-1][0]
    assert g.turns == 0, "learning is free"


def test_levels_grant_points_and_class_growth():
    for cls in ("warrior", "mage"):
        hp_gain, mana_gain = CLASSES[cls].hp_per_level, CLASSES[cls].mana_per_level
        p = Player(0, 0, cls)
        hp, mana = p.max_hp, p.max_mana
        p.gain_xp(p.xp_needed)
        assert p.skill_points == 2 and p.max_hp == hp + hp_gain and p.max_mana == mana + mana_gain


# ------------------------------------------------------------- passives
def learn(g, key, rank=1):
    g.player.skill_points += rank
    g.player.level = 10
    for _ in range(rank):
        assert g.learn_skill(key), g.log[-1][0]


def test_toughness_raises_max_and_current_hp():
    g = game_as("warrior")
    before = g.player.max_hp
    learn(g, "toughness", 2)
    assert g.player.max_hp == g.player.hp == before + 16


def test_brawn_iron_skin_executioner():
    g = game_as("warrior")
    p = g.player
    power, defense, crit = p.power, p.defense, p.crit_chance
    learn(g, "brawn", 3)
    learn(g, "toughness")
    learn(g, "iron skin", 2)
    learn(g, "power strike")
    learn(g, "cleave")
    learn(g, "executioner", 2)
    assert (p.power, p.defense, p.crit_chance) == (power + 3, defense + 2, crit + 10)


def test_unstoppable_grants_immunity():
    g = game_as("warrior")
    for key in ("toughness", "iron skin", "second wind", "unstoppable"):
        learn(g, key)
    assert {"stunned", "slowed"} <= g.player.immune
    assert not g.player.add_status("stunned", 3)


def test_ranger_passives():
    g = game_as("ranger")
    p = g.player
    acc, reach, sight, eva = p.ranged_accuracy, p.shot_range, g.fov_radius, p.evasion
    learn(g, "steady aim", 2)
    learn(g, "aimed shot")
    learn(g, "volley")
    learn(g, "eagle eye", 2)
    learn(g, "evasion", 3)
    assert p.ranged_accuracy == acc + 10 and p.shot_range == reach + 2 and g.fov_radius == sight + 2
    assert p.evasion == eva + 12


def test_trap_sense(arena, monkeypatch):
    monkeypatch.setattr(game_mod, "TRAP_SPOT_CHANCE", 0.0)
    g = arena(ROOM)
    g.map.traps[(5, 1)] = Trap("spike")
    g.map.tiles[1][5] = 6
    g.wait()
    assert not g.map.traps[(5, 1)].known
    g.player.skills["trap sense"] = 1
    g.wait()
    assert g.map.traps[(5, 1)].known


def test_meditation_and_arcane_power():
    g = game_as("mage")
    p = g.player
    mana, sp = p.max_mana, p.spell_power
    learn(g, "meditation", 2)
    learn(g, "frost bolt")
    learn(g, "fireball")
    learn(g, "arcane power", 2)
    assert p.max_mana == mana + 12 and p.spell_power == sp + 2


def test_mana_regenerates_by_class_and_meditation(arena):
    g = game_as("mage")
    p = g.player
    p.mana = 0
    turns = 3 * p.cls.mana_regen
    for _ in range(turns):
        g.wait()
    assert p.mana == 3, "a point every cls.mana_regen turns"
    w = game_as("warrior").player
    assert w.cls.mana_regen > p.cls.mana_regen


def test_active_skills_unlock_spells():
    g = game_as("warrior")
    learn(g, "brawn")
    learn(g, "power strike", 2)
    assert g.player.spells["power strike"] == 2
