"""Actors and items."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import settings as S
from .classes import CLASSES, SKILLS, PlayerClass
from .items import (  # noqa: F401  (re-exported: these used to live here)
    ARMORS,
    LAUNCHERS,
    WEAPONS,
    Item,
    make_ammo,
    make_armor,
    make_consumable,
    make_launcher,
    make_weapon,
    random_item,
)
from .status import STATUS_SPECS, Status

Color = tuple[int, int, int]


def with_article(name: str) -> str:
    """'an orc', 'a goblin', '5 arrows'."""
    if not name or name[0].isdigit():
        return name
    return f"{'an' if name[0].lower() in 'aeiou' else 'a'} {name}"


class Actor:
    crit_mult = 2

    def __init__(
        self,
        x: int,
        y: int,
        name: str,
        glyph: str,
        color: Color,
        hp: int,
        power: int,
        defense: int,
        accuracy: int = 75,
        evasion: int = 10,
        crit: int = 5,
    ) -> None:
        self.x, self.y = x, y
        self.name, self.glyph, self.color = name, glyph, color
        self.max_hp = self.hp = hp
        self.base_power = power
        self.base_defense = defense
        self.base_accuracy = accuracy
        self.base_evasion = evasion
        self.base_crit = crit
        self.statuses: dict[str, Status] = {}
        self.immune: frozenset[str] = frozenset()
        self.stun_immunity = 0  # rounds left during which new stuns are shrugged off

    # ------------------------------------------------------------- stats
    @property
    def power(self) -> int:
        return self.base_power

    @property
    def defense(self) -> int:
        return self.base_defense

    @property
    def accuracy(self) -> int:
        return self.base_accuracy + sum(STATUS_SPECS[s].accuracy for s in self.statuses)

    @property
    def evasion(self) -> int:
        if self.has("stunned"):
            return 0
        return max(0, self.base_evasion + sum(STATUS_SPECS[s].evasion for s in self.statuses))

    @property
    def crit_chance(self) -> int:
        return self.base_crit

    @property
    def ranged_power(self) -> int:
        return 0

    @property
    def shot_range(self) -> int:
        return 0

    @property
    def stun_on_crit(self) -> bool:
        return False

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def attack_damage(self, target: Actor, rng: random.Random, power: int | None = None) -> int:
        return max(1, (self.power if power is None else power) - target.defense + rng.randint(-1, 2))

    # ---------------------------------------------------------- statuses
    def has(self, status: str) -> bool:
        return status in self.statuses

    def add_status(self, status: str, turns: int, potency: int = 1) -> bool:
        """Apply (or extend) a status. Returns False if the actor is immune."""
        if status in self.immune or not self.alive:
            return False
        cur = self.statuses.get(status)
        if status == "stunned" and (cur or self.stun_immunity > 0):
            # Stuns never stack or refresh, and a freshly recovered actor
            # shrugs them off for a moment - otherwise stun-locks happen.
            return False
        if cur:
            cur.turns = max(cur.turns, turns)
            cur.potency = max(cur.potency, potency)
        else:
            self.statuses[status] = Status(turns, potency)
        return True

    def cure(self, *statuses: str) -> list[str]:
        """Remove the given statuses (all if none given); returns those removed."""
        names = statuses or tuple(self.statuses)
        removed = [s for s in names if s in self.statuses]
        for s in removed:
            del self.statuses[s]
        return removed


HUNGER_MAX = 2000
HUNGER_START = 1300
# (upper bound of satiation, label); checked in order
HUNGER_STATES = [(50, "Starving"), (150, "Fainting"), (400, "Weak"), (900, "Hungry"), (1700, ""),
                 (HUNGER_MAX + 1, "Satiated")]
PACK_SIZE = 20
MELEE_SLOTS = ("weapon", "armor", "ring")
RANGED_SLOTS = ("launcher", "armor", "ring")
ALL_SLOTS = ("weapon", "armor", "launcher", "ring")


class Player(Actor):
    """You. Stats are built from your class, level, gear, skills and statuses."""

    def __init__(self, x: int, y: int, player_class: str = "adventurer") -> None:
        cls = CLASSES[player_class]
        self._ready = False
        super().__init__(x, y, "You", "@", S.YELLOW, hp=30 + cls.hp, power=cls.power, defense=cls.defense,
                         accuracy=cls.accuracy, evasion=cls.evasion, crit=cls.crit)
        self.cls: PlayerClass = cls
        self.level = 1
        self.xp = 0
        self.gold = 0
        self.kills = 0
        self.weapon: Item | None = None
        self.armor: Item | None = None
        self.launcher: Item | None = None
        self.ring: Item | None = None
        self.pack: list[Item] = []
        self.arrows = 0
        self.has_amulet = False
        self.base_max_mana = cls.mana
        self.base_spell_power = cls.spell_power
        self.satiation = HUNGER_START
        self.skills: dict[str, int] = dict(cls.start_skills)
        self.skill_points = 1
        self.book_spells: dict[str, int] = {}  # spells learned from tomes (rank 1)
        self._ready = True
        self.mana = self.max_mana
        for spec in cls.kit:
            self._add_kit_item(spec)
        if self.launcher:
            self.arrows = 10 + cls.arrows
        self.potions = 1  # the game adjusts this for the difficulty

    def _add_kit_item(self, spec: str) -> None:
        """Equip or pack one starting item, given as "kind:subtype[:n]"."""
        kind, subtype, *rest = spec.split(":")
        n = int(rest[0]) if rest else 1
        if kind == "weapon":
            self.weapon = make_weapon(0, 0, n, base=subtype)
        elif kind == "armor":
            self.armor = make_armor(0, 0, n, base=subtype)
        elif kind == "launcher":
            name, _bonus, reach, acc = next(b for b in LAUNCHERS if b[0] == subtype)
            self.launcher = make_launcher(0, 0, name, n, reach, acc)
        else:
            self.pack.append(make_consumable(0, 0, kind, subtype, n))

    # ------------------------------------------------------------ equipment
    def gear(self, slots: tuple[str, ...] = ALL_SLOTS) -> list[Item]:
        return [it for it in (getattr(self, s) for s in slots) if it is not None]

    def gear_bonus(self, stat: str, slots: tuple[str, ...] = ALL_SLOTS) -> int:
        return sum(it.bonus(stat) for it in self.gear(slots) if it.kind != "launcher" or "launcher" in slots)

    def skill_bonus(self, stat: str) -> int:
        return sum(SKILLS[k].stats.get(stat, 0) * rank for k, rank in self.skills.items())

    def equipped(self, item: Item) -> bool:
        return any(it is item for it in self.gear())

    # ------------------------------------------------------------- stats
    @property
    def max_hp(self) -> int:  # type: ignore[override]
        if not getattr(self, "_ready", False):
            return self.base_max_hp
        return max(1, self.base_max_hp + self.gear_bonus("max_hp") + self.skill_bonus("max_hp"))

    @max_hp.setter
    def max_hp(self, value: int) -> None:
        """Setting max HP sets the *effective* value (gear and skills included)."""
        bonus = self.gear_bonus("max_hp") + self.skill_bonus("max_hp") if getattr(self, "_ready", False) else 0
        self.base_max_hp = value - bonus

    @property
    def max_mana(self) -> int:
        return max(0, self.base_max_mana + self.gear_bonus("max_mana") + self.skill_bonus("max_mana"))

    @property
    def spell_power(self) -> int:
        return self.base_spell_power + self.gear_bonus("spell_power") + self.skill_bonus("spell_power")

    @property
    def immune(self) -> frozenset[str]:  # type: ignore[override]
        extra = {s for k in self.skills for s in SKILLS[k].immune}
        return frozenset(self._immune | extra)

    @immune.setter
    def immune(self, value: frozenset[str]) -> None:
        self._immune = frozenset(value)

    @property
    def power(self) -> int:
        weapon = self.weapon.value if self.weapon else 0
        return self.base_power + weapon + self.gear_bonus("power", MELEE_SLOTS) + self.skill_bonus("power")

    @property
    def defense(self) -> int:
        armor = self.armor.value if self.armor else 0
        return self.base_defense + armor + self.gear_bonus("defense") + self.skill_bonus("defense")

    @property
    def hunger_penalty(self) -> int:
        return -10 if self.satiation < 400 else 0

    @property
    def accuracy(self) -> int:
        return (super().accuracy + self.gear_bonus("accuracy", MELEE_SLOTS) + self.skill_bonus("accuracy")
                + self.hunger_penalty)

    @property
    def ranged_accuracy(self) -> int:
        return (super().accuracy + self.gear_bonus("accuracy", RANGED_SLOTS) + self.skill_bonus("ranged_accuracy")
                + self.hunger_penalty)

    @property
    def evasion(self) -> int:
        if self.has("stunned"):
            return 0
        return max(0, super().evasion + self.gear_bonus("evasion") + self.skill_bonus("evasion"))

    @property
    def crit_chance(self) -> int:
        return self.base_crit + self.gear_bonus("crit", MELEE_SLOTS) + self.skill_bonus("crit")

    @property
    def ranged_crit(self) -> int:
        return self.base_crit + self.gear_bonus("crit", RANGED_SLOTS)

    @property
    def ranged_power(self) -> int:
        bow = self.launcher.value if self.launcher else 0
        return self.base_power // 2 + bow + self.gear_bonus("power", RANGED_SLOTS)

    @property
    def shot_range(self) -> int:
        return self.launcher.range + self.skill_bonus("range") if self.launcher else 0

    @property
    def stun_on_crit(self) -> bool:
        return bool(self.weapon and self.weapon.effect == "stun")

    @property
    def sight_bonus(self) -> int:
        return self.skill_bonus("sight")

    @property
    def hunger_rate(self) -> float:
        """Multiplier on how fast you get hungry (gear and skills)."""
        slower = self.gear_bonus("sustenance") + self.skill_bonus("sustenance")
        return max(0.25, 1 - slower / 100)

    @property
    def hunger_state(self) -> str:
        for bound, label in HUNGER_STATES:
            if self.satiation < bound:
                return label
        return "Satiated"  # pragma: no cover

    # ------------------------------------------------------------- spells
    @property
    def spells(self) -> dict[str, int]:
        """Known spells/abilities and their rank."""
        out = dict(self.book_spells)
        for key, rank in self.skills.items():
            spell = SKILLS[key].spell
            if spell and rank > 0:
                out[spell] = max(out.get(spell, 0), rank)
        return out

    # ------------------------------------------------------------- pack
    def count(self, kind: str, subtype: str) -> int:
        return sum(it.count for it in self.pack if it.kind == kind and it.subtype == subtype)

    def find(self, kind: str, subtype: str | None = None) -> Item | None:
        for it in self.pack:
            if it.kind == kind and (subtype is None or it.subtype == subtype):
                return it
        return None

    def set_count(self, kind: str, subtype: str, n: int) -> None:
        """Set how many of a consumable you carry (handy for tests and kits)."""
        for it in [it for it in self.pack if it.kind == kind and it.subtype == subtype]:
            self.pack.remove(it)
        if n > 0:
            self.pack.append(make_consumable(0, 0, kind, subtype, n))

    @property
    def potions(self) -> int:
        """Potions of healing carried (shorthand)."""
        return self.count("potion", "healing")

    @potions.setter
    def potions(self, n: int) -> None:
        self.set_count("potion", "healing", n)

    @property
    def scrolls(self) -> int:
        """Scrolls of fire carried (shorthand)."""
        return self.count("scroll", "fire")

    @scrolls.setter
    def scrolls(self, n: int) -> None:
        self.set_count("scroll", "fire", n)

    def pack_full_for(self, item: Item) -> bool:
        if item.stackable and any(it.same_stack(item) for it in self.pack):
            return False
        return len(self.pack) >= PACK_SIZE

    def add_to_pack(self, item: Item) -> Item | None:
        """Put ``item`` in the pack, stacking it if possible. Returns the item
        as it now sits in the pack (the stack it joined), or None if full."""
        if item.stackable:
            for it in self.pack:
                if it.same_stack(item):
                    it.count += item.count
                    return it
        if len(self.pack) >= PACK_SIZE:
            return None
        self.pack.append(item)
        return item

    def take_one(self, item: Item) -> Item:
        """Remove one of ``item`` from the pack and return it."""
        if item.count > 1:
            item.count -= 1
            return make_consumable(0, 0, item.kind, item.subtype)
        self.pack.remove(item)
        return item

    # ------------------------------------------------------------- levels
    @property
    def xp_needed(self) -> int:
        return self.level * 20

    def gain_xp(self, amount: int) -> bool:
        """Add XP; returns True if at least one level was gained."""
        self.xp += amount
        leveled = False
        while self.xp >= self.xp_needed:
            self.xp -= self.xp_needed
            self.level += 1
            self.base_max_hp += self.cls.hp_per_level
            self.hp = min(self.max_hp, self.hp + self.cls.hp_per_level)
            self.base_max_mana += self.cls.mana_per_level
            self.mana = min(self.max_mana, self.mana + self.cls.mana_per_level)
            self.base_power += 1
            self.base_accuracy += 2
            if self.level % 2 == 0:
                self.base_defense += 1
            self.skill_points += 1
            leveled = True
        return leveled


# ------------------------------------------------------------------ monsters
@dataclass(frozen=True)
class MonsterKind:
    name: str
    glyph: str
    color: Color
    hp: int
    power: int
    defense: int
    xp: int
    min_depth: int
    ai: str = "melee"  # see ai.BEHAVIOURS
    speed: int = 100  # energy gained per round; 100 acts once a round
    accuracy: int = 75
    evasion: int = 10
    crit: int = 5
    range: int = 0  # > 0: has a ranged attack
    ranged_power: int = 0
    projectile: str = "arrow"  # arrow | bolt (poison) | fire (fire bolt)
    on_hit: tuple[str, int, float] | None = None  # (status, turns, chance) on melee hits
    stun_on_crit: bool = False
    immune: frozenset[str] = frozenset()
    regen: int = 0  # HP regained per round
    spawnable: bool = True  # appears as a random spawn
    boss: bool = False
    description: str = ""


_KINDS = [
    MonsterKind("rat", "r", S.GREY, 6, 3, 0, 4, 1, ai="skittish", accuracy=70, evasion=15,
                description="A mangy rat. Flees when badly hurt."),
    MonsterKind("goblin", "g", S.GREEN, 10, 4, 0, 8, 1,
                description="A scrappy goblin that charges straight at you."),
    MonsterKind("jackal", "j", (200, 160, 90), 7, 3, 0, 6, 2, ai="pack", speed=150, evasion=20,
                description="Fast pack hunter. Hangs back when alone, swarms with friends."),
    MonsterKind("bat", "b", S.PURPLE, 8, 5, 0, 10, 2, ai="erratic", speed=150, accuracy=70, evasion=30,
                description="Flits about unpredictably. Hard to hit."),
    MonsterKind("goblin archer", "a", (120, 220, 120), 9, 3, 0, 12, 2, ai="ranged", range=6, ranged_power=5,
                evasion=12, description="Keeps its distance and looses arrows."),
    MonsterKind("orc", "o", S.ORANGE, 18, 6, 1, 16, 2, evasion=5,
                description="A brawny orc warrior."),
    MonsterKind("cave spider", "x", (150, 150, 170), 12, 4, 0, 14, 3, ai="ambusher", speed=150, evasion=20,
                on_hit=("poisoned", 4, 0.5), immune=frozenset({"poisoned"}),
                description="Lurks motionless until prey comes close. Venomous bite."),
    MonsterKind("goblin shaman", "s", (90, 200, 200), 12, 3, 0, 20, 3, ai="caster", range=6, ranged_power=3,
                projectile="bolt", evasion=10,
                description="Hurls hexes - poison, slow, blindness - and mends its allies."),
    MonsterKind("ogre", "O", S.RED, 30, 9, 2, 28, 3, ai="brute", speed=75, accuracy=70, evasion=0, crit=15,
                stun_on_crit=True, description="Lumbering and slow, but its blows can stun."),
    MonsterKind("skeleton", "k", (225, 225, 210), 16, 6, 2, 18, 4, evasion=5,
                immune=frozenset({"poisoned", "blinded"}), description="Rattling bones. Immune to poison."),
    MonsterKind("troll", "T", S.CYAN, 40, 10, 3, 40, 4, evasion=5, regen=1,
                description="Regenerates its wounds - unless it is burning."),
    MonsterKind("mimic", "&", S.ORANGE, 16, 6, 1, 20, 1, spawnable=False, evasion=0,
                description="A hungry chest with teeth."),
    # ---- bosses (see level.BOSS_FLOORS)
    MonsterKind("orc warlord", "W", (255, 120, 60), 60, 8, 3, 120, 3, ai="warlord", accuracy=80, evasion=5,
                crit=12, stun_on_crit=True, spawnable=False, boss=True,
                description="Commands the orc hordes. Calls for reinforcements and rages when wounded."),
    MonsterKind("lich", "L", (200, 120, 255), 100, 6, 2, 250, 5, ai="lich", accuracy=85, evasion=15,
                range=7, ranged_power=10, projectile="fire", immune=frozenset({"poisoned", "blinded"}),
                spawnable=False, boss=True,
                description="Undead sorcerer holding the Amulet. Blinks away from danger and raises the dead."),
]
MONSTER_KINDS: dict[str, MonsterKind] = {k.name: k for k in _KINDS}
MONSTER_TYPES: list[MonsterKind] = [k for k in _KINDS if k.spawnable]
MIMIC = MONSTER_KINDS["mimic"]
BOSS_HP_PER_FLOOR = 6


class Monster(Actor):
    def __init__(self, x: int, y: int, kind: MonsterKind | str, depth: int) -> None:
        if isinstance(kind, str):
            kind = MONSTER_KINDS[kind]
        # Regular monsters grow with depth from floor 1; bosses from their
        # home floor (so they're exactly as designed there) and faster, so
        # they stay a threat when they return deeper down in endless mode.
        scale = max(0, depth - max(1, kind.min_depth if kind.boss else 1))
        hp_per_floor = BOSS_HP_PER_FLOOR if kind.boss else 2
        super().__init__(
            x, y, kind.name, kind.glyph, kind.color,
            hp=kind.hp + scale * hp_per_floor,
            power=kind.power + scale // 2,
            defense=kind.defense,
            accuracy=kind.accuracy + scale * 2,
            evasion=kind.evasion,
            crit=kind.crit,
        )
        self.kind = kind
        self.ai = kind.ai
        self.speed = kind.speed
        self.energy = 0
        self.xp_value = kind.xp + scale * 2
        self.alert = False
        self.immune = kind.immune
        self.cooldowns: dict[str, int] = {}
        self._ranged_power = kind.ranged_power + scale // 2 if kind.range else 0
        self.carries_amulet = False
        self.enraged = False
        self.summoned_by: Monster | None = None  # the boss that raised/called it
        self.title = ""  # champions (quest targets) have a proper name

    @property
    def ranged_power(self) -> int:
        return self._ranged_power

    @property
    def shot_range(self) -> int:
        return self.kind.range

    @property
    def stun_on_crit(self) -> bool:
        return self.kind.stun_on_crit

    @property
    def is_boss(self) -> bool:
        return self.kind.boss

    @property
    def display_name(self) -> str:
        return f"{self.title}, {self.name} champion" if self.title else self.name

    @property
    def summoned(self) -> bool:
        return self.summoned_by is not None


class NPC(Actor):
    """A friendly, non-hostile character. Bump into one to talk."""

    def __init__(self, x: int, y: int, role: str, rng: random.Random) -> None:
        spec = NPC_ROLES[role]
        name = rng.choice(spec["names"])
        super().__init__(x, y, name, "@", spec["color"], hp=1, power=0, defense=0)
        self.role = role
        self.title: str = spec["title"]
        self.wanders: bool = spec["wanders"]
        self.used = False  # one-off services (e.g. the sage's map) are spent
        self.greeting: str = rng.choice(spec["greetings"])

    @property
    def display_name(self) -> str:
        return f"{self.name} the {self.title}"


NPC_ROLES: dict[str, dict] = {
    "merchant": {
        "title": "merchant", "color": S.GREEN, "wanders": False,
        "names": ["Olga", "Bartholomew", "Zed", "Mirela", "Fenwick"],
        "greetings": ["Finest wares this side of the abyss!", "Gold for goods, friend.",
                      "Buying? I'm always selling."],
    },
    "healer": {
        "title": "healer", "color": S.PINK, "wanders": False,
        "names": ["Sister Ana", "Brother Tomas", "Mother Ilse"],
        "greetings": ["Rest a moment, child.", "Your wounds can be tended, for a donation.",
                      "The light keeps even here."],
    },
    "sage": {
        "title": "sage", "color": S.CYAN, "wanders": True,
        "names": ["Aldous", "Quillon", "Yara", "Old Benno"],
        "greetings": ["I have walked these halls for a hundred years.",
                      "Knowledge is the only map that matters.", "Hmm? Ah, a visitor."],
    },
    "questgiver": {
        "title": "guild envoy", "color": S.YELLOW, "wanders": False,
        "names": ["Harlan", "Isembard", "Keziah", "Odo", "Marit"],
        "greetings": ["The Adventurers' Guild pays well for good work.", "You look capable. I have a job.",
                      "Ah, a fresh face. Care to earn some coin?"],
    },
    "wanderer": {
        "title": "lost adventurer", "color": S.WHITE, "wanders": True,
        "names": ["Pip", "Garrick", "Sela", "Dunmore"],
        "greetings": ["Have you seen the way out?", "Don't drink from every fountain... or do.",
                      "I lost my whole party down here."],
    },
}

# Rumours the wandering adventurer can share: they double as gameplay hints.
RUMOURS = [
    "Wait a turn or two near suspicious floors - searching reveals hidden traps.",
    "Known spike and alarm traps can be stepped around. Teleport runes can't.",
    "Some chests bite back. Mimics get nastier the deeper you go.",
    "Doors block sight. Monsters can open them too, mind you.",
    "Press X to look around. It will tell you how tough a monster is before you fight it.",
    "The stairs go both ways. Floors stay just as you left them.",
    "Fountains heal, but each one only has enough magic for a single drink.",
    "Sages can show you the layout of a whole floor.",
    "Press T to shoot. Arrows often survive the flight - pick them up again.",
    "Trolls knit their wounds shut. Fire stops them - read a scroll of fire.",
    "Archers and shamans hate being cornered. Close the distance or break line of sight.",
    "A warlord rules the third floor. His seal bars the stairs until he falls.",
    "The lich keeps the Amulet. Kill it and the Amulet is yours.",
    "Daggers find the gaps in armor. Warhammers leave foes reeling.",
    "A corridor that ends in bare rock? Search it. Secret doors hide the best rooms.",
    "Vault keys are never kept in the vault. Look around the rest of the floor.",
    "If you see a portcullis, there's a lever somewhere on the same floor.",
    "Guild envoys pay handsomely. Come back to them once the job is done.",
]


def random_monster(x: int, y: int, depth: int, rng: random.Random) -> Monster:
    pool = [k for k in MONSTER_TYPES if k.min_depth <= depth]
    # Bias towards the more dangerous monsters available at this depth.
    weights = [1 + k.min_depth for k in pool]
    kind = rng.choices(pool, weights=weights)[0]
    return Monster(x, y, kind, depth)


@dataclass
class Fx:
    """A cosmetic event for the UI to animate (the game itself is instant)."""

    kind: str  # "shot" | "text"
    path: list[tuple[int, int]] = field(default_factory=list)
    text: str = ""
    color: Color = S.WHITE
