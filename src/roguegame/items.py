"""Items: consumables, gear with rarity and affixes, and identification.

Item categories (``Item.kind``):

========== ===========================================================
gold       picked up straight into your purse
ammo       arrows; go straight into your quiver
potion     quaffed; type hidden behind a random appearance until known
scroll     read; type hidden behind a random label until known
food       eaten to stave off hunger
book       read to learn a spell
key        opens a locked door (used up)
quest      a relic someone asked you to find
weapon     melee weapon slot
armor      body armor slot
launcher   bow slot
ring       ring slot (always magical)
amulet     the Amulet of Yendor
========== ===========================================================

Gear has a *rarity* (common, magic, rare, legendary) that decides how many
*affixes* it rolls. Affixes are data: each adds to one stat. Some are curses;
a cursed item can't be taken off once equipped. Gear affixes stay hidden
until the item is identified (by equipping it, a scroll of identify, or a
merchant).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import settings as S

Color = tuple[int, int, int]

GEAR_KINDS = ("weapon", "armor", "launcher", "ring")
STACKABLE_KINDS = ("potion", "scroll", "food", "book", "key")


@dataclass(eq=False)  # items are things, not values: two identical swords are still two swords
class Item:
    x: int
    y: int
    kind: str
    name: str  # true, fully identified name, e.g. "potion of healing" or "Keen sword +2 of the Bear"
    glyph: str
    color: Color
    value: int = 0  # gold amount, gear enchantment (+N), or arrow count
    seen: bool = False  # has the player ever had this item in view?
    accuracy: int = 0  # base gear traits (percentage points)
    evasion: int = 0
    crit: int = 0
    effect: str = ""  # e.g. "stun": critical hits stun
    range: int = 0  # launchers only
    subtype: str = ""  # consumable type ("healing") or gear base ("sword")
    count: int = 1  # stack size for consumables
    rarity: str = "common"
    affixes: list[tuple[str, int]] = field(default_factory=list)  # (affix key, rolled value)
    identified: bool = True  # gear: are affixes and curses known?
    cursed: bool = False
    appearance: str = ""  # rings: gem name, e.g. "jade"

    @property
    def is_gear(self) -> bool:
        return self.kind in GEAR_KINDS

    @property
    def stackable(self) -> bool:
        return self.kind in STACKABLE_KINDS

    def bonus(self, stat: str) -> int:
        """Total of ``stat`` from this item's base traits and affixes."""
        total = sum(v for key, v in self.affixes if AFFIXES[key].stat == stat)
        if stat == "accuracy":
            total += self.accuracy
        elif stat == "evasion":
            total += self.evasion
        elif stat == "crit":
            total += self.crit
        return total

    def same_stack(self, other: Item) -> bool:
        return self.stackable and other.kind == self.kind and other.subtype == self.subtype


# ============================================================== consumables
@dataclass(frozen=True)
class Consumable:
    key: str
    name: str  # "healing" -> "potion of healing"
    description: str
    weight: int  # relative frequency
    min_depth: int = 1
    harmful: bool = False
    nutrition: int = 0  # food only


POTIONS: dict[str, Consumable] = {c.key: c for c in [
    Consumable("healing", "healing", "Heals wounds and cures poison and burning.", 10),
    Consumable("greater healing", "greater healing", "Heals you completely and cures every affliction.", 3, 3),
    Consumable("mana", "mana", "Restores magical energy.", 7),
    Consumable("haste", "haste", "For a while you act twice as fast.", 4, 2),
    Consumable("regeneration", "regeneration", "Your wounds knit rapidly for a while.", 4),
    Consumable("might", "might", "Permanently increases your strength (+1 ATK).", 1, 3),
    Consumable("poison", "poison", "Poisons whoever drinks it.", 4, harmful=True),
    Consumable("blindness", "blindness", "Blinds whoever drinks it.", 3, harmful=True),
]}

