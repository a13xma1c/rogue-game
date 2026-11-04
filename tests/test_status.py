"""Status effects: application, ticking, cures and their effect on the game."""

import pytest

from roguegame import settings as S
from roguegame.entities import Actor
from roguegame.game import BLIND_FOV_RADIUS, State
from roguegame.status import STATUS_SPECS

ROOM = """
    ####################
    #..................#
    #....@.............#
    #..................#
    ####################
"""


def dummy() -> Actor:
    return Actor(0, 0, "dummy", "d", (1, 1, 1), hp=20, power=1, defense=0)


# ------------------------------------------------------------ bookkeeping
def test_every_status_has_a_spec():
    assert set(STATUS_SPECS) == {"poisoned", "burning", "slowed", "stunned", "blinded",
                                 "hasted", "regenerating", "shielded"}
    for spec in STATUS_SPECS.values():
        assert spec.description and len(spec.color) == 3


def test_add_status_refreshes_rather_than_stacks():
    a = dummy()
    assert a.add_status("poisoned", 3)
    assert a.add_status("poisoned", 2, potency=2)
    assert a.statuses["poisoned"].turns == 3 and a.statuses["poisoned"].potency == 2
    a.add_status("poisoned", 5)
    assert a.statuses["poisoned"].turns == 5


def test_immunity():
    a = dummy()
    a.immune = frozenset({"poisoned"})
    assert not a.add_status("poisoned", 3) and not a.has("poisoned")


def test_dead_actors_get_no_statuses():
    a = dummy()
    a.hp = 0
    assert not a.add_status("burning", 3)


def test_cure():
    a = dummy()
    a.add_status("poisoned", 3)
    a.add_status("slowed", 3)
    assert a.cure("poisoned", "burning") == ["poisoned"]
    assert list(a.statuses) == ["slowed"]
    assert a.cure() == ["slowed"] and not a.statuses


# -------------------------------------------------------------- ticking
def test_poison_ticks_and_wears_off(arena):
    g = arena(ROOM)
    g.player.add_status("poisoned", 3)
    for _ in range(3):
        g.wait()
    assert g.player.hp == 27 and not g.player.has("poisoned")
    assert "poison wears off" in " ".join(m for m, _ in g.log)
    g.wait()
    assert g.player.hp == 27


def test_burning_potency(arena):
    g = arena(ROOM)
    g.player.add_status("burning", 2, potency=3)
    g.wait()
    assert g.player.hp == 27


def test_poison_can_kill(arena):
    g = arena(ROOM)
    g.player.hp = 1
    g.player.add_status("poisoned", 3)
    g.wait()
    assert g.state is State.DEAD and g.death_cause == "succumbed to poison"


def test_poison_blocks_natural_regeneration(arena):
    g = arena(ROOM)
    g.player.hp = 10
    g.player.add_status("poisoned", 30, potency=0)  # harmless, but still poisoned
    for _ in range(10):
        g.wait()
    assert g.player.hp == 10


def test_burning_monster_dies_and_player_gets_credit(arena, spawn):
    g = arena(ROOM)
    rat = spawn(g, "rat", 15, 1, hp=2)
    rat.add_status("burning", 3, potency=2)
    g.wait()
    assert rat not in g.monsters and g.player.kills == 1 and g.player.xp == rat.xp_value


def test_trolls_regenerate_unless_burning(arena, spawn):
    g = arena(ROOM)
    troll = spawn(g, "troll", 17, 3)
    troll.hp = 20
    troll.alert = False
    g.map.tiles[3][16] = 0  # keep it out of the fight
    g.map.visible[3][17] = False
    g.wait()
    assert troll.hp == 21
    troll.add_status("burning", 3, potency=1)
    g.wait()
    assert troll.hp == 20, "burns for 1 and doesn't regenerate"


# ----------------------------------------------------------- movement time
def test_slowed_player_gives_monsters_two_rounds(arena, spawn):
    g = arena(ROOM)
    orc = spawn(g, "orc", 12, 2, alert=True)
    g.player.add_status("slowed", 4)
    g.wait()
    assert orc.x == 10, "the orc moved twice while you took one action"


