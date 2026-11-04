"""Character classes and their skill trees.

Each class has two branches of four skills. A skill needs the one above it
in its branch (at least rank 1) and a minimum character level for its tier.
You get one skill point per level (and one to start with). Skills are either
passive stat bonuses or unlock an active ability/spell (see spells.py); extra
ranks in an active skill make it stronger.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import settings as S

TIER_LEVELS = (1, 2, 4, 6)  # character level needed for each tier of a branch


@dataclass(frozen=True)
class Skill:
    key: str
    name: str
    max_rank: int
    description: str  # what one rank does
    stats: dict[str, int] = field(default_factory=dict)  # passive bonus per rank
    spell: str | None = None  # active skills unlock this spell
    immune: tuple[str, ...] = ()  # statuses you become immune to


def _s(key, name, max_rank, description, spell=None, immune=(), **stats) -> Skill:
    return Skill(key, name, max_rank, description, dict(stats), spell, tuple(immune))


SKILLS: dict[str, Skill] = {s.key: s for s in [
    # ---- warrior
    _s("brawn", "Brawn", 3, "+1 melee attack per rank.", power=1),
    _s("power strike", "Power Strike", 3, "Ability: a mighty blow against an adjacent foe. Ranks add damage.",
       spell="power strike"),
    _s("cleave", "Cleave", 2, "Ability: strike every adjacent foe at once.", spell="cleave"),
    _s("executioner", "Executioner", 2, "+5% melee critical chance per rank.", crit=5),
    _s("toughness", "Toughness", 3, "+8 max HP per rank.", max_hp=8),
    _s("iron skin", "Iron Skin", 2, "+1 defense per rank.", defense=1),
    _s("second wind", "Second Wind", 2, "Ability: recover a chunk of health and shake off poison.",
       spell="second wind"),
    _s("unstoppable", "Unstoppable", 1, "You can no longer be stunned or slowed.",
       immune=("stunned", "slowed")),
    # ---- ranger
    _s("steady aim", "Steady Aim", 3, "+5% ranged accuracy per rank.", ranged_accuracy=5),
    _s("aimed shot", "Aimed Shot", 3, "Ability: a careful shot that rarely misses and often crits.",
       spell="aimed shot"),
    _s("volley", "Volley", 2, "Ability: loose an arrow at every foe in range.", spell="volley"),
    _s("eagle eye", "Eagle Eye", 2, "+1 bow range and +1 sight radius per rank.", range=1, sight=1),
    _s("evasion", "Evasion", 3, "+4% evasion per rank.", evasion=4),
    _s("forager", "Forager", 2, "You get hungry 25% slower per rank.", sustenance=25),
    _s("trap sense", "Trap Sense", 1, "You always notice traps next to you, and sometimes two tiles away.",
       trap_sense=1),
    _s("poison arrow", "Poison Arrow", 3, "Ability: a shot that poisons. Ranks make the venom stronger.",
       spell="poison arrow"),
    # ---- mage
    _s("magic missile", "Magic Missile", 3, "Spell: an unerring bolt of force. Ranks add damage.",
       spell="magic missile"),
    _s("frost bolt", "Frost Bolt", 3, "Spell: an icy bolt that slows its target.", spell="frost bolt"),
    _s("fireball", "Fireball", 3, "Spell: an exploding ball of fire that sets foes alight.", spell="fireball"),
    _s("arcane power", "Arcane Power", 3, "+1 spell power per rank.", spell_power=1),
    _s("meditation", "Meditation", 3, "+6 max mana per rank, and mana returns faster.", max_mana=6,
       mana_regen=1),
    _s("blink", "Blink", 2, "Spell: teleport to a spot you can see. Ranks add range.", spell="blink"),
    _s("mend", "Mend", 3, "Spell: heal your wounds and cure poison.", spell="mend"),
    _s("mana shield", "Mana Shield", 2, "Spell: damage drains your mana before your health.",
       spell="mana shield"),
]}


@dataclass(frozen=True)
class PlayerClass:
    key: str
    name: str
    description: str
    hp: int  # added to the difficulty's starting HP
    power: int
    defense: int
    accuracy: int
    evasion: int
    crit: int
    mana: int
    spell_power: int
    hp_per_level: int
    mana_per_level: int
    mana_regen: int  # turns per mana point
    arrows: int  # added to the difficulty's starting arrows (only with a bow)
    kit: tuple[str, ...]  # starting items, "kind:subtype[:count_or_bonus]"
    branches: tuple[tuple[str, tuple[str, ...]], ...]
    start_skills: tuple[tuple[str, int], ...] = ()
    color: tuple[int, int, int] = S.YELLOW

    def tree(self) -> list[tuple[str, list[str]]]:
        return [(name, list(skills)) for name, skills in self.branches]

    def skill_position(self, key: str) -> tuple[int, int] | None:
        """(branch index, tier) of a skill in this class's tree."""
        for b, (_, skills) in enumerate(self.branches):
            if key in skills:
                return b, skills.index(key)
        return None


