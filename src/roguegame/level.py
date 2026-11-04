"""A single, persistent dungeon floor and the code that populates it."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from . import settings as S
from .difficulty import DIFFICULTIES, Difficulty, endless_adjust
from .dungeon import DIRS8, DungeonMap, Pos, Room, Trap
from .entities import NPC, Item, Monster, random_item, random_monster
from .items import make_amulet, make_relic, random_food, random_gear
from .setpieces import SetPiece, add_library, add_secret_room, add_treasure_room, add_vault, place_champion
from .mapgen import generate_map
from .tiles import CHEST, DOOR_CLOSED, DOOR_OPEN, FLOOR, FOUNTAIN, SHRINE, STAIRS_DOWN, STAIRS_UP, TRAP, WALL

# Monsters never spawn this close (in steps) to where the player arrives.
SAFE_RADIUS = 8

# depth -> (boss, its guards, number of guards). The last floor's boss carries the Amulet.
BOSS_FLOORS: dict[int, tuple[str, str, int]] = {
    3: ("orc warlord", "orc", 1),  # his war cries bring plenty of extra company
    S.MAX_DEPTH: ("lich", "skeleton", 2),
}
# In endless mode the pattern repeats every BOSS_CYCLE floors (3, 5, 8, 10, 13, ...).
BOSS_CYCLE = S.MAX_DEPTH


def boss_for_depth(depth: int, max_depth: int | None = S.MAX_DEPTH) -> tuple[str, str, int] | None:
    """The boss (and guards) ruling ``depth``, if any. ``max_depth=None`` means endless."""
    if max_depth is None:
        return BOSS_FLOORS.get((depth - 1) % BOSS_CYCLE + 1)
    return BOSS_FLOORS.get(depth) if depth <= max_depth else None
LAIR_HALF_W, LAIR_HALF_H = 7, 5


@dataclass
class Level:
    depth: int
    map: DungeonMap
    start: Pos  # where the player appears when first arriving from above
    up_stairs: Pos | None  # None on floor 1
    down_stairs: Pos | None  # None on the last floor
    monsters: list[Monster] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    npcs: list[NPC] = field(default_factory=list)
    mimics: set[Pos] = field(default_factory=set)  # chests that are really monsters
    boss: Monster | None = None
    lair: Room | None = None
    pieces: list[SetPiece] = field(default_factory=list)  # vaults, secret rooms, treasure rooms, libraries
    quest: object | None = None  # the quest offered by this floor's guild envoy, if any

    @property
    def style(self) -> str:
        return self.map.style

    @property
    def sealed(self) -> bool:
        """Boss floors keep their stairs down sealed while the boss lives."""
        return self.boss is not None and self.boss.alive and self.boss in self.monsters


def level_rng(seed: int, depth: int) -> random.Random:
    """Each floor gets its own RNG stream, so a floor's layout depends only on
    the game seed and its depth - not on what the player did beforehand."""
    return random.Random(f"roguegame:{seed}:{depth}")


def carve_lair(m: DungeonMap, center: Pos) -> Room:
    """Open up a large hall around ``center`` with a few pillars for cover.

    Carving only turns walls into floor, so connectivity is preserved; doors
    that no longer sit in a doorway are removed afterwards.
    """
    cx = max(LAIR_HALF_W + 1, min(m.width - LAIR_HALF_W - 2, center[0]))
    cy = max(LAIR_HALF_H + 1, min(m.height - LAIR_HALF_H - 2, center[1]))
    room = Room(cx - LAIR_HALF_W, cy - LAIR_HALF_H, 2 * LAIR_HALF_W + 1, 2 * LAIR_HALF_H + 1)
    for y in range(room.y, room.y + room.h):
        for x in range(room.x, room.x + room.w):
            if m.tiles[y][x] not in (STAIRS_DOWN, STAIRS_UP):
                m.tiles[y][x] = FLOOR
    # Pillars: each has floor all around, so they can't cut the hall in two.
    for px, py in ((cx - 4, cy - 2), (cx + 4, cy - 2), (cx - 4, cy + 2), (cx + 4, cy + 2)):
        if (px, py) != center and m.is_open_spot(px, py):
            m.tiles[py][px] = WALL
    fix_doors(m)
    return room


def fix_doors(m: DungeonMap) -> None:
    """Turn doors that are no longer flanked by walls back into floor."""
    for x, y in m.find_tiles(DOOR_CLOSED) + m.find_tiles(DOOR_OPEN):
        horizontal = m.tile(x - 1, y) == WALL and m.tile(x + 1, y) == WALL
        vertical = m.tile(x, y - 1) == WALL and m.tile(x, y + 1) == WALL
        if not (horizontal or vertical):
            m.tiles[y][x] = FLOOR


# Monster/item/trap counts were tuned for 70x45 maps; bigger maps get more,
# but less than proportionally (so bigger floors are also a little roomier).
REFERENCE_AREA = 70 * 45
FOOD_PER_FLOOR = 1.2  # guaranteed food items on a reference-sized floor


def build_level(
    depth: int,
    rng: random.Random,
    max_depth: int | None = S.MAX_DEPTH,
    width: int = S.MAP_W,
    height: int = S.MAP_H,
    difficulty: Difficulty | None = None,
) -> Level:
    """Generate and populate floor ``depth``.

    ``max_depth`` is the last floor (which holds the Amulet instead of stairs
    down); ``None`` means endless mode: every floor has a way down.
    ``difficulty`` adjusts monster numbers and stats (default: normal).
    """
    rules = difficulty or DIFFICULTIES["normal"]
    last_floor = max_depth is not None and depth >= max_depth
    area = width * height / REFERENCE_AREA
    spread = area ** 0.7  # items, traps, food: a bit less than proportional to area
    density = area  # monsters: fully proportional, so bigger floors are just as crowded

    def scaled(n: float) -> int:
        return max(1, round(n * spread))

    def prepare(m: Monster) -> Monster:
        rules.adjust(m)
        if max_depth is None:
            endless_adjust(m, depth)
        return m

    def prepare_spawn(m: Monster) -> Monster:
        """Random spawns: bigger floors hold more of them, so each is worth a
        little less XP. Not proportionally less: clearing a bigger floor means
        more fights, and levelling a bit faster pays for the extra wear."""
        prepare(m)
        m.xp_value = max(1, round(m.xp_value / density ** 0.5))
        return m

    m = generate_map(width, height, depth, rng)
    floors = [(x, y) for x, y in m.cells() if m.tiles[y][x] == FLOOR]

    # ------------------------------------------------ arrival point & stairs
    if m.rooms:
        start = m.rooms[0].center
    else:
        start = rng.choice([p for p in floors if m.is_open_spot(*p)] or floors)
    dist = m.distance_map(start)
    far = max(dist.values())
    # Put the way down (or the Amulet) among the farthest tiles from the way in.
    candidates = [p for p in floors if dist.get(p, 0) >= far * 0.8 and p != start]
    goal = rng.choice(candidates)

    boss_spec = boss_for_depth(depth, max_depth)
    if boss_spec:
        # Carving the boss's hall can open shortcuts that bring it close to
        # the start. Try a few far spots on a scratch copy; keep one that
        # stays far away.
        for attempt in rng.sample(candidates, min(6, len(candidates))):
            trial = DungeonMap(m.width, m.height)
            trial.tiles = [row[:] for row in m.tiles]
            carve_lair(trial, attempt)
            after = trial.distance_map(start)
            if after.get(attempt, 0) >= 0.7 * max(after.values()):
                goal = attempt
                break
    lair = carve_lair(m, goal) if boss_spec else None
    if lair and lair.contains(*start):  # pathological tiny map: skip the lair
        lair = None

    up = start if depth > 1 else None
    down = None if last_floor else goal
    if up:
        m.tiles[up[1]][up[0]] = STAIRS_UP
    if down:
        m.tiles[down[1]][down[0]] = STAIRS_DOWN
    level = Level(depth, m, start, up, down, lair=lair)
    if last_floor and not boss_spec:
        level.items.append(make_amulet(*goal))

    # Tiles nothing else may claim: arrival area, goal, and the boss's hall.
    taken: set[Pos] = {start, goal}
    taken.update((start[0] + dx, start[1] + dy) for dx, dy in DIRS8)

    # ----------------------------------------------------------- set pieces
    def in_lair(p: Pos) -> bool:
        return lair is not None and lair.contains(*p)

    def room_ok(r: Room) -> bool:
        """Existing rooms that may become treasure rooms / libraries."""
        return (not r.contains(*start) and not r.contains(*goal) and not (lair and r.intersects(lair, pad=0))
                and dist.get(r.center, 0) >= SAFE_RADIUS and r.w * r.h >= 12)

    def main_spot(open_only: bool) -> Pos | None:
        """A free tile in the main part of the floor (for keys and levers)."""
        reserved = set().union(*(pc.interior() for pc in level.pieces)) if level.pieces else set()
        spots = [p for p in m.cells() if m.tiles[p[1]][p[0]] == FLOOR and p not in taken
                 and p not in reserved and not in_lair(p) and (not open_only or m.is_open_spot(*p))]
        if not spots:
            return None
        p = rng.choice(spots)
        taken.add(p)
        return p

    rooms_free = [r for r in m.rooms if room_ok(r)]
    if rng.random() < 0.5:
        piece = add_vault(level, rng, depth, main_spot)
        if piece:
            level.pieces.append(piece)
    if rng.random() < 0.5:
        piece = add_secret_room(level, rng, depth)
        if piece:
            level.pieces.append(piece)
    if rng.random() < 0.4:
        piece = add_treasure_room(level, rng, depth, rooms_free, prepare_spawn)
        if piece:
            level.pieces.append(piece)
            rooms_free = [r for r in rooms_free if r is not piece.room]
    if rooms_free and rng.random() < 0.35:
        piece = add_library(level, rng, rooms_free)
        if piece:
            level.pieces.append(piece)
    reserved: set[Pos] = set()
    for piece in level.pieces:
        if piece.kind != "library":
            reserved |= piece.interior()
    taken |= reserved
    # Carving changed the map: recompute what's where.
    floors = [(x, y) for x, y in m.cells() if m.tiles[y][x] == FLOOR]
    dist = m.distance_map(start)
    lair_tiles = {p for p in floors if in_lair(p)}

    open_candidates = [p for p in floors if m.is_open_spot(*p) and p not in lair_tiles and p not in reserved]
    rng.shuffle(open_candidates)

    def open_spot() -> Pos | None:
        # Candidates are re-checked lazily: placing furniture can make a
        # neighbouring spot no longer "open".
        while open_candidates:
            p = open_candidates.pop()
            if p not in taken and m.is_open_spot(*p):
                taken.add(p)
                return p
        return None

    # ------------------------------------------------------------ furniture
    # Furniture blocks movement, so only place it on open spots: a tile whose
    # 8 neighbours are all floor can be removed without disconnecting the map.
    for _ in range(rng.choice((0, 1, 1, 2))):
        p = open_spot()
        if p:
            m.tiles[p[1]][p[0]] = FOUNTAIN
    for _ in range(rng.randint(1, 2)):
        p = open_spot()
        if p:
            m.tiles[p[1]][p[0]] = CHEST
            if depth >= 2 and rng.random() < 0.1 + 0.05 * depth:
                level.mimics.add(p)
    if rng.random() < 0.35:
        p = open_spot()
        if p:
            m.tiles[p[1]][p[0]] = SHRINE

    # ---------------------------------------------------------------- traps
    kinds = ["spike", "alarm"] + (["teleport"] if depth >= 2 else [])
    weights = [5, 2] + ([2] if depth >= 2 else [])
    trap_spots = [p for p in floors if p not in taken and p not in lair_tiles and m.tiles[p[1]][p[0]] == FLOOR]
    rng.shuffle(trap_spots)
    for p in trap_spots[: scaled(2 + depth)]:
        kind = rng.choices(kinds, weights=weights)[0]
        # Known teleport runes can't be stepped around, so never put one in a
        # corridor or doorway where it would be unavoidable.
        if kind == "teleport" and not m.is_open_spot(*p):
            kind = "spike"
        m.tiles[p[1]][p[0]] = TRAP
        m.traps[p] = Trap(kind)
        taken.add(p)

    # ----------------------------------------------------------------- NPCs
    roles = ["wanderer"] if depth == 1 else []
    pool = ["merchant", "healer", "sage", "wanderer"]
    pool_weights = [3, 2, 2, 1]
    wanted = 1 + (rng.random() < 0.4)
    while len(roles) < wanted:
        role = rng.choices(pool, weights=pool_weights)[0]
        if role not in roles:
            roles.append(role)
    if rng.random() < 0.5:
        roles.append("questgiver")
    for role in roles:
        p = open_spot()
        if p:
            level.npcs.append(NPC(p[0], p[1], role, rng))
            # Keep NPCs apart so two of them can never plug a gap together.
            taken.update((p[0] + dx, p[1] + dy) for dx, dy in DIRS8)

    # ----------------------------------------------------------------- boss
    if boss_spec:
        boss_name, guard_name, guard_count = boss_spec
        lair_spots = sorted(
            (p for p in (lair_tiles or floors) if p not in taken and m.tiles[p[1]][p[0]] == FLOOR),
            key=lambda p: (abs(p[0] - goal[0]) + abs(p[1] - goal[1]), p),
        )
        boss_pos = goal if down is None else lair_spots.pop(0)
        boss = prepare(Monster(boss_pos[0], boss_pos[1], boss_name, depth))
        boss.carries_amulet = down is None
        level.boss = boss
        level.monsters.append(boss)
        taken.add(boss_pos)
        guards = [p for p in lair_spots if p != boss_pos][2:]  # leave the boss some elbow room
        rng.shuffle(guards)
        for p in guards[:guard_count]:
            level.monsters.append(prepare(Monster(p[0], p[1], guard_name, depth)))
            taken.add(p)

    # ------------------------------------------------------ monsters & items
    free = [p for p in floors if p not in taken and m.tiles[p[1]][p[0]] == FLOOR]
    rng.shuffle(free)
    monster_spots = [p for p in free if dist.get(p, 0) >= SAFE_RADIUS and p not in lair_tiles]
    for p in monster_spots[: rules.spawn_count(max(1, round((4 + min(depth, 10) * 2) * density)))]:
        level.monsters.append(prepare_spawn(random_monster(p[0], p[1], depth, rng)))
        taken.add(p)
    free = [p for p in free if p not in taken]
    count = scaled(rng.randint(4, 6))  # (set pieces and quests add more loot on top)
    for p in free[:count]:
        level.items.append(random_item(p[0], p[1], depth, rng))
        taken.add(p)
    # Every floor has food in proportion to its size (exploring a bigger
    # floor takes longer), so hunger stays survivable for a thorough explorer.
    for p in free[count: count + scaled(FOOD_PER_FLOOR)]:
        level.items.append(random_food(p[0], p[1], depth, rng))
        taken.add(p)

    # ---------------------------------------------------------------- quest
    giver = next((n for n in level.npcs if n.role == "questgiver"), None)
    if giver is not None:
        far_spots = [p for p in free if p not in taken and dist.get(p, 0) >= 15 and p not in lair_tiles]
        level.quest = make_quest(level, rng, depth, giver, far_spots, prepare)
    return level


def make_quest(level: Level, rng: random.Random, depth: int, giver: NPC, far_spots: list[Pos], prepare):
    """Set up a quest for ``giver``: a champion, a hidden relic or a cull."""
    from .quests import Quest, plural, relic_name

    kinds = Counter(mo.kind.name for mo in level.monsters if not mo.is_boss and mo.kind.spawnable)
    common = [k for k, n in kinds.items() if n >= 3]
    options = (["slay"] if far_spots else []) + ["fetch"] + (["cull"] if common else [])
    kind = rng.choice(options)
    reward_item = random_gear(0, 0, depth + 2, rng)
    if reward_item.rarity == "common":
        reward_item = random_gear(0, 0, depth + 5, rng)
    reward_item.identified = True  # the envoy knows exactly what they're offering
    reward_item.cursed = False  # ...and wouldn't hand over cursed junk
    gold, xp = rng.randint(30, 50) * depth, 25 * depth
    if kind == "slay":
        champ = place_champion(level, rng, depth, rng.choice(far_spots), prepare)
        return Quest("slay", depth, giver, f"Slay {champ.title}",
                     f"A {champ.name} called {champ.title} has been terrorising this floor. Put it down.",
                     gold, xp, reward_item, target=champ)
    if kind == "fetch":
        hidden = [pc for pc in level.pieces if pc.kind in ("secret", "vault")]
        spots: list[Pos] = []
        for pc in hidden:
            spots += [p for p in sorted(pc.interior()) if level.map.tile(*p) == FLOOR
                      and not any((it.x, it.y) == p for it in level.items)]
        spot = rng.choice(spots) if spots else rng.choice(far_spots or [level.start])
        relic = make_relic(spot[0], spot[1], relic_name(rng))
        level.items.append(relic)
        where = " Somewhere well hidden, I'd wager." if spots else ""
        return Quest("fetch", depth, giver, f"Recover {relic.name}",
                     f"I lost {relic.name} on this floor. Bring it back to me.{where}", gold, xp, reward_item,
                     relic=relic)
    target = rng.choice(common)
    needed = min(kinds[target], 3 + depth // 3)
    return Quest("cull", depth, giver, f"Cull the {plural(target)}",
                 f"There are far too many {plural(target)} on this floor. Kill {needed} of them.",
                 gold, xp, reward_item, monster_kind=target, needed=needed)
