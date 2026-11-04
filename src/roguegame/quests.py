"""Quests offered by guild envoys.

Three kinds:

* **slay**  - hunt down a named champion somewhere on the floor;
* **fetch** - find someone's lost relic (often tucked away somewhere tricky);
* **cull**  - thin out one kind of monster on the floor.

A quest is offered when you talk to the envoy, tracked in your journal once
accepted, and rewarded (gold, experience and a fine item) when you come back
to report success. Quests are generated with their floor, so they're part of
the seed like everything else.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entities import NPC, Monster
    from .items import Item

CHAMPION_NAMES = ["Grubnak", "Vorsha", "Ulthar", "Skarn", "Mirekka", "Old Tusk", "Gash", "Fenwyr", "Drezzik"]
CHAMPION_EPITHETS = ["the Cruel", "the Vile", "Bonecrusher", "the Unbowed", "Nightstalker", "the Butcher",
                     "Gutripper", "the Patient"]
RELIC_OWNERS = ["Maud", "the Abbot", "Captain Orrin", "Grandmother Ysolde", "the Guildmaster", "young Tam"]
RELIC_THINGS = ["silver locket", "prayer beads", "signet ring", "pocket watch", "lucky coin", "journal"]


def champion_name(kind: str, rng: random.Random) -> str:
    return f"{rng.choice(CHAMPION_NAMES)} {rng.choice(CHAMPION_EPITHETS)}"


def relic_name(rng: random.Random) -> str:
    return f"{rng.choice(RELIC_OWNERS)}'s {rng.choice(RELIC_THINGS)}"


def plural(name: str) -> str:
    if name.endswith("s"):
        return name
    if name.endswith("y") and not name.endswith("ey"):
        return name[:-1] + "ies"
    return name + "s"


@dataclass(eq=False)
class Quest:
    kind: str  # slay | fetch | cull
    depth: int
    giver: NPC
    title: str
    pitch: str  # what the envoy asks of you
    reward_gold: int
    reward_xp: int
    reward_item: Item | None = None
    target: Monster | None = None  # slay
    relic: Item | None = None  # fetch
    monster_kind: str = ""  # cull
    needed: int = 0
    progress: int = 0
    state: str = "offered"  # offered -> active -> rewarded

    def is_done(self, player) -> bool:
        if self.kind == "slay":
            return self.target is not None and self.target.hp <= 0
        if self.kind == "fetch":
            return any(it is self.relic for it in player.pack)
        return self.progress >= self.needed

    def status(self, player) -> str:
        if self.state == "rewarded":
            return "Completed."
        if self.is_done(player):
            return f"Done! Return to {self.giver.name} on floor {self.depth} for your reward."
        if self.kind == "cull":
            return f"{self.progress}/{self.needed} slain."
        if self.kind == "fetch":
            return "Not found yet."
        return "Still at large."

    def note_kill(self, monster, depth: int) -> None:
        if (self.state == "active" and self.kind == "cull" and depth == self.depth
                and monster.kind.name == self.monster_kind):
            self.progress += 1