SCROLLS: dict[str, Consumable] = {c.key: c for c in [
    Consumable("fire", "fire", "Engulfs every foe in sight in flames.", 6),
    Consumable("identify", "identify", "Reveals the true nature of an item.", 9),
    Consumable("teleportation", "teleportation", "Whisks you away to another part of the floor.", 5),
    Consumable("magic mapping", "magic mapping", "Reveals the layout of the floor.", 4),
    Consumable("enchant weapon", "enchant weapon", "Improves your wielded weapon by +1.", 3, 2),
    Consumable("enchant armor", "enchant armor", "Improves your worn armor by +1.", 3, 2),
    Consumable("remove curse", "remove curse", "Lifts the curses from everything you carry.", 3, 2),
    Consumable("aggravation", "aggravation", "A piercing shriek wakes every monster on the floor.", 3,
               harmful=True),
]}

FOODS: dict[str, Consumable] = {c.key: c for c in [
    Consumable("apple", "apple", "A crisp apple. A light snack.", 4, nutrition=250),
    Consumable("bread", "bread", "A hearty loaf.", 3, nutrition=500),
    Consumable("ration", "ration", "A preserved travel ration. Very filling.", 2, nutrition=900),
]}

# Spellbooks teach the spell with the same key (see spells.py).
BOOKS: dict[str, Consumable] = {c.key: c for c in [
    Consumable("magic missile", "Magic Missile", "Teaches Magic Missile.", 3),
    Consumable("frost bolt", "Frost Bolt", "Teaches Frost Bolt.", 3, 2),
    Consumable("fireball", "Fireball", "Teaches Fireball.", 2, 3),
    Consumable("blink", "Blink", "Teaches Blink.", 2, 2),
    Consumable("mend", "Mend", "Teaches Mend, a healing spell.", 2, 2),
]}

CONSUMABLES = {"potion": POTIONS, "scroll": SCROLLS, "food": FOODS, "book": BOOKS}

POTION_APPEARANCES: list[tuple[str, Color]] = [
    ("ruby", (220, 50, 60)), ("azure", (70, 130, 235)), ("emerald", (60, 200, 100)),
    ("amber", (235, 150, 40)), ("violet", (170, 90, 220)), ("murky", (120, 95, 60)),
    ("milky", (230, 230, 225)), ("golden", (240, 205, 60)), ("silver", (175, 180, 195)),
    ("pink", (235, 140, 190)),
]
SCROLL_SYLLABLES = ["ZEL", "GO", "MER", "FOO", "BAR", "XI", "NOK", "TAH", "VEX", "ULU", "KRA", "DUN",
                    "ELB", "IRA", "QOS", "YUM", "PRA", "THO", "ASH", "NIH"]
RING_GEMS: list[tuple[str, Color]] = [
    ("jade", (80, 190, 120)), ("onyx", (70, 70, 85)), ("garnet", (190, 40, 60)), ("opal", (220, 220, 240)),
    ("topaz", (235, 190, 60)), ("sapphire", (60, 90, 220)), ("amethyst", (160, 90, 210)),
]
BOOK_COLORS: dict[str, Color] = {
    "magic missile": (150, 110, 230), "frost bolt": (110, 190, 240), "fireball": (230, 100, 50),
    "blink": (200, 120, 230), "mend": (240, 150, 180),
}


def consumable_name(kind: str, subtype: str) -> str:
    spec = CONSUMABLES[kind][subtype]
    if kind == "potion":
        return f"potion of {spec.name}"
    if kind == "scroll":
        return f"scroll of {spec.name}"
    if kind == "book":
        return f"tome of {spec.name}"
    return spec.name


def make_consumable(x: int, y: int, kind: str, subtype: str, count: int = 1) -> Item:
    glyph, color = {"potion": ("!", S.RED), "scroll": ("?", S.ORANGE), "food": ("%", (200, 160, 90)),
                    "book": ("+", S.PURPLE)}[kind]
    if kind == "book":
        color = BOOK_COLORS.get(subtype, S.PURPLE)
    return Item(x, y, kind, consumable_name(kind, subtype), glyph, color, subtype=subtype, count=count)


