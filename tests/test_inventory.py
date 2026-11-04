"""Using items in the game: the pack, consumables, identification, curses,
equipment and shops."""

import random

import pytest

from roguegame import items as I
from roguegame.entities import PACK_SIZE
from roguegame.game import State, identify_price, uncurse_price

ROOM = """
    ##################
    #................#
    #...@............#
    #................#
    ##################
"""


def give(g, item):
    """Put ``item`` in the pack; returns the stack it ended up in."""
    stack = g.player.add_to_pack(item)
    assert stack is not None
    return stack


def magic_gear(kind="weapon", cursed=False, seed=1):
    rng = random.Random(seed)
    while True:
        gear = I.random_gear(0, 0, 6, rng, kind)
        if gear.affixes and gear.cursed == cursed:
            return gear


# ------------------------------------------------------------------ pack
def test_pickup_goes_into_the_pack_and_stacks(arena, item):
    g = arena(ROOM)
    item(g, "potion", 5, 2, subtype="mana")
    item(g, "potion", 6, 2, subtype="mana")
    g.player_move(1, 0)
    g.player_move(1, 0)
    assert g.player.count("potion", "mana") == 2
    assert sum(1 for it in g.player.pack if it.subtype == "mana") == 1


def test_full_pack_leaves_items_behind(arena, item):
    g = arena(ROOM)
    p = g.player
    while len(p.pack) < PACK_SIZE:
        p.pack.append(I.make_weapon(0, 0, 1))
    sword = item(g, "weapon", 5, 2, value=3)
    g.player_move(1, 0)
    assert sword in g.items and "pack is full" in g.log[-1][0]
    potion = give_potion_to_full_pack = I.make_potion(0, 0, "healing")
    assert p.add_to_pack(give_potion_to_full_pack), "an existing stack can still grow"
    assert potion.count == 1


def test_drop(arena):
    g = arena(ROOM)
    ration = g.player.find("food", "ration")
    assert g.drop(ration)
    assert ration in g.items and ration not in g.player.pack and g.turns == 1
    assert (ration.x, ration.y) != (g.player.x, g.player.y), "never dropped where it can't be picked up"


# ------------------------------------------------------------- potions
@pytest.mark.parametrize("subtype, check", [
    ("healing", lambda g: g.player.hp == 10 + 18),
    ("greater healing", lambda g: g.player.hp == g.player.max_hp and not g.player.has("poisoned")),
    ("mana", lambda g: g.player.mana == g.player.max_mana),
    ("haste", lambda g: g.player.has("hasted")),
    ("regeneration", lambda g: g.player.has("regenerating")),
    ("might", lambda g: g.player.base_power == 5),
    ("poison", lambda g: g.player.has("poisoned")),
    ("blindness", lambda g: g.player.has("blinded")),
])
def test_potion_effects(arena, subtype, check):
    g = arena(ROOM)
    g.player.hp = 10
    g.player.mana = 0
    g.player.add_status("poisoned", 1) if subtype == "greater healing" else None
    potion = give(g, I.make_potion(0, 0, subtype))
    before = g.player.count("potion", subtype)
    assert g.quaff(potion)
    assert check(g)
    assert ("potion", subtype) in g.ident.known, "drinking it teaches you what it was"
    assert g.player.count("potion", subtype) == before - 1


def test_unknown_potions_are_drunk_even_at_full_health(arena):
    g = arena(ROOM)
    g.ident.known.discard(("potion", "healing"))
    g.quaff(g.player.find("potion", "healing"))
    assert g.player.potions == 0 and g.turns == 1


def test_regeneration_heals_each_round(arena):
    g = arena(ROOM)
    g.player.hp = 10
    g.player.add_status("regenerating", 5, potency=2)
    g.wait()
    assert g.player.hp == 12


def test_haste_gives_free_actions(arena, spawn):
    g = arena(ROOM)
    orc = spawn(g, "orc", 14, 2, alert=True)
    g.player.add_status("hasted", 20)
    for _ in range(4):
        g.wait()
    assert orc.x == 12, "four actions, two monster rounds"


# ------------------------------------------------------------- scrolls
def test_identify_with_one_candidate_is_instant(arena):
    g = arena(ROOM)
    gear = give(g, magic_gear())
    scroll = give(g, I.make_scroll(0, 0, "identify"))
    assert g.read(scroll)
    assert gear.identified and g.pending is None and g.turns == 1


def test_identify_asks_which_item(arena):
    g = arena(ROOM)
    a = give(g, magic_gear(seed=1))
    b = give(g, I.make_potion(0, 0, "haste"))
    give(g, I.make_scroll(0, 0, "identify"))
    g.read(g.player.find("scroll", "identify"))
    assert g.pending == "identify" and g.turns == 0
    assert set(map(id, g.unidentified_items())) == {id(a), id(b)}
    g.wait()
    assert g.turns == 0, "the game waits for an answer"
    assert g.choose_item(b)
    assert ("potion", "haste") in g.ident.known and not a.identified and g.turns == 1


def test_cancelling_identify_wastes_the_scroll(arena):
    g = arena(ROOM)
    give(g, magic_gear(seed=1))
    give(g, I.make_potion(0, 0, "haste"))
    give(g, I.make_scroll(0, 0, "identify"))
    g.read(g.player.find("scroll", "identify"))
    g.cancel_pending()
    assert g.pending is None and g.player.count("scroll", "identify") == 0 and g.turns == 1


