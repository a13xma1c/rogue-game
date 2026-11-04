"""Attack resolution: accuracy vs. evasion, critical hits, and lines of fire.

An attack goes through three rolls:

1. **To hit.** ``hit chance = accuracy - evasion`` (percentage points, minus a
   range penalty for shots), clamped to 5..95%. If the roll fails but would
   have succeeded against an evasion of 0, the defender *dodged*; otherwise
   the attacker simply *missed*.
2. **Critical.** A hit is a critical with the attacker's crit chance and
   deals ``crit_mult`` times damage (and may stun, for some attackers).
3. **Damage.** ``max(1, power - defense + U{-1..2})``.

The helper functions here are pure so the look command and the tests can
reason about odds without rolling dice.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .dungeon import Pos

if TYPE_CHECKING:
    from .dungeon import DungeonMap
    from .entities import Actor

MIN_HIT, MAX_HIT = 5, 95
RANGE_PENALTY = 3  # accuracy lost per tile of distance beyond the first
CRIT_STUN_TURNS = 2


@dataclass(frozen=True)
class AttackResult:
    outcome: str  # "hit" | "crit" | "dodge" | "miss"
    damage: int = 0

    @property
    def hit(self) -> bool:
        return self.outcome in ("hit", "crit")

    @property
    def crit(self) -> bool:
        return self.outcome == "crit"


def distance(a: Pos, b: Pos) -> int:
    """Chebyshev distance (diagonal steps cost 1, like movement)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def attack_accuracy(attacker: Actor, ranged: bool) -> int:
    if ranged and hasattr(attacker, "ranged_accuracy"):
        return attacker.ranged_accuracy  # type: ignore[attr-defined]
    return attacker.accuracy


def hit_chance(attacker: Actor, defender: Actor, ranged: bool = False, dist: int = 1, bonus: int = 0) -> float:
    acc = attack_accuracy(attacker, ranged) + bonus
    if ranged:
        acc -= RANGE_PENALTY * max(0, dist - 1)
    return max(MIN_HIT, min(MAX_HIT, acc - defender.evasion)) / 100


def crit_chance(attacker: Actor, ranged: bool = False, bonus: int = 0) -> float:
    base = getattr(attacker, "ranged_crit", attacker.crit_chance) if ranged else attacker.crit_chance
    return max(0, min(100, base + bonus)) / 100


def attack_power(attacker: Actor, ranged: bool) -> int:
    return attacker.ranged_power if ranged else attacker.power


def damage_range(attacker: Actor, defender: Actor, ranged: bool = False) -> tuple[int, int]:
    power = attack_power(attacker, ranged)
    return max(1, power - defender.defense - 1), max(1, power - defender.defense + 2)


def expected_damage(power: int, defense: int) -> float:
    """Mean damage of a normal hit: max(1, power - defense + U{-1..2})."""
    return sum(max(1, power - defense + r) for r in (-1, 0, 1, 2)) / 4


def expected_attack(attacker: Actor, defender: Actor, ranged: bool = False, dist: int = 1) -> float:
    """Average damage per attack, counting misses and criticals."""
    base = expected_damage(attack_power(attacker, ranged), defender.defense)
    crit = crit_chance(attacker, ranged)
    return hit_chance(attacker, defender, ranged, dist) * base * (1 + crit * (attacker.crit_mult - 1))


def resolve_attack(
    attacker: Actor,
    defender: Actor,
    rng: random.Random,
    ranged: bool = False,
    dist: int = 1,
    acc_bonus: int = 0,
    crit_bonus: int = 0,
    dmg_mult: float = 1.0,
) -> AttackResult:
    roll = rng.random()
    chance = hit_chance(attacker, defender, ranged, dist, bonus=acc_bonus)
    if roll >= chance:
        # Would this roll have hit a defender who didn't dodge at all?
        undodged = max(MIN_HIT, min(MAX_HIT, attack_accuracy(attacker, ranged) + acc_bonus
                                    - (RANGE_PENALTY * max(0, dist - 1) if ranged else 0))) / 100
        return AttackResult("dodge" if roll < undodged and defender.evasion > 0 else "miss")
    dmg = max(1, round(attacker.attack_damage(defender, rng, power=attack_power(attacker, ranged)) * dmg_mult))
    if rng.random() < crit_chance(attacker, ranged, bonus=crit_bonus):
        return AttackResult("crit", dmg * attacker.crit_mult)
    return AttackResult("hit", dmg)


# ------------------------------------------------------------ line of fire
def bresenham(a: Pos, b: Pos) -> list[Pos]:
    """Tiles on the line from a to b, excluding a, including b."""
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    out: list[Pos] = []
    x, y = x0, y0
    while (x, y) != (x1, y1):
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
        out.append((x, y))
    return out


def line_of_fire(m: DungeonMap, a: Pos, b: Pos) -> list[Pos]:
    """A projectile path from a to b that isn't blocked by terrain, if one
    exists; otherwise the (blocked) straight line.

    Bresenham lines aren't symmetric, so both the a->b line and the reversed
    b->a line are tried - this keeps "I can see it" and "I can shoot it" in
    close agreement around corners.
    """
    forward = bresenham(a, b)
    if not _terrain_blocks(m, forward):
        return forward
    backward = bresenham(b, a)[::-1][1:] + [b] if a != b else []
    if backward and not _terrain_blocks(m, backward):
        return backward
    return forward


def _terrain_blocks(m: DungeonMap, path: list[Pos]) -> bool:
    return any(m.blocks_sight(x, y) for x, y in path[:-1])


def first_blocker(m: DungeonMap, path: list[Pos], occupied: set[Pos]) -> tuple[int, str]:
    """Walk ``path``; return (index, reason) of the first tile that stops a
    projectile: "wall" for terrain, "actor" for an occupied tile, or
    (len(path), "clear")."""
    for i, (x, y) in enumerate(path):
        if m.blocks_sight(x, y):
            return i, "wall"
        if (x, y) in occupied:
            return i, "actor"
    return len(path), "clear"
