"""Spells and class abilities, all powered by mana.

Every active skill and spellbook maps to a :class:`Spell`. A spell's *rank*
comes from the skill tree (spellbooks teach rank 1). Targeting kinds:

========= ===================================================================
bolt      a projectile at a visible spot; hits the first creature in its path
ball      like a bolt, but explodes, hitting everything next to the impact
tile      a visible, free floor tile (Blink)
adjacent  a monster next to you (Power Strike)
self      no target
bow       a bow shot (uses an arrow) with a twist
volley    arrows at every foe in range (no target)
========= ===================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import settings as S
from .combat import distance, first_blocker, line_of_fire

if TYPE_CHECKING:
    from .game import Game, ShotPlan


@dataclass(frozen=True)
class Spell:
    key: str
    name: str
    cost: int
    target: str
    range: int = 0
    color: tuple[int, int, int] = S.PURPLE


SPELLS: dict[str, Spell] = {s.key: s for s in [
    Spell("magic missile", "Magic Missile", 4, "bolt", 7, (180, 140, 255)),
    Spell("frost bolt", "Frost Bolt", 6, "bolt", 6, (140, 210, 255)),
    Spell("fireball", "Fireball", 10, "ball", 7, S.ORANGE),
    Spell("blink", "Blink", 4, "tile", 4, (200, 140, 255)),
    Spell("mend", "Mend", 6, "self"),
    Spell("mana shield", "Mana Shield", 5, "self"),
    Spell("power strike", "Power Strike", 4, "adjacent", 1, S.YELLOW),
    Spell("cleave", "Cleave", 6, "self"),
    Spell("second wind", "Second Wind", 8, "self"),
    Spell("aimed shot", "Aimed Shot", 3, "bow"),
    Spell("volley", "Volley", 7, "volley"),
    Spell("poison arrow", "Poison Arrow", 4, "bow"),
]}

TARGETED = ("bolt", "ball", "tile", "adjacent", "bow")


# ----------------------------------------------------------------- numbers
def missile_damage(rank: int, sp: int) -> tuple[int, int]:
    return 2 + 2 * rank + sp, 4 + 2 * rank + sp


def frost_damage(rank: int, sp: int) -> tuple[int, int]:
    return 3 + 2 * rank + sp, 5 + 2 * rank + sp


def spell_accuracy_bonus(sp: int) -> int:
    """Dodgeable spells (Frost Bolt) aim with your accuracy plus this."""
    return 10 + 2 * sp


def fireball_damage(rank: int, sp: int) -> tuple[int, int]:
    return 5 + 3 * rank + 2 * sp, 8 + 3 * rank + 2 * sp


def mend_amount(rank: int, sp: int) -> int:
    return 8 + 4 * rank + 3 * sp


def second_wind_fraction(rank: int) -> float:
    return 0.2 + 0.1 * rank


def strike_mult(rank: int) -> float:
    return 1.25 + 0.25 * rank


def aimed_mult(rank: int) -> float:
    return 1.25 + 0.25 * rank


def spell_range(key: str, rank: int) -> int:
    spell = SPELLS[key]
    return spell.range + (rank if key == "blink" else 0)


def describe(key: str, rank: int, sp: int) -> str:
    """What the spell does at ``rank`` with spell power ``sp`` - with numbers."""
    if key == "magic missile":
        lo, hi = missile_damage(rank, sp)
        return f"Unerring bolt: {lo}-{hi} damage."
    if key == "frost bolt":
        lo, hi = frost_damage(rank, sp)
        return f"Icy bolt: {lo}-{hi} damage and slows. Can be dodged."
    if key == "fireball":
        lo, hi = fireball_damage(rank, sp)
        return f"Explodes for {lo}-{hi} damage around the impact and sets foes alight."
    if key == "blink":
        return f"Teleport to a visible spot up to {spell_range(key, rank)} tiles away."
    if key == "mend":
        return f"Heal {mend_amount(rank, sp)} HP and cure poison."
    if key == "mana shield":
        return f"For {10 + 5 * rank} rounds, damage drains mana before health."
    if key == "power strike":
        return f"A sure-footed blow for {strike_mult(rank):.2g}x damage."
    if key == "cleave":
        return "Attack every adjacent foe" + (" with extra force." if rank > 1 else ".")
    if key == "second wind":
        return f"Recover {second_wind_fraction(rank):.0%} of your max HP and cure poison."
    if key == "aimed shot":
        return f"+25% to hit, +20% critical chance, {aimed_mult(rank):.2g}x damage."
    if key == "volley":
        return f"An arrow at up to {3 + rank} foes in range."
    if key == "poison arrow":
        return f"A shot that poisons for {1 + rank} damage per round."
    return ""


# ----------------------------------------------------------------- planning
def plan(game: Game, key: str, x: int, y: int) -> ShotPlan:
    """Work out a targeted spell at (x, y) without casting it."""
    from .game import ShotPlan

    p = game.player
    spell = SPELLS[key]
    rank = p.spells.get(key, 0)
    if rank <= 0:
        return ShotPlan(False, "You don't know that spell.")
    if p.mana < spell.cost:
        return ShotPlan(False, f"Not enough mana ({p.mana}/{spell.cost}).")
    if spell.target == "bow":
        return game.plan_shot(x, y, **bow_mods(key, rank))
    if (x, y) == (p.x, p.y):
        return ShotPlan(False, "Pick a target other than yourself.")
    if not game.map.in_bounds(x, y) or not game.map.visible[y][x]:
        return ShotPlan(False, "You can't see that spot.")
    dist = distance((p.x, p.y), (x, y))
    reach = spell_range(key, rank)
    if dist > reach:
        return ShotPlan(False, f"Out of range ({dist} > {reach}).", dist=dist)
    if spell.target == "adjacent":
        target = game.monster_at(x, y)
        if target is None:
            return ShotPlan(False, "No foe there.", dist=dist)
        from . import combat

        return ShotPlan(True, path=[(x, y)], target=target, dist=1,
                        hit=combat.hit_chance(p, target, bonus=30), crit=combat.crit_chance(p),
                        damage=_scaled(combat.damage_range(p, target), strike_mult(rank)))
    if spell.target == "tile":
        if not game.map.walkable(x, y) or game.blocking_actor_at(x, y):
            return ShotPlan(False, "You can't blink into that spot.", dist=dist)
        return ShotPlan(True, path=[(x, y)], dist=dist)
    # bolt / ball: a projectile path
    path = line_of_fire(game.map, (p.x, p.y), (x, y))
    idx, reason = first_blocker(game.map, path, game._occupied(p))
    if reason == "wall":
        if spell.target == "bolt" or idx == 0:
            return ShotPlan(False, "You don't have a clear line.", path=path[: idx + 1], dist=dist)
        path = path[:idx]  # a fireball bursts against the wall
    elif reason == "actor":
        path = path[: idx + 1]
        npc = game.npc_at(*path[-1])
        if npc:
            return ShotPlan(False, f"{npc.name} is in the way!", path=path, dist=dist)
    target = game.monster_at(*path[-1]) if path else None
    sp = p.spell_power
    dmg = {"magic missile": missile_damage, "frost bolt": frost_damage,
           "fireball": fireball_damage}[key](rank, sp)
    hit = 1.0
    if key == "frost bolt" and target is not None:
        from . import combat

        hit = combat.hit_chance(p, target, bonus=spell_accuracy_bonus(sp))
    result = ShotPlan(True, path=path, target=target, dist=dist, hit=hit, damage=dmg)
    if spell.target == "ball" and path:
        cx, cy = path[-1]
        result.area = [(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                       if game.map.in_bounds(cx + dx, cy + dy) and not game.map.blocks_sight(cx + dx, cy + dy)]
    return result


def _scaled(rng: tuple[int, int], mult: float) -> tuple[int, int]:
    return round(rng[0] * mult), round(rng[1] * mult)


def bow_mods(key: str, rank: int) -> dict:
    if key == "aimed shot":
        return {"acc_bonus": 25, "crit_bonus": 20, "dmg_mult": aimed_mult(rank)}
    if key == "poison arrow":
        return {"on_hit": ("poisoned", 5, 1 + rank)}
    return {}


# ----------------------------------------------------------------- effects
def cast(game: Game, key: str, rank: int, target: tuple[int, int] | None, plan_: ShotPlan | None) -> bool:
    """Carry out a spell whose mana has been paid. Returns False if it fizzled
    without effect (the caller refunds the mana)."""
    p = game.player
    sp = p.spell_power
    spell = SPELLS[key]
    if key in ("magic missile", "frost bolt"):
        assert plan_ is not None
        game.fx_shot(plan_.path, spell.color)
        if plan_.target is None:
            game.say(f"Your {spell.name.lower()} fizzles against nothing.", S.GREY)
            return True
        if game.rng.random() >= plan_.hit:
            game.say(f"The {plan_.target.name} dodges your {spell.name.lower()}.", S.GREY)
            game.alert_monster(plan_.target)
            return True
        lo, hi = plan_.damage
        dmg = game.rng.randint(lo, hi)
        game.say(f"Your {spell.name.lower()} hits the {plan_.target.name} for {dmg}.", spell.color)
        game.hurt_monster(plan_.target, dmg)
        if key == "frost bolt" and plan_.target.alive:
            game.inflict(plan_.target, "slowed", 4)
        return True
    if key == "fireball":
        assert plan_ is not None
        game.fx_shot(plan_.path, spell.color)
        game.say("The fireball explodes!", S.ORANGE)
        lo, hi = plan_.damage
        for pos in plan_.area:
            game.fx_shot([pos], S.ORANGE)
            m = game.monster_at(*pos)
            if m:
                dmg = game.rng.randint(lo, hi)
                game.say(f"The {m.name} is engulfed for {dmg}.", S.ORANGE)
                game.hurt_monster(m, dmg)
                if m.alive:
                    game.inflict(m, "burning", 3, 2)
        return True
    if key == "blink":
        assert target is not None
        old = (p.x, p.y)
        p.x, p.y = target
        game.fx_shot([old, target], spell.color)
        game.say("You blink across the room.", spell.color)
        game.on_player_moved()
        return True
    if key == "mend":
        healed = min(p.max_hp - p.hp, mend_amount(rank, sp))
        p.hp += healed
        cured = p.cure("poisoned")
        game.say(f"Soothing light mends {healed} HP.{' The poison fades.' if cured else ''}", S.GREEN)
        return True
    if key == "second wind":
        healed = min(p.max_hp - p.hp, round(p.max_hp * second_wind_fraction(rank)))
        p.hp += healed
        p.cure("poisoned", "burning")
        game.say(f"You catch your second wind and recover {healed} HP.", S.GREEN)
        return True
    if key == "mana shield":
        p.add_status("shielded", 10 + 5 * rank)
        game.say("A shimmering shield of mana surrounds you.", (150, 170, 255))
        return True
    if key == "power strike":
        assert plan_ is not None and plan_.target is not None
        game.say("You wind up a mighty blow...", S.YELLOW)
        game.melee(p, plan_.target, acc_bonus=30, dmg_mult=strike_mult(rank))
        return True
    if key == "cleave":
        foes = [m for m in game.monsters if m.alive and distance((m.x, m.y), (p.x, p.y)) == 1]
        if not foes:
            game.say("There is nothing next to you to cleave.", S.GREY)
            return False
        game.say("You swing in a wide arc!", S.YELLOW)
        for m in foes:
            if m.alive:
                game.melee(p, m, dmg_mult=1.0 + 0.25 * (rank - 1))
        return True
    if key in ("aimed shot", "poison arrow"):
        assert target is not None
        return game.fire_arrow(*target, **bow_mods(key, rank))
    if key == "volley":
        targets = volley_targets(game, 3 + rank)
        if not targets:
            game.say("No foes in range for a volley.", S.GREY)
            return False
        game.say("You loose a volley of arrows!", S.YELLOW)
        for m in targets:
            if p.arrows <= 0:
                break
            if m.alive:
                game.fire_arrow(m.x, m.y)
        return True
    raise KeyError(key)  # pragma: no cover


def volley_targets(game: Game, limit: int) -> list:
    p = game.player
    if not p.launcher or p.arrows <= 0:
        return []
    out = []
    for m in sorted(game.monsters, key=lambda m: distance((m.x, m.y), (p.x, p.y))):
        plan_ = game.plan_shot(m.x, m.y)
        if plan_.ok and plan_.target is m:
            out.append(m)
    return out[:limit]


def adjacent_foes(game: Game) -> list:
    p = game.player
    return [m for m in game.monsters if m.alive and max(abs(m.x - p.x), abs(m.y - p.y)) == 1]

