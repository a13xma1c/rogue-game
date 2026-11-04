"""The item model: consumables, stacking, identification, rarity and affixes."""

import random
from collections import Counter

import pytest

from roguegame import items as I
from roguegame.items import (
    AFFIXES,
    CONSUMABLES,
    RARITIES,
    Identification,
    add_affixes,
    affix_text,
    gear_name,
    make_consumable,
    make_ring,
    make_weapon,
    random_gear,
    random_item,
    roll_rarity,
)


# ------------------------------------------------------------ consumables
def test_consumable_tables():
    assert len(I.POTIONS) >= 8 and len(I.SCROLLS) >= 8 and len(I.FOODS) == 3 and len(I.BOOKS) >= 5
    for table in CONSUMABLES.values():
        for key, spec in table.items():
            assert spec.key == key and spec.description and spec.weight > 0
    assert all(f.nutrition > 0 for f in I.FOODS.values())
    assert {k for k, c in I.POTIONS.items() if c.harmful} == {"poison", "blindness"}
    assert {k for k, c in I.SCROLLS.items() if c.harmful} == {"aggravation"}


def test_books_teach_real_spells():
    from roguegame.spells import SPELLS

    assert set(I.BOOKS) <= set(SPELLS)


@pytest.mark.parametrize("kind, subtype, name", [
    ("potion", "healing", "potion of healing"), ("scroll", "magic mapping", "scroll of magic mapping"),
    ("food", "apple", "apple"), ("book", "fireball", "tome of Fireball"),
])
def test_consumable_names(kind, subtype, name):
    assert make_consumable(0, 0, kind, subtype).name == name


def test_consumables_respect_min_depth():
    rng = random.Random(0)
    for _ in range(300):
        assert I.pick_consumable("potion", 1, rng) not in ("might", "greater healing", "haste")


def test_stacking():
    a, b = make_consumable(0, 0, "potion", "mana"), make_consumable(0, 0, "potion", "mana", 2)
    assert a.stackable and a.same_stack(b)
    assert not a.same_stack(make_consumable(0, 0, "potion", "haste"))
    assert not make_weapon(0, 0, 1).stackable


# --------------------------------------------------------- identification
def test_appearances_are_shuffled_per_game_and_unique():
    a, b = Identification(random.Random(1)), Identification(random.Random(2))
    assert a.potion_looks != b.potion_looks or a.scroll_labels != b.scroll_labels
    for ident in (a, b):
        assert set(ident.potion_looks) == set(I.POTIONS)
        assert len({look for look, _ in ident.potion_looks.values()}) == len(I.POTIONS)
        assert len(set(ident.scroll_labels.values())) == len(I.SCROLLS)


def test_names_depend_on_knowledge():
    ident = Identification(random.Random(1))
    potion = make_consumable(0, 0, "potion", "haste", 2)
    look = ident.potion_looks["haste"][0]
    assert ident.name(potion) == f"2 {look} potions"
    assert ident.name(potion, with_count=False) == f"{look} potion"
    assert ident.learn("potion", "haste") and not ident.learn("potion", "haste")
    assert ident.name(potion) == "2 potions of haste"
    scroll = make_consumable(0, 0, "scroll", "identify")
    assert ident.name(scroll) == f"scroll labelled {ident.scroll_labels['identify']}"
    ident.identify(scroll)
    assert ident.name(scroll) == "scroll of identify"
    assert ident.name(make_consumable(0, 0, "food", "bread", 3)) == "3 loaves of bread"
    assert ident.name(make_consumable(0, 0, "food", "apple", 2)) == "2 apples"


def test_gear_identification():
    ident = Identification(random.Random(1))
    rng = random.Random(4)
    gear = next(g for g in (random_gear(0, 0, 6, rng, "weapon") for _ in range(100)) if g.affixes)
    assert not gear.identified and not ident.is_known(gear)
    assert ident.name(gear).endswith("(unidentified)") and "+" in ident.name(gear)
    ident.identify(gear)
    assert ident.name(gear) == gear.name == gear_name(gear)


def test_colours_mean_rarity_for_gear():
    ident = Identification(random.Random(1))
    plain = I.make_armor(0, 0, 1)
    assert ident.color(plain) == RARITIES["common"].color, "blue armor must not look magical"
    assert ident.color(make_consumable(0, 0, "potion", "mana")) == ident.potion_looks["mana"][1]


