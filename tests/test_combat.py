"""Accuracy, dodging, critical hits and lines of fire."""

import random
from collections import Counter

import pytest

from roguegame import combat
from roguegame.combat import (
    AttackResult,
    bresenham,
    damage_range,
    expected_attack,
    first_blocker,
    hit_chance,
    line_of_fire,
    resolve_attack,
)
from roguegame.entities import Actor, Player, make_armor, make_launcher, make_weapon
from roguegame.tiles import DOOR_OPEN

from conftest import parse_map


def actor(acc=75, eva=10, crit=5, power=5, defense=0, hp=100) -> Actor:
    return Actor(0, 0, "dummy", "d", (1, 1, 1), hp=hp, power=power, defense=defense,
                 accuracy=acc, evasion=eva, crit=crit)


def outcomes(attacker, defender, n=4000, seed=1, **kw) -> Counter:
    rng = random.Random(seed)
    return Counter(resolve_attack(attacker, defender, rng, **kw).outcome for _ in range(n))


# ------------------------------------------------------------ hit chance
@pytest.mark.parametrize("acc, eva, expected", [(80, 10, 0.70), (75, 0, 0.75), (200, 0, 0.95),
                                                (10, 60, 0.05), (50, 50, 0.05)])
def test_hit_chance_is_accuracy_minus_evasion_clamped(acc, eva, expected):
    assert hit_chance(actor(acc=acc), actor(eva=eva)) == pytest.approx(expected)


def test_range_penalty_only_for_shots():
    a, d = actor(acc=80), actor(eva=0)
    assert hit_chance(a, d, ranged=False, dist=6) == pytest.approx(0.80)
    assert hit_chance(a, d, ranged=True, dist=1) == pytest.approx(0.80)
    assert hit_chance(a, d, ranged=True, dist=6) == pytest.approx(0.80 - 5 * combat.RANGE_PENALTY / 100)


def test_status_effects_change_the_odds():
    a, d = actor(acc=80), actor(eva=20)
    base = hit_chance(a, d)
    a.add_status("blinded", 3)
    assert hit_chance(a, d) == pytest.approx(base - 0.35)
    a.cure()
    d.add_status("slowed", 3)
    assert hit_chance(a, d) == pytest.approx(base + 0.10)
    d.add_status("stunned", 1)
    assert d.evasion == 0 and hit_chance(a, d) == pytest.approx(0.80)


# ------------------------------------------------------------- outcomes
def test_hit_rate_matches_hit_chance():
    a, d = actor(acc=80, crit=0), actor(eva=20)
    counts = outcomes(a, d)
    assert counts["hit"] / 4000 == pytest.approx(0.60, abs=0.03)


def test_failed_rolls_split_into_dodges_and_misses():
    a, d = actor(acc=80), actor(eva=30)
    counts = outcomes(a, d)
    # Rolls in [0.50, 0.80) would have hit an evasion-0 target: dodges.
    assert counts["dodge"] / 4000 == pytest.approx(0.30, abs=0.03)
    assert counts["miss"] / 4000 == pytest.approx(0.20, abs=0.03)


def test_no_dodges_against_zero_evasion():
    counts = outcomes(actor(acc=80), actor(eva=0))
    assert counts["dodge"] == 0 and counts["miss"] > 0


def test_crit_rate_and_damage():
    a, d = actor(acc=200, crit=25, power=6), actor(eva=0, defense=0)
    rng = random.Random(3)
    results = [resolve_attack(a, d, rng) for _ in range(4000)]
    crits = [r for r in results if r.crit]
    hits = [r for r in results if r.outcome == "hit"]
    assert len(crits) / len(crits + hits) == pytest.approx(0.25, abs=0.03)
    assert {r.damage for r in hits} == {5, 6, 7, 8}
    assert {r.damage for r in crits} == {10, 12, 14, 16}, "criticals double the damage"


def test_attack_result_flags():
    assert AttackResult("crit", 8).hit and AttackResult("crit", 8).crit
    assert AttackResult("hit", 3).hit and not AttackResult("hit", 3).crit
    assert not AttackResult("dodge").hit and not AttackResult("miss").hit


