"""Endless mode: no last floor, recurring and scaling bosses."""

import pytest

from roguegame import settings as S
from roguegame.difficulty import ENDLESS, GameOptions
from roguegame.entities import BOSS_HP_PER_FLOOR, MONSTER_KINDS, Monster
from roguegame.game import Game, State
from roguegame import settings as S_
from roguegame.level import BOSS_CYCLE, REFERENCE_AREA, boss_for_depth, build_level, level_rng
from roguegame.tiles import STAIRS_DOWN, STAIRS_UP

from conftest import add_monster, all_openable, reachable, slay_boss

DENSITY = S_.MAP_W * S_.MAP_H / REFERENCE_AREA  # monsters scale fully with floor area

ENDLESS_NORMAL = GameOptions(ENDLESS, "normal")


def descend_to(g: Game, depth: int) -> None:
    while g.depth < depth:
        slay_boss(g)
        g.player.x, g.player.y = g.level.down_stairs
        g._update_fov()
        g.use_stairs()


def connected(m, start) -> bool:
    return reachable(m, start) == all_openable(m)


# ---------------------------------------------------------------- bosses
def test_classic_boss_floors():
    assert [d for d in range(1, 12) if boss_for_depth(d)] == [3, 5]


def test_endless_bosses_cycle():
    floors = {d: boss_for_depth(d, None) for d in range(1, 26)}
    warlords = [d for d, b in floors.items() if b and b[0] == "orc warlord"]
    liches = [d for d, b in floors.items() if b and b[0] == "lich"]
    assert warlords == [3, 8, 13, 18, 23]
    assert liches == [5, 10, 15, 20, 25]
    assert BOSS_CYCLE == S.MAX_DEPTH


def test_bosses_grow_each_cycle():
    home = Monster(0, 0, "orc warlord", 3)
    later = Monster(0, 0, "orc warlord", 8)
    assert home.max_hp == MONSTER_KINDS["orc warlord"].hp
    assert later.max_hp == home.max_hp + 5 * BOSS_HP_PER_FLOOR
    assert later.power > home.power


# ----------------------------------------------------------------- floors
@pytest.mark.parametrize("depth", [5, 6, 10, 17, 30])
def test_endless_floors_always_lead_down(depth):
    lvl = build_level(depth, level_rng(3, depth), max_depth=None)
    m = lvl.map
    assert lvl.down_stairs and m.tile(*lvl.down_stairs) == STAIRS_DOWN
    assert lvl.up_stairs and m.tile(*lvl.up_stairs) == STAIRS_UP
    assert not [it for it in lvl.items if it.kind == "amulet"]
    assert not any(mon.carries_amulet for mon in lvl.monsters)
    assert connected(m, lvl.start)


@pytest.mark.parametrize("depth", [11, 12, 14, 16])
def test_monster_count_stops_growing(depth):
    """Beyond floor 10 floors get harder through monster stats, not sheer numbers."""
    assert boss_for_depth(depth, None) is None
    lvl = build_level(depth, level_rng(1, depth), max_depth=None)
    random_spawns = [m for m in lvl.monsters if not m.title]  # quest champions come on top
    assert len(random_spawns) <= round((4 + 10 * 2) * DENSITY) + 3  # (+ treasure-room guards)
    deeper = build_level(depth + 10, level_rng(1, depth + 10), max_depth=None)
    assert len([m for m in deeper.monsters if not m.title and not m.is_boss]) <= round((4 + 10 * 2) * DENSITY) + 5


def test_deep_monsters_are_stronger():
    shallow = Monster(0, 0, "orc", 2)
    deep = Monster(0, 0, "orc", 20)
    assert deep.max_hp > shallow.max_hp and deep.power > shallow.power and deep.accuracy > shallow.accuracy


# ------------------------------------------------------------------ games
def test_endless_game_basics():
    g = Game(seed=6, options=ENDLESS_NORMAL)
    assert g.endless and g.max_depth is None
    assert "Endless mode" in g.log[-1][0]


def test_descending_past_the_classic_bottom():
    g = Game(seed=6, options=ENDLESS_NORMAL)
    descend_to(g, 12)
    assert g.depth == 12 == g.deepest and set(g.levels) == set(range(1, 13))
    assert g.state is State.PLAYING


def test_the_endless_lich_guards_a_hoard_not_the_amulet():
    g = Game(seed=6, options=ENDLESS_NORMAL)
    descend_to(g, 5)
    lich = g.level.boss
    assert lich.name == "lich" and not lich.carries_amulet and g.level.sealed
    slay_boss(g)
    kinds = [it.kind for it in g.items if abs(it.x - lich.x) <= 3 and abs(it.y - lich.y) <= 3]
    assert "amulet" not in kinds and "gold" in kinds and len(kinds) >= 2
    assert not g.level.sealed
    g.player.x, g.player.y = g.level.down_stairs
    g.use_stairs()
    assert g.depth == 6


