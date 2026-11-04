"""Boss floors: lairs, sealed stairs, boss abilities and the Amulet."""

import pytest

from roguegame import ai
from roguegame import settings as S
from roguegame.game import Game, State
from roguegame.level import BOSS_FLOORS, SAFE_RADIUS, build_level, level_rng
from roguegame.look import describe
from roguegame.tiles import FLOOR, STAIRS_DOWN

from conftest import add_monster, all_openable, reachable, slay_boss

ARENA = """
    ##############################
    #............................#
    #............................#
    #..@.........................#
    #............................#
    #............................#
    ##############################
"""


# ----------------------------------------------------------- generation
def test_boss_floor_configuration():
    assert set(BOSS_FLOORS) == {3, S.MAX_DEPTH}
    assert BOSS_FLOORS[3][0] == "orc warlord" and BOSS_FLOORS[S.MAX_DEPTH][0] == "lich"


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("depth", sorted(BOSS_FLOORS))
def test_boss_floors_are_sound(seed, depth):
    lvl = build_level(depth, level_rng(seed, depth))
    boss = lvl.boss
    name, guard, guard_count = BOSS_FLOORS[depth]
    assert boss is not None and boss.name == name and boss.is_boss and boss in lvl.monsters
    assert lvl.lair is not None and lvl.lair.contains(boss.x, boss.y)
    assert lvl.sealed
    # The hall is really carved out (mostly floor, a few pillars).
    m = lvl.map
    inside = [(x, y) for x in range(lvl.lair.x, lvl.lair.x + lvl.lair.w)
              for y in range(lvl.lair.y, lvl.lair.y + lvl.lair.h)]
    assert sum(m.walkable(*p) for p in inside) >= len(inside) - 6
    # Everything stays connected and the boss is far from the arrival point.
    region = reachable(m, lvl.start)
    assert all_openable(m) == region
    assert m.distance_map(lvl.start)[(boss.x, boss.y)] >= SAFE_RADIUS
    guards = [mon for mon in lvl.monsters if mon.name == guard and lvl.lair.contains(mon.x, mon.y)]
    assert len(guards) >= guard_count
    if depth == S.MAX_DEPTH:
        assert boss.carries_amulet and lvl.down_stairs is None
    else:
        assert not boss.carries_amulet and m.tile(*lvl.down_stairs) == STAIRS_DOWN
        assert lvl.lair.contains(*lvl.down_stairs), "the stairs are in the boss's hall"
    assert not any(lvl.lair.contains(*t) for t in m.traps)
    assert not any(lvl.lair.contains(n.x, n.y) for n in lvl.npcs)


def test_regular_floors_have_no_boss():
    for depth in range(1, S.MAX_DEPTH + 1):
        if depth not in BOSS_FLOORS:
            lvl = build_level(depth, level_rng(1, depth))
            assert lvl.boss is None and lvl.lair is None and not lvl.sealed
            assert not any(m.is_boss for m in lvl.monsters)


def test_bosses_are_not_scaled_below_their_floor():
    lvl = build_level(3, level_rng(2, 3))
    assert lvl.boss.max_hp == lvl.boss.kind.hp


# ----------------------------------------------------------------- seals
def reach_floor(depth: int, seed: int = 3) -> Game:
    g = Game(seed=seed)
    while g.depth < depth:
        slay_boss(g)
        g.player.x, g.player.y = g.level.down_stairs
        g.use_stairs()
    return g


def test_sealed_stairs_until_the_boss_dies():
    g = reach_floor(3)
    assert any("Something powerful" in m for m, _ in g.log)
    g.player.x, g.player.y = g.level.down_stairs
    g._update_fov()
    g.use_stairs()
    assert g.depth == 3 and "seal of dark magic" in g.log[-1][0]
    assert "sealed by dark magic" in describe(g, *g.level.down_stairs).text
    slay_boss(g)
    assert any("seal on the stairs down shatters" in m for m, _ in g.log)
    g.use_stairs()
    assert g.depth == 4


def test_the_lich_drops_the_amulet():
    g = reach_floor(S.MAX_DEPTH)
    lich = g.level.boss
    assert g._amulet_pos() == (lich.x, lich.y), "the sage would point you at the lich"
    slay_boss(g)
    amulet = [it for it in g.items if it.kind == "amulet"]
    assert len(amulet) == 1 and (amulet[0].x, amulet[0].y) == (lich.x, lich.y)
    assert g.state is State.PLAYING


def test_boss_summons_fade_when_it_dies(arena):
    g = arena(ARENA, depth=3)
    boss = add_monster(g, "orc warlord", 10, 3, alert=True)
    g.level.boss = boss
    g.summon(boss, "goblin")
    regular = add_monster(g, "orc", 20, 3)
    g._kill(boss)
    assert [m for m in g.monsters] == [regular]