def make_potion(x: int, y: int, subtype: str = "healing", count: int = 1) -> Item:
    return make_consumable(x, y, "potion", subtype, count)


def make_scroll(x: int, y: int, subtype: str = "fire", count: int = 1) -> Item:
    return make_consumable(x, y, "scroll", subtype, count)


def make_food(x: int, y: int, subtype: str = "ration", count: int = 1) -> Item:
    return make_consumable(x, y, "food", subtype, count)


def make_book(x: int, y: int, subtype: str) -> Item:
    return make_consumable(x, y, "book", subtype)


def pick_consumable(kind: str, depth: int, rng: random.Random) -> str:
    pool = [c for c in CONSUMABLES[kind].values() if c.min_depth <= depth]
    return rng.choices(pool, weights=[c.weight for c in pool])[0].key


# ============================================================ gear & affixes
WEAPONS = [
    # name, accuracy, crit, effect
    ("dagger", 5, 10, ""),
    ("sword", 5, 5, ""),
    ("axe", 0, 8, ""),
    ("warhammer", -5, 5, "stun"),
]
ARMORS = [
    # name, evasion
    ("leather armor", 0),
    ("chain mail", -2),
    ("plate mail", -5),
    ("dragon scale", 3),
]
LAUNCHERS = [
    # name, bonus, range, accuracy
    ("shortbow", 1, 6, 0),
    ("longbow", 2, 8, 0),
    ("crossbow", 3, 7, 10),
]


@dataclass(frozen=True)
class Affix:
    key: str
    label: str  # "Flaming" (prefix) or "of the Bear" (suffix)
    prefix: bool
    slots: frozenset[str]
    stat: str
    low: int
    high: int
    curse: bool = False
    text: str = ""  # "+{v} max HP"; {v} is the rolled value

    def describe(self, value: int) -> str:
        return self.text.format(v=value, s=f"{value:+d}")


def _a(key, label, prefix, slots, stat, low, high, text, curse=False) -> Affix:
    return Affix(key, label, prefix, frozenset(slots.split()), stat, low, high, curse, text)


AFFIXES: dict[str, Affix] = {a.key: a for a in [
    # ---- prefixes
    _a("keen", "Keen", True, "weapon launcher", "crit", 4, 10, "{s}% critical chance"),
    _a("heavy", "Heavy", True, "weapon launcher", "power", 1, 3, "{s} attack"),
    _a("accurate", "Accurate", True, "weapon launcher ring", "accuracy", 4, 10, "{s}% accuracy"),
    _a("flaming", "Flaming", True, "weapon launcher", "burn", 15, 30, "{v}% chance to set foes alight"),
    _a("venomous", "Venomous", True, "weapon launcher", "poison", 20, 35, "{v}% chance to poison foes"),
    _a("frozen", "Frozen", True, "weapon launcher", "slow", 15, 30, "{v}% chance to slow foes"),
    _a("vampiric", "Vampiric", True, "weapon", "lifesteal", 10, 25, "heals you for {v}% of damage dealt"),
    _a("sturdy", "Sturdy", True, "armor ring", "defense", 1, 2, "{s} defense"),
    _a("nimble", "Nimble", True, "armor ring", "evasion", 3, 7, "{s}% evasion"),
    _a("arcane", "Arcane", True, "weapon ring", "spell_power", 1, 2, "{s} spell power"),
    # ---- suffixes
    _a("bear", "of the Bear", False, "weapon armor ring", "max_hp", 5, 15, "{s} max HP"),
    _a("magi", "of the Magi", False, "armor ring", "max_mana", 5, 12, "{s} max mana"),
    _a("wizardry", "of Wizardry", False, "ring weapon", "spell_power", 1, 2, "{s} spell power"),
    _a("regeneration", "of Regeneration", False, "armor ring", "regen", 1, 2, "regenerate {v} HP every 10 turns"),
    _a("sustenance", "of Sustenance", False, "armor ring", "sustenance", 20, 40, "{v}% slower hunger"),
    _a("precision", "of Precision", False, "armor ring", "accuracy", 4, 8, "{s}% accuracy"),
    _a("slaying", "of Slaying", False, "weapon ring", "power", 1, 2, "{s} attack"),
    # ---- curses
    _a("rusty", "Rusty", True, "weapon launcher", "power", -2, -1, "{s} attack", curse=True),
    _a("clumsy", "Clumsy", True, "weapon launcher ring", "accuracy", -15, -8, "{s}% accuracy", curse=True),
    _a("frailty", "of Frailty", False, "weapon armor ring", "max_hp", -12, -5, "{s} max HP", curse=True),
    _a("hunger", "of Hunger", False, "armor ring", "sustenance", -50, -30, "hunger {v}% faster", curse=True),
    _a("brittleness", "of Brittleness", False, "armor", "defense", -2, -1, "{s} defense", curse=True),
]}
def affix_text(key: str, value: int) -> str:
    """Human-readable effect of one rolled affix, e.g. '+12 max HP'."""
    if key == "hunger":  # stored as negative sustenance
        return f"hunger {abs(value)}% faster"
    return AFFIXES[key].describe(value)


