"""Look / inspect: knowledge rules and heuristics."""

import math

import pytest

from roguegame import settings as S
from roguegame.entities import Item, Player
from roguegame.look import (
    REMEMBERED,
    UNKNOWN,
    VISIBLE,
    assess_threat,
    describe,
    expected_damage,
    health_word,
    interesting_targets,
    item_advice,
    knowledge,
    route_length,
)
from roguegame.tiles import FOUNTAIN

from conftest import add_monster

ROOM = """
    ##################
    #................#
    #...@............#
    #................#
    ##################
"""

SPLIT = """
    ####################
    #@.......#.........#
    #........+.........#
    ####################
"""


# --------------------------------------------------------------- numbers
def test_expected_damage():
    assert expected_damage(4, 0) == (3 + 4 + 5 + 6) / 4
    assert expected_damage(1, 5) == 1, "minimum one damage per hit"
    assert expected_damage(3, 2) == (1 + 1 + 2 + 3) / 4


def test_threat_labels_cover_the_range(arena):
    g = arena(ROOM)
    p = g.player
    labels = {}
    for name in ("rat", "goblin", "orc", "ogre", "troll"):
        labels[name] = assess_threat(p, add_monster(g, name, 10, 2)).label
    assert labels["rat"] in ("harmless", "easy")
    assert labels["troll"] == "deadly"
    order = ["harmless", "easy", "fair fight", "dangerous", "deadly"]
    ranks = [order.index(labels[n]) for n in ("rat", "goblin", "orc", "ogre", "troll")]
    assert ranks == sorted(ranks), "tougher monsters never look safer"


def test_threat_drops_as_monster_weakens_and_grows_as_you_weaken(arena):
    g = arena(ROOM)
    ogre = add_monster(g, "ogre", 10, 2)
    base = assess_threat(g.player, ogre)
    ogre.hp = 1
    assert assess_threat(g.player, ogre).ratio > base.ratio
    ogre.hp = ogre.max_hp
    g.player.hp = 2
    assert assess_threat(g.player, ogre).ratio < base.ratio


def test_threat_numbers(arena):
    g = arena(ROOM)
    p = g.player
    rat = add_monster(g, "rat", 10, 2)  # hp 6, power 3, def 0, acc 70, eva 15
    t = assess_threat(p, rat)
    # You: 4.5 avg damage, (80 - 15)% to hit, 5% crits doubling damage.
    yours = 4.5 * 0.65 * 1.05
    # Rat: 3.5 avg damage, (70 - 10)% to hit, 5% crits.
    its = 3.5 * 0.60 * 1.05
    assert t.hits_to_kill == math.ceil(6 / yours) == 2
    assert t.hits_to_die == math.ceil(30 / its) == 14


@pytest.mark.parametrize("hp, word", [(10, "unhurt"), (7, "lightly wounded"), (4, "badly wounded"),
                                      (1, "almost dead")])
def test_health_words(hp, word):
    p = Player(0, 0)
    p.max_hp, p.hp = 10, hp
    assert health_word(p) == word


def test_item_advice():
    p = Player(0, 0)
    sword = Item(0, 0, "weapon", "sword +2", "/", S.WHITE, 2)
    text, color = item_advice(p, sword, 1)
    assert "Upgrade: +2 ATK" in text and "bare fists" in text and color == S.GREEN
    p.weapon = Item(0, 0, "weapon", "axe +3", "/", S.WHITE, 3)
    text, color = item_advice(p, sword, 1)
    assert "No better than your axe +3" in text and color == S.GREY
    armor = Item(0, 0, "armor", "plate +1", "[", S.WHITE, 1)
    assert "DEF" in item_advice(p, armor, 1)[0] and "no armor" in item_advice(p, armor, 1)[0]
    from roguegame.items import make_potion, make_scroll

    assert "18 HP" in item_advice(p, make_potion(0, 0, "healing"), 1)[0]
    assert "11" in item_advice(p, make_scroll(0, 0, "fire"), 1)[0]
    assert "40 gold" in item_advice(p, Item(0, 0, "gold", "g", "$", S.RED, 40), 1)[0]
    assert "win" in item_advice(p, Item(0, 0, "amulet", "a", "*", S.RED), 1)[0]


# -------------------------------------------------------------- knowledge
def test_knowledge_states(arena):
    g = arena(SPLIT)
    assert knowledge(g, 2, 1) == VISIBLE
    assert knowledge(g, 15, 1) == UNKNOWN
    assert knowledge(g, -3, 0) == UNKNOWN
    g.map.explored[1][15] = True
    assert knowledge(g, 15, 1) == REMEMBERED