def test_teleport_mapping_aggravate(arena, spawn):
    g = arena("#" * 40 + "\n#@" + "." * 37 + "#\n" + "#" * 40)
    sleeper = spawn(g, "orc", 35, 1)
    g.read(give(g, I.make_scroll(0, 0, "aggravation")))
    assert sleeper.alert and sleeper.x < 35, "it wakes - and comes for you from across the floor"
    g.read(give(g, I.make_scroll(0, 0, "magic mapping")))
    assert all(g.map.explored[1][x] for x in range(1, 39))
    g.read(give(g, I.make_scroll(0, 0, "teleportation")))
    assert g.player.x > 9


def test_enchanting(arena):
    g = arena(ROOM)
    g.player.weapon = I.make_weapon(0, 0, 1)
    g.read(give(g, I.make_scroll(0, 0, "enchant weapon")))
    assert g.player.weapon.value == 2 and "+2" in g.player.weapon.name
    g.read(give(g, I.make_scroll(0, 0, "enchant armor")))  # no armor: wasted, harmlessly
    assert g.player.armor is None


def test_you_cannot_read_blind(arena):
    g = arena(ROOM)
    g.player.add_status("blinded", 5)
    scroll = give(g, I.make_scroll(0, 0, "magic mapping"))
    assert not g.read(scroll) and scroll in g.player.pack


# ------------------------------------------------------------- equipment
def test_equipping_identifies_and_curses_bind(arena):
    g = arena(ROOM)
    cursed = give(g, magic_gear(cursed=True))
    assert not cursed.identified
    g.equip(cursed)
    assert cursed.identified and g.player.weapon is cursed
    assert any("cursed" in m for m, _ in g.log)
    assert not g.unequip("weapon") and not g.drop(cursed)
    other = give(g, I.make_weapon(0, 0, 2))
    assert not g.equip(other), "can't swap out a cursed weapon"
    g.read(give(g, I.make_scroll(0, 0, "remove curse")))
    assert not cursed.cursed and g.unequip("weapon") and cursed in g.player.pack


def test_gear_stats_apply_and_max_hp_clamps(arena):
    g = arena(ROOM)
    ring = I.make_ring(0, 0, 3, random.Random(1))
    ring.affixes, ring.identified, ring.cursed = [("bear", 10), ("nimble", 5)], True, False
    give(g, ring)
    base_hp, base_eva = g.player.max_hp, g.player.evasion
    g.equip(ring)
    assert g.player.max_hp == base_hp + 10 and g.player.evasion == base_eva + 5
    g.player.hp = g.player.max_hp
    g.unequip("ring")
    assert g.player.hp == g.player.max_hp == base_hp


def test_lifesteal_and_burning_weapons(arena, spawn, sure_hits, monkeypatch):
    g = arena(ROOM)
    blade = I.make_weapon(0, 0, 3)
    blade.affixes = [("vampiric", 50), ("flaming", 100)]
    g.player.weapon = blade
    g.player.hp = 10
    orc = spawn(g, "orc", 5, 2, hp=100, max_hp=100)
    g.melee(g.player, orc)  # just your swing, before the orc answers
    assert g.player.hp > 10 and orc.has("burning")


def test_gear_regeneration_and_sustenance(arena):
    g = arena(ROOM)
    ring = I.make_ring(0, 0, 3, random.Random(1))
    ring.affixes = [("regeneration", 2), ("sustenance", 40)]
    g.player.ring = ring
    assert g.player.hunger_rate == pytest.approx(0.6)
    g.player.hp = 10
    for _ in range(10):
        g.wait()
    assert g.player.hp == 10 + 2 + 1  # ring + natural regeneration


# ---------------------------------------------------------------- shops
def test_merchant_sells_into_the_pack_and_identifies(arena, npc):
    g = arena(ROOM)
    g.player.gold = 500
    g.talk(npc(g, "merchant", 8, 2))
    actions = [o.action for o in g.dialogue.options]
    g.choose(actions.index("buy_identify"))
    assert g.player.count("scroll", "identify") == 1 and ("scroll", "identify") in g.ident.known
    g.choose(actions.index("buy_ration"))
    assert g.player.count("food", "ration") == 2


def test_merchant_identifies_everything(arena, npc):
    g = arena(ROOM)
    g.player.gold = 500
    gear = give(g, magic_gear())
    give(g, I.make_potion(0, 0, "poison"))
    g.talk(npc(g, "merchant", 8, 2))
    actions = [o.action for o in g.dialogue.options]
    assert g.dialogue.options[actions.index("identify_all")].enabled
    g.choose(actions.index("identify_all"))
    assert gear.identified and ("potion", "poison") in g.ident.known and not g.unidentified_items()
    assert g.player.gold == 500 - identify_price(1)


def test_healer_lifts_curses(arena, npc):
    g = arena(ROOM)
    g.player.gold = 500
    cursed = magic_gear(cursed=True)
    cursed.identified = True
    g.player.weapon = cursed
    g.talk(npc(g, "healer", 8, 2))
    actions = [o.action for o in g.dialogue.options]
    g.choose(actions.index("uncurse"))
    assert not cursed.cursed and g.player.gold == 500 - uncurse_price(1)


def test_amulet_still_wins(arena, item):
    g = arena(ROOM)
    item(g, "amulet", 5, 2)
    g.player_move(1, 0)
    assert g.state is State.WON


def test_equipping_one_of_two_identical_items(arena):
    """Regression for the twin-removal bug, end to end."""
    g = arena(ROOM)
    first, second = give(g, I.make_armor(0, 0, 1)), give(g, I.make_armor(0, 0, 1))
    g.equip(second)
    assert g.player.armor is second and first in g.player.pack
    assert not any(it is second for it in g.player.pack)
