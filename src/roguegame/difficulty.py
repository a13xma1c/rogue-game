"""Game modes and difficulty levels.

A game is configured by :class:`GameOptions`: a *mode* (the classic five-floor
quest for the Amulet, or an endless descent) and a *difficulty*. Every
difficulty knob lives in :class:`Difficulty` so the rules code just asks
"what does this difficulty say?" instead of hard-coding numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entities import Monster

CLASSIC = "classic"
ENDLESS = "endless"
MODES = (CLASSIC, ENDLESS)

MODE_DESCRIPTIONS = {
    CLASSIC: "Five floors. Defeat the warlord and the lich, and claim the Amulet of Yendor.",
    ENDLESS: "No Amulet, no bottom. Bosses return every five floors, stronger each time. "
             "How deep can you go?",
}


@dataclass(frozen=True)
class Difficulty:
    name: str
    description: str
    # ---- you
    player_hp: int  # starting max HP
    start_potions: int
    start_arrows: int
    regen_interval: int  # turns per natural HP point
    rest_fraction: float  # fraction of max HP restored on reaching a new floor
    # ---- them
    monster_hp: float  # multiplier
    monster_power: int  # added to melee and ranged power
    monster_accuracy: int  # percentage points
    monster_count: float  # multiplier on random spawns per floor
    trap_damage: float  # multiplier
    hunger: float  # multiplier on how fast you get hungry
    # ---- bookkeeping
    score_mult: float

    def adjust(self, m: Monster) -> Monster:
        """Apply this difficulty to a freshly created monster (in place)."""
        m.max_hp = m.hp = max(1, round(m.max_hp * self.monster_hp))
        m.base_power = max(1, m.base_power + self.monster_power)
        if m.ranged_power:
            m._ranged_power = max(1, m._ranged_power + self.monster_power)
        m.base_accuracy += self.monster_accuracy
        return m

    def spawn_count(self, base: int) -> int:
        return max(1, round(base * self.monster_count))


DIFFICULTIES: dict[str, Difficulty] = {
    "easy": Difficulty(
        "easy", "More health and supplies; monsters are fewer and weaker.",
        player_hp=40, start_potions=3, start_arrows=15, regen_interval=6, rest_fraction=0.5,
        monster_hp=0.8, monster_power=-1, monster_accuracy=-5, monster_count=0.75, trap_damage=0.5,
        hunger=0.75, score_mult=0.5,
    ),
    "normal": Difficulty(
        "normal", "The intended experience.",
        player_hp=30, start_potions=1, start_arrows=10, regen_interval=10, rest_fraction=0.25,
        monster_hp=1.0, monster_power=0, monster_accuracy=0, monster_count=1.0, trap_damage=1.0,
        hunger=1.0, score_mult=1.0,
    ),
    "hard": Difficulty(
        "hard", "Less health, no spare potion, no rest between floors; monsters are tougher and more numerous.",
        player_hp=25, start_potions=0, start_arrows=6, regen_interval=15, rest_fraction=0.0,
        monster_hp=1.25, monster_power=1, monster_accuracy=5, monster_count=1.3, trap_damage=1.5,
        hunger=1.25, score_mult=1.5,
    ),
}
DIFFICULTY_NAMES = tuple(DIFFICULTIES)  # easiest first


# Endless mode: below the classic bottom, monsters grow by a compounding
# factor per floor. Player levels grow roughly linearly with depth, so this
# guarantees every endless run eventually meets its match.
ENDLESS_RAMP_START = 5  # floors up to here are exactly as in classic mode
ENDLESS_HP_GROWTH = 1.09  # per floor below ENDLESS_RAMP_START
ENDLESS_POWER_GROWTH = 1.07


def endless_factor(depth: int, growth: float) -> float:
    return growth ** max(0, depth - ENDLESS_RAMP_START)


def endless_adjust(m: Monster, depth: int) -> Monster:
    """Apply endless-mode depth pressure to a freshly created monster (in place)."""
    hp = endless_factor(depth, ENDLESS_HP_GROWTH)
    power = endless_factor(depth, ENDLESS_POWER_GROWTH)
    m.max_hp = m.hp = max(1, round(m.max_hp * hp))
    m.base_power = max(1, round(m.base_power * power))
    if m.ranged_power:
        m._ranged_power = max(1, round(m._ranged_power * power))
    return m


@dataclass(frozen=True)
class GameOptions:
    mode: str = CLASSIC
    difficulty: str = "normal"
    player_class: str = "adventurer"

    def __post_init__(self) -> None:
        from .classes import CLASSES

        if self.mode not in MODES:
            raise ValueError(f"unknown mode {self.mode!r}; choose from {', '.join(MODES)}")
        if self.difficulty not in DIFFICULTIES:
            raise ValueError(f"unknown difficulty {self.difficulty!r}; choose from {', '.join(DIFFICULTIES)}")
        if self.player_class not in CLASSES:
            raise ValueError(f"unknown class {self.player_class!r}; choose from {', '.join(CLASSES)}")

    @property
    def endless(self) -> bool:
        return self.mode == ENDLESS

    @property
    def rules(self) -> Difficulty:
        return DIFFICULTIES[self.difficulty]

    def prepare(self, m: Monster, depth: int) -> Monster:
        """Everything a new monster needs for these options: difficulty and,
        in endless mode, depth pressure."""
        self.rules.adjust(m)
        if self.endless:
            endless_adjust(m, depth)
        return m

    @property
    def label(self) -> str:
        return f"{self.mode.capitalize()} - {self.difficulty.capitalize()}"
