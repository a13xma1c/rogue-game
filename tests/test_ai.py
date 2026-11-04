"""Distinct monster behaviours and the speed/energy system."""

import pytest

from roguegame import ai
from roguegame.entities import MONSTER_KINDS

HALL = """
    ##########################
    #........................#
    #..@.....................#
    #........................#
    ##########################
"""

CORRIDOR = """
    ##############################
    #@...........................#
    ##############################
"""


def cheb(a, b):
    return max(abs(a.x - b.x), abs(a.y - b.y))


def test_every_kind_has_a_known_behaviour_and_description():
    for kind in MONSTER_KINDS.values():
        assert kind.ai in ai.BEHAVIOURS, kind.name
        assert kind.ai in ai.DESCRIPTIONS
        assert kind.description
    behaviours_in_use = {k.ai for k in MONSTER_KINDS.values()}
    assert behaviours_in_use == set(ai.BEHAVIOURS), "no dead behaviours"


# ------------------------------------------------------------------ speed
def test_fast_monsters_act_three_times_in_two_rounds(arena, spawn):
    g = arena(CORRIDOR)
    jackal = spawn(g, "jackal", 20, 1, alert=True)
    jackal.hp -= 1  # hurt jackals stop waiting for their pack
    g.map.visible[1][20] = True
    g.wait()
    g.wait()
    assert jackal.x == 17


def test_slow_monsters_act_three_times_in_four_rounds(arena, spawn):
    g = arena(CORRIDOR)
    ogre = spawn(g, "ogre", 20, 1, alert=True)
    for _ in range(4):
        g.wait()
    assert ogre.x == 17


def test_unaware_monsters_bank_no_energy(arena, spawn):
    g = arena(CORRIDOR)
    bat = spawn(g, "bat", 25, 1)
    g.map.tiles[1][23] = 0  # out of sight behind a wall
    for _ in range(5):
        g.wait()
    assert bat.energy == 0 and not bat.alert


def test_cooldowns_tick_every_round(arena, spawn):
    g = arena(HALL)
    shaman = spawn(g, "goblin shaman", 20, 3)
    shaman.cooldowns["hex"] = 3
    g.map.tiles[3][19] = 0
    g.wait()
    g.wait()
    assert shaman.cooldowns["hex"] == 1


# ------------------------------------------------------------- behaviours
def test_melee_monsters_close_in_and_attack(arena, spawn, sure_hits):
    g = arena(HALL)
    goblin = spawn(g, "goblin", 6, 2, alert=True)
    for _ in range(3):  # two steps to close the gap, then a swing
        g.wait()
    assert cheb(goblin, g.player) == 1
    assert any("goblin hits you" in m for m, _ in g.log)


def test_skittish_monsters_flee_when_hurt(arena, spawn):
    g = arena(HALL)
    rat = spawn(g, "rat", 6, 2, alert=True)
    rat.hp = 1
    g.wait()
    assert cheb(rat, g.player) == 4, "it ran away instead of closing in"


def test_cornered_skittish_monsters_fight(arena, spawn, sure_hits):
    g = arena("""
        #####
        #@.##
        #####
    """)
    rat = spawn(g, "rat", 2, 1, alert=True)
    rat.hp = 1
    g.wait()
    assert any("rat hits you" in m for m, _ in g.log)


def test_erratic_monsters_flutter(arena, spawn, monkeypatch):
    g = arena(HALL)
    bat = spawn(g, "bat", 12, 2, alert=True)
    moves = []
    for _ in range(10):
        before = cheb(bat, g.player)
        g.wait()
        moves.append(cheb(bat, g.player) - before)
    assert any(d >= 0 for d in moves), "sometimes it doesn't approach"
    assert any(d < 0 for d in moves), "but it does come for you"


def test_lone_pack_hunter_hangs_back(arena, spawn):
    g = arena(HALL)
    jackal = spawn(g, "jackal", 5, 2, alert=True)
    for _ in range(4):
        g.wait()
        assert cheb(jackal, g.player) >= 2, "it won't engage alone"


def test_lone_pack_hunter_loses_patience(arena, spawn, sure_hits):
    g = arena(HALL)
    g.player.max_hp = g.player.hp = 500
    jackal = spawn(g, "jackal", 5, 2, alert=True)
    for _ in range(ai.PACK_PATIENCE + 3):
        g.wait()
    assert cheb(jackal, g.player) == 1
    assert any("jackal hits you" in m for m, _ in g.log)


def test_lone_pack_hunter_pounces_on_weak_prey(arena, spawn):
    g = arena(HALL)
    g.player.hp = 10
    jackal = spawn(g, "jackal", 6, 2, alert=True)
    g.wait()
    assert cheb(jackal, g.player) < 3


def test_pack_hunters_attack_together(arena, spawn, sure_hits):
    g = arena(HALL)
    a = spawn(g, "jackal", 6, 2, alert=True)
    spawn(g, "jackal", 7, 3, alert=True)
    for _ in range(3):
        g.wait()
    assert cheb(a, g.player) == 1
    assert any("jackal hits you" in m for m, _ in g.log)


