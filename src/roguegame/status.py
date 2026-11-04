"""Status effects (poison, burning, slow, stun, blindness).

Statuses are stored on an actor as ``{name: Status}``. Durations count
*rounds* of world time, and a round passes for everyone at once (see
``Game._world_round``). Damage-over-time effects are applied by the game
when the actor's statuses tick.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import settings as S


@dataclass
class Status:
    turns: int
    potency: int = 1  # damage per round for damage-over-time effects


@dataclass(frozen=True)
class StatusSpec:
    name: str
    color: tuple[int, int, int]
    description: str
    damage: bool = False  # deals ``potency`` damage every round
    accuracy: int = 0  # modifiers while active (percentage points)
    evasion: int = 0
    speed_factor: float = 1.0  # monsters: multiplies energy gain
    skips_turn: bool = False
    positive: bool = False  # a blessing rather than an affliction
    heals: bool = False  # restores ``potency`` HP every round


STATUS_SPECS: dict[str, StatusSpec] = {
    "poisoned": StatusSpec("poisoned", S.GREEN, "Loses health every round.", damage=True),
    "burning": StatusSpec("burning", S.ORANGE, "On fire: loses health every round and cannot regenerate.",
                          damage=True),
    "slowed": StatusSpec("slowed", S.BLUE, "Moves at half speed and dodges poorly.", evasion=-10,
                         speed_factor=0.5),
    "stunned": StatusSpec("stunned", S.YELLOW, "Reeling: cannot act or dodge.", skips_turn=True),
    "blinded": StatusSpec("blinded", S.GREY, "Can barely see: short sight and poor aim.", accuracy=-35),
    # ---- blessings
    "hasted": StatusSpec("hasted", (120, 240, 255), "Acts twice as fast.", positive=True, speed_factor=2.0),
    "regenerating": StatusSpec("regenerating", (120, 255, 150), "Regains health every round.", positive=True,
                               heals=True),
    "shielded": StatusSpec("shielded", (150, 170, 255), "A mana shield absorbs damage, draining mana instead.",
                           positive=True),
}

# Statuses a potion of healing cures; fountains and healers cure every NEGATIVE one.
CURED_BY_POTION = ("poisoned", "burning")
NEGATIVE = tuple(k for k, v in STATUS_SPECS.items() if not v.positive)
POSITIVE = tuple(k for k, v in STATUS_SPECS.items() if v.positive)
