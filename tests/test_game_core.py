"""Turn structure, combat, items and win/lose - on hand-made arenas."""

import random

import pytest

from roguegame.game import Game, State

# These tests are about what attacks *do*; test_combat.py covers the odds.
pytestmark = pytest.mark.usefixtures("sure_hits")

ROOM = """
    ##########
    #........#
    #...@....#
    #........#
    ##########
"""


def test_new_game_setup():
    g = Game(seed=5)
    assert g.state is State.PLAYING and g.depth == 1 and g.turns == 0
    assert g.seed == 5 and set(g.levels) == {1}
    assert g.map.walkable(g.player.x, g.player.y)
    assert g.map.visible[g.player.y][g.player.x]
    assert "Amulet" in g.log[-1][0]


def test_seed_is_chosen_when_not_given():
    a, b = Game(), Game()
    assert isinstance(a.seed, int) and a.seed != b.seed


def test_same_seed_same_dungeon():
    a, b = Game(seed=9), Game(seed=9)
    assert a.map.tiles == b.map.tiles
    assert (a.player.x, a.player.y) == (b.player.x, b.player.y)


def test_moving_takes_a_turn(arena):
    g = arena(ROOM)
    g.player_move(1, 0)
    assert (g.player.x, g.player.y) == (5, 2) and g.turns == 1


def test_bumping_a_wall_is_free(arena):
    g = arena("""
        ####
        #@.#
        ####
    """)
    g.player_move(-1, 0)
    assert (g.player.x, g.player.y) == (1, 1) and g.turns == 0


def test_wait_takes_a_turn(arena):
    g = arena(ROOM)
    g.wait()
    assert g.turns == 1


def test_bump_attacks_monster(arena, spawn):
    g = arena(ROOM)
    rat = spawn(g, "rat", 5, 2, hp=100, max_hp=100)
    g.player_move(1, 0)
    assert rat.hp < 100 and (g.player.x, g.player.y) == (4, 2)
    assert "You hit the rat" in " ".join(m for m, _ in g.log)


def test_killing_grants_xp_and_removes_monster(arena, spawn):
    g = arena(ROOM)
    rat = spawn(g, "rat", 5, 2, hp=1)
    g.player_move(1, 0)
    assert rat not in g.monsters
    assert g.player.kills == 1 and g.player.xp == rat.xp_value


def test_monster_drops_are_placed_on_floor(arena, spawn):
    g = arena(ROOM)
    g.rng = random.Random(0)
    drops = 0
    for _ in range(40):
        g.items.clear()
        rat = spawn(g, "rat", 5, 2, hp=1)
        g._kill(rat)
        drops += bool(g.items)
        for it in g.items:
            assert (it.x, it.y) == (5, 2)
    assert 0 < drops < 40, "drops happen sometimes, not always"


def test_level_up_message(arena, spawn):
    g = arena(ROOM)
    spawn(g, "rat", 5, 2, hp=1, xp_value=25)
    g.player_move(1, 0)
    assert g.player.level == 2
    assert any("reach level 2" in m for m, _ in g.log)


def test_adjacent_awake_monster_attacks(arena, spawn):
    g = arena(ROOM)
    spawn(g, "orc", 5, 2, alert=True)
    g.wait()
    assert g.player.hp < g.player.max_hp


def test_monsters_notice_and_chase(arena, spawn):
    g = arena("""
        ################
        #@.............#
        ################
    """)
    orc = spawn(g, "orc", 8, 1)
    g.wait()
    assert orc.alert and orc.x == 7


def test_unseen_monsters_stay_put(arena, spawn):
    g = arena("""
        ###########
        #@..#.....#
        ###########
    """)
    orc = spawn(g, "orc", 8, 1)
    for _ in range(5):
        g.wait()
    assert (orc.x, orc.y) == (8, 1) and not orc.alert


def test_death(arena, spawn):
    g = arena(ROOM)
    g.player.hp = 1
    spawn(g, "troll", 5, 2, alert=True)
    g.wait()
    assert g.state is State.DEAD and g.death_cause == "killed by a troll"
    turns = g.turns
    g.player_move(-1, 0)
    g.wait()
    g.use_potion()
    assert g.turns == turns, "the dead don't act"


def test_natural_regeneration(arena):
    g = arena(ROOM)
    g.player.hp = 10
    for _ in range(10):
        g.wait()
    assert g.player.hp == 11