def test_hoard(arena):
    g = arena("""
        ##########
        #@.......#
        ##########
    """, depth=3)
    boss = add_monster(g, "orc warlord", 6, 1)
    g.level.boss = boss
    g._kill(boss)
    gold = [it for it in g.items if it.kind == "gold"]
    loot = [it for it in g.items if it.kind != "gold"]
    assert len(gold) == 1 and gold[0].value == 40 * 3
    assert len(loot) == 1
    assert all((it.x, it.y) != (g.player.x, g.player.y) for it in g.items)
    assert any("hoard" in m for m, _ in g.log)


def test_classic_lich_still_drops_the_amulet():
    g = Game(seed=6)
    descend_to(g, 5)
    slay_boss(g)
    assert [it.kind for it in g.items].count("amulet") == 1


def test_endless_score_keeps_climbing():
    g = Game(seed=8, options=ENDLESS_NORMAL)
    scores = []
    for depth in (2, 6, 11):
        descend_to(g, depth)
        scores.append(g.score)
    assert scores == sorted(scores) and len(set(scores)) == 3


def test_levels_stay_persistent_in_endless():
    g = Game(seed=9, options=ENDLESS_NORMAL)
    descend_to(g, 7)
    seventh = g.level
    g.player.x, g.player.y = g.level.up_stairs
    g.use_stairs()
    assert g.depth == 6
    g.player.x, g.player.y = g.level.down_stairs
    g.use_stairs()
    assert g.level is seventh


# ------------------------------------------------------------ depth pressure
def test_depth_pressure_starts_below_the_classic_bottom():
    from roguegame.difficulty import ENDLESS_HP_GROWTH, ENDLESS_RAMP_START, endless_factor

    assert ENDLESS_RAMP_START == S.MAX_DEPTH
    assert all(endless_factor(d, ENDLESS_HP_GROWTH) == 1 for d in range(1, ENDLESS_RAMP_START + 1))
    assert endless_factor(ENDLESS_RAMP_START + 10, ENDLESS_HP_GROWTH) == pytest.approx(ENDLESS_HP_GROWTH ** 10)


def test_endless_floors_one_to_five_match_classic():
    """Endless mode only diverges below floor 5 (apart from the Amulet)."""
    for depth in (1, 2, 4):
        classic = build_level(depth, level_rng(2, depth))
        endless = build_level(depth, level_rng(2, depth), max_depth=None)
        assert classic.map.tiles == endless.map.tiles
        assert [(m.name, m.max_hp, m.power) for m in classic.monsters] == \
               [(m.name, m.max_hp, m.power) for m in endless.monsters]


def test_endless_monsters_outgrow_classic_scaling():
    from roguegame.difficulty import ENDLESS_HP_GROWTH, ENDLESS_POWER_GROWTH, endless_factor

    plain = Monster(0, 0, "orc", 15)  # classic-style linear scaling only
    pressured = ENDLESS_NORMAL.prepare(Monster(0, 0, "orc", 15), 15)
    assert pressured.max_hp == round(plain.max_hp * endless_factor(15, ENDLESS_HP_GROWTH))
    assert pressured.power == round(plain.power * endless_factor(15, ENDLESS_POWER_GROWTH))
    assert GameOptions().prepare(Monster(0, 0, "orc", 15), 15).max_hp == plain.max_hp, "classic: no pressure"


def test_every_way_a_monster_appears_gets_the_pressure(arena):
    g = arena("""
        ##########
        #@.&.....#
        #........#
        ##########
    """, depth=12)
    g.options = ENDLESS_NORMAL
    boss = add_monster(g, "orc warlord", 7, 2)
    minion = g.summon(boss, "goblin")
    assert minion.max_hp == ENDLESS_NORMAL.prepare(Monster(0, 0, "goblin", 12), 12).max_hp > \
           Monster(0, 0, "goblin", 12).max_hp
    g.level.mimics.add((3, 1))
    g.player_move(1, 0)
    g.player_move(1, 0)
    assert g.monster_at(3, 1).max_hp == ENDLESS_NORMAL.prepare(Monster(0, 0, "mimic", 12), 12).max_hp
    lvl = build_level(12, level_rng(1, 12), max_depth=None)
    sample = lvl.monsters[0]
    assert sample.max_hp == ENDLESS_NORMAL.prepare(Monster(0, 0, sample.kind, 12), 12).max_hp