@dataclass(frozen=True)
class Rarity:
    key: str
    color: Color
    affixes: tuple[int, int]  # min/max number of affixes
    roll_bonus: float  # legendary rolls hit harder


RARITIES: dict[str, Rarity] = {r.key: r for r in [
    Rarity("common", (220, 220, 220), (0, 0), 1.0),
    Rarity("magic", (100, 150, 255), (1, 1), 1.0),
    Rarity("rare", (245, 215, 70), (2, 3), 1.0),
    Rarity("legendary", (255, 140, 40), (3, 4), 1.5),
]}
CURSE_CHANCE = 0.12  # of non-common gear, from floor 2 down


def rarity_weights(depth: int) -> list[float]:
    return [max(20, 62 - 4 * depth), 28, 8 + 2 * depth, 1 + 0.7 * depth]


def roll_rarity(depth: int, rng: random.Random, minimum: str = "common") -> str:
    keys = list(RARITIES)
    weights = rarity_weights(depth)
    lo = keys.index(minimum)
    return rng.choices(keys[lo:], weights=weights[lo:])[0]


LEGENDARY_SYLLABLES = ["dra", "kor", "mith", "el", "vor", "gar", "thu", "zan", "rim", "ash", "fang", "bane",
                       "storm", "dusk", "gloom", "star"]


def legendary_title(rng: random.Random) -> str:
    return (rng.choice(LEGENDARY_SYLLABLES) + rng.choice(LEGENDARY_SYLLABLES)).capitalize()


def add_affixes(item: Item, depth: int, rng: random.Random) -> None:
    """Roll rarity-appropriate affixes (and maybe a curse) onto ``item``."""
    rarity = RARITIES[item.rarity]
    n = rng.randint(*rarity.affixes)
    good = [a for a in AFFIXES.values() if item.kind in a.slots and not a.curse]
    rng.shuffle(good)
    chosen: list[Affix] = []
    for a in good:
        if len(chosen) >= n:
            break
        # At most one prefix and one suffix per stat, and no duplicate stats.
        if any(c.stat == a.stat for c in chosen):
            continue
        chosen.append(a)
    if item.rarity != "common" and depth >= 2 and rng.random() < CURSE_CHANCE:
        curses = [a for a in AFFIXES.values() if item.kind in a.slots and a.curse]
        if curses:
            if chosen:
                chosen.pop()
            chosen.append(rng.choice(curses))
            item.cursed = True
    depth_bonus = depth // 5
    for a in chosen:
        v = rng.randint(a.low, a.high)
        if not a.curse:
            v = round(v * rarity.roll_bonus) + (depth_bonus if a.stat in ("power", "defense", "max_hp") else 0)
        item.affixes.append((a.key, v))
    item.identified = not item.affixes
    if item.rarity == "legendary" and not item.cursed:
        item.appearance = legendary_title(rng)
    item.name = gear_name(item)