# --------------------------------------------------------------- pickups
def test_pickup_gold_potion_scroll(arena, item):
    g = arena(ROOM)
    item(g, "gold", 5, 2, value=12)
    item(g, "potion", 6, 2)
    item(g, "scroll", 7, 2)
    for _ in range(3):
        g.player_move(1, 0)
    p = g.player
    assert p.gold == 12 and p.potions == 2 and p.scrolls == 1 and not g.items
    assert p.find("scroll", "fire") in p.pack


def test_gear_goes_into_the_pack_not_onto_you(arena, item):
    """Gear is never auto-equipped any more (it might be cursed)."""
    g = arena(ROOM)
    sword = item(g, "weapon", 5, 2, value=3, name="sword +3")
    g.player_move(1, 0)
    assert sword in g.player.pack and g.player.weapon is None
    assert "upgrade" in g.log[-1][0]


def test_equipping_from_the_pack(arena, item):
    g = arena(ROOM)
    sword = item(g, "weapon", 5, 2, value=3, name="sword +3")
    dagger = item(g, "weapon", 6, 2, value=1, name="dagger +1")
    g.player_move(1, 0)
    g.player_move(1, 0)
    assert g.equip(sword) and g.player.weapon is sword and g.turns == 3
    assert g.equip(dagger) and g.player.weapon is dagger
    assert sword in g.player.pack, "the old weapon goes back into the pack"


def test_armor_equip(arena, item):
    g = arena(ROOM)
    mail = item(g, "armor", 5, 2, value=2, name="chain mail +2")
    g.player_move(1, 0)
    g.equip(mail)
    assert g.player.armor is mail and g.player.defense == 2


def test_amulet_wins(arena, item):
    g = arena(ROOM)
    item(g, "amulet", 5, 2)
    g.player_move(1, 0)
    assert g.state is State.WON and g.player.has_amulet


# ------------------------------------------------------------- consumables
def test_potion_rules(arena):
    g = arena(ROOM)
    g.use_potion()
    assert g.player.potions == 1 and g.turns == 0, "no drinking at full health"
    g.player.hp = 5
    g.use_potion()
    assert g.player.potions == 0 and g.player.hp == 5 + 15 + 3 and g.turns == 1
    g.player.hp = 5
    g.use_potion()
    assert g.player.hp == 5 and g.turns == 1


def test_scroll_burns_only_visible_monsters(arena, spawn, npc):
    g = arena("""
        ##############
        #@....#......#
        ##############
    """)
    g.player.scrolls = 1
    near = spawn(g, "orc", 4, 1, hp=100, max_hp=100)
    far = spawn(g, "orc", 10, 1, hp=100, max_hp=100)
    friend = npc(g, "merchant", 3, 1)
    g._update_fov()
    g.use_scroll()
    # 11 from the blast, then the survivor burns for 2 when the round ticks.
    assert near.hp == 100 - (8 + 3) - 2 and near.has("burning")
    assert far.hp == 100 and not far.statuses
    assert friend.hp == friend.max_hp
    assert g.player.scrolls == 0


def test_scroll_needs_targets_and_stock(arena, spawn):
    g = arena(ROOM)
    g.use_scroll()
    assert "no scrolls" in g.log[-1][0]
    g.player.scrolls = 1
    g.ident.learn("scroll", "fire")
    g.use_scroll()
    assert g.player.scrolls == 1 and "No enemies" in g.log[-1][0], "a known fire scroll isn't wasted"


def test_unknown_fire_scrolls_can_be_wasted(arena):
    g = arena(ROOM)
    g.player.scrolls = 1
    g.use_scroll()
    assert g.player.scrolls == 0 and "harmlessly" in " ".join(m for m, _ in g.log)
    assert ("scroll", "fire") in g.ident.known, "but reading it teaches you what it was"


def test_scroll_can_kill(arena, spawn):
    g = arena(ROOM)
    g.player.scrolls = 1
    rat = spawn(g, "rat", 7, 2, hp=2)
    g._update_fov()
    g.use_scroll()
    assert rat not in g.monsters and g.player.kills == 1


def test_log_is_capped():
    g = Game(seed=1)
    for i in range(200):
        g.say(str(i))
    assert len(g.log) == 50 and g.log[-1][0] == "199"


@pytest.mark.parametrize("method", ["player_move", "wait", "use_potion", "use_scroll", "use_stairs",
                                    "descend", "ascend"])
def test_no_actions_after_winning(arena, method):
    g = arena(ROOM)
    g.state = State.WON
    args = (1, 0) if method == "player_move" else ()
    getattr(g, method)(*args)
    assert g.turns == 0 and (g.player.x, g.player.y) == (4, 2)
