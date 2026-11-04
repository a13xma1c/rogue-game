"""Mana, spells and class abilities."""

import pytest

from roguegame import spells as sp
from roguegame.difficulty import GameOptions
from roguegame.items import make_book
from roguegame.spells import SPELLS

HALL = """
    ######################
    #....................#
    #..@.................#
    #....................#
    ######################
"""


def caster(arena, *spells, cls="mage", mana=100, rank=1):
    g = arena(HALL)
    g.options = GameOptions(player_class=cls)
    p = g.player
    p.base_max_mana = mana
    p.mana = mana
    for key in spells:
        p.book_spells[key] = rank
    return g


def test_every_spell_is_described():
    for key in SPELLS:
        assert sp.describe(key, 1, 0), key
        assert sp.describe(key, 3, 2)


# --------------------------------------------------------------- basics
def test_unknown_spells_and_mana(arena):
    g = caster(arena, "magic missile", mana=2)
    assert not g.cast("fireball", 5, 2) and "don't know" in g.log[-1][0]
    assert not g.cast("magic missile", 5, 2) and "Not enough mana" in g.log[-1][0]
    assert g.turns == 0


def test_targeted_spells_need_a_valid_target(arena, npc, spawn):
    g = caster(arena, "magic missile")
    assert not g.cast("magic missile") and "needs a target" in g.log[-1][0]
    assert not g.plan_cast("magic missile", 3, 2).ok, "not yourself"
    assert "Out of range" in g.plan_cast("magic missile", 11, 2).reason  # visible (8) but range 7
    npc(g, "sage", 5, 2)
    spawn(g, "orc", 7, 2)
    g._update_fov()
    assert "in the way" in g.plan_cast("magic missile", 7, 2).reason


def test_magic_missile_never_misses(arena, spawn, sure_misses):
    g = caster(arena, "magic missile", rank=2)
    orc = spawn(g, "orc", 7, 2, hp=100, max_hp=100)
    g._update_fov()
    assert g.cast("magic missile", 7, 2)
    lo, hi = sp.missile_damage(2, g.player.spell_power)
    assert 100 - hi <= orc.hp <= 100 - lo
    assert g.player.mana == 100 - SPELLS["magic missile"].cost and g.turns == 1
    assert orc.alert


def test_frost_bolt_slows(arena, spawn):
    g = caster(arena, "frost bolt")
    orc = spawn(g, "orc", 7, 2, hp=100, max_hp=100)
    g._update_fov()
    g.cast("frost bolt", 7, 2)
    assert orc.has("slowed") and orc.hp < 100


def test_fireball_hits_everything_in_the_blast_but_you(arena, spawn):
    g = caster(arena, "fireball")
    a = spawn(g, "orc", 8, 2, hp=100, max_hp=100)
    b = spawn(g, "goblin", 9, 1, hp=100, max_hp=100)
    far = spawn(g, "rat", 12, 2, hp=100, max_hp=100)
    g._update_fov()
    plan = g.plan_cast("fireball", 8, 2)
    assert (8, 2) in plan.area and (9, 1) in plan.area and len(plan.area) == 9
    g.cast("fireball", 8, 2)
    assert a.hp < 100 and b.hp < 100 and far.hp == 100
    assert a.has("burning") and b.has("burning")
    assert g.player.hp == g.player.max_hp


def test_fireball_at_close_range_spares_you(arena, spawn):
    g = caster(arena, "fireball")
    orc = spawn(g, "orc", 4, 2, hp=100, max_hp=100)
    g._update_fov()
    g.cast("fireball", 4, 2)
    assert orc.hp < 100 and g.player.hp == g.player.max_hp


def test_blink(arena, spawn):
    g = caster(arena, "blink", rank=2)
    assert sp.spell_range("blink", 2) == 6
    assert not g.plan_cast("blink", 12, 2).ok, "too far"
    spawn(g, "orc", 7, 2)
    g._update_fov()
    assert not g.plan_cast("blink", 7, 2).ok, "occupied"
    assert g.cast("blink", 8, 3)
    assert (g.player.x, g.player.y) == (8, 3)


def test_mend_and_second_wind(arena):
    g = caster(arena, "mend", "second wind")
    p = g.player
    p.hp = 5
    p.add_status("poisoned", 5)
    g.cast("mend")
    assert p.hp == 5 + sp.mend_amount(1, p.spell_power) and not p.has("poisoned")
    p.hp = 5
    g.cast("second wind")
    assert p.hp == 5 + round(p.max_hp * sp.second_wind_fraction(1))


def test_mana_shield_absorbs_damage(arena, spawn, sure_hits):
    g = caster(arena, "mana shield", mana=20)
    g.cast("mana shield")
    assert g.player.has("shielded")
    mana = g.player.mana
    orc = spawn(g, "orc", 4, 2, alert=True)
    g.wait()
    assert g.player.hp == g.player.max_hp and g.player.mana < mana
    assert orc.alive