# ------------------------------------------------------------- abilities
def test_warlord_war_cry_summons_goblins(arena):
    g = arena(ARENA, depth=3)
    boss = add_monster(g, "orc warlord", 8, 3, alert=True)
    g.wait()
    goblins = [m for m in g.monsters if m.name == "goblin"]
    assert len(goblins) == 2 and all(m.summoned and m.alert for m in goblins)
    # Cooldowns tick at the start of each round, before monsters act.
    assert boss.cooldowns["warcry"] == ai.WARCRY_COOLDOWN
    assert all(max(abs(m.x - boss.x), abs(m.y - boss.y)) <= 3 for m in goblins)


def test_warlord_summons_are_capped(arena):
    g = arena(ARENA, depth=3)
    boss = add_monster(g, "orc warlord", 8, 3, alert=True)
    g.summon(boss, "goblin")
    g.summon(boss, "goblin")
    ai.warlord(g, boss)  # room for just one more
    assert g.living_summons(boss) == ai.WARLORD_SUMMON_CAP
    boss.cooldowns.clear()
    ai.warlord(g, boss)
    assert g.living_summons(boss) == ai.WARLORD_SUMMON_CAP


def test_warlord_enrages_once(arena):
    g = arena(ARENA, depth=3)
    boss = add_monster(g, "orc warlord", 20, 3, alert=True)
    power = boss.power
    boss.hp = boss.max_hp // 2
    ai.warlord(g, boss)
    ai.warlord(g, boss)
    assert boss.enraged and boss.power == power + ai.ENRAGE_POWER and boss.speed == ai.ENRAGE_SPEED
    assert sum("roars in fury" in m for m, _ in g.log) == 1


def test_lich_blinks_away_when_cornered(arena):
    g = arena(ARENA, depth=5)
    lich = add_monster(g, "lich", 4, 3, alert=True)
    ai.lich(g, lich)
    d = max(abs(lich.x - g.player.x), abs(lich.y - g.player.y))
    assert 4 <= d <= 7 and g.map.tile(lich.x, lich.y) == FLOOR
    assert lich.cooldowns["blink"] > 0
    # Cornered again straight away: no blink this time, it fights.
    lich.x, lich.y = 4, 3
    ai.lich(g, lich)
    assert (lich.x, lich.y) == (4, 3)


def test_lich_fire_bolts_burn(arena, sure_hits, monkeypatch):
    g = arena(ARENA, depth=5)
    g.player.max_hp = g.player.hp = 300
    lich = add_monster(g, "lich", 9, 3, alert=True)
    monkeypatch.setattr(g.rng, "random", lambda: 0.0)
    ai.lich(g, lich)
    assert g.player.hp < 300 and g.player.has("burning")
    assert lich.cooldowns["firebolt"] == 2


def test_lich_raises_the_dead_when_wounded(arena):
    g = arena(ARENA, depth=5)
    lich = add_monster(g, "lich", 15, 3, alert=True)
    ai.lich(g, lich)
    assert not [m for m in g.monsters if m.name == "skeleton"]
    lich.hp = int(lich.max_hp * ai.LICH_RAISE_AT)
    ai.lich(g, lich)
    assert len([m for m in g.monsters if m.name == "skeleton" and m.summoned]) == 2


def test_lich_is_immune_to_poison(arena):
    g = arena(ARENA, depth=5)
    lich = add_monster(g, "lich", 15, 3)
    assert not lich.add_status("poisoned", 5)
    assert lich.add_status("burning", 5)


def test_teleport_traps_never_drop_you_in_a_lair():
    g = reach_floor(3)
    lair = g.level.lair
    for _ in range(30):
        dest = g._random_teleport_destination()
        assert dest is not None and not lair.contains(*dest)


def test_look_marks_bosses(arena):
    g = arena(ARENA, depth=5)
    lich = add_monster(g, "lich", 8, 3)
    lich.carries_amulet = True
    g._update_fov()
    text = describe(g, 8, 3).text
    assert text.startswith("BOSS: Lich") and "carries the Amulet" in text and "Immune to" in text


def test_amulet_never_drops_under_the_player(arena):
    """Regression: with the lich's own tile occupied by an item, the Amulet
    used to land on the nearest free tile - which could be under the player,
    where it could never be picked up."""
    g = arena(ARENA, depth=5)
    lich = add_monster(g, "lich", 4, 3)
    lich.carries_amulet = True
    from conftest import add_item

    add_item(g, "ammo", 4, 3, value=1)  # something already lying where the lich stands
    g.player.x, g.player.y = 3, 2  # the first neighbour the search for a free spot tries
    g._kill(lich)
    amulet = next(it for it in g.items if it.kind == "amulet")
    assert (amulet.x, amulet.y) != (g.player.x, g.player.y)
    assert (amulet.x, amulet.y) != (4, 3)