def test_describe_unexplored(arena):
    g = arena(SPLIT)
    insp = describe(g, 15, 1)
    assert insp.title == "Unexplored" and "haven't seen" in insp.text


def test_describe_self(arena):
    g = arena(ROOM)
    insp = describe(g, 4, 2)
    assert insp.title == "You" and "HP 30/30" in insp.text


def test_describe_self_on_stairs(arena):
    g = arena("""
        #####
        #.>.#
        #####
    """.replace(">", "@"))
    g.map.tiles[1][2] = 2  # stairs down under the player
    assert "standing on: stairs down" in describe(g, 2, 1).text


def test_describe_visible_monster(arena, spawn):
    g = arena(ROOM)
    spawn(g, "troll", 10, 2)
    spawn(g, "rat", 12, 3)
    insp = describe(g, 10, 2)
    assert insp.title == "Troll - deadly" and insp.color == S.RED
    assert "unaware" in insp.text and "~" in insp.text
    assert "1 other foe in view" in insp.text
    assert "About 6 steps away" in insp.text


def test_monsters_out_of_sight_are_not_revealed(arena, spawn):
    g = arena(SPLIT)
    spawn(g, "troll", 15, 1)
    g.map.explored[1][15] = True
    insp = describe(g, 15, 1)
    assert "roll" not in insp.text
    assert "remembered" in insp.text


def test_describe_npc(arena, npc):
    g = arena(ROOM)
    n = npc(g, "merchant", 8, 2)
    g._update_fov()
    insp = describe(g, 8, 2)
    assert insp.title == n.display_name and "Friendly" in insp.text and "gold" in insp.text


def test_describe_items_seen_and_remembered(arena, item):
    g = arena(SPLIT)
    sword = item(g, "weapon", 5, 1, value=2, name="sword +2")
    assert sword.seen
    insp = describe(g, 5, 1)
    assert insp.title == "Sword +2" and "Upgrade" in insp.text
    g.map.visible[1][5] = False
    insp = describe(g, 5, 1)
    assert "remembered" in insp.text and "Sword" in insp.title


def test_unseen_items_are_not_described(arena, item):
    g = arena(SPLIT)
    hidden = item(g, "potion", 15, 1)
    assert not hidden.seen
    g.map.explored[1][15] = True
    assert describe(g, 15, 1).title == "Floor"


def test_hidden_traps_look_like_floor(arena):
    g = arena("""
        ########
        #@.^...#
        ########
    """)
    assert describe(g, 3, 1).title == "Floor"
    g.map.traps[(3, 1)].known = True
    insp = describe(g, 3, 1)
    assert insp.title == "Spike trap" and "step around" in insp.text


def test_stairs_descriptions(arena):
    g = arena("""
        ########
        #@.>.<.#
        ########
    """, depth=2)
    assert "floor 3 (unexplored)" in describe(g, 3, 1).text
    assert "up to floor 1" in describe(g, 5, 1).text
    g.levels[3] = g.levels[2]  # pretend floor 3 was visited
    assert "floor 3 (visited)" in describe(g, 3, 1).text


def test_fountain_and_chest_heuristics(arena):
    g = arena("""
        ########
        #@.{.&.#
        ########
    """, depth=3)
    assert "save it for later" in describe(g, 3, 1).text
    g.player.hp = 10
    assert "restore 15 HP" in describe(g, 3, 1).text
    assert "mimics" in describe(g, 5, 1).text


def test_walls_have_no_route_line(arena):
    g = arena(ROOM)
    assert "step" not in describe(g, 0, 0).text
    assert describe(g, 0, 0).title == "Wall"


# ------------------------------------------------------------------ routes
def test_route_length_over_known_ground(arena):
    g = arena(SPLIT)
    assert route_length(g, 5, 1) == 4
    g.map.explored[1][15] = True
    assert route_length(g, 15, 1) is None, "no known way through unexplored tiles"
    assert "No known route" in describe(g, 15, 1).text
    g.map.reveal()
    assert route_length(g, 15, 1) == 14


def test_route_to_furniture_means_standing_next_to_it(arena):
    g = arena("""
        ########
        #@...{.#
        ########
    """)
    assert g.map.tile(5, 1) == FOUNTAIN
    assert route_length(g, 5, 1) == 4


def test_precomputed_distance_map_is_used(arena):
    g = arena(ROOM)
    fake = {(10, 2): 99}
    assert "99 steps" in describe(g, 10, 2, dist=fake).text


