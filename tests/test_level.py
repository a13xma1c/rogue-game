"""Floor population: stairs, furniture, traps, NPCs, monsters and items."""

import pytest

from roguegame import settings as S
from roguegame.dungeon import DIRS8
from roguegame.level import REFERENCE_AREA, SAFE_RADIUS, build_level, level_rng
from roguegame.mapgen import STYLES
from roguegame.tiles import CHEST, FLOOR, FOUNTAIN, STAIRS_DOWN, STAIRS_UP, TRAP

from conftest import all_openable, cached_level, reachable

SPREAD = (S.MAP_W * S.MAP_H / REFERENCE_AREA) ** 0.7

SEEDS = range(12)
DEPTHS = range(1, S.MAX_DEPTH + 1)


@pytest.fixture(scope="module")
def levels():
    return {(seed, depth): cached_level(seed, depth) for seed in SEEDS for depth in DEPTHS}


def each(levels):
    return levels.values()


def test_stairs_layout(levels):
    for lvl in each(levels):
        m = lvl.map
        ups, downs = m.find_tiles(STAIRS_UP), m.find_tiles(STAIRS_DOWN)
        if lvl.depth == 1:
            assert lvl.up_stairs is None and ups == []
        else:
            assert ups == [lvl.up_stairs] and lvl.start == lvl.up_stairs
        if lvl.depth == S.MAX_DEPTH:
            assert lvl.down_stairs is None and downs == []
        else:
            assert downs == [lvl.down_stairs]


def test_amulet_is_carried_by_the_final_boss(levels):
    for lvl in each(levels):
        assert not [it for it in lvl.items if it.kind == "amulet"], "the Amulet is never just lying around"
        carriers = [m for m in lvl.monsters if m.carries_amulet]
        if lvl.depth == S.MAX_DEPTH:
            assert carriers == [lvl.boss] and lvl.boss.name == "lich"
        else:
            assert carriers == []


def test_everything_important_is_reachable(levels):
    """Furniture must never cut the level in two."""
    for lvl in each(levels):
        m = lvl.map
        region = reachable(m, lvl.start)
        assert region == all_openable(m), f"depth {lvl.depth}: furniture split the map"
        goals = [lvl.down_stairs] + [(it.x, it.y) for it in lvl.items]
        for g in goals:
            if g:
                assert g in region
        for furn in m.find_tiles(FOUNTAIN) + m.find_tiles(CHEST):
            assert any((furn[0] + dx, furn[1] + dy) in region for dx, dy in DIRS8)


def test_way_down_is_far_from_way_in(levels):
    for lvl in each(levels):
        goal = lvl.down_stairs or (lvl.boss.x, lvl.boss.y)
        dist = lvl.map.distance_map(lvl.start)
        assert dist[goal] >= 0.6 * max(dist.values())


def test_monsters_keep_away_from_arrival(levels):
    for lvl in each(levels):
        dist = lvl.map.distance_map(lvl.start)
        assert len(lvl.monsters) >= 3
        for mon in lvl.monsters:
            assert lvl.map.tile(mon.x, mon.y) == FLOOR
            assert dist[(mon.x, mon.y)] >= SAFE_RADIUS


def test_nothing_overlaps(levels):
    for lvl in each(levels):
        spots = [(a.x, a.y) for a in lvl.monsters + lvl.npcs] + [(it.x, it.y) for it in lvl.items]
        assert len(spots) == len(set(spots))
        assert lvl.start not in spots


def test_items_lie_on_walkable_floor(levels):
    for lvl in each(levels):
        for it in lvl.items:
            assert lvl.map.walkable(it.x, it.y)
            assert not it.seen


def test_npcs(levels):
    for lvl in each(levels):
        assert 1 <= len(lvl.npcs) <= 3
        if lvl.depth == 1:
            assert "wanderer" in [n.role for n in lvl.npcs]
        roles = [n.role for n in lvl.npcs]
        assert len(roles) == len(set(roles)), "no duplicate roles on one floor"
        assert ("questgiver" in roles) == (lvl.quest is not None)
        for n in lvl.npcs:
            assert lvl.map.is_open_spot(n.x, n.y), "NPCs must not block passages"
            for o in lvl.npcs:
                if o is not n:
                    assert max(abs(o.x - n.x), abs(o.y - n.y)) > 1


def test_every_npc_role_shows_up_somewhere(levels):
    roles = {n.role for lvl in each(levels) for n in lvl.npcs}
    assert roles == {"merchant", "healer", "sage", "wanderer", "questgiver"}


