"""Actors, items and their templates."""

import random

import pytest

from roguegame import settings as S
from roguegame.entities import (
    MIMIC,
    MONSTER_KINDS,
    MONSTER_TYPES,
    NPC,
    NPC_ROLES,
    RUMOURS,
    Actor,
    Item,
    Monster,
    Player,
    random_item,
    random_monster,
)


def test_player_defaults():
    p = Player(3, 4)
    assert (p.x, p.y, p.hp, p.max_hp, p.level) == (3, 4, 30, 30, 1)
    assert p.potions == 1 and p.scrolls == 0 and p.gold == 0
    assert p.alive and not p.has_amulet


def test_gear_adds_to_power_and_defense():
    p = Player(0, 0)
    base_atk, base_def = p.power, p.defense
    p.weapon = Item(0, 0, "weapon", "sword +2", "/", S.WHITE, 2)
    p.armor = Item(0, 0, "armor", "chain mail +3", "[", S.BLUE, 3)
    assert p.power == base_atk + 2 and p.defense == base_def + 3


def test_leveling_up():
    p = Player(0, 0)
    assert p.xp_needed == 20
    assert not p.gain_xp(19)
    assert p.gain_xp(1)
    assert p.level == 2 and p.xp == 0 and p.max_hp == 38 and p.base_power == 5 and p.base_defense == 1


def test_gaining_several_levels_at_once():
    p = Player(0, 0)
    assert p.gain_xp(20 + 40 + 5)
    assert p.level == 3 and p.xp == 5


def test_damage_is_at_least_one():
    weak = Actor(0, 0, "weak", "w", S.WHITE, hp=5, power=1, defense=0)
    tank = Actor(0, 0, "tank", "t", S.WHITE, hp=5, power=1, defense=50)
    rng = random.Random(0)
    assert all(weak.attack_damage(tank, rng) == 1 for _ in range(50))


def test_damage_range():
    a = Actor(0, 0, "a", "a", S.WHITE, hp=5, power=6, defense=0)
    b = Actor(0, 0, "b", "b", S.WHITE, hp=5, power=1, defense=2)
    rng = random.Random(1)
    rolls = {a.attack_damage(b, rng) for _ in range(300)}
    assert rolls == {3, 4, 5, 6}


def test_monsters_scale_with_depth():
    rat = MONSTER_TYPES[0]
    shallow, deep = Monster(0, 0, rat, 1), Monster(0, 0, rat, 5)
    assert deep.max_hp > shallow.max_hp and deep.power >= shallow.power
    assert deep.xp_value > shallow.xp_value
    assert not shallow.alert


def test_random_monster_respects_min_depth():
    rng = random.Random(0)
    for depth in range(1, 6):
        allowed = {k.name for k in MONSTER_TYPES if k.min_depth <= depth}
        for _ in range(100):
            assert random_monster(0, 0, depth, rng).name in allowed


def test_mimic_is_not_a_random_spawn():
    assert MIMIC.name == "mimic" and not MIMIC.spawnable
    assert all(k.name != "mimic" and not k.boss for k in MONSTER_TYPES)
    assert set(MONSTER_KINDS) >= {k.name for k in MONSTER_TYPES}


def test_random_items_cover_all_kinds_and_are_sane():
    rng = random.Random(3)
    kinds = set()
    for _ in range(400):
        it = random_item(1, 2, 3, rng)
        kinds.add(it.kind)
        assert (it.x, it.y) == (1, 2) and it.glyph and it.name and not it.seen
        if it.kind in ("weapon", "armor", "gold", "ammo", "launcher"):
            assert it.value > 0
        if it.kind == "launcher":
            assert it.range >= 6
        if it.kind in ("potion", "scroll", "food", "book"):
            assert it.subtype and it.count == 1
    assert kinds == {"gold", "potion", "scroll", "food", "book", "weapon", "armor", "ammo", "launcher", "ring"}


@pytest.mark.parametrize("role", sorted(NPC_ROLES))
def test_npc_roles(role):
    npc = NPC(5, 6, role, random.Random(0))
    spec = NPC_ROLES[role]
    assert npc.role == role and npc.glyph == "@" and npc.color == spec["color"]
    assert npc.name in spec["names"] and npc.greeting in spec["greetings"]
    assert npc.display_name == f"{npc.name} the {spec['title']}"
    assert npc.wanders == spec["wanders"] and not npc.used


def test_rumours_are_non_empty():
    assert len(RUMOURS) >= 5 and all(r.strip() for r in RUMOURS)


def test_monster_table_sanity():
    from roguegame import settings as S

    for k in MONSTER_KINDS.values():
        assert k.hp > 0 and k.power > 0 and k.speed > 0 and 0 <= k.crit <= 100
        assert (k.range > 0) == (k.ranged_power > 0), f"{k.name}: range and ranged power go together"
        if k.spawnable:
            assert 1 <= k.min_depth <= S.MAX_DEPTH and not k.boss
        if k.on_hit:
            status, turns, chance = k.on_hit
            assert turns > 0 and 0 < chance <= 1
    assert {k.name for k in MONSTER_KINDS.values() if k.boss} == {"orc warlord", "lich"}


def test_weapon_and_armor_traits():
    from roguegame.entities import ARMORS, WEAPONS, make_armor, make_weapon

    for bonus in range(1, 6):
        w = make_weapon(0, 0, bonus)
        name, acc, crit, effect = WEAPONS[min(3, bonus - 1)]
        assert w.name == f"{name} +{bonus}" and (w.accuracy, w.crit, w.effect) == (acc, crit, effect)
        a = make_armor(0, 0, bonus)
        assert a.evasion == ARMORS[min(3, bonus - 1)][1]


def test_player_starts_with_a_bow():
    p = Player(0, 0)
    assert p.launcher.kind == "launcher" and p.launcher.range == 6 and p.arrows == 10


@pytest.mark.parametrize("name, expected", [("orc", "an orc"), ("goblin", "a goblin"), ("ogre", "an ogre"),
                                            ("5 arrows", "5 arrows"), ("health potion", "a health potion")])
def test_with_article(name, expected):
    from roguegame.entities import with_article

    assert with_article(name) == expected