def gear_name(item: Item) -> str:
    """The true, identified name of a piece of gear."""
    prefix = next((AFFIXES[k].label for k, _ in item.affixes if AFFIXES[k].prefix), "")
    suffix = next((AFFIXES[k].label for k, _ in item.affixes if not AFFIXES[k].prefix), "")
    base = item.subtype if item.kind != "ring" else "ring"
    if item.kind != "ring" or item.value:
        base = f"{base} {item.value:+d}"
    name = " ".join(part for part in (prefix, base, suffix) if part)
    if item.rarity == "legendary" and item.appearance and item.kind != "ring":
        name = f"{item.appearance}, {name}"
    return name


def unidentified_name(item: Item) -> str:
    if item.kind == "ring":
        return f"{item.appearance} ring"
    return f"{item.subtype} {item.value:+d}"


def make_weapon(x: int, y: int, bonus: int, base: str | None = None) -> Item:
    """A plain weapon. The base type follows the bonus (dagger, sword, axe,
    warhammer) unless ``base`` is given."""
    spec = next(w for w in WEAPONS if w[0] == base) if base else WEAPONS[min(3, bonus - 1)]
    name, acc, crit, effect = spec
    return Item(x, y, "weapon", f"{name} +{bonus}", "/", S.WHITE, bonus, accuracy=acc, crit=crit, effect=effect,
                subtype=name)


def make_armor(x: int, y: int, bonus: int, base: str | None = None) -> Item:
    spec = next(a for a in ARMORS if a[0] == base) if base else ARMORS[min(3, bonus - 1)]
    name, eva = spec
    return Item(x, y, "armor", f"{name} +{bonus}", "[", S.BLUE, bonus, evasion=eva, subtype=name)


def make_launcher(x: int, y: int, name: str, bonus: int, rng_: int, acc: int) -> Item:
    return Item(x, y, "launcher", f"{name} +{bonus}", "}", S.BROWN, bonus, accuracy=acc, range=rng_,
                subtype=name)


def make_ring(x: int, y: int, depth: int, rng: random.Random, rarity: str | None = None) -> Item:
    gem, color = rng.choice(RING_GEMS)
    ring = Item(x, y, "ring", "ring", "=", color, 0, subtype="ring", appearance=gem,
                rarity=rarity or roll_rarity(depth, rng, minimum="magic"))
    add_affixes(ring, depth, rng)
    if ring.rarity == "legendary" and not ring.cursed:
        ring.appearance = gem  # rings keep their gem name
        ring.name = gear_name(ring)
    return ring


def make_ammo(x: int, y: int, count: int) -> Item:
    return Item(x, y, "ammo", f"{count} arrow{'s' if count != 1 else ''}", "(", (200, 170, 120), count)


def make_key(x: int, y: int) -> Item:
    return Item(x, y, "key", "iron key", "-", S.YELLOW, subtype="key")


def make_relic(x: int, y: int, name: str) -> Item:
    """A quest item: somebody's lost heirloom."""
    return Item(x, y, "quest", name, '"', (230, 200, 255), subtype="relic")


def make_gold(x: int, y: int, amount: int) -> Item:
    return Item(x, y, "gold", "gold", "$", S.YELLOW, amount)


def make_amulet(x: int, y: int) -> Item:
    return Item(x, y, "amulet", "Amulet of Yendor", "*", S.PURPLE)


