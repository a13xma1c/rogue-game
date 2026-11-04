"""Monster behaviours.

Each behaviour is a function ``(game, monster) -> None`` that spends the
monster's action. ``Game._world_round`` decides *when* a monster acts (speed,
stuns, alertness, cooldown ticking); this module decides *what* it does.

Behaviours:

========== ==============================================================
melee      Chase and hit.
skittish   Like melee, but runs away when badly hurt (and cowers, biting
           only at close quarters, once cornered).
erratic    Flutters randomly much of the time.
pack       Holds back at a distance when alone; attacks when packmates are
           near, when you are badly hurt, or once it loses patience. Wakes
           its pack when it spots you.
ranged     Shoots from range; backs off when you get close.
caster     Heals wounded allies, throws hexes (poison / slow / blind),
           keeps its distance.
ambusher   Sits motionless until you come within a few tiles, then strikes
           (alertness rule lives in the game loop).
brute      Slow melee whose critical hits stun (stats do the work).
warlord    Boss: war cries summon goblins; enrages when wounded.
lich       Boss: fire bolts, blinks away when cornered, raises skeletons
           once wounded.
========== ==============================================================
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from . import settings as S
from .combat import distance
from .dungeon import DIRS8

if TYPE_CHECKING:
    from .entities import Monster
    from .game import Game

AMBUSH_RADIUS = 3  # ambushers only notice you this close
FLEE_HP = 0.35  # skittish monsters run below this fraction of their HP
KITE_DISTANCE = 2  # ranged monsters try to back off when you're this close
KITE_CHANCE = 0.5
PACK_RADIUS = 4  # packmates this close count as support
PACK_PATIENCE = 8  # rounds a lone pack hunter stalks before attacking anyway
SUMMON_CAP = 4  # max living summons (the lich's skeletons)
WARLORD_SUMMON_CAP = 3  # goblins the warlord can have at his side at once
WARCRY_COOLDOWN = 10
ENRAGE_POWER = 2  # the warlord's rage at half health
ENRAGE_SPEED = 115
LICH_RAISE_AT = 0.6  # fraction of health below which the lich raises the dead


# ------------------------------------------------------------------ helpers
def ready(m: Monster, ability: str) -> bool:
    return m.cooldowns.get(ability, 0) <= 0


def use(m: Monster, ability: str, cooldown: int) -> None:
    m.cooldowns[ability] = cooldown


def dist_to_player(game: Game, m: Monster) -> int:
    return distance((m.x, m.y), (game.player.x, game.player.y))


def sees_player(game: Game, m: Monster) -> bool:
    if m.has("blinded"):
        return dist_to_player(game, m) <= 1
    return game.visible(m.x, m.y)


def chase(game: Game, m: Monster) -> None:
    p = game.player
    step = game.map.next_step((m.x, m.y), (p.x, p.y), game.blocked_for(m))
    if step:
        game.try_move(m, *step)


def flee(game: Game, m: Monster) -> bool:
    """Step to the free neighbouring tile that gets furthest from the player.
    Returns False (no move) if nothing increases the distance - cornered."""
    p = game.player
    here = dist_to_player(game, m)
    best: list[tuple[int, int]] = []
    best_d = here
    for dx, dy in DIRS8:
        nx, ny = m.x + dx, m.y + dy
        if not game.map.walkable(nx, ny) or game.blocking_actor_at(nx, ny):
            continue
        d = distance((nx, ny), (p.x, p.y))
        if d > best_d:
            best, best_d = [(nx, ny)], d
        elif d == best_d and d > here:
            best.append((nx, ny))
    if not best:
        return False
    game.try_move(m, *game.rng.choice(best))
    return True


def melee_or_chase(game: Game, m: Monster) -> None:
    if dist_to_player(game, m) <= 1:
        game.melee(m, game.player)
    else:
        chase(game, m)


def can_shoot(game: Game, m: Monster) -> bool:
    return 0 < dist_to_player(game, m) <= m.shot_range and game.clear_shot(m, game.player)


# --------------------------------------------------------------- behaviours
def melee(game: Game, m: Monster) -> None:
    melee_or_chase(game, m)


def skittish(game: Game, m: Monster) -> None:
    if m.hp <= m.max_hp * FLEE_HP:
        if flee(game, m):
            return
        # Cornered: cower in place, and bite only if you come right up to it.
        if dist_to_player(game, m) <= 1:
            game.melee(m, game.player)
        return
    melee_or_chase(game, m)


def erratic(game: Game, m: Monster) -> None:
    if game.rng.random() < 0.4:
        dx, dy = game.rng.choice(DIRS8)
        game.try_move(m, m.x + dx, m.y + dy)
        return
    melee_or_chase(game, m)


def pack(game: Game, m: Monster) -> None:
    d = dist_to_player(game, m)
    if d <= 1:
        game.melee(m, game.player)
        return
    allies = [
        o for o in game.monsters
        if o is not m and o.alive and o.ai == "pack" and distance((o.x, o.y), (m.x, m.y)) <= PACK_RADIUS
    ]
    # Brave with friends, once hurt, when you look weak - or when it has run
    # out of patience stalking you alone.
    patience = m.cooldowns.setdefault("patience", PACK_PATIENCE)
    weak_prey = game.player.hp < game.player.max_hp * 0.5
    if allies or m.hp < m.max_hp or weak_prey or patience <= 0:
        chase(game, m)
    elif d <= 2:
        flee(game, m)  # alone: keep just out of reach and wait for the pack
    elif d > 4:
        chase(game, m)


def ranged(game: Game, m: Monster) -> None:
    d = dist_to_player(game, m)
    if d <= KITE_DISTANCE and game.rng.random() < KITE_CHANCE and flee(game, m):
        return
    if can_shoot(game, m):
        game.ranged_attack(m, game.player)
        return
    melee_or_chase(game, m)


HEXES = [
    # (name, status, turns, message)
    ("poison bolt", "poisoned", 5, "hurls a sizzling green bolt"),
    ("slowing hex", "slowed", 4, "weaves a sluggish hex"),
    ("blinding dust", "blinded", 3, "throws a fistful of blinding dust"),
]


def caster(game: Game, m: Monster) -> None:
    if ready(m, "heal"):
        wounded = [
            o for o in game.monsters
            if o is not m and o.alive and not o.is_boss and o.hp < o.max_hp * 0.6
            and distance((o.x, o.y), (m.x, m.y)) <= 6 and game.clear_shot(m, o)
        ]
        if wounded:
            target = min(wounded, key=lambda o: o.hp / o.max_hp)
            amount = 6 + game.depth
            target.hp = min(target.max_hp, target.hp + amount)
            use(m, "heal", 4)
            if game.visible(m.x, m.y):
                game.say(f"The {m.name} mends the {target.name}'s wounds.", S.CYAN)
            return
    d = dist_to_player(game, m)
    if d <= KITE_DISTANCE and game.rng.random() < KITE_CHANCE and flee(game, m):
        return
    if can_shoot(game, m):
        if ready(m, "hex"):
            name, status, turns, verb = game.rng.choice(HEXES)
            use(m, "hex", 3)
            game.say(f"The {m.name} {verb}!", S.PURPLE)
            game.ranged_attack(m, game.player, on_hit=(status, turns, 1.0), projectile="hex",
                               damage=name == "poison bolt")
        else:
            game.ranged_attack(m, game.player, projectile="bolt")
        return
    melee_or_chase(game, m)


def ambusher(game: Game, m: Monster) -> None:
    melee_or_chase(game, m)


def brute(game: Game, m: Monster) -> None:
    melee_or_chase(game, m)


def warlord(game: Game, m: Monster) -> None:
    if not m.enraged and m.hp <= m.max_hp // 2:
        m.enraged = True
        m.base_power += ENRAGE_POWER
        m.speed = ENRAGE_SPEED
        game.say(f"The {m.name} roars in fury! He grows faster and stronger.", S.RED)
    if ready(m, "warcry") and sees_player(game, m) and game.living_summons(m) < WARLORD_SUMMON_CAP:
        use(m, "warcry", WARCRY_COOLDOWN)
        game.say(f"The {m.name} bellows a war cry! Goblins rush to his side.", S.ORANGE)
        for _ in range(min(2, WARLORD_SUMMON_CAP - game.living_summons(m))):
            game.summon(m, "goblin")
        return
    melee_or_chase(game, m)


def lich(game: Game, m: Monster) -> None:
    d = dist_to_player(game, m)
    if m.hp <= m.max_hp * LICH_RAISE_AT and ready(m, "raise") and game.living_summons(m) < SUMMON_CAP:
        use(m, "raise", 7)
        game.say(f"The {m.name} raises the dead!", S.PURPLE)
        for _ in range(2):
            game.summon(m, "skeleton")
        return
    if d <= 1 and ready(m, "blink") and game.blink(m):
        use(m, "blink", 6)
        return
    if can_shoot(game, m) and ready(m, "firebolt"):
        use(m, "firebolt", 2)
        game.ranged_attack(m, game.player, on_hit=("burning", 3, 0.5), projectile="fire")
        return
    if d <= 1:
        game.melee(m, game.player)
    elif d <= KITE_DISTANCE:
        flee(game, m)
    elif not can_shoot(game, m):
        chase(game, m)
    # otherwise: stand its ground while the next bolt gathers


BEHAVIOURS: dict[str, Callable[[Game, Monster], None]] = {
    "melee": melee,
    "skittish": skittish,
    "erratic": erratic,
    "pack": pack,
    "ranged": ranged,
    "caster": caster,
    "ambusher": ambusher,
    "brute": brute,
    "warlord": warlord,
    "lich": lich,
}

# One-line summaries for the look command.
DESCRIPTIONS = {
    "melee": "Charges straight at you.",
    "skittish": "Flees when badly hurt.",
    "erratic": "Flits about unpredictably.",
    "pack": "Hunts in packs; stalks you when alone, then pounces.",
    "ranged": "Keeps its distance and shoots.",
    "caster": "Casts hexes from afar and heals its allies.",
    "ambusher": "Waits motionless, then pounces when you come close.",
    "brute": "Slow, but its heavy blows can stun.",
    "warlord": "Boss. Summons goblins with war cries; enrages when wounded.",
    "lich": "Boss. Hurls fire, blinks away when cornered, raises the dead.",
}


def act(game: Game, m: Monster) -> None:
    BEHAVIOURS[m.ai](game, m)