# ---------------------------------------------------------------- targets
def test_targets_ranked_by_danger_then_kind(arena, spawn, npc, item):
    g = arena("""
        ##################
        #................#
        #...@......>.....#
        #................#
        ##################
    """)
    potion = item(g, "potion", 6, 1)
    friend = npc(g, "healer", 6, 3)
    rat = spawn(g, "rat", 7, 2)
    troll = spawn(g, "troll", 7, 1)
    g._update_fov()
    t = interesting_targets(g)
    assert t[:4] == [(troll.x, troll.y), (rat.x, rat.y), (friend.x, friend.y), (potion.x, potion.y)]
    assert t[4] == (11, 2), "then features such as stairs"
    assert (g.player.x, g.player.y) not in t


def test_closer_threats_rank_higher(arena, spawn):
    g = arena(ROOM)
    far = spawn(g, "orc", 11, 2)  # still inside the FOV radius
    near = spawn(g, "orc", 6, 2)
    g._update_fov()
    assert interesting_targets(g)[:2] == [(near.x, near.y), (far.x, far.y)]


def test_targets_skip_unseen_things_but_include_remembered_stairs(arena, spawn):
    g = arena("""
        ####################
        #@.......#.......>.#
        #........+.........#
        ####################
    """)
    spawn(g, "troll", 15, 1)
    assert interesting_targets(g) == []
    g.map.explored[1][17] = True
    assert interesting_targets(g) == [(17, 1)]


def test_amulet_is_the_top_item(arena, item):
    g = arena(ROOM)
    item(g, "gold", 5, 2, value=5)
    item(g, "amulet", 12, 2)
    assert interesting_targets(g)[0] == (12, 2)


def test_describe_self_mentions_item_underfoot(arena, item):
    g = arena(ROOM)
    g.player.weapon = item(g, "weapon", 0, 0, value=5, name="axe +5")
    g.items.remove(g.player.weapon)
    item(g, "weapon", 4, 2, value=1, name="dagger +1")
    text = describe(g, 4, 2).text
    assert "dagger +1 here" in text and "No better" in text


# ----------------------------------------------------- combat-era heuristics
def test_monster_description_covers_behaviour_and_odds(arena, spawn):
    g = arena(ROOM)
    spawn(g, "goblin archer", 9, 2)
    spider = spawn(g, "cave spider", 10, 3)
    spider.add_status("burning", 2)
    g._update_fov()
    archer = describe(g, 9, 2).text
    assert "Keeps its distance and shoots" in archer and "up to 6 tiles" in archer
    assert "Your hit chance" in archer and "its hit chance" in archer
    text = describe(g, 10, 3).text
    assert "Fast." in text and "leave you poisoned" in text and "Immune to: poisoned" in text
    assert "It is burning (2)" in text


def test_ranged_and_speed_make_monsters_scarier(arena, spawn):
    g = arena(ROOM)
    slow = spawn(g, "orc", 10, 2)
    fast = spawn(g, "orc", 10, 3)
    fast.speed = 200
    assert assess_threat(g.player, fast).ratio < assess_threat(g.player, slow).ratio


def test_your_bow_counts_towards_threat(arena, spawn):
    g = arena(ROOM)
    orc = spawn(g, "orc", 10, 2)
    from roguegame.entities import make_launcher

    with_bow = assess_threat(g.player, orc).hits_to_kill
    g.player.launcher = make_launcher(0, 0, "crossbow", 9, 7, 30)
    assert assess_threat(g.player, orc).hits_to_kill < with_bow
    g.player.arrows = 0
    assert assess_threat(g.player, orc).hits_to_kill == with_bow, "no arrows, no help"


def test_gear_traits_in_item_advice():
    from roguegame.entities import make_ammo, make_armor, make_launcher, make_weapon

    p = Player(0, 0)
    text, _ = item_advice(p, make_weapon(0, 0, 1), 1)
    assert "accuracy +5%" in text and "crit +10%" in text
    text, _ = item_advice(p, make_weapon(0, 0, 4), 1)
    assert "criticals stun" in text
    text, _ = item_advice(p, make_armor(0, 0, 3), 1)
    assert "evasion -5%" in text
    text, _ = item_advice(p, make_launcher(0, 0, "longbow", 2, 8, 0), 1)
    assert "Upgrade: +1 ranged ATK over your shortbow +1" in text and "range 8" in text
    assert "5 arrows" in item_advice(p, make_ammo(0, 0, 5), 1)[0]


def test_self_description_shows_combat_stats_and_statuses(arena):
    g = arena(ROOM)
    g.player.add_status("slowed", 3)
    text = describe(g, 4, 2).text
    assert "Accuracy 80%" in text and "slowed (3)" in text
    assert "evasion 0%" in text, "being slowed costs 10 evasion"
