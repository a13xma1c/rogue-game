"""Friendly NPCs: talking, services and movement."""

import pytest

from roguegame.entities import RUMOURS
from roguegame.game import Game, State, arrow_price, healing_price, potion_price, scroll_price
from roguegame.level import build_level, level_rng

ROOM = """
    #############
    #...........#
    #...........#
    #....@......#
    #...........#
    #...........#
    #############
"""


def options(g):
    return [o.action for o in g.dialogue.options]


def test_bumping_an_npc_starts_a_conversation(arena, npc):
    g = arena(ROOM)
    n = npc(g, "merchant", 6, 3)
    g.player_move(1, 0)
    assert g.dialogue is not None and g.dialogue.npc is n
    assert g.turns == 0, "talking is free"
    assert n.hp == n.max_hp and (g.player.x, g.player.y) == (5, 3)
    assert n.greeting in g.dialogue.text


def test_actions_are_paused_during_dialogue(arena, npc):
    g = arena(ROOM)
    g.talk(npc(g, "sage", 7, 3))
    g.player_move(-1, 0)
    g.wait()
    assert g.turns == 0 and g.player.x == 5
    g.choose(len(g.dialogue.options) - 1)  # Goodbye
    assert g.dialogue is None
    g.player_move(-1, 0)
    assert g.player.x == 4


def test_invalid_choices_are_ignored(arena, npc):
    g = arena(ROOM)
    g.choose(0)  # no dialogue open
    g.talk(npc(g, "merchant", 7, 3))
    g.choose(99)
    g.choose(-1)
    assert g.dialogue is not None


def test_merchant(arena, npc):
    g = arena(ROOM)
    g.talk(npc(g, "merchant", 7, 3))
    assert options(g) == ["buy_potion", "buy_scroll", "buy_arrows", "buy_ration", "buy_identify",
                          "identify_all", "bye"]
    assert not any(o.enabled for o in g.dialogue.options[:-1]), "no gold, no sale"
    g.choose(0)
    assert g.player.potions == 1 and "can't" in g.dialogue.text

    g.player.gold = 100
    g.close_dialogue()
    g.talk(g.npcs[0])
    g.choose(0)
    g.choose(1)
    arrows = g.player.arrows
    g.choose(2)
    assert g.player.potions == 2 and g.player.scrolls == 1 and g.player.arrows == arrows + 8
    assert g.player.gold == 100 - potion_price(1) - scroll_price(1) - arrow_price(1)


def test_healer(arena, npc):
    g = arena(ROOM)
    g.player.gold = 50
    g.talk(npc(g, "healer", 7, 3))
    assert not g.dialogue.options[0].enabled, "nothing to heal"
    g.close_dialogue()
    g.player.hp = 3
    g.talk(g.npcs[0])
    g.choose(0)
    assert g.player.hp == g.player.max_hp and g.player.gold == 50 - healing_price(1)


def find_level_with(role):
    """Search generated floors for one that has an NPC with ``role``."""
    for depth in range(2, 6):
        for seed in range(40):
            lvl = build_level(depth, level_rng(seed, depth))
            found = next((n for n in lvl.npcs if n.role == role), None)
            if found:
                return lvl, found
    raise AssertionError(f"no {role} generated")


def test_sage_reveals_the_floor_once():
    g = Game(seed=11)
    lvl, sage = find_level_with("sage")
    g.levels[lvl.depth], g.depth = lvl, lvl.depth
    explored_before = sum(map(sum, g.map.explored))
    g.talk(sage)
    assert options(g)[0] == "guidance"
    g.choose(0)
    goal = g.level.down_stairs or g._amulet_pos()
    assert g.map.explored[goal[1]][goal[0]]
    assert sum(map(sum, g.map.explored)) > explored_before + 300
    assert sage.used and "guidance" not in options(g)
    assert "lies to the" in g.dialogue.text


def test_rumours_and_gift(arena, npc):
    g = arena(ROOM)
    g.talk(npc(g, "wanderer", 7, 3))
    assert options(g) == ["rumour", "gift", "bye"]
    g.choose(0)
    assert g.dialogue.text.strip('"') in RUMOURS
    stock = g.player.potions + g.player.scrolls
    g.choose(1)
    assert g.player.potions + g.player.scrolls == stock + 1
    assert "gift" not in options(g), "only one gift"


def test_dead_players_cannot_talk(arena, npc):
    g = arena(ROOM)
    g.state = State.DEAD
    g.talk(npc(g, "sage", 7, 3))
    assert g.dialogue is None


def test_monsters_never_attack_npcs(arena, spawn, npc):
    g = arena(ROOM)
    friend = npc(g, "merchant", 9, 3)
    spawn(g, "ogre", 10, 3, alert=True)
    for _ in range(10):
        g.wait()
    assert friend.hp == friend.max_hp


def test_monsters_walk_around_npcs(arena, spawn, npc):
    g = arena(ROOM)
    npc(g, "merchant", 7, 3)
    orc = spawn(g, "orc", 8, 3, alert=True)
    g.wait()
    assert (orc.x, orc.y) != (7, 3)
    assert max(abs(orc.x - 5), abs(orc.y - 3)) == 2


@pytest.mark.parametrize("role, moves", [("sage", True), ("wanderer", True), ("merchant", False),
                                         ("healer", False)])
def test_npc_wandering(arena, npc, role, moves):
    g = arena("""
        ###############
        #.............#
        #.............#
        #.............#
        #.............#
        #......@......#
        #.............#
        ###############
    """)
    n = npc(g, role, 4, 3)
    start = (n.x, n.y)
    visited = set()
    for _ in range(150):
        g.wait()
        visited.add((n.x, n.y))
        assert g.map.is_open_spot(n.x, n.y), "wanderers stay off walls and doorways"
        assert (n.x, n.y) != (g.player.x, g.player.y)
    assert (len(visited) > 1) is moves
    if not moves:
        assert visited == {start}
