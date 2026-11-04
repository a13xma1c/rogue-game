"""Randomised whole-game simulations.

* A fuzzer mashes random actions and checks game invariants after every one.
* A goal-seeking bot proves every floor can be crossed and the game won.
"""

import random
from collections import deque

import pytest

from roguegame import settings as S
from roguegame.dungeon import DIRS8
from roguegame.difficulty import CLASSIC, ENDLESS, GameOptions
from roguegame.entities import HUNGER_MAX, PACK_SIZE
from roguegame.game import Game, State
from roguegame.spells import SPELLS, TARGETED

from conftest import all_openable, reachable
from roguegame.tiles import STAIRS_DOWN, STAIRS_UP, TRAP


def check_invariants(g: Game) -> None:
    p, m = g.player, g.map
    assert m.walkable(p.x, p.y), "player inside a wall"
    spots = [(p.x, p.y)] + [(a.x, a.y) for a in g.monsters] + [(n.x, n.y) for n in g.npcs]
    assert len(spots) == len(set(spots)), "two actors share a tile"
    for mon in g.monsters:
        assert mon.alive and m.walkable(mon.x, mon.y)
    for npc in g.npcs:
        assert m.is_open_spot(npc.x, npc.y), "NPC drifted into a chokepoint"
    for it in g.items:
        assert m.walkable(it.x, it.y)
    assert p.hp <= p.max_hp and p.gold >= 0 and p.potions >= 0 and p.scrolls >= 0
    assert all(m.tiles[y][x] == TRAP for x, y in m.traps)  # full two-way check at the end
    assert m.visible[p.y][p.x]
    assert g.depth >= 1 and (g.endless or g.depth <= S.MAX_DEPTH)
    assert (g.state is State.DEAD) == (p.hp <= 0)
    assert p.arrows >= 0
    for actor in [p, *g.monsters]:
        assert all(st.turns > 0 for st in actor.statuses.values()), "expired statuses are removed"
    # Items: nothing is in two places at once, and the pack respects its size.
    assert len(p.pack) <= PACK_SIZE
    everywhere = [id(it) for it in p.pack] + [id(it) for it in p.gear()] + [id(it) for it in g.items]
    assert len(everywhere) == len(set(everywhere)), "an item is in two places at once"
    assert all(it.count >= 1 for it in p.pack)
    assert 0 <= p.mana <= p.max_mana and 0 <= p.satiation <= HUNGER_MAX
    assert p.max_hp >= 1 and p.skill_points >= 0
    if g.pending:
        assert g.state is State.PLAYING and g.unidentified_items()
    if g.state is State.PLAYING:  # (a death ends the round early, leaving energy unspent)
        for mon in g.monsters:
            assert mon.energy < 100, "nobody banks a whole extra action between turns"
        assert not p.has("stunned"), "you never get control back while stunned"
    boss = g.level.boss
    assert g.level.sealed == (boss is not None and boss in g.monsters)


def fully_connected(m, start) -> bool:
    """Every tile a determined player could open their way to is reachable."""
    return reachable(m, start) == all_openable(m)


_fields: dict = {}


def downhill_step(g: Game, goal):
    """Neighbouring tile that gets closer to ``goal``, using a distance field
    computed once per floor (much cheaper than a BFS every turn). NPCs are
    routed around - they never block a passage, but may sit on the shortest
    path - so the field is rebuilt when they move."""
    npcs = frozenset((n.x, n.y) for n in g.npcs)
    key = (id(g.level), goal, npcs)
    if key not in _fields:
        _fields.clear()
        _fields[key] = field_around(g.map, goal, npcs)
    field = _fields[key]
    p = g.player
    here = field.get((p.x, p.y))
    if here is None:
        return None
    options = [
        (field[n], n)
        for n in ((p.x + dx, p.y + dy) for dx, dy in DIRS8)
        if n in field and field[n] < here and n not in npcs
    ]
    return min(options)[1] if options else None


def field_around(m, goal, blocked):
    dist = {goal: 0}
    queue = deque([goal])
    while queue:
        x, y = queue.popleft()
        for dx, dy in DIRS8:
            n = (x + dx, y + dy)
            if n not in dist and n not in blocked and m.pathable(*n):
                dist[n] = dist[(x, y)] + 1
                queue.append(n)
    return dist


def random_item_action(g: Game, rng: random.Random) -> None:
    """Do something random with the pack, the skill tree or spells."""
    p = g.player
    roll = rng.random()
    if roll < 0.5 and p.pack:
        item = rng.choice(p.pack)
        if rng.random() < 0.15:
            g.drop(item)
        else:
            g.use_item(item)
    elif roll < 0.6 and p.gear():
        g.drop(rng.choice(p.gear()))
    elif roll < 0.75:
        skills = [k for _, branch in p.cls.branches for k in branch]
        g.learn_skill(rng.choice(skills))
    elif p.spells:
        key = rng.choice(sorted(p.spells))
        if SPELLS[key].target in TARGETED:
            g.cast(key, p.x + rng.randint(-6, 6), p.y + rng.randint(-6, 6))
        else:
            g.cast(key)


