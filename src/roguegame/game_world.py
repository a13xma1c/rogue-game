"""Interacting with the world: locked doors and keys, levers and
portcullises, secret doors, shrines, bookshelves, water - and quests.
Mixed into :class:`roguegame.game.Game`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import settings as S
from .dungeon import DIRS8
from .items import make_consumable, pick_consumable
from .tiles import (
    BOOKSHELF,
    BOOKSHELF_EMPTY,
    DOOR_CLOSED,
    DOOR_LOCKED,
    DOOR_OPEN,
    LEVER,
    LEVER_PULLED,
    PORTCULLIS,
    PORTCULLIS_OPEN,
    SECRET_DOOR,
    SHRINE,
    SHRINE_USED,
    WATER,
)

if TYPE_CHECKING:
    from .game import DialogueOption, Game

SECRET_SPOT_CHANCE = 0.15  # per turn, next to a secret door (x2.5 while searching)
BOOKSHELF_FIND_CHANCE = 0.6


class World:
    # -------------------------------------------------------------- tiles
    def _interact_world(self: Game, x: int, y: int, tile: int) -> bool | None:
        """Handle the newer interactive tiles. Returns True if it took a turn,
        False if it didn't, or None if the tile isn't one of these."""
        p = self.player
        if tile == DOOR_LOCKED:
            key = p.find("key")
            if key is None:
                self.say("The door is locked. You need a key.", S.GREY)
                return False
            p.take_one(key)
            self.map.tiles[y][x] = DOOR_OPEN
            self.say("You unlock the door with an iron key. The key stays in the lock.", S.YELLOW)
            return True
        if tile == PORTCULLIS:
            self.say("The portcullis won't budge. There must be a lever somewhere on this floor.", S.GREY)
            return False
        if tile in (LEVER, LEVER_PULLED):
            self._pull_lever(x, y)
            return True
        if tile == SHRINE:
            self._pray(x, y)
            return True
        if tile == BOOKSHELF:
            self.map.tiles[y][x] = BOOKSHELF_EMPTY
            if self.rng.random() < BOOKSHELF_FIND_CHANCE:
                kind = "book" if self.rng.random() < 0.25 and self.depth >= 2 else "scroll"
                found = make_consumable(0, 0, kind, pick_consumable(kind, self.depth, self.rng))
                name = self.item_name(found)
                if p.add_to_pack(found):
                    self.say(f"Tucked between the books you find {name}!", S.YELLOW)
                else:
                    found.x, found.y = self._free_item_spot((p.x, p.y))
                    found.seen = True
                    self.items.append(found)
                    self.say(f"You find {name}, but your pack is full - you set it down.", S.YELLOW)
            else:
                self.say("You leaf through mouldy books. Nothing useful.", S.GREY)
            return True
        return None

    def _pull_lever(self: Game, x: int, y: int) -> None:
        pulled = self.map.tiles[y][x] == LEVER
        self.map.tiles[y][x] = LEVER_PULLED if pulled else LEVER
        gates = self.map.find_tiles(PORTCULLIS if pulled else PORTCULLIS_OPEN)
        for gx, gy in gates:
            if not pulled and self.blocking_actor_at(gx, gy):
                continue  # don't drop a gate on someone's head
            self.map.tiles[gy][gx] = PORTCULLIS_OPEN if pulled else PORTCULLIS
        seen = any(self.visible(gx, gy) for gx, gy in gates)
        if not gates:
            self.say("You pull the lever. Nothing seems to happen.", S.GREY)
        elif pulled:
            self.say("You pull the lever. " + ("The portcullis rises!" if seen else
                                               "Somewhere, iron grinds against stone."), S.YELLOW)
        else:
            self.say("You push the lever back. " + ("The portcullis slams down." if seen else
                                                    "Something heavy crashes down in the distance."), S.GREY)
        self._update_fov()

    def _pray(self: Game, x: int, y: int) -> None:
        p = self.player
        self.map.tiles[y][x] = SHRINE_USED
        blessing = self.rng.choice(("mana", "regeneration", "haste", "shield", "cleanse"))
        if blessing == "mana":
            p.mana = p.max_mana
            self.say("You pray. Power floods your mind - your mana is restored.", S.BLUE)
        elif blessing == "regeneration":
            p.add_status("regenerating", 20, potency=2)
            self.say("You pray. A warm glow settles on you; your wounds begin to close.", (120, 255, 150))
        elif blessing == "haste":
            p.add_status("hasted", 12)
            self.say("You pray. Your feet feel light as air!", (120, 240, 255))
        elif blessing == "shield":
            p.add_status("shielded", 15)
            p.mana = max(p.mana, min(p.max_mana, 10))
            self.say("You pray. A shimmering ward surrounds you.", (150, 170, 255))
        else:
            for it in [*p.gear(), *p.pack]:
                it.cursed = False
            self.say("You pray. You feel cleansed of every curse.", S.CYAN)
        self.say("The shrine falls silent.", S.GREY)

    def _search_secrets(self: Game) -> None:
        """Chance to notice secret doors next to you (better when searching)."""
        p = self.player
        chance = SECRET_SPOT_CHANCE * (2.5 if self._searching else 1)
        if p.skill_bonus("trap_sense"):
            chance *= 2
        for dx, dy in DIRS8:
            x, y = p.x + dx, p.y + dy
            if self.map.tile(x, y) == SECRET_DOOR and self.rng.random() < chance:
                self.map.tiles[y][x] = DOOR_CLOSED
                self.say("You discover a secret door!", S.YELLOW)

    def _wade(self: Game, actor) -> None:
        """Stepping into water puts out flames."""
        if self.map.tile(actor.x, actor.y) == WATER and actor.has("burning"):
            actor.cure("burning")
            if actor is self.player:
                self.say("The water hisses as it puts out the flames.", S.BLUE)

    # ------------------------------------------------------------- quests
    def quest_for(self: Game, npc):
        for lvl in self.levels.values():
            if lvl.quest is not None and lvl.quest.giver is npc:
                return lvl.quest
        return None

    def _quest_options(self: Game, npc, opts: list[DialogueOption]) -> None:
        from .game import DialogueOption

        quest = self.quest_for(npc)
        if quest is None or quest.state == "rewarded":
            opts.append(DialogueOption("Ask for rumours", "rumour"))
            return
        if quest.state == "offered":
            opts.append(DialogueOption("Ask about the job", "quest_ask"))
            opts.append(DialogueOption(f"Accept: {quest.title}", "quest_accept"))
        elif quest.is_done(self.player):
            opts.append(DialogueOption("Report success", "quest_claim"))
        else:
            opts.append(DialogueOption("Ask about the job again", "quest_ask"))

    def _quest_choose(self: Game, action: str, npc) -> str | None:
        """Handle a quest dialogue action; returns the envoy's reply."""
        quest = self.quest_for(npc)
        if quest is None:
            return None
        p = self.player
        if action == "quest_ask":
            reward = self.item_name(quest.reward_item) if quest.reward_item else "my thanks"
            extra = f" ({quest.status(p)})" if quest.state == "active" else ""
            return f'"{quest.pitch} Pay is {quest.reward_gold} gold and a {reward}."{extra}'
        if action == "quest_accept":
            quest.state = "active"
            self.quests.append(quest)
            self.say(f"New quest: {quest.title}. (J: journal)", S.YELLOW)
            return '"Good. Come back to me when it is done."'
        if action == "quest_claim" and quest.is_done(p):
            quest.state = "rewarded"
            if quest.kind == "fetch" and quest.relic is not None:
                p.pack.remove(quest.relic)
            p.gold += quest.reward_gold
            self.say(f"Quest complete: {quest.title}! +{quest.reward_gold} gold, +{quest.reward_xp} xp.", S.YELLOW)
            if p.gain_xp(quest.reward_xp):
                self.say(f"You reach level {p.level}! You feel stronger.", S.YELLOW)
            item = quest.reward_item
            if item is not None:
                self.ident.identify(item)
                if not p.add_to_pack(item):
                    item.x, item.y = self._free_item_spot((p.x, p.y))
                    item.seen = True
                    self.items.append(item)
                self.say(f"{npc.name} hands you a {self.item_name(item)}.", self.item_color(item))
            return '"The Guild is in your debt."'
        return None

    def _quest_kill(self: Game, monster) -> None:
        for quest in self.quests:
            quest.note_kill(monster, self.depth)
            if quest.state == "active" and quest.kind == "slay" and quest.target is monster:
                self.say(f"You have slain {monster.title}! Return to {quest.giver.name} for your reward.",
                         S.YELLOW)