def test_pack_howl_wakes_the_pack(arena, spawn):
    g = arena("""
        ##########################
        #..@.........#...........#
        #............#...........#
        ##########################
    """)
    scout = spawn(g, "jackal", 8, 1)
    hidden = spawn(g, "jackal", 15, 1)
    g.wait()
    assert scout.alert and hidden.alert
    assert any("howls" in m for m, _ in g.log)


def test_archers_shoot_from_range(arena, spawn, sure_hits):
    g = arena(HALL)
    archer = spawn(g, "goblin archer", 8, 2, alert=True)
    g.fx.clear()
    g.wait()
    assert (archer.x, archer.y) == (8, 2), "no need to move: it has a shot"
    assert any("arrow hits you" in m for m, _ in g.log)
    assert any(fx.kind == "shot" for fx in g.fx)


def test_archers_back_off_when_you_close_in(arena, spawn, monkeypatch):
    monkeypatch.setattr(ai, "KITE_CHANCE", 1.0)
    g = arena(HALL)
    archer = spawn(g, "goblin archer", 5, 2, alert=True)
    g.wait()
    assert cheb(archer, g.player) == 3


def test_archers_need_a_clear_shot(arena, spawn):
    g = arena(CORRIDOR)
    spawn(g, "orc", 3, 1)  # standing between you and the archer
    archer = spawn(g, "goblin archer", 6, 1, alert=True)
    g.wait()
    assert not any("arrow" in m for m, _ in g.log), "it won't shoot through its friend"
    assert archer.x == 6 or archer.x == 5


def test_shaman_heals_wounded_allies(arena, spawn):
    g = arena(HALL)
    orc = spawn(g, "orc", 10, 1)
    orc.hp = 3
    shaman = spawn(g, "goblin shaman", 10, 3, alert=True)
    g.wait()
    assert orc.hp == 3 + 6 + g.depth and shaman.cooldowns["heal"] > 0
    assert any("mends" in m for m, _ in g.log)


def test_shaman_hexes_then_uses_plain_bolts(arena, spawn, sure_hits, monkeypatch):
    monkeypatch.setattr(ai, "KITE_CHANCE", 0.0)
    g = arena(HALL)
    g.player.max_hp = g.player.hp = 200
    spawn(g, "goblin shaman", 9, 2, alert=True)
    g.wait()
    assert g.player.statuses, "the hex landed"
    hexed = dict(g.player.statuses)
    g.player.cure()
    g.wait()
    assert not g.player.statuses, "hex on cooldown: just a bolt"
    assert any("bolt hits you" in m for m, _ in g.log)
    assert set(hexed) <= {"poisoned", "slowed", "blinded"}


def test_ambushers_wait_until_you_are_close(arena, spawn):
    g = arena(HALL)
    spider = spawn(g, "cave spider", 10, 2)
    g.wait()
    assert not spider.alert and (spider.x, spider.y) == (10, 2)
    g.player.x = 7
    g._update_fov()
    g.wait()
    assert spider.alert


def test_spider_bites_poison(arena, spawn, sure_hits, monkeypatch):
    g = arena(HALL)
    spawn(g, "cave spider", 4, 2, alert=True)
    monkeypatch.setattr(g.rng, "random", lambda: 0.0)  # every chance roll succeeds
    g.wait()
    assert g.player.has("poisoned")


def test_brutes_stun_on_critical_hits(arena, spawn, sure_crits):
    g = arena(HALL)
    g.player.max_hp = g.player.hp = 300
    spawn(g, "ogre", 4, 2, alert=True, energy=100)
    g.wait()
    assert any("stunned" in m for m, _ in g.log)


def test_monsters_give_up_when_far(arena, spawn):
    g = arena("#" * 40 + "\n#@" + "." * 37 + "#\n" + "#" * 40)
    orc = spawn(g, "orc", 30, 1, alert=True)
    g.wait()
    assert not orc.alert


@pytest.mark.parametrize("name", ["goblin", "orc", "skeleton", "troll", "mimic"])
def test_plain_melee_kinds(name):
    assert MONSTER_KINDS[name].ai == "melee"


def test_shooting_an_ambusher_wakes_it(arena, spawn, sure_hits):
    """Regression: damage didn't alert monsters, so an ambusher could be shot
    to death from outside its 3-tile ambush radius without reacting."""
    g = arena(HALL)
    spider = spawn(g, "cave spider", 8, 2, hp=100, max_hp=100)
    g._update_fov()
    g.wait()
    assert not spider.alert
    g.shoot(8, 2)
    assert spider.alert
    assert (spider.x, spider.y) != (8, 2), "and it comes for you"


def test_cornered_skittish_monsters_cower_instead_of_advancing(arena, spawn):
    """Regression: a cornered, wounded rat used to walk back towards you,
    then flee again next turn - oscillating forever at the edge of sight."""
    g = arena("""
        ############
        #@.........#
        ##########.#
        ##########.#
        ############
    """)
    rat = spawn(g, "rat", 10, 3, alert=True)
    rat.hp = 1
    for _ in range(5):
        g.wait()
        assert (rat.x, rat.y) == (10, 3), "stays in its dead end"


def test_shamans_do_not_heal_bosses(arena, spawn):
    g = arena(HALL)
    boss = spawn(g, "orc warlord", 10, 1)
    boss.hp = 5
    spawn(g, "goblin shaman", 10, 3, alert=True)
    g.wait()
    assert boss.hp == 5