def test_traps(levels):
    for lvl in each(levels):
        m = lvl.map
        assert set(m.traps) == set(m.find_tiles(TRAP))
        assert len(m.traps) == max(1, round((2 + lvl.depth) * SPREAD))
        assert all(not t.known for t in m.traps.values()), "traps start hidden"
        if lvl.depth == 1:
            assert all(t.kind != "teleport" for t in m.traps.values())
        start = lvl.start
        for x, y in m.traps:
            assert max(abs(x - start[0]), abs(y - start[1])) > 1, "no trap right at the arrival point"


def test_furniture_and_mimics(levels):
    chests = 0
    for lvl in each(levels):
        m = lvl.map
        chests += len(m.find_tiles(CHEST))
        assert len(m.find_tiles(FOUNTAIN)) <= 2
        for pos in lvl.mimics:
            assert m.tile(*pos) == CHEST
        if lvl.depth == 1:
            assert not lvl.mimics
    assert chests >= len(levels), "at least one chest per floor on average"
    assert any(lvl.mimics for lvl in each(levels)), "mimics should exist somewhere"


def test_level_rng_is_deterministic_and_per_floor():
    a = build_level(3, level_rng(7, 3))
    b = build_level(3, level_rng(7, 3))
    assert a.map.tiles == b.map.tiles
    assert [(m.name, m.x, m.y) for m in a.monsters] == [(m.name, m.x, m.y) for m in b.monsters]
    assert [(n.role, n.x, n.y) for n in a.npcs] == [(n.role, n.x, n.y) for n in b.npcs]
    c = build_level(3, level_rng(8, 3))
    d = build_level(4, level_rng(7, 4))
    assert a.map.tiles != c.map.tiles and a.map.tiles != d.map.tiles


def test_style_property(levels):
    for lvl in each(levels):
        assert lvl.style == lvl.map.style in STYLES


def test_teleport_traps_are_always_avoidable(levels):
    """Regression: a teleport rune in a 1-wide corridor was impossible to
    avoid even once known (they always fire), forcing a random teleport."""
    from roguegame.tiles import TRAP

    teleports = 0
    for lvl in each(levels):
        m = lvl.map
        for (x, y), trap in m.traps.items():
            if trap.kind != "teleport":
                continue
            teleports += 1
            around = [m.tile(x + dx, y + dy) for dx, dy in DIRS8]
            assert all(t in (FLOOR, TRAP) for t in around), f"teleport trap at {(x, y)} blocks a passage"
    assert teleports > 0, "teleport traps still exist"


def test_set_pieces_never_open_into_each_other(levels):
    """Regression: a stamped room's tunnel could end inside an earlier vault,
    making it (and its guards) reachable only through the vault's lock."""
    for lvl in each(levels):
        dist = lvl.map.distance_map(lvl.start)  # monster-style pathing: no locks, gates or secrets
        for pc in lvl.pieces:
            if pc.kind in ("treasure", "library"):
                assert any(p in dist for p in pc.interior()), f"{pc.kind} room sealed off behind another room"
        for mon in lvl.monsters:
            assert (mon.x, mon.y) in dist, f"{mon.name} stuck somewhere sealed"


def test_set_pieces_appear(levels):
    kinds = {pc.kind for lvl in each(levels) for pc in lvl.pieces}
    locks = {pc.lock for lvl in each(levels) for pc in lvl.pieces if pc.kind == "vault"}
    assert kinds == {"vault", "secret", "treasure", "library"} and locks == {"key", "lever"}


def test_monster_density_is_constant_and_xp_grows_gently_with_map_size():
    """Bigger floors hold proportionally more monsters (same crowding). Each
    is worth a bit less XP, so a bigger floor gives ~sqrt(area) times the XP:
    more than a small floor (clearing it means more fights), but not double."""
    small = build_level(2, level_rng(3, 2), width=70, height=45)
    big = build_level(2, level_rng(3, 2), width=100, height=64)

    def spawns(lvl):
        return [m for m in lvl.monsters if not m.title and not m.is_boss]

    ratio = (100 * 64) / (70 * 45)
    assert len(spawns(big)) == pytest.approx(len(spawns(small)) * ratio, rel=0.25)
    xp_small = sum(m.xp_value for m in spawns(small))
    xp_big = sum(m.xp_value for m in spawns(big))
    assert xp_big == pytest.approx(xp_small * ratio ** 0.5, rel=0.35)