def random_action(g: Game, rng: random.Random) -> None:
    if g.dialogue:
        g.choose(rng.randrange(len(g.dialogue.options)))
        return
    if g.pending:
        if rng.random() < 0.8:
            g.choose_item(rng.choice(g.unidentified_items()))
        else:
            g.cancel_pending()
        return
    if rng.random() < 0.12:
        random_item_action(g, rng)
        return
    here = g.map.tile(g.player.x, g.player.y)
    roll = rng.random()
    if here in (STAIRS_DOWN, STAIRS_UP) and roll < 0.4:
        g.use_stairs()
    elif roll < 0.03:
        g.use_potion()
    elif roll < 0.05:
        g.use_scroll()
    elif roll < 0.12:
        foes = [m for m in g.monsters if g.visible(m.x, m.y)]
        if foes:
            target = rng.choice(foes)
            g.shoot(target.x, target.y)
    elif roll < 0.1:
        g.wait()
    elif roll < 0.5 and g.level.down_stairs:
        step = downhill_step(g, g.level.down_stairs)
        if step:
            g.player_move(step[0] - g.player.x, step[1] - g.player.y)
    else:
        g.player_move(*rng.choice(DIRS8))


def seeds(n: int, fast: int):
    """The first ``fast`` seeds always run; the rest are marked slow."""
    return [pytest.param(s, marks=pytest.mark.slow) if s >= fast else s for s in range(n)]


OTHER_MODES = [GameOptions(ENDLESS, "hard", "warrior"), GameOptions(CLASSIC, "easy", "mage"),
               GameOptions(ENDLESS, "easy", "ranger"), GameOptions(CLASSIC, "normal", "mage")]


@pytest.mark.parametrize("options", OTHER_MODES, ids=lambda o: o.label.replace(" - ", "-"))
@pytest.mark.parametrize("seed", seeds(6, fast=1))
def test_random_play_keeps_invariants_in_every_mode(seed, options):
    test_random_play_keeps_invariants(seed, options)


@pytest.mark.parametrize("seed", seeds(30, fast=5))
def test_random_play_keeps_invariants(seed, options=None):
    from roguegame.saves import load_game, save_game

    g = Game(seed=seed, options=options)
    rng = random.Random(seed)
    g.player.max_hp = g.player.hp = 300 if seed % 2 else 30  # half the runs survive longer
    for _ in range(800):
        if g.state is not State.PLAYING:
            break
        random_action(g, rng)
        check_invariants(g)
        if rng.random() < 0.01 and g.state is State.PLAYING:
            # Save and reload mid-run, then carry on with the reloaded game.
            save_game(g, 1)
            g = load_game(1)
            check_invariants(g)
    for depth, lvl in g.levels.items():
        assert fully_connected(lvl.map, lvl.start), f"floor {depth} got cut in two"
        assert set(lvl.map.traps) == set(lvl.map.find_tiles(TRAP))


def bot_turn(g: Game) -> None:
    """Head for the stairs down (or the Amulet), fighting through anything."""
    p = g.player
    boss = g.level.boss
    if boss is not None and boss in g.monsters and (g.level.sealed or boss.carries_amulet):
        goal = (boss.x, boss.y)  # bosses must die before you can move on
    else:
        goal = g.level.down_stairs or g._amulet_pos()
    if (p.x, p.y) == goal:
        g.use_stairs()
        return
    step = downhill_step(g, goal)
    if step is None:
        g.wait()  # e.g. an NPC is briefly in the way; let it wander off
        return
    g.player_move(step[0] - p.x, step[1] - p.y)  # attacks / opens doors as needed
    if g.dialogue:
        g.close_dialogue()


@pytest.mark.parametrize("seed", seeds(12, fast=3))
def test_every_game_can_be_won(seed):
    g = Game(seed=seed)
    # We're testing that every floor can be crossed and every boss beaten -
    # geography and game logic, not balance - so the bot is a demigod.
    g.player.max_hp = g.player.hp = 10_000
    g.player.base_power = 40
    for _ in range(4000):
        if g.state is not State.PLAYING:
            break
        bot_turn(g)
    assert g.state is State.WON, f"stuck on floor {g.depth} after {g.turns} turns"
    assert set(g.levels) == set(range(1, S.MAX_DEPTH + 1))


@pytest.mark.parametrize("difficulty", ["easy", pytest.param("hard", marks=pytest.mark.slow)])
@pytest.mark.parametrize("seed", seeds(4, fast=1))
def test_endless_descent(seed, difficulty):
    """Endless floors keep coming - bosses and all - well past the classic bottom."""
    g = Game(seed=seed, options=GameOptions(ENDLESS, difficulty))
    g.player.max_hp = g.player.hp = 100_000
    g.player.base_power = 80
    for _ in range(15000):
        if g.depth >= 15 or g.state is not State.PLAYING:
            break
        bot_turn(g)
    assert g.depth >= 15 and g.state is State.PLAYING
    assert not any(it.kind == "amulet" for lvl in g.levels.values() for it in lvl.items)