def test_slowed_monster_moves_at_half_speed(arena, spawn):
    g = arena(ROOM)
    orc = spawn(g, "orc", 14, 2, alert=True)
    orc.add_status("slowed", 10)
    for _ in range(4):
        g.wait()
    assert orc.x == 12


def test_stun_from_a_crit_costs_the_player_rounds(arena, spawn, sure_crits):
    g = arena(ROOM)
    g.player.max_hp = g.player.hp = 500
    ogre = spawn(g, "ogre", 6, 2, alert=True, energy=100)  # ogres stun on crits
    g.wait()
    # Round 1: the ogre crits and stuns you for 2 rounds. Rounds 2 and 3 are
    # lost to the stun; the ogre (speed 75) swings in each of them too.
    crushing = [m for m, _ in g.log if "crushing blow" in m]
    assert len(crushing) == 3
    assert sum("reel, stunned" in m for m, _ in g.log) == 2
    assert not g.player.has("stunned"), "control comes back once the stun is over"
    assert ogre.alive


def test_no_stun_lock(arena, spawn, sure_crits):
    """Stuns don't refresh, and you shrug off new ones for a moment after."""
    g = arena(ROOM)
    g.player.max_hp = g.player.hp = 5000
    spawn(g, "ogre", 6, 2, alert=True, energy=100)
    for _ in range(20):
        turns_lost_before = sum("reel, stunned" in m for m, _ in g.log)
        g.wait()
        lost = sum("reel, stunned" in m for m, _ in g.log) - turns_lost_before
        assert lost <= 2
    assert not g.player.has("stunned")


def test_stuns_do_not_refresh():
    a = dummy()
    assert a.add_status("stunned", 1)
    assert not a.add_status("stunned", 5)
    assert a.statuses["stunned"].turns == 1


def test_stunned_monster_skips_its_turn(arena, spawn):
    g = arena(ROOM)
    orc = spawn(g, "orc", 12, 2, alert=True)
    orc.add_status("stunned", 2)
    g.wait()
    g.wait()
    assert orc.x == 12
    g.wait()
    assert orc.x == 11


def test_blindness_shrinks_sight(arena, spawn):
    g = arena(ROOM)
    g.player.add_status("blinded", 5)
    g._update_fov()
    assert g.fov_radius == BLIND_FOV_RADIUS
    assert g.map.visible[2][5 + BLIND_FOV_RADIUS] and not g.map.visible[2][5 + BLIND_FOV_RADIUS + 2]
    g.player.cure()
    g._update_fov()
    assert g.fov_radius == S.FOV_RADIUS


# ---------------------------------------------------------------- cures
def test_potion_cures_poison_even_at_full_health(arena):
    g = arena(ROOM)
    g.player.add_status("poisoned", 5)
    g.player.add_status("slowed", 5)
    g.use_potion()
    assert g.player.potions == 0
    assert not g.player.has("poisoned") and g.player.has("slowed"), "potions don't cure everything"


def test_fountain_cures_everything(arena):
    g = arena("""
        #######
        #.@{..#
        #######
    """)
    g.player.add_status("blinded", 5)
    g.player.add_status("slowed", 5)
    g.player_move(1, 0)
    assert not g.player.statuses and "afflictions" in g.log[-1][0]


@pytest.mark.parametrize("status", ["poisoned", "stunned", "blinded"])
def test_healer_cures(arena, npc, status):
    g = arena(ROOM)
    g.player.gold = 100
    g.player.add_status(status, 5)
    g.talk(npc(g, "healer", 8, 2))
    assert g.dialogue.options[0].enabled, "worth visiting the healer even at full HP"
    g.choose(0)
    assert not g.player.statuses


def test_fire_scroll_sets_survivors_alight(arena, spawn):
    g = arena(ROOM)
    g.player.scrolls = 1
    ogre = spawn(g, "ogre", 10, 2, hp=100, max_hp=100)
    g._update_fov()
    g.use_scroll()
    assert ogre.has("burning")