CLASSES: dict[str, PlayerClass] = {c.key: c for c in [
    PlayerClass(
        "adventurer", "Adventurer", "A jack of all trades: sword arm, bow and a little magic.",
        hp=0, power=4, defense=0, accuracy=80, evasion=10, crit=5, mana=5, spell_power=0,
        hp_per_level=8, mana_per_level=1, mana_regen=8, arrows=0,
        kit=("launcher:shortbow:1", "food:ration:1"),
        branches=(("Survivor", ("toughness", "evasion", "forager", "second wind")),
                  ("Dabbler", ("steady aim", "magic missile", "blink", "meditation"))),
    ),
    PlayerClass(
        "warrior", "Warrior", "Tough and strong. Excels in melee and shrugs off punishment.",
        hp=10, power=5, defense=1, accuracy=80, evasion=5, crit=5, mana=6, spell_power=0,
        hp_per_level=10, mana_per_level=1, mana_regen=8, arrows=0,
        kit=("weapon:sword:1", "armor:leather armor:1", "food:ration:1"),
        branches=(("Weapon Master", ("brawn", "power strike", "cleave", "executioner")),
                  ("Juggernaut", ("toughness", "iron skin", "second wind", "unstoppable"))),
        color=(230, 120, 90),
    ),
    PlayerClass(
        "ranger", "Ranger", "A deadly archer who is hard to pin down and lives off the land.",
        hp=0, power=4, defense=0, accuracy=85, evasion=15, crit=8, mana=8, spell_power=0,
        hp_per_level=7, mana_per_level=1, mana_regen=6, arrows=15,
        kit=("launcher:longbow:2", "weapon:dagger:1", "food:ration:1"),
        branches=(("Marksman", ("steady aim", "aimed shot", "volley", "eagle eye")),
                  ("Survivalist", ("evasion", "forager", "trap sense", "poison arrow"))),
        color=(110, 200, 110),
    ),
    PlayerClass(
        "mage", "Mage", "Frail, but commands devastating spells fuelled by a deep pool of mana.",
        hp=-6, power=3, defense=0, accuracy=75, evasion=10, crit=5, mana=20, spell_power=2,
        hp_per_level=5, mana_per_level=2, mana_regen=6, arrows=0,
        kit=("weapon:dagger:1", "potion:mana:2", "food:ration:1"),
        branches=(("Evocation", ("magic missile", "frost bolt", "fireball", "arcane power")),
                  ("Arcana", ("meditation", "blink", "mend", "mana shield"))),
        start_skills=(("magic missile", 1),),
        color=(150, 120, 240),
    ),
]}
CLASS_NAMES = tuple(CLASSES)


def can_learn(cls: PlayerClass, skills: dict[str, int], level: int, key: str) -> tuple[bool, str]:
    """Whether ``key`` can take another rank, and why not if it can't."""
    pos = cls.skill_position(key)
    if pos is None:
        return False, "Not in your skill tree."
    branch, tier = pos
    skill = SKILLS[key]
    if skills.get(key, 0) >= skill.max_rank:
        return False, "Already at its highest rank."
    if level < TIER_LEVELS[tier]:
        return False, f"Requires character level {TIER_LEVELS[tier]}."
    if tier > 0:
        above = cls.branches[branch][1][tier - 1]
        if skills.get(above, 0) < 1:
            return False, f"Requires {SKILLS[above].name}."
    return True, ""
