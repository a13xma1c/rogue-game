"""Core game logic and state.

Everything here is independent of pygame so it can be driven directly by the
tests.

Time advances in *rounds*. Each player action normally costs one round
(two while slowed; a stunned player loses rounds until the stun wears off).
In a round, the player's statuses tick, then every awake monster gains
energy according to its speed and acts once per 100 energy, then the
monsters' statuses tick.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

from . import ai
from . import combat
from . import settings as S
from .combat import CRIT_STUN_TURNS, AttackResult, distance, first_blocker, line_of_fire
from .dungeon import DIRS8, DungeonMap, Pos, compass
from .entities import (
    MIMIC,
    NPC,
    RUMOURS,
    Actor,
    Fx,
    Item,
    Monster,
    Player,
    make_ammo,
    random_item,
    random_monster,  # noqa: F401  (kept for API compatibility)
    with_article,
)
from .difficulty import Difficulty, GameOptions
from .game_items import ItemActions
from .game_magic import Magic
from .game_world import World
from .items import Identification, make_food, make_potion, make_scroll
from .level import Level, build_level, level_rng
from .status import NEGATIVE, STATUS_SPECS
from .tiles import (
    TILES,
    CHEST,
    CHEST_OPEN,
    DOOR_CLOSED,
    DOOR_OPEN,
    FLOOR,
    FOUNTAIN,
    FOUNTAIN_DRY,
    STAIRS_DOWN,
    STAIRS_UP,
    TRAP_KINDS,
)

# Chance per turn to notice a hidden trap next to you (higher while waiting).
TRAP_SPOT_CHANCE = 0.25
TRAP_SEARCH_CHANCE = 0.6
BLIND_FOV_RADIUS = 2
STUN_IMMUNITY_ROUNDS = 2  # after a stun wears off, new stuns are ignored this long
# Chance a fired arrow can be picked up again.
ARROW_RECOVERY_HIT = 0.35
ARROW_RECOVERY_MISS = 0.6
ARROW_BUNDLE = 8

PROJECTILE_COLORS = {
    "arrow": (225, 205, 160),
    "bolt": (120, 230, 200),
    "hex": S.PURPLE,
    "fire": S.ORANGE,
}

STATUS_MESSAGES = {
    # status: (message when you get it, message when it wears off)
    "poisoned": ("You are poisoned!", "The poison wears off."),
    "burning": ("You catch fire!", "The flames die down."),
    "slowed": ("Your limbs grow heavy - you are slowed!", "You can move freely again."),
    "stunned": ("You are stunned!", "Your head clears."),
    "blinded": ("You are blinded!", "Your sight returns."),
    "hasted": ("You speed up!", "You slow back down to normal speed."),
    "regenerating": ("Your wounds begin to knit.", "Your rapid healing fades."),
    "shielded": ("A mana shield surrounds you.", "Your mana shield fades."),
}


class State(Enum):
    PLAYING = auto()
    DEAD = auto()
    WON = auto()


@dataclass
class DialogueOption:
    label: str
    action: str
    enabled: bool = True


@dataclass
class Dialogue:
    npc: NPC
    text: str
    options: list[DialogueOption] = field(default_factory=list)


@dataclass
class ShotPlan:
    """What would happen if the player fired at a tile (used by the UI preview
    and by ``Game.shoot``)."""

    ok: bool
    reason: str = ""  # why the shot can't be taken
    path: list[Pos] = field(default_factory=list)  # tiles the arrow flies over, up to impact
    target: Monster | None = None
    hit: float = 0.0
    crit: float = 0.0
    damage: tuple[int, int] = (0, 0)
    dist: int = 0
    area: list[Pos] = field(default_factory=list)  # tiles a blast would hit


# ----------------------------------------------------------------- prices
def potion_price(depth: int) -> int:
    return 15 + 5 * depth


def scroll_price(depth: int) -> int:
    return 20 + 5 * depth


def healing_price(depth: int) -> int:
    return 10 + 5 * depth


def arrow_price(depth: int) -> int:
    return 10 + 2 * depth


def ration_price(depth: int) -> int:
    return 12 + 2 * depth


def identify_price(depth: int) -> int:
    return 25 + 5 * depth


def uncurse_price(depth: int) -> int:
    return 30 + 5 * depth


class Game(ItemActions, Magic, World):
    def __init__(
        self, seed: int | None = None, options: GameOptions | None = None, first_level: Level | None = None
    ) -> None:
        """A new game. ``first_level`` replaces the generated floor 1 (for
        hand-made scenarios and tests); everything deeper is generated."""
        if seed is None:
            seed = random.SystemRandom().randrange(2**32)
        self.seed = seed
        self.options = options or GameOptions()
        # The last floor (home of the Amulet); None in endless mode.
        self.max_depth: int | None = None if self.options.endless else S.MAX_DEPTH
        self.rng = random.Random(seed)  # combat & other turn-by-turn randomness
        self.state = State.PLAYING
        self.depth = 1
        self.log: list[tuple[str, tuple[int, int, int]]] = []
        self.fx: list[Fx] = []  # cosmetic events for the UI; drained by the front-end
        self.turns = 0
        # Bumped whenever something that could be drawn may have changed, so
        # the front-end can redraw only when needed (see ``touch``).
        self.revision = 0
        self.player = Player(0, 0, self.options.player_class)
        p = self.player
        p.max_hp = p.hp = self.rules.player_hp + p.cls.hp
        p.potions = self.rules.start_potions
        if p.launcher:
            p.arrows = self.rules.start_arrows + p.cls.arrows
        # This run's potion colours and scroll labels; you know what you start with.
        self.ident = Identification(random.Random(f"ident:{seed}"))
        for it in p.pack:
            self.ident.identify(it)
        self.ident.learn("potion", "healing")
        self.pending: str | None = None  # an item prompt waiting for an answer ("identify")
        self.quests: list = []  # accepted quests (see quests.py)
        self._hunger_acc = 0.0
        self._hunger_warned = ""
        self._haste_phase = 0
        self.levels: dict[int, Level] = {}
        self.dialogue: Dialogue | None = None
        self.death_cause = ""
        self._searching = False
        if first_level is not None:
            self.levels[1] = first_level
        self._enter_level(1, "start")
        if self.options.endless:
            self.say("Endless mode: there is no bottom. Descend as deep as you dare!", S.CYAN)
        else:
            self.say(f"You enter the dungeon. Find the Amulet on floor {S.MAX_DEPTH}!", S.CYAN)

    @property
    def rules(self) -> Difficulty:
        return self.options.rules

    @property
    def endless(self) -> bool:
        return self.options.endless

    @property
    def deepest(self) -> int:
        """The deepest floor reached so far."""
        return max(self.levels)

    @property
    def score(self) -> int:
        """Run score: depth is worth the most, then kills, level and gold;
        a classic victory adds a bonus. Scaled by difficulty."""
        p = self.player
        raw = (self.deepest - 1) * 250 + p.kills * 10 + p.level * 25 + p.gold
        if self.state is State.WON:
            raw += 2000
        return round(raw * self.rules.score_mult)

    # ------------------------------------------------------ current level
    @property
    def level(self) -> Level:
        return self.levels[self.depth]

    @property
    def map(self) -> DungeonMap:
        return self.level.map

    @property
    def monsters(self) -> list[Monster]:
        return self.level.monsters

    @property
    def items(self) -> list[Item]:
        return self.level.items

    @property
    def npcs(self) -> list[NPC]:
        return self.level.npcs

    # ------------------------------------------------------------------ log
    def touch(self) -> None:
        """Note that the game's visible state changed (the UI will redraw)."""
        self.revision += 1

    def say(self, text: str, color: tuple[int, int, int] = S.WHITE) -> None:
        self.log.append((text, color))
        del self.log[:-50]
        self.revision += 1

    def _fx(self, fx: Fx) -> None:
        self.fx.append(fx)
        del self.fx[:-64]

    def _popup(self, actor: Actor, text: str, color: tuple[int, int, int]) -> None:
        self._fx(Fx("text", [(actor.x, actor.y)], text, color))

    # ----------------------------------------------------- level handling
    def _enter_level(self, depth: int, via: str) -> bool:
        """Move the player to ``depth``. ``via`` is "start", "down" (arrived by
        going down a staircase) or "up". Returns True if the floor is new."""
        self.touch()
        first_visit = depth not in self.levels
        if first_visit:
            self.levels[depth] = build_level(
                depth, level_rng(self.seed, depth), max_depth=self.max_depth, difficulty=self.rules
            )
        self.depth = depth
        lvl = self.level
        if via == "up" and lvl.down_stairs:
            pos = lvl.down_stairs
        elif via == "down" and lvl.up_stairs:
            pos = lvl.up_stairs
        else:
            pos = lvl.start
        self._make_room_at(pos)
        self.player.x, self.player.y = pos
        self._update_fov()
        return first_visit

    def _make_room_at(self, pos: Pos) -> None:
        """Shove any monster standing on ``pos`` to the nearest free tile."""
        m = self.monster_at(*pos)
        if not m:
            return
        dest = self._nearest_free(pos)
        if dest:
            m.x, m.y = dest

    def _nearest_free(self, origin: Pos, max_dist: int | None = None) -> Pos | None:
        seen = {origin}
        queue = deque([origin])
        while queue:
            cur = queue.popleft()
            for dx, dy in DIRS8:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt in seen or not self.map.walkable(*nxt):
                    continue
                if max_dist is not None and distance(nxt, origin) > max_dist:
                    continue
                seen.add(nxt)
                if not self.blocking_actor_at(*nxt):
                    return nxt
                queue.append(nxt)
        return None

    @property
    def fov_radius(self) -> int:
        if self.player.has("blinded"):
            return BLIND_FOV_RADIUS
        return S.FOV_RADIUS + self.player.sight_bonus

    def _update_fov(self) -> None:
        self.map.compute_fov(self.player.x, self.player.y, self.fov_radius)
        for it in self.items:
            if self.map.visible[it.y][it.x]:
                it.seen = True

    # --------------------------------------------------------------- queries
    def monster_at(self, x: int, y: int) -> Monster | None:
        for m in self.monsters:
            if m.x == x and m.y == y and m.alive:
                return m
        return None

    def npc_at(self, x: int, y: int) -> NPC | None:
        for n in self.npcs:
            if n.x == x and n.y == y:
                return n
        return None

    def blocking_actor_at(self, x: int, y: int) -> Actor | None:
        if (x, y) == (self.player.x, self.player.y):
            return self.player
        return self.monster_at(x, y) or self.npc_at(x, y)

    def item_at(self, x: int, y: int) -> Item | None:
        for it in self.items:
            if it.x == x and it.y == y:
                return it
        return None

    def visible(self, x: int, y: int) -> bool:
        return self.map.visible[y][x]

    def blocked_for(self, m: Monster) -> set[Pos]:
        """Tiles a monster's path finding should route around."""
        blocked = {(o.x, o.y) for o in self.monsters if o is not m}
        blocked.update((n.x, n.y) for n in self.npcs)
        return blocked

    def _occupied(self, *exclude: Actor) -> set[Pos]:
        actors: list[Actor] = [self.player, *self.monsters, *self.npcs]
        return {(a.x, a.y) for a in actors if a not in exclude and a.alive}

    def clear_shot(self, src: Actor, dst: Actor) -> bool:
        """Can ``src`` fire at ``dst`` without terrain or anyone else in the way?"""
        path = line_of_fire(self.map, (src.x, src.y), (dst.x, dst.y))
        _, reason = first_blocker(self.map, path, self._occupied(src, dst))
        return reason == "clear"

    def living_summons(self, summoner: Monster) -> int:
        return sum(1 for m in self.monsters if m.summoned_by is summoner and m.alive)

    def _can_act(self) -> bool:
        return self.state is State.PLAYING and self.dialogue is None and self.pending is None

    # ---------------------------------------------------------- player turns
    def player_move(self, dx: int, dy: int) -> None:
        if not self._can_act():
            return
        p = self.player
        nx, ny = p.x + dx, p.y + dy
        target = self.monster_at(nx, ny)
        if target:
            self.melee(p, target)
        elif npc := self.npc_at(nx, ny):
            self.talk(npc)
            return  # talking is free
        elif TILES[self.map.tile(nx, ny)].interactive:
            if not self._interact(nx, ny):
                return
        elif self.map.walkable(nx, ny):
            p.x, p.y = nx, ny
            self._on_enter_tile()
        else:
            return  # bumping a wall takes no time
        self._end_turn()

    def wait(self) -> None:
        """Pass a turn, searching carefully for hidden traps nearby."""
        if self._can_act():
            self._searching = True
            self._end_turn()

    def use_stairs(self) -> None:
        if not self._can_act():
            return
        tile = self.map.tile(self.player.x, self.player.y)
        if tile == STAIRS_DOWN:
            self.descend()
        elif tile == STAIRS_UP:
            self.ascend()
        else:
            self.say("There are no stairs here.", S.GREY)

    def descend(self) -> None:
        if not self._can_act():
            return
        p = self.player
        if self.map.tile(p.x, p.y) != STAIRS_DOWN:
            self.say("There are no stairs down here.", S.GREY)
            return
        if self.level.sealed:
            boss = self.level.boss
            assert boss is not None
            self.say(f"A seal of dark magic bars the stairs. Defeat the {boss.name} first!", S.PURPLE)
            return
        first = self._enter_level(self.depth + 1, "down")
        if first:
            # Only the first arrival on a floor is restful; no stair-scumming.
            p.hp = min(p.max_hp, p.hp + int(p.max_hp * self.rules.rest_fraction))
            flavour = "Rough cavern walls surround you." if self.level.style == "caves" else ""
            self.say(f"You descend to floor {self.depth}. {flavour}".strip(), S.CYAN)
            if self.level.boss:
                self.say("A chill runs down your spine. Something powerful rules this floor.", S.PURPLE)
        else:
            self.say(f"You return to floor {self.depth}.", S.CYAN)

    def ascend(self) -> None:
        if not self._can_act():
            return
        p = self.player
        if self.map.tile(p.x, p.y) != STAIRS_UP:
            self.say("There are no stairs up here.", S.GREY)
            return
        self._enter_level(self.depth - 1, "up")
        self.say(f"You climb back up to floor {self.depth}.", S.CYAN)

    def use_potion(self) -> bool:
        """Drink a potion of healing (shorthand used by tests and quick keys)."""
        if not self._can_act():
            return False
        potion = self.player.find("potion", "healing")
        if potion is None:
            self.say("You have no potions of healing.", S.GREY)
            return False
        return self.quaff(potion)

    def use_scroll(self) -> bool:
        """Read a scroll of fire (shorthand used by tests)."""
        if not self._can_act():
            return False
        scroll = self.player.find("scroll", "fire")
        if scroll is None:
            self.say("You have no scrolls of fire.", S.GREY)
            return False
        return self.read(scroll)

    # ---------------------------------------------------------------- ranged
    def plan_shot(
        self, x: int, y: int, acc_bonus: int = 0, crit_bonus: int = 0, dmg_mult: float = 1.0,
        on_hit: tuple[str, int, int] | None = None,
    ) -> ShotPlan:
        """Work out a shot at (x, y) without taking it. The optional modifiers
        come from bow abilities (Aimed Shot, Poison Arrow)."""
        p = self.player
        if not p.launcher:
            return ShotPlan(False, "You have nothing to shoot with.")
        if p.arrows <= 0:
            return ShotPlan(False, "You are out of arrows.")
        if (x, y) == (p.x, p.y):
            return ShotPlan(False, "You can't shoot yourself.")
        if not self.map.in_bounds(x, y) or not self.map.visible[y][x]:
            return ShotPlan(False, "You can't see that spot.")
        dist = distance((p.x, p.y), (x, y))
        if dist > p.shot_range:
            return ShotPlan(False, f"Out of range ({dist} > {p.shot_range}).", dist=dist)
        path = line_of_fire(self.map, (p.x, p.y), (x, y))
        idx, reason = first_blocker(self.map, path, self._occupied(p))
        if reason == "wall":
            return ShotPlan(False, "You don't have a clear shot.", path=path[: idx + 1], dist=dist)
        if reason == "actor":
            bx, by = path[idx]
            npc = self.npc_at(bx, by)
            if npc:
                return ShotPlan(False, f"{npc.name} is in the way!", path=path[: idx + 1], dist=dist)
            target = self.monster_at(bx, by)
            assert target is not None
            d = distance((p.x, p.y), (bx, by))
            lo, hi = combat.damage_range(p, target, ranged=True)
            return ShotPlan(
                True, path=path[: idx + 1], target=target, dist=d,
                hit=combat.hit_chance(p, target, ranged=True, dist=d, bonus=acc_bonus),
                crit=combat.crit_chance(p, ranged=True, bonus=crit_bonus),
                damage=(max(1, round(lo * dmg_mult)), max(1, round(hi * dmg_mult))),
            )
        return ShotPlan(True, path=path, dist=dist)

    def shoot(self, x: int, y: int) -> bool:
        """Fire an arrow at (x, y). Returns True if a shot was taken."""
        if not self._can_act():
            return False
        if not self.fire_arrow(x, y):
            return False
        self._end_turn()
        return True

    def fire_arrow(
        self, x: int, y: int, acc_bonus: int = 0, crit_bonus: int = 0, dmg_mult: float = 1.0,
        on_hit: tuple[str, int, int] | None = None,
    ) -> bool:
        """Loose one arrow (no turn passes by itself). Returns True if fired."""
        plan = self.plan_shot(x, y)
        if not plan.ok:
            self.say(plan.reason, S.GREY)
            return False
        p = self.player
        p.arrows -= 1
        self._fx(Fx("shot", plan.path, color=PROJECTILE_COLORS["arrow"]))
        landing = plan.path[-1]
        recovery = ARROW_RECOVERY_MISS
        if plan.target:
            res = combat.resolve_attack(p, plan.target, self.rng, ranged=True, dist=plan.dist,
                                        acc_bonus=acc_bonus, crit_bonus=crit_bonus, dmg_mult=dmg_mult)
            self._report(p, plan.target, res, ranged=True)
            if res.hit:
                recovery = ARROW_RECOVERY_HIT
                self._damage(plan.target, res.damage, p)
                self._gear_on_hit(plan.target, res.damage, ranged=True)
                if on_hit and plan.target.alive:
                    self._inflict(plan.target, on_hit[0], on_hit[1], on_hit[2])
        else:
            self.say("Your arrow clatters to the floor.", S.GREY)
        if self.rng.random() < recovery:
            self._drop_arrow(landing)
        return True

    def _drop_arrow(self, pos: Pos) -> None:
        if not self.map.walkable(*pos):
            return
        existing = self.item_at(*pos)
        if existing is None:
            arrow = make_ammo(pos[0], pos[1], 1)
            arrow.seen = self.visible(*pos)
            self.items.append(arrow)
        elif existing.kind == "ammo":
            existing.value += 1
            existing.name = f"{existing.value} arrows"

    # ---------------------------------------------------------- attacking
    def melee(self, attacker: Actor, target: Actor, acc_bonus: int = 0, dmg_mult: float = 1.0) -> AttackResult:
        res = combat.resolve_attack(attacker, target, self.rng, acc_bonus=acc_bonus, dmg_mult=dmg_mult)
        self._report(attacker, target, res, ranged=False)
        if res.hit:
            self._damage(target, res.damage, attacker)
            if attacker is self.player:
                self._gear_on_hit(target, res.damage, ranged=False)
            if target.alive:
                self._on_hit_effects(attacker, target, res)
        return res

    def _attack(self, attacker: Actor, target: Actor) -> None:  # backwards-compatible name
        self.melee(attacker, target)

    def ranged_attack(
        self,
        attacker: Monster,
        target: Actor,
        on_hit: tuple[str, int, float] | None = None,
        projectile: str = "arrow",
        damage: bool = True,
    ) -> AttackResult | None:
        """A monster's shot or spell at ``target``. Returns None if something
        got in the way."""
        path = line_of_fire(self.map, (attacker.x, attacker.y), (target.x, target.y))
        idx, reason = first_blocker(self.map, path, self._occupied(attacker))
        shown = path[: idx + 1] if reason != "wall" else path[:idx]
        self._fx(Fx("shot", shown, color=PROJECTILE_COLORS.get(projectile, S.WHITE)))
        victim = self.blocking_actor_at(*path[idx]) if reason == "actor" else None
        if victim is not target:
            return None
        dist = distance((attacker.x, attacker.y), (target.x, target.y))
        res = combat.resolve_attack(attacker, target, self.rng, ranged=True, dist=dist)
        self._report(attacker, target, res, ranged=True, projectile=projectile, damaging=damage)
        if res.hit:
            if damage:
                self._damage(target, res.damage, attacker)
            if on_hit and target.alive and self.rng.random() < on_hit[2]:
                self._inflict(target, on_hit[0], on_hit[1])
        return res

    def _on_hit_effects(self, attacker: Actor, target: Actor, res: AttackResult) -> None:
        if isinstance(attacker, Monster) and attacker.kind.on_hit:
            status, turns, chance = attacker.kind.on_hit
            if self.rng.random() < chance:
                self._inflict(target, status, turns)
        if res.crit and attacker.stun_on_crit:
            self._inflict(target, "stunned", CRIT_STUN_TURNS)

    def _inflict(self, target: Actor, status: str, turns: int, potency: int = 1) -> None:
        if not target.add_status(status, turns, potency):
            if status in target.immune and target is not self.player and self.visible(target.x, target.y):
                self.say(f"The {target.name} is unaffected.", S.GREY)
            return
        self._popup(target, status, STATUS_SPECS[status].color)
        if target is self.player:
            self.say(STATUS_MESSAGES[status][0], STATUS_SPECS[status].color)
        elif self.visible(target.x, target.y):
            self.say(f"The {target.name} is {status}!", STATUS_SPECS[status].color)

    def _report(
        self, attacker: Actor, target: Actor, res: AttackResult, ranged: bool,
        projectile: str = "arrow", damaging: bool = True,
    ) -> None:
        you_attack = attacker is self.player
        you_defend = target is self.player
        a = "You" if you_attack else f"The {attacker.name}"
        what = {"arrow": "arrow", "bolt": "bolt", "hex": "spell", "fire": "fire bolt"}[projectile]
        if res.outcome == "miss":
            self._popup(target, "miss", S.GREY)
            if you_attack:
                self.say(f"Your arrow misses the {target.name}." if ranged else f"You miss the {target.name}.",
                         S.GREY)
            elif you_defend:
                self.say(f"The {attacker.name}'s {what} misses you." if ranged else f"{a} misses you.", S.GREY)
            return
        if res.outcome == "dodge":
            self._popup(target, "dodge", S.CYAN)
            if you_attack:
                self.say(f"The {target.name} dodges your {'arrow' if ranged else 'attack'}.", S.GREY)
            elif you_defend:
                self.say(f"You dodge the {attacker.name}'s {what if ranged else 'attack'}.", S.CYAN)
            return
        if not damaging:
            return
        crit = res.outcome == "crit"
        popup_color = S.YELLOW if crit else (S.RED if you_defend else S.WHITE)
        self._popup(target, f"{res.damage}{'!' if crit else ''}", popup_color)
        if you_attack:
            verb = "Your arrow hits" if ranged else "You hit"
            prefix = "Critical hit! " if crit else ""
            self.say(f"{prefix}{verb} the {target.name} for {res.damage}.", S.YELLOW if crit else S.WHITE)
        elif you_defend:
            hit = f"The {attacker.name}'s {what} hits you" if ranged else f"The {attacker.name} hits you"
            if crit:
                self.say(f"{hit} with a crushing blow! {res.damage} damage.", S.RED)
            else:
                self.say(f"{hit} for {res.damage}.", S.RED)

    def _damage(self, target: Actor, amount: int, source: Actor | str) -> None:
        p = self.player
        if target is p and p.has("shielded") and p.mana > 0:
            absorbed = min(amount, p.mana)
            p.mana -= absorbed
            amount -= absorbed
            self._popup(p, f"({absorbed})", (150, 170, 255))
            if p.mana <= 0:
                p.cure("shielded")
                self.say("Your mana shield shatters!", (150, 170, 255))
            if amount <= 0:
                return
        target.hp -= amount
        if isinstance(target, Monster):
            target.alert = True  # getting hurt wakes anyone up - even a patient ambusher
        if target.alive:
            return
        if target is self.player:
            if isinstance(source, str):
                cause = {"poisoned": "succumbed to poison", "burning": "burned to death",
                         "fire": "burned to death", "starvation": "starved to death"}.get(source, f"killed by {source}")
            else:
                cause = f"killed by {with_article(source.name)}"
            self._player_died(cause)
        elif isinstance(target, Monster):
            self._kill(target)

    # ------------------------------------------------------ monster actions
    def try_move(self, m: Monster, nx: int, ny: int) -> None:
        if self.blocking_actor_at(nx, ny):
            return
        if self.map.tile(nx, ny) == DOOR_CLOSED:
            # Opening a door costs the monster its move.
            self.map.tiles[ny][nx] = DOOR_OPEN
            if self.visible(nx, ny):
                self.say(f"The {m.name} opens a door.", S.GREY)
                self._update_fov()
            return
        if not self.map.walkable(nx, ny):
            return
        m.x, m.y = nx, ny
        self._wade(m)

    _try_move = try_move  # backwards-compatible name

    def summon(self, summoner: Monster, kind: str) -> Monster | None:
        spot = self._nearest_free((summoner.x, summoner.y), max_dist=3)
        if spot is None:
            return None
        minion = self.options.prepare(Monster(spot[0], spot[1], kind, self.depth), self.depth)
        minion.alert = True
        minion.summoned_by = summoner
        self.monsters.append(minion)
        self._popup(minion, "!", S.ORANGE)
        return minion

    def blink(self, m: Monster) -> bool:
        """Teleport ``m`` a safe distance from the player, within reach of
        where it stands. Returns False if there's nowhere to go."""
        p = self.player
        reach = self.map.distance_map((m.x, m.y))
        spots = [
            pos for pos, d in reach.items()
            if d <= 12 and 4 <= distance(pos, (p.x, p.y)) <= 7
            and self.map.tile(*pos) == FLOOR and not self.blocking_actor_at(*pos)
        ]
        if not spots:
            return False
        occupied = self._occupied(m, p)

        def has_shot(pos: Pos) -> bool:
            return first_blocker(self.map, line_of_fire(self.map, pos, (p.x, p.y)), occupied)[1] == "clear"

        with_shot = [pos for pos in spots if has_shot(pos)]
        old = (m.x, m.y)
        m.x, m.y = self.rng.choice(with_shot or spots)
        self._fx(Fx("shot", [old, (m.x, m.y)], color=S.PURPLE))
        if self.visible(*old) or self.visible(m.x, m.y):
            self.say(f"The {m.name} vanishes and reappears out of reach!", S.PURPLE)
        return True

    # ------------------------------------------------------ interactive tiles
    def _interact(self, x: int, y: int) -> bool:
        """Use the furniture at (x, y). Returns True if it took a turn."""
        tile = self.map.tile(x, y)
        handled = self._interact_world(x, y, tile)
        if handled is not None:
            return handled
        if tile == DOOR_CLOSED:
            self.map.tiles[y][x] = DOOR_OPEN
            self.say("You open the door.", S.GREY)
            return True
        if tile == FOUNTAIN:
            p = self.player
            if p.hp >= p.max_hp and not any(p.has(st) for st in NEGATIVE):
                self.say("You are at full health; you leave the fountain for later.", S.GREY)
                return False
            healed = min(p.max_hp - p.hp, max(10, p.max_hp // 2))
            p.hp += healed
            cured = p.cure(*NEGATIVE)
            self.map.tiles[y][x] = FOUNTAIN_DRY
            extra = " It washes away your afflictions." if cured else ""
            self.say(f"You drink from the fountain and recover {healed} HP.{extra} It runs dry.", S.BLUE)
            return True
        if tile == CHEST:
            self._open_chest(x, y)
            return True
        return False

    def _open_chest(self, x: int, y: int) -> None:
        lvl = self.level
        if (x, y) in lvl.mimics:
            lvl.mimics.discard((x, y))
            self.map.tiles[y][x] = FLOOR
            mimic = self.options.prepare(Monster(x, y, MIMIC, self.depth), self.depth)
            mimic.alert = True
            lvl.monsters.append(mimic)
            self.say("The chest sprouts teeth - it's a mimic!", S.ORANGE)
            return
        self.map.tiles[y][x] = CHEST_OPEN
        gold = self.rng.randint(5, 15) * self.depth
        self.player.gold += gold
        loot = random_item(x, y, self.depth, self.rng)
        loot.seen = True
        if loot.kind == "gold":
            self.player.gold += loot.value
            gold += loot.value
            self.say(f"You open the chest and find {gold} gold.", S.YELLOW)
        else:
            lvl.items.append(loot)
            self.say(f"You open the chest: {gold} gold and {with_article(loot.name)}!", S.YELLOW)

    def _on_enter_tile(self) -> None:
        p = self.player
        self._wade(p)
        trap = self.map.traps.get((p.x, p.y))
        if trap:
            self._spring_trap(trap)
            if self.state is not State.PLAYING:
                return
        self._pickup()

    def _spring_trap(self, trap) -> None:
        p = self.player
        name = TRAP_KINDS[trap.kind][0]
        if trap.known and trap.kind != "teleport":
            self.say(f"You step carefully around the {name}.", S.GREY)
            return
        trap.known = True
        if trap.kind == "spike":
            dmg = max(1, round((2 + self.depth * 2) * self.rules.trap_damage))
            self.say(f"Spikes shoot up from the floor! You take {dmg} damage.", S.RED)
            self._damage(p, dmg, "a spike trap")
            if not p.alive:
                self.death_cause = "impaled by a spike trap"
        elif trap.kind == "alarm":
            for m in self.monsters:
                m.alert = True
            self.say("A bell clangs loudly! Monsters nearby come running.", S.YELLOW)
        elif trap.kind == "teleport":
            dest = self._random_teleport_destination()
            if dest:
                p.x, p.y = dest
                self.say("A rune flares beneath you - you are somewhere else!", S.PURPLE)

    def _random_teleport_destination(self) -> Pos | None:
        m = self.map
        p = self.player
        lair = self.level.lair
        sealed = set().union(*(pc.interior() for pc in self.level.pieces if pc.kind in ("vault", "secret")))
        spots = [
            (x, y)
            for x, y in m.cells()
            if m.tiles[y][x] == FLOOR
            and not self.blocking_actor_at(x, y)
            and not self.item_at(x, y)
            and max(abs(x - p.x), abs(y - p.y)) > S.FOV_RADIUS
            and not (lair and lair.contains(x, y))  # never straight into a boss's hall
            and (x, y) not in sealed  # nor into a vault or secret room
        ]
        return self.rng.choice(spots) if spots else None

    def _detect_traps(self) -> None:
        p = self.player
        chance = TRAP_SEARCH_CHANCE if self._searching else TRAP_SPOT_CHANCE
        sense = p.skill_bonus("trap_sense") > 0
        reach = 2 if sense else 1
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                trap = self.map.traps.get((p.x + dx, p.y + dy))
                if not trap or trap.known or (dx, dy) == (0, 0):
                    continue
                near = max(abs(dx), abs(dy)) == 1
                odds = 1.0 if (sense and near) else chance
                if self.rng.random() < odds:
                    trap.known = True
                    self.say(f"You spot a {TRAP_KINDS[trap.kind][0]}!", S.YELLOW)

    # ------------------------------------------------------------------ NPCs
    def talk(self, npc: NPC) -> None:
        if self.state is not State.PLAYING:
            return
        self.dialogue = Dialogue(npc, f'"{npc.greeting}"')
        self._refresh_options()

    def close_dialogue(self) -> None:
        self.dialogue = None

    def _refresh_options(self) -> None:
        d = self.dialogue
        if d is None:
            return
        npc, p, depth = d.npc, self.player, self.depth
        opts: list[DialogueOption] = []

        def offer(label: str, action: str, price: int, extra: bool = True) -> None:
            opts.append(DialogueOption(f"{label} ({price} gold)", action, p.gold >= price and extra))

        if npc.role == "merchant":
            offer("Buy a potion of healing", "buy_potion", potion_price(depth))
            offer("Buy a scroll of fire", "buy_scroll", scroll_price(depth))
            offer(f"Buy {ARROW_BUNDLE} arrows", "buy_arrows", arrow_price(depth))
            offer("Buy a ration", "buy_ration", ration_price(depth))
            offer("Buy a scroll of identify", "buy_identify", scroll_price(depth))
            offer("Identify everything you carry", "identify_all", identify_price(depth),
                  bool(self.unidentified_items()))
        elif npc.role == "healer":
            offer("Ask to be healed", "heal", healing_price(depth),
                  p.hp < p.max_hp or any(p.has(st) for st in NEGATIVE))
            offer("Ask to lift your curses", "uncurse", uncurse_price(depth), any(it.cursed for it in p.gear()))
        elif npc.role == "sage":
            if not npc.used:
                opts.append(DialogueOption("Ask for guidance", "guidance"))
            opts.append(DialogueOption("Ask about the dungeon", "rumour"))
        elif npc.role == "wanderer":
            opts.append(DialogueOption("Ask for rumours", "rumour"))
            if not npc.used:
                opts.append(DialogueOption("Ask if they can spare anything", "gift"))
        elif npc.role == "questgiver":
            self._quest_options(npc, opts)
        opts.append(DialogueOption("Goodbye", "bye"))
        d.options = opts

    def _give(self, item: Item) -> bool:
        """Hand ``item`` to the player, learning what it is. False if no room."""
        self.ident.identify(item)
        if not self.player.add_to_pack(item):
            self.say("Your pack is full.", S.GREY)
            return False
        return True

    def choose(self, index: int) -> None:
        """Pick dialogue option ``index`` (0-based)."""
        self.touch()
        d = self.dialogue
        if d is None or not 0 <= index < len(d.options):
            return
        opt = d.options[index]
        if not opt.enabled:
            d.text = "You can't do that right now."
            return
        npc, p, depth = d.npc, self.player, self.depth
        if opt.action == "bye":
            self.close_dialogue()
            return
        purchases = {
            "buy_potion": (potion_price, lambda: make_potion(0, 0, "healing"), "Drink it before it's too late."),
            "buy_scroll": (scroll_price, lambda: make_scroll(0, 0, "fire"), "Careful, it's hot."),
            "buy_ration": (ration_price, lambda: make_food(0, 0, "ration"), "Keeps for years. Tastes like it."),
            "buy_identify": (scroll_price, lambda: make_scroll(0, 0, "identify"), "Knowledge is power."),
        }
        if opt.action in purchases:
            price, factory, line = purchases[opt.action]
            item = factory()
            if self._give(item):
                p.gold -= price(depth)
                d.text = f'"{line}"'
                self.say(f"You buy {with_article(self.item_name(item, with_count=False))}.", S.YELLOW)
        elif opt.action == "buy_arrows":
            p.gold -= arrow_price(depth)
            p.arrows += ARROW_BUNDLE
            d.text = '"Straight and true, every one."'
            self.say(f"You buy {ARROW_BUNDLE} arrows.", (200, 170, 120))
        elif opt.action == "identify_all":
            p.gold -= identify_price(depth)
            for it in self.unidentified_items():
                self.identify_item(it)
            d.text = '"Let me see... ah. Interesting."'
        elif opt.action == "heal":
            p.gold -= healing_price(depth)
            p.hp = p.max_hp
            p.cure(*NEGATIVE)
            d.text = '"Be whole again."'
            self.say("The healer's touch restores you completely.", S.GREEN)
        elif opt.action == "uncurse":
            p.gold -= uncurse_price(depth)
            for it in [*p.gear(), *p.pack]:
                it.cursed = False
            d.text = '"Begone, foul magic!"'
            self.say("The curses on your belongings are lifted.", S.CYAN)
        elif opt.action == "guidance":
            npc.used = True
            self.map.reveal(find_secrets=True)
            target = self.level.down_stairs or self._amulet_pos()
            where = "The way onwards"
            if target:
                where += f" lies to the {compass(target[0] - npc.x, target[1] - npc.y)}"
            d.text = f'"Close your eyes... see? {where}."'
            self.say(f"{npc.name} shows you the layout of this floor.", S.CYAN)
        elif opt.action.startswith("quest_"):
            reply = self._quest_choose(opt.action, npc)
            if reply:
                d.text = reply
        elif opt.action == "rumour":
            d.text = f'"{self.rng.choice(RUMOURS)}"'
        elif opt.action == "gift":
            npc.used = True
            roll = self.rng.random()
            if roll < 0.6:
                gift, line = make_potion(0, 0, "healing"), "Here, take this potion. I've no use for it now."
            elif roll < 0.85:
                gift, line = make_scroll(0, 0, "fire"), "Take this scroll. Burn them all for me."
            else:
                gift, line = make_food(0, 0, "ration"), "You look hungry. Here."
            if self._give(gift):
                d.text = f'"{line}"'
                self.say(f"{npc.name} gives you {with_article(self.item_name(gift))}.", S.YELLOW)
        self._refresh_options()

    def _amulet_pos(self) -> Pos | None:
        for it in self.items:
            if it.kind == "amulet":
                return it.x, it.y
        for m in self.monsters:
            if m.carries_amulet:
                return m.x, m.y
        return None

    def _npcs_act(self) -> None:
        for npc in self.npcs:
            if not npc.wanders or self.rng.random() > 0.3:
                continue
            dx, dy = self.rng.choice(DIRS8)
            nx, ny = npc.x + dx, npc.y + dy
            if not self._npc_can_stand(npc, nx, ny):
                continue
            npc.x, npc.y = nx, ny

    def _npc_can_stand(self, npc: NPC, x: int, y: int) -> bool:
        # Only wander over open floor so an NPC never plugs a corridor/doorway.
        if not self.map.is_open_spot(x, y) or (x, y) in self.map.traps:
            return False
        if self.blocking_actor_at(x, y) or self.item_at(x, y):
            return False
        return not any(
            o is not npc and max(abs(o.x - x), abs(o.y - y)) <= 1 for o in self.npcs
        )

    # ------------------------------------------------------------- internals
    def _player_died(self, cause: str) -> None:
        self.state = State.DEAD
        self.death_cause = cause
        self.dialogue = None
        self.say("You die...", S.RED)

    def _kill(self, m: Monster) -> None:
        p = self.player
        self.say(f"The {m.name} dies. (+{m.xp_value} xp)", S.GREEN)
        p.kills += 1
        if m in self.monsters:
            self.monsters.remove(m)
        if m.carries_amulet:
            spot = (m.x, m.y) if self.item_at(m.x, m.y) is None else self._free_item_spot((m.x, m.y))
            amulet = Item(spot[0], spot[1], "amulet", "Amulet of Yendor", "*", S.PURPLE)
            amulet.seen = self.visible(*spot)
            self.items.append(amulet)
            self.say("The Amulet of Yendor clatters to the floor!", S.PURPLE)
        elif m.is_boss:
            self._drop_hoard(m)
        elif self.rng.random() < 0.3 and self.item_at(m.x, m.y) is None and self.map.tile(m.x, m.y) == FLOOR:
            self.items.append(random_item(m.x, m.y, self.depth, self.rng))
        if m is self.level.boss:
            self.say(f"You have slain the {m.name}!", S.PURPLE)
            if self.level.down_stairs:
                self.say("The seal on the stairs down shatters.", S.CYAN)
        for minion in [o for o in self.monsters if o.summoned_by is m]:
            self.monsters.remove(minion)  # summons fade with their master
        self._quest_kill(m)
        if p.gain_xp(m.xp_value):
            self.say(f"You reach level {p.level}! You feel stronger.", S.YELLOW)

    def _drop_hoard(self, boss: Monster) -> None:
        """A slain boss leaves a pile of gold and a piece of loot from deeper down."""
        gold_spot = self._free_item_spot((boss.x, boss.y))
        gold = Item(gold_spot[0], gold_spot[1], "gold", "gold", "$", S.YELLOW, 40 * self.depth)
        self.items.append(gold)
        loot_spot = self._free_item_spot((boss.x, boss.y))
        loot = random_item(loot_spot[0], loot_spot[1], self.depth + 2, self.rng)
        while loot.kind == "gold":
            loot = random_item(loot_spot[0], loot_spot[1], self.depth + 2, self.rng)
        self.items.append(loot)
        for it in (gold, loot):
            it.seen = self.visible(it.x, it.y)
        self.say(f"The {boss.name} leaves behind a hoard: {gold.value} gold and {with_article(loot.name)}.",
                 S.YELLOW)

    def _free_item_spot(self, origin: Pos) -> Pos:
        """Nearest walkable tile without an item - and not under the player,
        where it could never be picked up (pickup happens on entering a tile)."""
        seen = {origin}
        queue = deque([origin])
        player = (self.player.x, self.player.y)
        while queue:
            cur = queue.popleft()
            if self.map.walkable(*cur) and self.item_at(*cur) is None and cur != player:
                return cur
            for dx, dy in DIRS8:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt not in seen and self.map.walkable(*nxt):
                    seen.add(nxt)
                    queue.append(nxt)
        return origin

    # ------------------------------------------------------------ the clock
    def _end_turn(self) -> None:
        self.turns += 1
        self.touch()
        p = self.player
        weak = p.satiation < 400  # "Weak" or worse: no natural healing
        regen = self.turns % self.rules.regen_interval == 0
        if regen and p.hp < p.max_hp and not weak and not (p.has("poisoned") or p.has("burning")):
            p.hp += 1  # slow natural regeneration
        gear_regen = p.gear_bonus("regen")
        if gear_regen and self.turns % 10 == 0 and p.hp < p.max_hp:
            p.hp = min(p.max_hp, p.hp + gear_regen)
        self._tick_mana()
        self._tick_hunger()
        if self.state is State.PLAYING:
            self._detect_traps()
            self._search_secrets()
        self._searching = False
        self._npcs_act()
        rounds = 2 if p.has("slowed") else 1
        if p.has("hasted"):
            # Hasted: every other action is free.
            self._haste_phase ^= 1
            rounds = rounds - 1 if self._haste_phase else rounds
        rounds += self._maybe_faint()
        for _ in range(rounds):
            if self.state is State.PLAYING:
                self._world_round()
        lost = 0
        while self.state is State.PLAYING and p.has("stunned") and lost < 10:
            self.say("You reel, stunned, unable to act.", S.YELLOW)
            self._world_round()
            lost += 1
        self._update_fov()

    def _world_round(self) -> None:
        p = self.player
        self._tick_statuses(p)
        if self.state is not State.PLAYING:
            return
        self._update_fov()
        for m in list(self.monsters):
            if not m.alive or m not in self.monsters or self.state is not State.PLAYING:
                continue
            for ability in m.cooldowns:
                m.cooldowns[ability] -= 1
            self._update_alert(m)
            if not m.alert:
                m.energy = 0
                continue
            if distance((m.x, m.y), (p.x, p.y)) > 20 and m.cooldowns.get("aggravated", 0) <= 0:
                m.alert = False  # lost interest (unless aggravated)
                continue
            if m.has("stunned"):
                continue
            factor = 1.0
            for s in m.statuses:
                factor *= STATUS_SPECS[s].speed_factor
            m.energy += int(m.speed * factor)
            while m.energy >= 100 and m.alive and m in self.monsters and self.state is State.PLAYING:
                m.energy -= 100
                ai.act(self, m)
        for m in list(self.monsters):
            if m.alive:
                self._tick_statuses(m)
                if m.alive and m.kind.regen and m.hp < m.max_hp and not m.has("burning"):
                    m.hp = min(m.max_hp, m.hp + m.kind.regen)

    def _update_alert(self, m: Monster) -> None:
        if m.alert or not ai.sees_player(self, m):
            return
        d = distance((m.x, m.y), (self.player.x, self.player.y))
        if m.ai == "ambusher" and d > ai.AMBUSH_RADIUS:
            return
        m.alert = True
        if m.ai == "pack":
            woken = [o for o in self.monsters
                     if o.ai == "pack" and not o.alert and distance((o.x, o.y), (m.x, m.y)) <= 8]
            for o in woken:
                o.alert = True
            if woken or self.visible(m.x, m.y):
                self.say(f"The {m.name} howls for its pack!", S.ORANGE)

    def _tick_statuses(self, actor: Actor) -> None:
        if actor.stun_immunity > 0:
            actor.stun_immunity -= 1
        for name in list(actor.statuses):
            st = actor.statuses.get(name)
            if st is None:
                continue
            spec = STATUS_SPECS[name]
            if spec.heals and actor.hp < actor.max_hp:
                actor.hp = min(actor.max_hp, actor.hp + st.potency)
            if spec.damage:
                if actor is self.player:
                    self.say(f"You take {st.potency} damage from being {name}.", spec.color)
                self._popup(actor, str(st.potency), spec.color)
                self._damage(actor, st.potency, name)
                if not actor.alive:
                    return
            st.turns -= 1
            if st.turns <= 0:
                del actor.statuses[name]
                if name == "stunned":
                    actor.stun_immunity = STUN_IMMUNITY_ROUNDS
                if actor is self.player:
                    self.say(STATUS_MESSAGES[name][1], S.GREY)