def test_mana_shield_breaks_when_mana_runs_out(arena):
    g = caster(arena, "mana shield", mana=20)
    g.cast("mana shield")
    g.player.mana = 3
    g._damage(g.player, 10, "a test")
    assert not g.player.has("shielded") and g.player.hp == g.player.max_hp - 7


# ------------------------------------------------------------ abilities
def test_power_strike(arena, spawn, sure_hits):
    g = caster(arena, "power strike", cls="warrior", rank=3)
    orc = spawn(g, "orc", 4, 2, hp=200, max_hp=200)
    g._update_fov()
    assert not g.plan_cast("power strike", 6, 2).ok, "adjacent only"
    plan = g.plan_cast("power strike", 4, 2)
    assert plan.ok and plan.target is orc
    g.cast("power strike", 4, 2)
    assert orc.hp <= 200 - round(g.player.power * sp.strike_mult(3)) + 3


def test_cleave_hits_all_neighbours_and_refunds_when_alone(arena, spawn, sure_hits):
    g = caster(arena, "cleave", cls="warrior", mana=20)
    assert not g.cast("cleave") and g.player.mana == 20 and g.turns == 0
    a = spawn(g, "orc", 4, 2, hp=100, max_hp=100)
    b = spawn(g, "orc", 2, 1, hp=100, max_hp=100)
    g.cast("cleave")
    assert a.hp < 100 and b.hp < 100 and g.player.mana == 20 - SPELLS["cleave"].cost


def test_aimed_shot_is_more_accurate(arena, spawn):
    g = caster(arena, "aimed shot", cls="ranger")
    orc = spawn(g, "orc", 8, 2)
    g._update_fov()
    normal, aimed = g.plan_shot(8, 2), g.plan_cast("aimed shot", 8, 2)
    assert aimed.hit > normal.hit and aimed.crit > normal.crit and aimed.damage[1] > normal.damage[1]
    arrows = g.player.arrows
    assert g.cast("aimed shot", 8, 2) and g.player.arrows == arrows - 1
    assert orc.alert


def test_volley_shoots_everything_in_range(arena, spawn, sure_hits):
    g = caster(arena, "volley", cls="ranger", rank=2)
    foes = [spawn(g, "orc", 6, y, hp=100, max_hp=100) for y in (1, 2, 3)]  # each on its own clear line
    hidden = spawn(g, "orc", 9, 2, hp=100, max_hp=100)  # directly behind another: no clear shot
    g._update_fov()
    arrows = g.player.arrows
    assert g.cast("volley")
    assert all(f.hp < 100 for f in foes) and g.player.arrows == arrows - 3
    assert hidden.hp == 100


def test_volley_needs_a_bow(arena):
    g = caster(arena, "volley", cls="ranger")
    g.player.launcher = None
    assert not g.cast("volley") and g.turns == 0


def test_poison_arrow(arena, spawn, sure_hits):
    g = caster(arena, "poison arrow", cls="ranger", rank=2)
    orc = spawn(g, "orc", 7, 2, hp=100, max_hp=100)
    g._update_fov()
    g.cast("poison arrow", 7, 2)
    assert orc.has("poisoned") and orc.statuses["poisoned"].potency == 3


# ---------------------------------------------------------------- books
def test_tomes_teach_spells(arena):
    g = caster(arena)
    tome = g.player.add_to_pack(make_book(0, 0, "frost bolt"))
    assert g.study(tome) and g.player.spells["frost bolt"] == 1 and g.turns == 1
    second = g.player.add_to_pack(make_book(0, 0, "frost bolt"))
    assert not g.study(second) and second in g.player.pack, "you keep a tome you can't learn from"


@pytest.mark.parametrize("cls", ["warrior", "ranger", "adventurer"])
def test_anyone_can_learn_from_a_tome(arena, cls):
    g = caster(arena, cls=cls)
    g.study(g.player.add_to_pack(make_book(0, 0, "blink")))
    assert "blink" in g.player.spells


def test_frost_bolt_can_be_dodged_but_missile_cannot(arena, spawn):
    g = caster(arena, "frost bolt", "magic missile")
    bat = spawn(g, "bat", 7, 2, hp=100, max_hp=100)  # evasive
    g._update_fov()
    frost = g.plan_cast("frost bolt", 7, 2)
    assert 0.05 <= frost.hit < 1.0
    assert g.plan_cast("magic missile", 7, 2).hit == 1.0
    import random

    g.rng = random.Random(0)
    outcomes = set()
    for _ in range(30):
        g.player.mana = 100
        before = bat.hp
        g.cast("frost bolt", bat.x, bat.y)
        outcomes.add(bat.hp < before)
        bat.hp = 100
        bat.x, bat.y = 7, 2
        g._update_fov()
    assert outcomes == {True, False}, "some bolts land, some are dodged"
