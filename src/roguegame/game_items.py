"""Player item actions: the pack, equipment, consumables, identification and
hunger. Mixed into :class:`roguegame.game.Game`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import settings as S
from .entities import HUNGER_MAX, Item
from .items import AFFIXES, CONSUMABLES, FOODS, gear_name
from .status import CURED_BY_POTION, NEGATIVE

if TYPE_CHECKING:
    from .game import Game

SLOTS = {"weapon": "weapon", "armor": "armor", "launcher": "launcher", "ring": "ring"}
SLOT_NAMES = {"weapon": "wielded", "armor": "worn", "launcher": "readied", "ring": "worn"}
FAINT_CHANCE = 0.15
AGGRAVATION_ROUNDS = 40
HUNGER_MESSAGES = {
    "Hungry": ("You are getting hungry.", S.YELLOW),
    "Weak": ("You feel weak with hunger.", S.ORANGE),
    "Fainting": ("You are fainting from hunger!", S.RED),
    "Starving": ("You are starving!", S.RED),
}


class ItemActions:
    """Everything you can do with items. All methods that take game time
    return True if they did (and end the turn themselves)."""

    # ------------------------------------------------------------- naming
    def item_name(self: Game, item: Item, with_count: bool = True) -> str:
        if item.kind == "gold":
            return f"{item.value} gold"
        return self.ident.name(item, with_count)

    def item_color(self: Game, item: Item) -> tuple[int, int, int]:
        return self.ident.color(item)

    def unidentified_items(self: Game) -> list[Item]:
        p = self.player
        return [it for it in [*p.gear(), *p.pack] if not self.ident.is_known(it)]

    # -------------------------------------------------------------- use
    def use_item(self: Game, item: Item) -> bool:
        """The obvious action for ``item``: quaff, read, eat, or (un)equip."""
        if item.kind == "potion":
            return self.quaff(item)
        if item.kind == "scroll":
            return self.read(item)
        if item.kind == "food":
            return self.eat(item)
        if item.kind == "book":
            return self.study(item)
        if item.is_gear:
            return self.unequip(item.kind) if self.player.equipped(item) else self.equip(item)
        self.say("You can't use that.", S.GREY)
        return False

    def _owned(self: Game, item: Item) -> bool:
        return any(it is item for it in self.player.pack)

    # ------------------------------------------------------------ potions
    def quaff(self: Game, item: Item) -> bool:
        if not self._can_act() or not self._owned(item) or item.kind != "potion":
            return False
        p = self.player
        known = self.ident.is_known(item)
        if known and item.subtype == "healing" and p.hp >= p.max_hp and not any(p.has(s) for s in CURED_BY_POTION):
            self.say("You are already at full health.", S.GREY)
            return False
        p.take_one(item)
        self._potion_effect(item.subtype)
        self._learn(item)
        self._end_turn()
        return True

    def _potion_effect(self: Game, kind: str) -> None:
        p = self.player
        if kind == "healing":
            heal = 15 + self.depth * 3
            p.hp = min(p.max_hp, p.hp + heal)
            curable = [s for s in CURED_BY_POTION if p.has(s)]
            p.cure(*curable)
            cured = f" You are no longer {' or '.join(curable)}." if curable else ""
            self.say(f"You drink a potion and heal up to {heal} HP.{cured}", S.GREEN)
        elif kind == "greater healing":
            p.hp = p.max_hp
            p.cure(*NEGATIVE)
            self.say("Warmth floods through you. You are completely healed!", S.GREEN)
        elif kind == "mana":
            gain = min(p.max_mana - p.mana, 15 + self.depth * 2)
            p.mana += gain
            self.say(f"Your mind clears. (+{gain} mana)", S.BLUE)
        elif kind == "haste":
            p.add_status("hasted", 12)
            self.say("The world slows around you - you are hasted!", (120, 240, 255))
        elif kind == "regeneration":
            p.add_status("regenerating", 15, potency=2)
            self.say("Your wounds begin to knit.", (120, 255, 150))
        elif kind == "might":
            p.base_power += 1
            self.say("Raw strength surges through your limbs! (+1 ATK)", S.YELLOW)
        elif kind == "poison":
            self.say("Ugh - that tasted foul.", S.GREEN)
            self._inflict(p, "poisoned", 6, 2)
        elif kind == "blindness":
            self.say("A cloud seems to pass over your eyes.", S.GREY)
            self._inflict(p, "blinded", 8)
            self._update_fov()

    def _learn(self: Game, item: Item) -> None:
        if item.kind in ("potion", "scroll") and self.ident.learn(item.kind, item.subtype):
            spec = CONSUMABLES[item.kind][item.subtype]
            self.say(f"(That was a {item.kind} of {spec.name}.)", S.CYAN)

    # ------------------------------------------------------------ scrolls
    def read(self: Game, item: Item) -> bool:
        if not self._can_act() or not self._owned(item) or item.kind != "scroll":
            return False
        p = self.player
        if item.subtype == "fire" and self.ident.is_known(item):
            if not any(m.alive and self.visible(m.x, m.y) for m in self.monsters):
                self.say("No enemies in sight to burn.", S.GREY)
                return False
        if p.has("blinded"):
            self.say("You can't read while blinded!", S.GREY)
            return False
        p.take_one(item)
        self._learn(item)
        finished = self._scroll_effect(item.subtype)
        if finished:
            self._end_turn()
        return True

    def _scroll_effect(self: Game, kind: str) -> bool:
        """Apply a scroll. Returns False if it's waiting for the player to pick
        an item (scroll of identify); the turn ends once they do."""
        p = self.player
        if kind == "fire":
            targets = [m for m in self.monsters if m.alive and self.visible(m.x, m.y)]
            if not targets:
                self.say("The scroll bursts into flames, harmlessly.", S.ORANGE)
            else:
                self._fire_blast(targets)
        elif kind == "identify":
            pending = self.unidentified_items()
            if not pending:
                self.say("You feel very knowledgeable... but there is nothing to identify.", S.GREY)
            elif len(pending) == 1:
                self.identify_item(pending[0])
            else:
                self.pending = "identify"
                self.say("Identify which item?", S.CYAN)
                return False
        elif kind == "teleportation":
            dest = self._random_teleport_destination()
            if dest:
                p.x, p.y = dest
                self.say("You are whisked away!", S.PURPLE)
                self._pickup()
        elif kind == "magic mapping":
            self.map.reveal(find_secrets=True)
            self.say("A map of the floor forms in your mind.", S.CYAN)
        elif kind in ("enchant weapon", "enchant armor"):
            slot = "weapon" if kind == "enchant weapon" else "armor"
            target = getattr(p, slot)
            if target is None:
                self.say("Your skin tingles for a moment." if slot == "armor" else "Your hands twitch.", S.GREY)
            else:
                target.value += 1
                target.name = gear_name(target)
                self.say(f"Your {self.item_name(target)} glows blue for a moment.", S.BLUE)
        elif kind == "remove curse":
            cursed = [it for it in [*p.gear(), *p.pack] if it.cursed]
            for it in cursed:
                it.cursed = False
            self.say("You feel as if someone is watching over you." if cursed else
                     "You feel a brief sense of relief - nothing here was cursed.", S.CYAN)
        elif kind == "aggravation":
            for m in self.monsters:
                m.alert = True
                m.cooldowns["aggravated"] = AGGRAVATION_ROUNDS  # they hunt you from anywhere for a while
            self.say("A piercing shriek echoes through the dungeon!", S.RED)
        return True

    def _fire_blast(self: Game, targets: list) -> None:
        dmg = 8 + self.depth * 3
        self.say("The scroll erupts in flames!", S.ORANGE)
        for m in targets:
            self.say(f"The {m.name} burns for {dmg}.", S.ORANGE)
            self._damage(m, dmg, "fire")
            if m.alive:
                m.add_status("burning", 3, 2)

    def identify_item(self: Game, item: Item) -> None:
        before = self.item_name(item)
        self.ident.identify(item)
        self.say(f"You identify the {before}: {self.item_name(item)}.", S.CYAN)
        if item.cursed:
            self.say("It is cursed!", S.RED)

    def choose_item(self: Game, item: Item) -> bool:
        """Answer a pending item prompt (scroll of identify)."""
        if self.pending != "identify" or item not in self.unidentified_items():
            return False
        self.pending = None
        self.identify_item(item)
        self._end_turn()
        return True

    def cancel_pending(self: Game) -> None:
        if self.pending:
            self.pending = None
            self.say("You lose your train of thought. The scroll's magic is wasted.", S.GREY)
            self._end_turn()

    # --------------------------------------------------------------- food
    def eat(self: Game, item: Item) -> bool:
        if not self._can_act() or not self._owned(item) or item.kind != "food":
            return False
        p = self.player
        if p.satiation > HUNGER_MAX - 200:
            self.say("You're too full to eat another bite.", S.GREY)
            return False
        p.take_one(item)
        before = p.hunger_state
        p.satiation = min(HUNGER_MAX, p.satiation + FOODS[item.subtype].nutrition)
        self._hunger_warned = p.hunger_state
        flavour = {"apple": "Crunchy!", "bread": "Filling.", "ration": "That hit the spot."}[item.subtype]
        done = " You are no longer hungry." if before and not p.hunger_state else ""
        self.say(f"You eat the {item.subtype}. {flavour}{done}", (200, 160, 90))
        self._end_turn()
        return True

    def _tick_hunger(self: Game) -> None:
        p = self.player
        self._hunger_acc += p.hunger_rate * self.rules.hunger
        while self._hunger_acc >= 1:
            self._hunger_acc -= 1
            p.satiation = max(0, p.satiation - 1)
        state = p.hunger_state
        if state != self._hunger_warned:
            self._hunger_warned = state
            if state in HUNGER_MESSAGES:
                self.say(*HUNGER_MESSAGES[state])
        if state == "Starving":
            self._damage(p, 1, "starvation")

    def _maybe_faint(self: Game) -> int:
        """Fainting from hunger costs extra rounds. Returns how many."""
        if self.player.hunger_state == "Fainting" and self.rng.random() < FAINT_CHANCE:
            self.say("You faint from lack of food.", S.RED)
            return 2
        return 0

    # ------------------------------------------------------------- books
    def study(self: Game, item: Item) -> bool:
        if not self._can_act() or not self._owned(item) or item.kind != "book":
            return False
        from .spells import SPELLS

        p = self.player
        key = item.subtype
        if p.spells.get(key, 0) >= 1:
            self.say(f"You already know {SPELLS[key].name}.", S.GREY)
            return False
        p.take_one(item)
        p.book_spells[key] = 1
        self.say(f"You study the tome and learn {SPELLS[key].name}! (Z to cast)", S.PURPLE)
        self._end_turn()
        return True

    # --------------------------------------------------------- equipment
    def equip(self: Game, item: Item) -> bool:
        if not self._can_act() or not self._owned(item) or not item.is_gear:
            return False
        p = self.player
        slot = SLOTS[item.kind]
        current = getattr(p, slot)
        if current is not None and current.cursed:
            self.say(f"Your {self.item_name(current)} is cursed - you can't take it off!", S.RED)
            return False
        p.pack.remove(item)
        if current is not None:
            p.pack.append(current)
        setattr(p, slot, item)
        if not item.identified:
            item.identified = True
            self.say(f"As you {'wield' if slot == 'weapon' else 'don'} it, you learn it is a "
                     f"{self.item_name(item)}.", S.CYAN)
        else:
            self.say(f"You {'wield' if slot == 'weapon' else 'ready' if slot == 'launcher' else 'put on'} "
                     f"the {self.item_name(item)}.", S.WHITE)
        if item.cursed:
            self.say("It's cursed! It binds itself to you.", S.RED)
        self._clamp_pools()
        self._end_turn()
        return True

    def unequip(self: Game, slot: str) -> bool:
        if not self._can_act():
            return False
        p = self.player
        item = getattr(p, slot, None)
        if item is None:
            return False
        if item.cursed:
            self.say(f"Your {self.item_name(item)} is cursed - you can't take it off!", S.RED)
            return False
        if len(p.pack) >= 20:
            self.say("Your pack is too full.", S.GREY)
            return False
        setattr(p, slot, None)
        p.pack.append(item)
        self.say(f"You take off the {self.item_name(item)}.", S.WHITE)
        self._clamp_pools()
        self._end_turn()
        return True

    def _clamp_pools(self: Game) -> None:
        p = self.player
        p.hp = min(p.hp, p.max_hp)
        p.mana = min(p.mana, p.max_mana)

    def drop(self: Game, item: Item) -> bool:
        if not self._can_act():
            return False
        p = self.player
        if p.equipped(item):
            if item.cursed:
                self.say(f"Your {self.item_name(item)} is cursed - you can't let go of it!", S.RED)
                return False
            setattr(p, SLOTS[item.kind], None)
        elif self._owned(item):
            p.pack.remove(item)
        else:
            return False
        spot = self._free_item_spot((p.x, p.y))
        item.x, item.y = spot
        item.seen = True
        self.items.append(item)
        self._clamp_pools()
        self.say(f"You drop the {self.item_name(item)}.", S.GREY)
        self._end_turn()
        return True

    # ------------------------------------------------------------ pickup
    def _pickup(self: Game) -> None:
        p = self.player
        it = self.item_at(p.x, p.y)
        if not it:
            return
        if it.kind == "gold":
            p.gold += it.value
            self.say(f"You pick up {it.value} gold.", S.YELLOW)
        elif it.kind == "ammo":
            p.arrows += it.value
            self.say(f"You pick up {it.name}.", it.color)
        elif it.kind == "amulet":
            from .game import State

            p.has_amulet = True
            self.state = State.WON
            self.say("You grasp the Amulet of Yendor. You win!", S.PURPLE)
        else:
            name = self.item_name(it)
            if not p.add_to_pack(it):
                self.say(f"Your pack is full - you leave the {name} where it lies.", S.GREY)
                return
            hint = ""
            if it.kind == "quest":
                hint = " Someone will want this back - return it to the guild envoy."
            if it.is_gear and self.ident.is_known(it):
                current = getattr(p, SLOTS[it.kind])
                if current is None or it.value > current.value:
                    hint = " (an upgrade? I to equip)"
            self.say(f"You pick up {'the ' if it.count == 1 else ''}{name}.{hint}", self.item_color(it))
        self.items.remove(it)

    # --------------------------------------------------- on-hit gear effects
    def _gear_on_hit(self: Game, target, damage: int, ranged: bool) -> None:
        """Affixes on the weapon (melee) or bow (ranged) that trigger on a hit."""
        p = self.player
        source = p.launcher if ranged else p.weapon
        if source is None:
            return
        for key, value in source.affixes:
            stat = AFFIXES[key].stat
            if stat == "lifesteal":
                healed = min(p.max_hp - p.hp, max(1, damage * value // 100))
                if healed > 0:
                    p.hp += healed
                    self._popup(p, f"+{healed}", S.GREEN)
            elif target.alive and stat in ("burn", "poison", "slow") and self.rng.random() < value / 100:
                status, turns, potency = {"burn": ("burning", 3, 2), "poison": ("poisoned", 4, 1),
                                          "slow": ("slowed", 3, 1)}[stat]
                self._inflict(target, status, turns, potency)