def random_gear(x: int, y: int, depth: int, rng: random.Random, kind: str | None = None) -> Item:
    kind = kind or rng.choices(GEAR_KINDS, weights=[9, 8, 3, 4])[0]
    if kind == "ring":
        return make_ring(x, y, depth, rng)
    if kind == "weapon":
        item = make_weapon(x, y, rng.randint(1, 2) + depth // 2)
    elif kind == "armor":
        item = make_armor(x, y, rng.randint(1, 2) + depth // 2)
    else:
        tier = min(len(LAUNCHERS) - 1, rng.randint(0, 1) + depth // 3)
        name, bonus, rng_, acc = LAUNCHERS[tier]
        item = make_launcher(x, y, name, bonus, rng_, acc)
    item.rarity = roll_rarity(depth, rng)
    add_affixes(item, depth, rng)
    return item


def random_item(x: int, y: int, depth: int, rng: random.Random) -> Item:
    kinds = ["gold", "potion", "scroll", "food", "ammo", "gear", "book"]
    weights = [22, 18, 13, 12, 8, 26, 3 if depth >= 2 else 0]
    kind = rng.choices(kinds, weights=weights)[0]
    if kind == "gold":
        return make_gold(x, y, rng.randint(5, 15) * depth)
    if kind == "ammo":
        return make_ammo(x, y, rng.randint(4, 8))
    if kind == "gear":
        return random_gear(x, y, depth, rng)
    return make_consumable(x, y, kind, pick_consumable(kind, depth, rng))


def random_food(x: int, y: int, depth: int, rng: random.Random) -> Item:
    return make_food(x, y, pick_consumable("food", depth, rng))


# ============================================================ identification
class Identification:
    """What this game's potions and scrolls look like, and which are known.

    Appearances are shuffled per game, so "ruby potion" means something
    different every run and has to be learned.
    """

    def __init__(self, rng: random.Random) -> None:
        looks = POTION_APPEARANCES[:]
        rng.shuffle(looks)
        self.potion_looks: dict[str, tuple[str, Color]] = dict(zip(POTIONS, looks, strict=False))
        labels: set[str] = set()
        self.scroll_labels: dict[str, str] = {}
        for key in SCROLLS:
            while True:
                label = " ".join(
                    "".join(rng.choice(SCROLL_SYLLABLES) for _ in range(rng.randint(1, 2)))
                    for _ in range(rng.randint(1, 2))
                )
                if label not in labels:
                    break
            labels.add(label)
            self.scroll_labels[key] = label
        self.known: set[tuple[str, str]] = set()

    def is_known(self, item: Item) -> bool:
        if item.kind in ("potion", "scroll"):
            return (item.kind, item.subtype) in self.known
        if item.is_gear:
            return item.identified
        return True

    def learn(self, kind: str, subtype: str) -> bool:
        """Mark a potion/scroll type as known. Returns True if it was new."""
        if (kind, subtype) in self.known:
            return False
        self.known.add((kind, subtype))
        return True

    def identify(self, item: Item) -> None:
        if item.kind in ("potion", "scroll"):
            self.learn(item.kind, item.subtype)
        elif item.is_gear:
            item.identified = True

    def color(self, item: Item) -> Color:
        """Display colour: potions show their liquid; gear its rarity."""
        if item.kind == "potion":
            return self.potion_looks[item.subtype][1]
        if item.is_gear and item.kind != "ring":
            # Colour means rarity for gear - even common gear, so a blue
            # (magic) name is never confused with plain blue armor.
            return RARITIES[item.rarity].color
        if item.kind == "ring":
            return RARITIES[item.rarity].color
        return item.color

    def name(self, item: Item, with_count: bool = True) -> str:
        """The name as the player knows it, e.g. '2 ruby potions'."""
        n = item.count if with_count else 1
        plural = "s" if n != 1 else ""
        if item.kind == "potion":
            if self.is_known(item):
                base = f"potion{plural} of {POTIONS[item.subtype].name}"
            else:
                base = f"{self.potion_looks[item.subtype][0]} potion{plural}"
        elif item.kind == "scroll":
            if self.is_known(item):
                base = f"scroll{plural} of {SCROLLS[item.subtype].name}"
            else:
                base = f"scroll{plural} labelled {self.scroll_labels[item.subtype]}"
        elif item.kind == "food":
            base = item.name + ("s" if n != 1 and item.subtype != "bread" else "")
            if item.subtype == "bread" and n != 1:
                base = "loaves of bread"
        elif item.kind == "book":
            base = item.name if n == 1 else item.name.replace("tome", "tomes", 1)
        elif item.kind == "key":
            base = "iron key" if n == 1 else "iron keys"
        elif item.is_gear:
            return item.name if item.identified else f"{unidentified_name(item)} (unidentified)"
        else:
            return item.name
        return f"{n} {base}" if n != 1 else base