def test_expected_attack_matches_simulation():
    a, d = actor(acc=85, crit=20, power=7), actor(eva=15, defense=2)
    rng = random.Random(9)
    n = 20000
    mean = sum(resolve_attack(a, d, rng).damage for _ in range(n)) / n
    assert mean == pytest.approx(expected_attack(a, d), rel=0.04)


def test_damage_range():
    a, d = actor(power=6), actor(defense=2)
    assert damage_range(a, d) == (3, 6)
    assert damage_range(actor(power=1), actor(defense=9)) == (1, 1)


# ------------------------------------------------------------ the player
def test_player_gear_traits_feed_into_stats():
    p = Player(0, 0)
    acc, eva, crit = p.accuracy, p.evasion, p.crit_chance
    p.weapon = make_weapon(0, 0, 1)  # dagger: +5 acc, +10 crit
    p.armor = make_armor(0, 0, 3)  # plate: -5 evasion
    assert p.accuracy == acc + 5 and p.crit_chance == crit + 10 and p.evasion == eva - 5
    p.armor = make_armor(0, 0, 4)  # dragon scale: +3 evasion
    assert p.evasion == eva + 3


def test_player_ranged_stats_come_from_the_bow():
    p = Player(0, 0)
    assert p.launcher is not None and p.arrows > 0
    assert p.ranged_power == p.base_power // 2 + p.launcher.value
    assert p.shot_range == p.launcher.range
    p.weapon = make_weapon(0, 0, 1)  # a dagger doesn't help your aim with a bow
    p.launcher = make_launcher(0, 0, "crossbow", 3, 7, 10)
    assert p.ranged_accuracy == p.base_accuracy + 10
    assert p.stun_on_crit is False
    p.weapon = make_weapon(0, 0, 4)  # warhammer
    assert p.stun_on_crit is True


def test_evasion_never_negative():
    p = Player(0, 0)
    p.armor = make_armor(0, 0, 3)
    p.base_evasion = 1
    assert p.evasion == 0


def test_levelling_improves_accuracy():
    p = Player(0, 0)
    acc = p.accuracy
    p.gain_xp(p.xp_needed)
    assert p.accuracy == acc + 2


# ---------------------------------------------------------- line of fire
def test_bresenham():
    assert bresenham((0, 0), (3, 0)) == [(1, 0), (2, 0), (3, 0)]
    assert bresenham((0, 0), (2, 2)) == [(1, 1), (2, 2)]
    line = bresenham((1, 1), (7, 4))
    assert line[-1] == (7, 4) and len(line) == 6
    for (ax, ay), (bx, by) in zip([(1, 1), *line[:-1]], line, strict=True):
        assert max(abs(ax - bx), abs(ay - by)) == 1, "each step is to a neighbouring tile"


def test_line_of_fire_and_blockers():
    m, _ = parse_map("""
        ##########
        #@.......#
        #...#....#
        #........#
        ##########
    """)
    assert first_blocker(m, line_of_fire(m, (1, 1), (8, 1)), set()) == (7, "clear")
    idx, reason = first_blocker(m, line_of_fire(m, (1, 1), (8, 1)), {(5, 1)})
    assert (idx, reason) == (3, "actor")
    path = line_of_fire(m, (1, 2), (8, 2))
    idx, reason = first_blocker(m, path, set())
    assert reason == "wall" and path[idx] == (4, 2)


def test_line_of_fire_tries_the_reverse_line_around_corners():
    m, _ = parse_map("""
        #######
        #@....#
        ##....#
        #######
    """)
    # The forward line from (1,1) to (5,2) is fine; from (5,2) back to (1,1)
    # Bresenham would clip the corner at (1,2) - the reverse attempt saves it.
    forward = line_of_fire(m, (5, 2), (1, 1))
    assert first_blocker(m, forward, set())[1] == "clear"


def test_doors_and_furniture():
    m, _ = parse_map("""
        #########
        #@.{.+..#
        #########
    """)
    path = line_of_fire(m, (1, 1), (7, 1))
    idx, reason = first_blocker(m, path, set())
    assert reason == "wall" and path[idx] == (5, 1), "arrows fly over fountains but not through closed doors"
    m.tiles[1][5] = DOOR_OPEN
    assert first_blocker(m, line_of_fire(m, (1, 1), (7, 1)), set())[1] == "clear"