# ------------------------------------------------------- rarity & affixes
def test_rarities_get_rarer_and_deeper_is_better():
    def share(depth, rarity):
        rng = random.Random(depth)
        rolls = Counter(roll_rarity(depth, rng) for _ in range(4000))
        return rolls[rarity] / 4000

    assert share(1, "common") > share(1, "magic") > share(1, "rare") > share(1, "legendary") > 0
    assert share(10, "legendary") > share(1, "legendary")
    assert share(10, "common") < share(1, "common")


def test_minimum_rarity():
    rng = random.Random(3)
    assert all(roll_rarity(1, rng, minimum="magic") != "common" for _ in range(200))


@pytest.mark.parametrize("rarity", list(RARITIES))
def test_affix_counts_follow_rarity(rarity):
    rng = random.Random(9)
    lo, hi = RARITIES[rarity].affixes
    for _ in range(100):
        item = make_weapon(0, 0, 2)
        item.rarity = rarity
        add_affixes(item, 1, rng)  # depth 1: no curses
        assert lo <= len(item.affixes) <= hi
        stats = [AFFIXES[k].stat for k, _ in item.affixes]
        assert len(stats) == len(set(stats)), "never two affixes for the same stat"
        for key, value in item.affixes:
            a = AFFIXES[key]
            assert "weapon" in a.slots and not a.curse
            assert value >= a.low
        assert item.identified == (not item.affixes)


def test_affixes_only_roll_on_their_slots():
    rng = random.Random(11)
    for _ in range(500):
        gear = random_gear(0, 0, 8, rng)
        for key, _ in gear.affixes:
            assert gear.kind in AFFIXES[key].slots


def test_curses():
    rng = random.Random(12)
    gear = [random_gear(0, 0, 6, rng) for _ in range(1500)]
    cursed = [g for g in gear if g.cursed]
    assert 0.02 < len(cursed) / len(gear) < 0.2
    for g in cursed:
        assert any(AFFIXES[k].curse for k, _ in g.affixes) and g.rarity != "common"
    shallow = [random_gear(0, 0, 1, rng) for _ in range(500)]
    assert not any(g.cursed for g in shallow), "no curses on the first floor"


def test_gear_names_and_bonuses():
    sword = make_weapon(0, 0, 2, base="sword")
    sword.affixes = [("keen", 7), ("bear", 10)]
    sword.rarity = "rare"
    assert gear_name(sword) == "Keen sword +2 of the Bear"
    assert sword.bonus("crit") == 7 + sword.crit
    assert sword.bonus("max_hp") == 10 and sword.bonus("defense") == 0
    sword.rarity, sword.appearance = "legendary", "Dusklight"
    assert gear_name(sword) == "Dusklight, Keen sword +2 of the Bear"


def test_affix_text():
    assert affix_text("bear", 12) == "+12 max HP"
    assert affix_text("hunger", -40) == "hunger 40% faster"
    assert affix_text("flaming", 20) == "20% chance to set foes alight"
    for key, a in AFFIXES.items():
        assert affix_text(key, a.low), key


def test_rings_are_always_magical():
    rng = random.Random(5)
    for _ in range(100):
        ring = make_ring(0, 0, 2, rng)
        assert ring.rarity != "common" and ring.affixes and ring.appearance
        assert not ring.identified


def test_random_items_spread():
    rng = random.Random(7)
    kinds = Counter(random_item(0, 0, 4, rng).kind for _ in range(3000))
    assert set(kinds) == {"gold", "potion", "scroll", "food", "ammo", "weapon", "armor", "launcher", "ring", "book"}
    assert kinds["gold"] > kinds["book"]
    assert Counter(random_item(0, 0, 1, rng).kind for _ in range(1000))["book"] == 0, "no tomes on floor 1"


def test_identical_items_are_still_different_items():
    """Regression: Item used dataclass value-equality, so pack.remove(item)
    could remove an identical twin instead - duplicating an item between the
    pack and an equipment slot."""
    a, b = make_weapon(0, 0, 1, base="sword"), make_weapon(0, 0, 1, base="sword")
    assert a != b and a == a
    pack = [a, b]
    pack.remove(b)
    assert pack[0] is a
    assert len({a, b}) == 2, "hashable by identity"
