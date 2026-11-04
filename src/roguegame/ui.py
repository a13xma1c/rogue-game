"""Pygame front-end: input, rendering and the main loop.

``App`` holds UI state (mode, look/aim cursor, camera, running animations)
and translates key/mouse input into calls on :class:`~roguegame.game.Game`.
``Renderer`` draws an ``App``. Neither needs a real window, so both can be
exercised in tests with SDL's dummy video driver.
"""

from __future__ import annotations

import contextlib
from enum import Enum, auto

import pygame

from . import fonts
from . import settings as S
from .classes import CLASS_NAMES, CLASSES, SKILLS, TIER_LEVELS
from .difficulty import DIFFICULTIES, DIFFICULTY_NAMES, MODE_DESCRIPTIONS, MODES, GameOptions
from .items import Item
from .entities import Actor, Fx
from .game import Game, ShotPlan, State
from .look import (
    Inspection,
    apparent_tile,
    item_lines,
    describe,
    interesting_targets,
    knowledge,
    shootable_targets,
)
from .minimap import Minimap, build_minimap
from . import saves
from .scores import ScoreBoard
from .spells import SPELLS, TARGETED
from .spells import describe as describe_spell
from .sprites import SpriteSheet, item_sprite, sprite_key
from .status import STATUS_SPECS
from .tiles import (
    DEEP_WATER,
    DOOR_CLOSED,
    DOOR_LOCKED,
    DOOR_OPEN,
    FLOOR,
    PORTCULLIS,
    TILES,
    TRAP,
    TRAP_KINDS,
    WALL,
    WATER,
)

WATER_COLORS = {WATER: (38, 64, 110), DEEP_WATER: (20, 34, 78)}

MOVE_KEYS = {
    pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1), pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0),
    pygame.K_w: (0, -1), pygame.K_s: (0, 1), pygame.K_a: (-1, 0), pygame.K_d: (1, 0),
    pygame.K_k: (0, -1), pygame.K_j: (0, 1), pygame.K_h: (-1, 0), pygame.K_l: (1, 0),
    pygame.K_y: (-1, -1), pygame.K_u: (1, -1), pygame.K_b: (-1, 1), pygame.K_n: (1, 1),
    pygame.K_KP8: (0, -1), pygame.K_KP2: (0, 1), pygame.K_KP4: (-1, 0), pygame.K_KP6: (1, 0),
    pygame.K_KP7: (-1, -1), pygame.K_KP9: (1, -1), pygame.K_KP1: (-1, 1), pygame.K_KP3: (1, 1),
}
WAIT_KEYS = (pygame.K_SPACE, pygame.K_PERIOD, pygame.K_KP5)
STAIRS_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER)
FIRE_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_t, pygame.K_f, pygame.K_z)
UP_KEYS = (pygame.K_UP, pygame.K_w, pygame.K_k, pygame.K_KP8)
DOWN_KEYS = (pygame.K_DOWN, pygame.K_s, pygame.K_j, pygame.K_KP2)
LEFT_KEYS = (pygame.K_LEFT, pygame.K_a, pygame.K_h, pygame.K_KP4)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d, pygame.K_l, pygame.K_KP6)
# Item menus opened by a quick key: (filter, empty message)
ITEM_MENUS = {
    "quaff": ("potion", "You have nothing to drink."),
    "read": ("scroll book", "You have nothing to read."),
    "eat": ("food", "You have nothing to eat."),
}
PANEL_MODES: tuple = ()  # filled in below
DIGIT_KEYS = {getattr(pygame, f"K_{i}"): i for i in range(1, 10)}
DIGIT_KEYS.update({getattr(pygame, f"K_KP{i}"): i for i in range(1, 10)})


VIEW_PX_W = S.VIEW_W * S.TILE
VIEW_PX_H = S.VIEW_H * S.TILE
HUD_TOP = VIEW_PX_H
MINIMAP_RECT = pygame.Rect(
    S.SCREEN_W - S.MINIMAP_W - 8, HUD_TOP + (S.HUD_H - S.MINIMAP_H) // 2, S.MINIMAP_W, S.MINIMAP_H
)
BIGMAP_RECT = pygame.Rect(0, 0, S.MAP_W * S.BIGMAP_SCALE, S.MAP_H * S.BIGMAP_SCALE)
BIGMAP_RECT.center = (VIEW_PX_W // 2, VIEW_PX_H // 2 + 10)

SHOT_FX_MS = 220  # how long a projectile trail stays on screen
TEXT_FX_MS = 800  # floating damage numbers

HELP_LINES = [
    ("Move / attack / talk / open", "arrows, WASD, hjkl yubn, numpad"),
    ("Wait & search for traps", "Space  .  numpad 5"),
    ("Use stairs", "Enter  (or < and >)"),
    ("Shoot your bow", "T or F, then aim (Tab cycles) and T/Enter to fire"),
    ("Inventory (use, equip, drop)", "I"),
    ("Quaff / read / eat", "Q (or P) / R / E"),
    ("Cast a spell or ability", "Z"),
    ("Character sheet and skill tree", "C"),
    ("Quest journal", "Shift+J"),
    ("Pause menu: save, load, seed, quit", "Esc"),
    ("Look mode", "X  (Tab: next target, Shift+Tab: previous)"),
    ("Inspect with the mouse", "click the map or minimap; hover in look mode"),
    ("Full map", "M"),
    ("Sprites / ASCII glyphs", "G"),
    ("Talk to NPCs", "walk into them, then press 1-9"),
    ("After a run ends", "R: play again, Enter: title screen"),
    ("Close a panel", "Esc"),
]


class Mode(Enum):
    MENU = auto()  # title screen: pick mode and difficulty
    NORMAL = auto()
    LOOK = auto()
    TARGET = auto()
    MAP = auto()
    HELP = auto()
    INVENTORY = auto()  # browse / pick an item (also used by quaff/read/eat/identify prompts)
    CHARACTER = auto()  # stats and skill tree
    SPELLS = auto()  # choose a spell to cast
    PAUSE = auto()  # Esc menu: save, load, seed, quit
    SLOTS = auto()  # pick a save slot (to save into or load from)
    JOURNAL = auto()  # accepted quests


CURSOR_MODES = (Mode.LOOK, Mode.TARGET)
PANEL_MODES = (Mode.INVENTORY, Mode.CHARACTER, Mode.SPELLS, Mode.PAUSE, Mode.SLOTS, Mode.JOURNAL)
PAUSE_ROWS = ("Resume", "Save game", "Load game", "Copy seed to clipboard", "Quit to title", "Quit game")


def seed_from_text(text: str) -> int:
    """Turn whatever the player typed into a seed: digits are used as-is,
    anything else (a word, a phrase) is hashed - so "dragon" is a valid seed."""
    import hashlib

    text = text.strip()
    if text.isdigit():
        return int(text)
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")


def replay_command(game: Game) -> str:
    o = game.options
    return f"roguegame --{o.mode} -d {o.difficulty} -c {o.player_class} --seed {game.seed}"


def copy_to_clipboard(text: str) -> bool:
    """Best effort: put ``text`` on the system clipboard."""
    try:
        import pygame.scrap as scrap

        scrap.put_text(text)  # pygame-ce >= 2.2: no init needed
        return True
    except Exception:  # noqa: BLE001 - no clipboard support on this platform/driver
        return False


def camera_origin(cx: int, cy: int, map_w: int = S.MAP_W, map_h: int = S.MAP_H) -> tuple[int, int]:
    """Top-left map tile of a viewport centred (as far as possible) on (cx, cy)."""
    ox = max(0, min(map_w - S.VIEW_W, cx - S.VIEW_W // 2))
    oy = max(0, min(map_h - S.VIEW_H, cy - S.VIEW_H // 2))
    return ox, oy


class App:
    def __init__(
        self,
        game: Game | None = None,
        seed: int | None = None,
        options: GameOptions | None = None,
        menu: bool = False,
        scores: ScoreBoard | None = None,
    ) -> None:
        """``menu=True`` starts on the title screen; otherwise a game starts
        right away (``game`` if given). ``scores`` enables the high-score
        table (off by default, so tests never touch the user's files)."""
        self.use_sprites = True
        self.scores = scores
        self.menu_options = options or (game.options if game else GameOptions())
        self.menu_index = 0
        self._seed = seed  # used for the first game only
        self.seed_text = str(seed) if seed is not None else ""  # title screen seed ("" = random)
        self.editing_seed = False
        self.pause_index = 0
        self.slot_action = "save"  # what the slot picker does: "save" or "load"
        self.slot_return = Mode.PAUSE  # where Esc in the slot picker goes back to
        self.notice = ""  # one-line message for menus that hide the game log
        self.game: Game = None  # type: ignore[assignment]  # set by restart(); None only on the title screen
        if menu:
            self.mode = Mode.MENU
        else:
            self.restart(game or Game(self._take_seed(), self.menu_options))

    def _take_seed(self) -> int | None:
        seed, self._seed = self._seed, None
        return seed

    def restart(self, game: Game | None = None) -> None:
        """Start ``game``, or a fresh one with the same options as the last."""
        if game is None:
            options = self.game.options if self.game is not None else self.menu_options
            game = Game(self._take_seed(), options)
        self.game = game
        self.recorded = False  # has this run gone into the score table yet?
        self.rank: int | None = None
        self.mode = Mode.NORMAL
        self.aim = "bow"  # what targeting mode is aiming: "bow" or a spell key
        self.inv_action: str | None = None  # quaff / read / eat / identify, or None to browse
        self.inv_selected: Item | None = None
        self.char_index = 0
        self.cursor = (self.game.player.x, self.game.player.y)
        self._look_center: tuple[int, int] | None = None
        self._target_index = -1
        self._dist_key: tuple | None = None
        self._dist: dict = {}
        self.effects: list[tuple[Fx, int]] = []  # (effect, start time in ms)

    # --------------------------------------------------------------- camera
    def camera(self) -> tuple[int, int]:
        p = self.game.player
        if self.mode not in CURSOR_MODES:
            self._look_center = None
            return camera_origin(p.x, p.y)
        # While aiming/looking the view stays put until the cursor leaves it.
        center = self._look_center or (p.x, p.y)
        ox, oy = camera_origin(*center)
        cx, cy = self.cursor
        if not (ox <= cx < ox + S.VIEW_W and oy <= cy < oy + S.VIEW_H):
            center = self.cursor
            ox, oy = camera_origin(*center)
        self._look_center = center
        return ox, oy

    # ------------------------------------------------------------ effects
    def update_effects(self, now: int) -> list[tuple[Fx, float]]:
        """Collect new effects from the game and return the live ones with
        their progress (0..1)."""
        for fx in self.game.fx:
            self.effects.append((fx, now))
        self.game.fx.clear()
        live: list[tuple[Fx, float]] = []
        kept: list[tuple[Fx, int]] = []
        for fx, start in self.effects:
            duration = SHOT_FX_MS if fx.kind == "shot" else TEXT_FX_MS
            t = (now - start) / duration
            if t < 1:
                kept.append((fx, start))
                live.append((fx, max(0.0, t)))
        self.effects = kept
        return live

    # --------------------------------------------------------------- look
    def start_look(self) -> None:
        p = self.game.player
        self.mode = Mode.LOOK
        self._target_index = -1
        self.cursor = (p.x, p.y)
        targets = interesting_targets(self.game)
        if targets:
            self._target_index = 0
            self.cursor = targets[0]

    def _targets(self) -> list[tuple[int, int]]:
        if self.mode is Mode.TARGET:
            return self.aim_targets()
        return interesting_targets(self.game)

    def aim_targets(self) -> list[tuple[int, int]]:
        """Sensible targets for what's being aimed, best first."""
        g = self.game
        if self.aim == "bow" or SPELLS[self.aim].target == "bow":
            return shootable_targets(g)
        out = []
        for pos in interesting_targets(g):
            mon = g.monster_at(*pos)
            if mon is not None:
                plan = g.plan_cast(self.aim, *pos)
                if plan.ok and plan.target is mon:
                    out.append(pos)
        return out

    def cycle_target(self, step: int = 1) -> None:
        targets = self._targets()
        if not targets:
            return
        self._target_index = (self._target_index + step) % len(targets)
        self.cursor = targets[self._target_index]

    def move_cursor(self, dx: int, dy: int) -> None:
        m = self.game.map
        x = max(0, min(m.width - 1, self.cursor[0] + dx))
        y = max(0, min(m.height - 1, self.cursor[1] + dy))
        self.cursor = (x, y)

    def inspection(self) -> Inspection:
        g = self.game
        key = (id(g.level), g.turns, g.player.x, g.player.y)
        if key != self._dist_key:
            # The known-route BFS is the expensive part; reuse it until something changes.
            self._dist = g.map.distance_map((g.player.x, g.player.y), known_only=True)
            self._dist_key = key
        return describe(g, *self.cursor, dist=self._dist)

    # ------------------------------------------------------------- aiming
    def start_target(self, aim: str = "bow") -> None:
        """Enter aiming mode for the bow (``aim="bow"``) or a targeted spell."""
        g = self.game
        p = g.player
        needs_bow = aim == "bow" or SPELLS[aim].target == "bow"
        if needs_bow and (not p.launcher or p.arrows <= 0):
            g.say("You have nothing to shoot with." if not p.launcher else "You are out of arrows.", S.GREY)
            return
        self.aim = aim
        self.mode = Mode.TARGET
        self._target_index = -1
        self.cursor = (p.x, p.y)
        targets = self.aim_targets()
        if targets:
            self._target_index = 0
            self.cursor = targets[0]
        else:
            visible = [m for m in g.monsters if g.visible(m.x, m.y)]
            if visible:  # nothing hittable, but point at the nearest foe so the panel explains why
                near = min(visible, key=lambda m: max(abs(m.x - p.x), abs(m.y - p.y)))
                self.cursor = (near.x, near.y)

    def shot_plan(self) -> ShotPlan:
        if self.aim == "bow":
            return self.game.plan_shot(*self.cursor)
        return self.game.plan_cast(self.aim, *self.cursor)

    def fire(self) -> None:
        g = self.game
        done = g.shoot(*self.cursor) if self.aim == "bow" else g.cast(self.aim, *self.cursor)
        if done:
            self.mode = Mode.NORMAL

    # ---------------------------------------------------------- item menus
    def inventory_entries(self) -> list[Item]:
        """Items listed in the inventory panel (equipped first), lettered a, b, c..."""
        g = self.game
        p = g.player
        if self.inv_action == "identify":
            return g.unidentified_items()[:26]
        if self.inv_action in ITEM_MENUS:
            kinds = ITEM_MENUS[self.inv_action][0].split()
            return [it for it in p.pack if it.kind in kinds][:26]
        return [*p.gear(), *p.pack][:26]

    def open_inventory(self, action: str | None = None) -> None:
        self.inv_action = action
        self.inv_selected = None
        if action in ITEM_MENUS and not self.inventory_entries():
            self.game.say(ITEM_MENUS[action][1], S.GREY)
            self.mode = Mode.NORMAL
            return
        self.mode = Mode.INVENTORY

    def _item_action(self, item: Item, verb: str = "use") -> None:
        g = self.game
        if self.inv_action == "identify":
            g.choose_item(item)
            self.mode = Mode.NORMAL
            return
        done = g.drop(item) if verb == "drop" else g.use_item(item)
        if done:
            self.mode = Mode.NORMAL
            self.inv_selected = None

    def _inventory_key(self, key: int, unicode: str) -> None:
        g = self.game
        if key == pygame.K_ESCAPE:
            if self.inv_selected is not None:
                self.inv_selected = None
            else:
                if self.inv_action == "identify":
                    g.cancel_pending()
                self.mode = Mode.NORMAL
            return
        if self.inv_selected is not None:
            if key in (pygame.K_u, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_e):
                self._item_action(self.inv_selected)
            elif key == pygame.K_d:
                self._item_action(self.inv_selected, "drop")
            return
        if len(unicode) == 1 and "a" <= unicode.lower() <= "z":
            entries = self.inventory_entries()
            index = ord(unicode.lower()) - ord("a")
            if index < len(entries):
                item = entries[index]
                if self.inv_action:
                    self._item_action(item)
                else:
                    self.inv_selected = item

    def _character_key(self, key: int) -> None:
        skills = [k for _, branch in self.game.player.cls.branches for k in branch]
        per_branch = len(skills) // 2
        if key in (pygame.K_ESCAPE, pygame.K_c):
            self.mode = Mode.NORMAL
        elif key in UP_KEYS:
            self.char_index = (self.char_index - 1) % len(skills)
        elif key in DOWN_KEYS:
            self.char_index = (self.char_index + 1) % len(skills)
        elif key in LEFT_KEYS + RIGHT_KEYS:
            self.char_index = (self.char_index + per_branch) % len(skills)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.game.learn_skill(skills[self.char_index])

    def known_spells(self) -> list[str]:
        known = self.game.player.spells
        return [k for k in SPELLS if k in known]

    def _spells_key(self, key: int, unicode: str) -> None:
        if key in (pygame.K_ESCAPE, pygame.K_z):
            self.mode = Mode.NORMAL
            return
        if len(unicode) == 1 and "a" <= unicode.lower() <= "z":
            spells = self.known_spells()
            index = ord(unicode.lower()) - ord("a")
            if index < len(spells):
                self.choose_spell(spells[index])

    def choose_spell(self, key: str) -> None:
        g = self.game
        spell = SPELLS[key]
        if g.player.mana < spell.cost:
            g.say(f"Not enough mana for {spell.name} ({g.player.mana}/{spell.cost}).", S.GREY)
            return
        if spell.target in TARGETED:
            self.start_target(key)
        else:
            self.mode = Mode.NORMAL
            g.cast(key)

    # ----------------------------------------------------------- title menu
    def menu_rows(self) -> tuple[str, ...]:
        rows = ("mode", "difficulty", "class", "seed", "start")
        return rows + (("load",) if saves.list_saves() else ())

    def open_menu(self) -> None:
        if self.game is not None:
            self.menu_options = self.game.options
        self.game = None  # type: ignore[assignment]
        self.mode = Mode.MENU
        self.menu_index = self.menu_rows().index("start")  # replaying is one keypress

    def change_option(self, step: int) -> None:
        row = self.menu_rows()[self.menu_index]
        o = self.menu_options
        if row == "mode":
            mode = MODES[(MODES.index(o.mode) + step) % len(MODES)]
            self.menu_options = GameOptions(mode, o.difficulty, o.player_class)
        elif row == "difficulty":
            diff = DIFFICULTY_NAMES[(DIFFICULTY_NAMES.index(o.difficulty) + step) % len(DIFFICULTY_NAMES)]
            self.menu_options = GameOptions(o.mode, diff, o.player_class)
        elif row == "class":
            cls = CLASS_NAMES[(CLASS_NAMES.index(o.player_class) + step) % len(CLASS_NAMES)]
            self.menu_options = GameOptions(o.mode, o.difficulty, cls)

    def start_game(self) -> None:
        seed = seed_from_text(self.seed_text) if self.seed_text.strip() else self._take_seed()
        self._seed = None
        self.restart(Game(seed, self.menu_options))

    def _menu_key(self, key: int, unicode: str = "") -> bool:
        rows = self.menu_rows()
        self.menu_index = min(self.menu_index, len(rows) - 1)
        if self.editing_seed:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE, pygame.K_TAB):
                self.editing_seed = False
            elif key == pygame.K_BACKSPACE:
                self.seed_text = self.seed_text[:-1]
            elif unicode and unicode.isprintable() and len(self.seed_text) < 24:
                self.seed_text += unicode
            return True
        row = rows[self.menu_index]
        if key == pygame.K_ESCAPE:
            return False
        if key in (pygame.K_UP, pygame.K_w, pygame.K_k, pygame.K_KP8):
            self.menu_index = (self.menu_index - 1) % len(rows)
        elif key in (pygame.K_DOWN, pygame.K_s, pygame.K_j, pygame.K_KP2, pygame.K_TAB):
            self.menu_index = (self.menu_index + 1) % len(rows)
        elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_h, pygame.K_KP4):
            self.change_option(-1)
        elif key in (pygame.K_RIGHT, pygame.K_d, pygame.K_l, pygame.K_KP6):
            self.change_option(1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            if row == "seed":
                self.editing_seed = True
            elif row == "load":
                self.open_slots("load", back=Mode.MENU)
            else:
                self.start_game()
        elif row == "seed" and key == pygame.K_BACKSPACE:
            self.seed_text = ""
        return True

    # ---------------------------------------------------- pause & save slots
    def open_slots(self, action: str, back: Mode = Mode.PAUSE) -> None:
        self.slot_action = action
        self.slot_return = back
        self.notice = ""
        self.mode = Mode.SLOTS

    def _pause_key(self, key: int) -> bool:
        if key == pygame.K_ESCAPE:
            self.mode = Mode.NORMAL
            return True
        if key in UP_KEYS:
            self.pause_index = (self.pause_index - 1) % len(PAUSE_ROWS)
        elif key in DOWN_KEYS:
            self.pause_index = (self.pause_index + 1) % len(PAUSE_ROWS)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            choice = PAUSE_ROWS[self.pause_index]
            if choice == "Resume":
                self.mode = Mode.NORMAL
            elif choice == "Save game":
                if self.game.state is State.PLAYING:
                    self.open_slots("save")
                else:
                    self.notice = "The run is over - there's nothing to save."
            elif choice == "Load game":
                self.open_slots("load")
            elif choice == "Copy seed to clipboard":
                seed = str(self.game.seed)
                self.notice = (f"Seed {seed} copied to the clipboard." if copy_to_clipboard(seed)
                               else f"No clipboard available - the seed is {seed}.")
            elif choice == "Quit to title":
                self.open_menu()
            elif choice == "Quit game":
                return False
        return True

    def _slots_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self.mode = self.slot_return
            return
        if key in DIGIT_KEYS and DIGIT_KEYS[key] in saves.SLOTS:
            self.use_slot(DIGIT_KEYS[key])

    def use_slot(self, slot: int) -> bool:
        """Save into or load from ``slot``, depending on ``slot_action``."""
        try:
            if self.slot_action == "save":
                saves.save_game(self.game, slot)
                self.game.say(f"Game saved to slot {slot}.", S.GREEN)
                self.mode = Mode.NORMAL
            else:
                game = saves.load_game(slot)
                self.restart(game)
                self.game.say(f"Game loaded from slot {slot}. Welcome back!", S.GREEN)
            return True
        except saves.SaveError as e:
            self.notice = str(e)
            return False

    def note_game_over(self) -> None:
        """Record a finished run in the score table (once)."""
        g = self.game
        if g is None or g.state is State.PLAYING or self.recorded:
            return
        self.recorded = True
        if self.scores is not None:
            self.rank = self.scores.record(g)

    # ---------------------------------------------------------------- input
    def handle_key(self, key: int, unicode: str = "", mod: int = 0) -> bool:
        """Process one key press. Returns False when the player quits."""
        if self.mode is Mode.MENU:
            return self._menu_key(key, unicode)
        if self.mode is Mode.SLOTS and self.game is None:  # loading from the title screen
            self._slots_key(key)
            return True
        try:
            return self._game_key(key, unicode, mod)
        finally:
            self.note_game_over()
            if self.game is not None and self.game.pending == "identify" and self.mode is not Mode.INVENTORY:
                self.open_inventory("identify")

    def _game_key(self, key: int, unicode: str, mod: int) -> bool:
        g = self.game
        if g.dialogue is not None:
            if key == pygame.K_ESCAPE:
                g.close_dialogue()
            elif key in DIGIT_KEYS:
                g.choose(DIGIT_KEYS[key] - 1)
            return True

        if key == pygame.K_g and self.mode not in (Mode.HELP, *PANEL_MODES):  # in menus, g is a letter
            self.use_sprites = not self.use_sprites
            return True
        if self.mode is Mode.HELP:
            self.mode = Mode.NORMAL
            return True
        if self.mode is Mode.MAP:
            if key in (pygame.K_m, pygame.K_ESCAPE, pygame.K_RETURN):
                self.mode = Mode.NORMAL
            return True
        if self.mode is Mode.INVENTORY:
            self._inventory_key(key, unicode)
            return True
        if self.mode is Mode.CHARACTER:
            self._character_key(key)
            return True
        if self.mode is Mode.SPELLS:
            self._spells_key(key, unicode)
            return True
        if self.mode is Mode.PAUSE:
            return self._pause_key(key)
        if self.mode is Mode.SLOTS:
            self._slots_key(key)
            return True
        if self.mode is Mode.JOURNAL:
            if key in (pygame.K_ESCAPE, pygame.K_RETURN) or unicode == "J":
                self.mode = Mode.NORMAL
            return True
        if self.mode in CURSOR_MODES:
            if key in MOVE_KEYS:
                self.move_cursor(*MOVE_KEYS[key])
            elif key == pygame.K_TAB:
                self.cycle_target(-1 if mod & pygame.KMOD_SHIFT else 1)
            elif self.mode is Mode.TARGET and key in FIRE_KEYS:
                self.fire()
            elif key in (pygame.K_ESCAPE, pygame.K_x, pygame.K_RETURN):
                self.mode = Mode.NORMAL
            return True

        # ---- normal mode
        if key == pygame.K_ESCAPE:
            self.mode = Mode.PAUSE
            self.pause_index = 0
            self.notice = ""
            return True
        if g.state is not State.PLAYING and key == pygame.K_r:
            self.restart()
            return True
        if g.state is not State.PLAYING and key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.open_menu()
            return True
        if unicode == "J":  # (plain j is a movement key)
            self.mode = Mode.JOURNAL
        elif unicode == ">":
            g.descend()
        elif unicode == "<":
            g.ascend()
        elif unicode == "?":
            self.mode = Mode.HELP
        elif key in MOVE_KEYS:
            g.player_move(*MOVE_KEYS[key])
        elif key in WAIT_KEYS:
            g.wait()
        elif key in STAIRS_KEYS:
            g.use_stairs()
        elif key in (pygame.K_q, pygame.K_p):
            self.open_inventory("quaff")
        elif key == pygame.K_r:
            self.open_inventory("read")
        elif key == pygame.K_e:
            self.open_inventory("eat")
        elif key == pygame.K_i:
            self.open_inventory()
        elif key == pygame.K_c:
            self.mode = Mode.CHARACTER
        elif key == pygame.K_z:
            if self.known_spells():
                self.mode = Mode.SPELLS
            else:
                g.say("You don't know any spells or abilities yet. (C: skill tree)", S.GREY)
        elif key in (pygame.K_t, pygame.K_f):
            self.start_target()
        elif key in (pygame.K_x, pygame.K_TAB):
            self.start_look()
        elif key == pygame.K_m:
            self.mode = Mode.MAP
        return True

    def tile_at_screen(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        """Map tile under a screen pixel (main view, minimap or full map)."""
        sx, sy = pos
        m = self.game.map
        if self.mode is Mode.MAP:
            if BIGMAP_RECT.collidepoint(sx, sy):
                return ((sx - BIGMAP_RECT.x) // S.BIGMAP_SCALE, (sy - BIGMAP_RECT.y) // S.BIGMAP_SCALE)
            return None
        if MINIMAP_RECT.collidepoint(sx, sy):
            return ((sx - MINIMAP_RECT.x) // S.MINIMAP_SCALE, (sy - MINIMAP_RECT.y) // S.MINIMAP_SCALE)
        if 0 <= sx < VIEW_PX_W and 0 <= sy < VIEW_PX_H:
            ox, oy = self.camera()
            x, y = ox + sx // S.TILE, oy + sy // S.TILE
            if m.in_bounds(x, y):
                return x, y
        return None

    def handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        if self.mode not in CURSOR_MODES or self.game.dialogue is not None:  # (also covers the menu)
            return
        if 0 <= pos[0] < VIEW_PX_W and 0 <= pos[1] < VIEW_PX_H:
            tile = self.tile_at_screen(pos)
            if tile:
                self.cursor = tile

    def handle_click(self, pos: tuple[int, int], button: int = 1) -> None:
        if self.mode is Mode.MENU or self.game.dialogue is not None or self.mode is Mode.HELP:
            return
        try:
            self._click(pos, button)
        finally:
            self.note_game_over()

    def _click(self, pos: tuple[int, int], button: int) -> None:
        if button == 3 and self.mode in CURSOR_MODES:
            self.mode = Mode.NORMAL
            return
        if button != 1:
            return
        tile = self.tile_at_screen(pos)
        if self.mode is Mode.TARGET:
            if tile and 0 <= pos[0] < VIEW_PX_W and 0 <= pos[1] < VIEW_PX_H:
                self.cursor = tile
                self.fire()
            return
        # Clicking any map (main view, minimap or full map) inspects that tile.
        if tile:
            self.mode = Mode.LOOK
            self._target_index = -1
            self.cursor = tile
            self._look_center = tile  # jump the view to the clicked spot


class Layer:
    """An off-screen surface that is only redrawn when its key changes.

    Keys hold the game and level *objects* (not ids - ids get reused after
    garbage collection), plus whatever else the picture depends on.
    """

    def __init__(self, size: tuple[int, int]) -> None:
        self.surface = pygame.Surface(size)
        self.key: tuple | None = None
        self.redraws = 0

    def refresh(self, key: tuple, draw) -> pygame.Surface:
        if key != self.key:
            draw(self.surface)
            self.key = key
            self.redraws += 1
        return self.surface


class Renderer:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.glyph_font = fonts.font(S.TILE - 4, bold=True)
        self.ui_font = fonts.font(15)
        self.small_font = fonts.font(13)
        self.fx_font = fonts.font(14, bold=True)
        self.big_font = fonts.font(44, bold=True)
        self.sprites = SpriteSheet(S.TILE)
        self._cache: dict[tuple, pygame.Surface] = {}
        # Cached layers: the map view, the HUD, and the minimap data/images.
        self.map_layer = Layer((VIEW_PX_W, VIEW_PX_H))
        self.hud_layer = Layer((S.SCREEN_W, S.HUD_H))
        self._minimap_key: tuple | None = None
        self._minimap_data: Minimap | None = None
        self._minimap_images: dict[int, pygame.Surface] = {}
        self.minimap_builds = 0

    @contextlib.contextmanager
    def drawing_on(self, surface: pygame.Surface):
        """Point the drawing helpers (which draw on ``self.screen``) at
        another surface for a while."""
        saved, self.screen = self.screen, surface
        try:
            yield
        finally:
            self.screen = saved

    @staticmethod
    def _world_key(game: Game) -> tuple:
        return (game, game.level, game.revision)

    def glyph(self, ch: str, color: tuple[int, int, int]) -> pygame.Surface:
        key = (ch, color)
        if key not in self._cache:
            self._cache[key] = self.glyph_font.render(ch, True, color)
        return self._cache[key]

    def blit_glyph(self, ch: str, color: tuple[int, int, int], sx: int, sy: int) -> None:
        g = self.glyph(ch, color)
        self.screen.blit(g, (sx + (S.TILE - g.get_width()) // 2, sy + (S.TILE - g.get_height()) // 2))

    def item_surface(self, game: Game, item: Item, size: int | None = None) -> pygame.Surface | None:
        key, tint, outline = item_sprite(item, game.ident)
        return self.sprites.get(key, tint, outline, size)

    def blit_item(self, game: Game, item: Item, sx: int, sy: int, use_sprites: bool, lit: bool = True) -> None:
        sprite = self.item_surface(game, item) if use_sprites else None
        if sprite is not None:
            if not lit:  # remembered, out of sight: draw it darkened
                sprite = sprite.copy()
                sprite.fill((110, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(sprite, (sx, sy))
        else:
            color = game.item_color(item)
            self.blit_glyph(item.glyph, color if lit else _dim(color), sx, sy)

    def blit_actor(self, actor: Actor, sx: int, sy: int, use_sprites: bool) -> None:
        # Quest champions glow gold so they stand out from ordinary monsters.
        outline = S.YELLOW if getattr(actor, "title", "") else None
        sprite = self.sprites.get(sprite_key(actor), outline=outline) if use_sprites else None
        if sprite is not None:
            self.screen.blit(sprite, (sx, sy))
        else:
            self.blit_glyph(actor.glyph, actor.color, sx, sy)
        # One coloured pip per status effect along the top edge of the tile.
        for i, name in enumerate(actor.statuses):
            color = STATUS_SPECS[name].color
            pygame.draw.rect(self.screen, (0, 0, 0), (sx + 1 + i * 6, sy, 6, 6))
            pygame.draw.rect(self.screen, color, (sx + 2 + i * 6, sy + 1, 4, 4))

    # ------------------------------------------------------------------ main
    def draw(self, app: App, now: int | None = None) -> None:
        if app.mode is Mode.MENU or (app.mode is Mode.SLOTS and app.game is None):
            self._title_screen(app)
            if app.mode is Mode.SLOTS:
                self._slots_panel(app)
            return
        game = app.game
        now = pygame.time.get_ticks() if now is None else now
        effects = app.update_effects(now)
        self.screen.fill(S.BLACK)
        cx, cy = app.camera()
        self.screen.blit(self._map_view(app, cx, cy), (0, 0))
        if app.mode is Mode.TARGET:
            self._draw_aim(app, cx, cy)
        if app.mode in CURSOR_MODES:
            self._draw_cursor(app, cx, cy)
        self._draw_effects(effects, cx, cy)
        self._boss_bar(game)
        self.screen.blit(self._hud_view(app), (0, HUD_TOP))
        self._minimap(app, cx, cy)
        if app.mode is Mode.LOOK:
            self._look_panel(app, cx, cy)
        elif app.mode is Mode.TARGET:
            self._aim_panel(app, cx, cy)
        elif app.mode is Mode.MAP:
            self._big_map(app)
        elif app.mode is Mode.HELP:
            self._help()
        elif app.mode is Mode.INVENTORY:
            self._inventory_panel(app)
        elif app.mode is Mode.CHARACTER:
            self._character_panel(app)
        elif app.mode is Mode.SPELLS:
            self._spells_panel(app)
        elif app.mode is Mode.PAUSE:
            self._pause_panel(app)
        elif app.mode is Mode.SLOTS:
            self._slots_panel(app)
        elif app.mode is Mode.JOURNAL:
            self._journal_panel(app)
        if game.dialogue is not None:
            self._dialogue(game)
        if game.state is State.DEAD:
            self._banner("YOU DIED", S.RED, app)
        elif game.state is State.WON:
            self._banner("VICTORY!", S.PURPLE, app)

    def _map_view(self, app: App, cx: int, cy: int) -> pygame.Surface:
        """The map, its items and its actors - redrawn only after something
        changed (a turn passed, a message, a level change...) or the view moved."""
        game = app.game

        def draw(surface: pygame.Surface) -> None:
            surface.fill(S.BLACK)
            with self.drawing_on(surface):
                self._draw_map(game, cx, cy, app.use_sprites)

        return self.map_layer.refresh((*self._world_key(game), cx, cy, app.use_sprites), draw)

    def _hud_view(self, app: App) -> pygame.Surface:
        def draw(surface: pygame.Surface) -> None:
            with self.drawing_on(surface):
                self._hud(app, top=0)

        return self.hud_layer.refresh(self._world_key(app.game), draw)

    def minimap_data(self, game: Game) -> Minimap:
        """The minimap model, rebuilt only when the game changed."""
        key = self._world_key(game)
        if key != self._minimap_key:
            self._minimap_data = build_minimap(game)
            self._minimap_images = {}
            self._minimap_key = key
            self.minimap_builds += 1
        assert self._minimap_data is not None
        return self._minimap_data

    def minimap_image(self, game: Game, scale: int) -> pygame.Surface:
        """The minimap painted at ``scale`` pixels per tile (cached per scale)."""
        mm = self.minimap_data(game)
        image = self._minimap_images.get(scale)
        if image is None:
            image = paint_minimap(mm, scale)
            self._minimap_images[scale] = image
        return image

    def _draw_map(self, game: Game, cx: int, cy: int, use_sprites: bool) -> None:
        m = game.map
        for vy in range(S.VIEW_H):
            for vx in range(S.VIEW_W):
                x, y = cx + vx, cy + vy
                if not m.in_bounds(x, y) or not m.explored[y][x]:
                    continue
                lit = m.visible[y][x]
                px, py = vx * S.TILE, vy * S.TILE
                tile = apparent_tile(game, x, y)
                if tile == WALL:
                    pygame.draw.rect(self.screen, S.WALL_LIT if lit else S.WALL_DIM, (px, py, S.TILE, S.TILE))
                    pygame.draw.rect(self.screen, S.BLACK, (px, py, S.TILE, S.TILE), 1)
                    continue
                floor_color = S.FLOOR_LIT if lit else S.FLOOR_DIM
                if tile in (WATER, DEEP_WATER):
                    floor_color = WATER_COLORS[tile] if lit else _dim(WATER_COLORS[tile])
                pygame.draw.rect(self.screen, floor_color, (px, py, S.TILE, S.TILE))
                tt = TILES[tile]
                if tile in (DOOR_CLOSED, DOOR_LOCKED):
                    panel = S.DOOR_PANEL if lit else _dim(S.DOOR_PANEL)
                    pygame.draw.rect(self.screen, panel, (px + 2, py + 2, S.TILE - 4, S.TILE - 4))
                    if tile == DOOR_LOCKED:  # a brass lock plate
                        pygame.draw.rect(self.screen, S.YELLOW if lit else _dim(S.YELLOW),
                                         (px + S.TILE // 2 - 3, py + S.TILE // 2 + 2, 6, 6))
                elif tile == PORTCULLIS:
                    bars = (170, 170, 185) if lit else _dim((170, 170, 185))
                    for bx in range(3, S.TILE, 5):
                        pygame.draw.line(self.screen, bars, (px + bx, py), (px + bx, py + S.TILE - 1), 2)
                    pygame.draw.line(self.screen, bars, (px, py + 6), (px + S.TILE - 1, py + 6), 2)
                    continue
                elif tile == DOOR_OPEN:
                    # Two jambs either side of the gap, along the wall line.
                    jamb = S.BROWN if lit else _dim(S.BROWN)
                    if m.tile(x - 1, y) == WALL and m.tile(x + 1, y) == WALL:
                        pygame.draw.rect(self.screen, jamb, (px, py, 4, S.TILE))
                        pygame.draw.rect(self.screen, jamb, (px + S.TILE - 4, py, 4, S.TILE))
                    else:
                        pygame.draw.rect(self.screen, jamb, (px, py, S.TILE, 4))
                        pygame.draw.rect(self.screen, jamb, (px, py + S.TILE - 4, S.TILE, 4))
                if tile == TRAP:
                    color = TRAP_KINDS[m.traps[(x, y)].kind][1]
                    self.blit_glyph("^", color if lit else S.GREY, px, py)
                elif tt.glyph:
                    self.blit_glyph(tt.glyph, tt.color if lit else _dim(tt.color), px, py)
                elif lit and tile == FLOOR:
                    pygame.draw.rect(self.screen, (68, 62, 54), (px + 11, py + 11, 2, 2))

        def on_screen(x: int, y: int) -> bool:
            return cx <= x < cx + S.VIEW_W and cy <= y < cy + S.VIEW_H

        for it in game.items:
            if it.seen and m.explored[it.y][it.x] and on_screen(it.x, it.y):
                self.blit_item(game, it, (it.x - cx) * S.TILE, (it.y - cy) * S.TILE, use_sprites,
                               lit=m.visible[it.y][it.x])
        actors: list[Actor] = [*game.npcs, *game.monsters]
        for a in actors:
            if m.visible[a.y][a.x] and on_screen(a.x, a.y):
                self.blit_actor(a, (a.x - cx) * S.TILE, (a.y - cy) * S.TILE, use_sprites)
        p = game.player
        self.blit_actor(p, (p.x - cx) * S.TILE, (p.y - cy) * S.TILE, use_sprites)

    def _draw_cursor(self, app: App, cx: int, cy: int) -> None:
        x, y = app.cursor
        color = S.RED if app.mode is Mode.TARGET else S.YELLOW
        rect = pygame.Rect((x - cx) * S.TILE, (y - cy) * S.TILE, S.TILE, S.TILE)
        pygame.draw.rect(self.screen, color, rect, 2)

    def _draw_aim(self, app: App, cx: int, cy: int) -> None:
        plan = app.shot_plan()
        color = (S.GREEN if plan.target else S.YELLOW) if plan.ok else S.RED
        for x, y in plan.area:
            rect = pygame.Rect((x - cx) * S.TILE, (y - cy) * S.TILE, S.TILE, S.TILE)
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill((240, 140, 50, 70))
            self.screen.blit(overlay, rect.topleft)
        for x, y in plan.path:
            sx, sy = (x - cx) * S.TILE + S.TILE // 2, (y - cy) * S.TILE + S.TILE // 2
            pygame.draw.circle(self.screen, (0, 0, 0), (sx, sy), 4)
            pygame.draw.circle(self.screen, color, (sx, sy), 3)

    def _draw_effects(self, effects: list[tuple[Fx, float]], cx: int, cy: int) -> None:
        for fx, t in effects:
            if fx.kind == "shot" and fx.path:
                # A bolt travelling along its path, with a short fading tail.
                head = min(len(fx.path) - 1, int(t * len(fx.path)))
                for i in range(max(0, head - 2), head + 1):
                    x, y = fx.path[i]
                    sx, sy = (x - cx) * S.TILE + S.TILE // 2, (y - cy) * S.TILE + S.TILE // 2
                    pygame.draw.circle(self.screen, fx.color, (sx, sy), 4 if i == head else 2)
            elif fx.kind == "text" and fx.path:
                x, y = fx.path[0]
                surf = self.fx_font.render(fx.text, True, fx.color)
                shadow = self.fx_font.render(fx.text, True, (0, 0, 0))
                sx = (x - cx) * S.TILE + (S.TILE - surf.get_width()) // 2
                sy = (y - cy) * S.TILE - int(t * 18) - 4
                alpha = int(255 * (1 - t * t))
                surf.set_alpha(alpha)
                shadow.set_alpha(alpha)
                self.screen.blit(shadow, (sx + 1, sy + 1))
                self.screen.blit(surf, (sx, sy))

    def _boss_bar(self, game: Game) -> None:
        boss = game.level.boss
        if boss is None or boss not in game.monsters or not (boss.alert or game.visible(boss.x, boss.y)):
            return
        rect = pygame.Rect(0, 8, 420, 18)
        rect.centerx = VIEW_PX_W // 2
        pygame.draw.rect(self.screen, (40, 10, 30), rect)
        frac = max(0, boss.hp) / boss.max_hp
        pygame.draw.rect(self.screen, S.PURPLE if boss.name == "lich" else S.RED,
                         (rect.x, rect.y, int(rect.w * frac), rect.h))
        pygame.draw.rect(self.screen, S.WHITE, rect, 1)
        label = f"{boss.name.title()}  {max(0, boss.hp)}/{boss.max_hp}"
        if boss.statuses:
            label += "  (" + ", ".join(boss.statuses) + ")"
        t = self.small_font.render(label, True, S.WHITE)
        self.screen.blit(t, t.get_rect(center=rect.center))

    def text(self, s: str, color: tuple[int, int, int], x: int, y: int, font=None) -> int:
        surf = (font or self.ui_font).render(s, True, color)
        self.screen.blit(surf, (x, y))
        return x + surf.get_width()

    # ------------------------------------------------------------------- HUD
    def _bar(self, x: int, y: int, w: int, frac: float, color, back) -> pygame.Rect:
        bar = pygame.Rect(x, y, w, 16)
        pygame.draw.rect(self.screen, back, bar)
        pygame.draw.rect(self.screen, color, (bar.x, bar.y, int(bar.w * max(0.0, min(1.0, frac))), bar.h))
        pygame.draw.rect(self.screen, S.WHITE, bar, 1)
        return bar

    def _hud(self, app: App, top: int = HUD_TOP) -> None:
        """Bars, stats and the last messages (the minimap is drawn separately)."""
        game = app.game
        p = game.player
        width = MINIMAP_RECT.x - 20  # text must stay clear of the minimap
        pygame.draw.rect(self.screen, (18, 18, 24), (0, top, S.SCREEN_W, S.HUD_H))
        pygame.draw.line(self.screen, S.GREY, (0, top), (S.SCREEN_W, top))

        frac = max(0, p.hp) / p.max_hp
        hp_color = S.RED if frac < 0.35 else S.GREEN
        if p.has("poisoned"):
            hp_color = (150, 200, 60)
        bar = self._bar(10, top + 8, 150, frac, hp_color, (60, 20, 20))
        x = self.text(f"HP {max(0, p.hp)}/{p.max_hp}", S.WHITE, bar.right + 6, top + 8)
        mana = self._bar(x + 14, top + 8, 90, p.mana / p.max_mana if p.max_mana else 0, S.BLUE, (20, 25, 60))
        x = self.text(f"MP {p.mana}/{p.max_mana}", S.WHITE, mana.right + 6, top + 8)
        floor = f"Floor {game.depth}" if game.endless else f"Floor {game.depth}/{S.MAX_DEPTH}"
        x = self.text(f"{floor} ({game.level.style})", S.CYAN, x + 16, top + 8)
        self.text(f"  Seed {game.seed}", S.DARK_GREY, x, top + 8, self.small_font)

        x = self.text(f"Lv {p.level} {p.cls.name}   XP {p.xp}/{p.xp_needed}   Gold {p.gold}   Kills {p.kills}"
                      f"   Turn {game.turns}", S.WHITE, 10, top + 30)
        self.text(f"   {game.options.label}", S.DARK_GREY, x, top + 30)
        self.text(f"ATK {p.power}  DEF {p.defense}  ACC {p.accuracy}%  EVA {p.evasion}%  CRIT {p.crit_chance}%"
                  f"  SP {p.spell_power}", S.GREY, 10, top + 50)
        # Conditions: hunger, statuses, unspent skill points.
        x = 10
        hunger = p.hunger_state
        if hunger:
            hunger_color = {"Satiated": S.GREEN, "Hungry": S.YELLOW, "Weak": S.ORANGE}.get(hunger, S.RED)
            x = self.text(hunger + "  ", hunger_color, x, top + 70)
        for name, st in p.statuses.items():
            x = self.text(f"{name.capitalize()} {st.turns}  ", STATUS_SPECS[name].color, x, top + 70)
        if p.skill_points:
            x = self.text(f"Skill points: {p.skill_points} (C)  ", S.YELLOW, x, top + 70)
        self.text(f"Arrows {p.arrows}   Pack {len(p.pack)}/20", S.GREY, max(x, 10), top + 70)
        gear = "   ".join(
            f"{label}: {game.item_name(it) if it else '-'}"
            for label, it in (("Wpn", p.weapon), ("Arm", p.armor), ("Bow", p.launcher), ("Ring", p.ring))
        )
        self.text(_clip(self.small_font, gear, width), S.GREY, 10, top + 91, self.small_font)
        self.text("I inv  Q quaff  R read  E eat  Z cast  C skills  J quests  T shoot  X look  M map  ? help",
                  (100, 100, 110), 10, top + 110, self.small_font)

        recent = game.log[-2:]
        for i, (msg, color) in enumerate(recent):
            self.text(_clip(self.ui_font, msg, width), color, 10, top + 130 + i * 19)

    def _minimap(self, app: App, cx: int, cy: int) -> None:
        rect = MINIMAP_RECT
        # Drawn at its true scale (matching click-to-inspect), on a blank frame.
        pygame.draw.rect(self.screen, MINIMAP_BACKGROUND, rect)
        self.screen.blit(self.minimap_image(app.game, S.MINIMAP_SCALE), rect.topleft)
        sc = S.MINIMAP_SCALE
        # Current viewport and (in look/aim mode) the cursor.
        pygame.draw.rect(self.screen, (120, 120, 140),
                         (rect.x + cx * sc, rect.y + cy * sc, S.VIEW_W * sc, S.VIEW_H * sc), 1)
        if app.mode in CURSOR_MODES:
            x, y = app.cursor
            pygame.draw.rect(self.screen, S.WHITE, (rect.x + x * sc - 2, rect.y + y * sc - 2, sc + 4, sc + 4), 1)
        pygame.draw.rect(self.screen, S.GREY, rect.inflate(2, 2), 1)

    # -------------------------------------------------------------- overlays
    def _panel(self, rect: pygame.Rect, alpha: int = 225) -> None:
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((12, 12, 20, alpha))
        self.screen.blit(overlay, rect.topleft)
        pygame.draw.rect(self.screen, S.GREY, rect, 1)

    def _info_panel(
        self, app: App, cy: int, title: str, title_color, lines, footer: str, corner: str = ""
    ) -> None:
        width = 560
        wrapped: list[tuple[str, tuple[int, int, int]]] = []
        for text, color in lines:
            wrapped.extend((part, color) for part in wrap(text, self.ui_font, width - 20))
        height = 34 + 19 * len(wrapped) + 22
        # Keep the panel on the opposite half of the screen from the cursor.
        cursor_sy = (app.cursor[1] - cy) * S.TILE
        y = VIEW_PX_H - height - 6 if cursor_sy < VIEW_PX_H // 2 else 34
        rect = pygame.Rect(6, y, width, height)
        self._panel(rect)
        self.text(title, title_color, rect.x + 10, rect.y + 8, self.ui_font)
        if corner:
            self.text(corner, S.DARK_GREY, rect.right - 150, rect.y + 8, self.small_font)
        for i, (text, color) in enumerate(wrapped):
            self.text(text, color, rect.x + 10, rect.y + 32 + i * 19)
        self.text(footer, S.DARK_GREY, rect.x + 10, rect.bottom - 20, self.small_font)

    def _look_panel(self, app: App, cx: int, cy: int) -> None:
        insp = app.inspection()
        state = knowledge(app.game, *app.cursor)
        self._info_panel(app, cy, insp.title, insp.color, insp.lines,
                         "move: cursor  Tab: next target  mouse: hover  Esc/X: done",
                         f"({app.cursor[0]},{app.cursor[1]}) {state}")

    def _aim_panel(self, app: App, cx: int, cy: int) -> None:
        plan = app.shot_plan()
        p = app.game.player
        lines: list[tuple[str, tuple[int, int, int]]] = []
        spell = SPELLS.get(app.aim)
        what = spell.name if spell else "Shoot"
        if not plan.ok:
            title, color = f"{what}: can't target that", S.RED
            lines.append((plan.reason, S.GREY))
        elif spell and spell.target == "tile":
            title, color = f"{what}: here", S.GREEN
            lines.append((f"Teleport {plan.dist} tiles.", S.GREY))
        elif plan.target or plan.area:
            t = plan.target
            title = f"{what}: the {t.name}" if t else f"{what}: this spot"
            color = S.GREEN
            lo, hi = plan.damage
            if spell and spell.target in ("bolt", "ball") and plan.hit >= 1:
                lines.append((f"Damage {lo}-{hi}; this spell never misses.", S.WHITE))
            elif spell and spell.target in ("bolt", "ball"):
                lines.append((f"Hit chance {plan.hit:.0%}, damage {lo}-{hi}.", S.WHITE))
            else:
                lines.append((f"Hit chance {plan.hit:.0%}, critical {plan.crit:.0%}, damage {lo}-{hi}.", S.WHITE))
            if plan.area:
                caught = [m.name for m in app.game.monsters if (m.x, m.y) in plan.area]
                lines.append((f"Blast hits: {', '.join(caught) or 'nothing'}.", S.ORANGE))
            if t:
                lines.append((f"It has {t.hp}/{t.max_hp} HP. Range {plan.dist}.", S.GREY))
        else:
            title, color = f"{what}: at the floor", S.YELLOW
            lines.append(("Nothing there to hit.", S.GREY))
        if spell:
            lines.append((f"Costs {spell.cost} mana (you have {p.mana}).", S.BLUE))
        else:
            bow = p.launcher.name if p.launcher else "no bow"
            lines.append((f"{bow}, {p.arrows} arrow{'s' if p.arrows != 1 else ''} left.", S.DARK_GREY))
        self._info_panel(app, cy, title, color, lines,
                         "move: aim  Tab: next target  Enter/click: confirm  Esc: cancel")

    # ------------------------------------------------------------- panels
    def _menu_panel(self, width: int, height: int) -> pygame.Rect:
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (VIEW_PX_W // 2, VIEW_PX_H // 2)
        self._panel(rect, alpha=245)
        return rect

    def _inventory_panel(self, app: App) -> None:
        g = app.game
        p = g.player
        titles = {None: "Inventory", "quaff": "Quaff which potion?", "read": "Read which scroll or tome?",
                  "eat": "Eat what?", "identify": "Identify which item?"}
        rect = self._menu_panel(880, 560)
        self.text(titles[app.inv_action], S.YELLOW, rect.x + 16, rect.y + 12)
        self.text(f"Pack {len(p.pack)}/20   Arrows {p.arrows}   Gold {p.gold}", S.GREY, rect.right - 290,
                  rect.y + 12)
        entries = app.inventory_entries()
        y = rect.y + 44
        for i, item in enumerate(entries):
            selected = item is app.inv_selected
            if selected:
                pygame.draw.rect(self.screen, (40, 40, 60), (rect.x + 8, y - 2, 420, 22))
            icon = self.item_surface(g, item, 20)
            if icon is not None and app.use_sprites:
                self.screen.blit(icon, (rect.x + 38, y))
            else:
                self.text(item.glyph, g.item_color(item), rect.x + 42, y)
            name = g.item_name(item)
            if p.equipped(item):
                how = {"weapon": "wielded", "launcher": "readied"}.get(item.kind, "worn")
                name += f"  ({how})"
            self.text(f"{chr(ord('a') + i)})", S.GREY, rect.x + 14, y)
            self.text(_clip(self.ui_font, name, 360), g.item_color(item), rect.x + 64, y)
            y += 22
        if not entries:
            self.text("(empty)", S.DARK_GREY, rect.x + 16, y)
        # Details of the selected item.
        if app.inv_selected is not None:
            item = app.inv_selected
            dx = rect.x + 450
            big = self.item_surface(g, item, 48)
            if big is not None and app.use_sprites:
                self.screen.blit(big, (dx, rect.y + 44))
            name = g.item_name(item)
            yy = rect.y + 100
            for line in wrap(name[:1].upper() + name[1:], self.ui_font, 410):
                self.text(line, g.item_color(item), dx, yy)
                yy += 20
            yy += 6
            for text, color in item_lines(g, item):
                for part in wrap(text, self.small_font, 410):
                    self.text(part, color, dx, yy, self.small_font)
                    yy += 17
            verb = {"potion": "quaff", "scroll": "read", "food": "eat", "book": "study"}.get(item.kind, "")
            if item.is_gear:
                verb = "take off" if p.equipped(item) else "equip"
            actions = f"u: {verb}   d: drop   Esc: back" if verb else "d: drop   Esc: back"
            self.text(actions, S.CYAN, dx, rect.bottom - 40)
        footer = ("letter: choose" if app.inv_action else "letter: select an item") + "   Esc: close"
        self.text(footer, S.DARK_GREY, rect.x + 16, rect.bottom - 22, self.small_font)

    def _character_panel(self, app: App) -> None:
        g = app.game
        p = g.player
        rect = self._menu_panel(900, 570)
        self.text(f"{p.cls.name}, level {p.level}", p.cls.color, rect.x + 16, rect.y + 12)
        self.text(f"Skill points: {p.skill_points}", S.YELLOW if p.skill_points else S.GREY,
                  rect.right - 200, rect.y + 12)
        stats = [
            f"HP {p.hp}/{p.max_hp}    Mana {p.mana}/{p.max_mana}",
            f"XP {p.xp}/{p.xp_needed}",
            f"Attack {p.power}   Ranged {p.ranged_power}",
            f"Defense {p.defense}   Evasion {p.evasion}%",
            f"Accuracy {p.accuracy}% (bow {p.ranged_accuracy}%)",
            f"Critical {p.crit_chance}% (bow {p.ranged_crit}%)",
            f"Spell power {p.spell_power}",
            f"Hunger: {p.hunger_state or 'not hungry'} ({p.satiation})",
        ]
        for i, line in enumerate(stats):
            self.text(line, S.WHITE, rect.x + 16, rect.y + 48 + i * 21, self.small_font)
        spells = app.known_spells()
        y = rect.y + 48 + len(stats) * 21 + 14
        self.text("Spells & abilities", S.CYAN, rect.x + 16, y)
        for i, key in enumerate(spells):
            spell = SPELLS[key]
            self.text(f"{spell.name} (rank {p.spells[key]}, {spell.cost} mana)", S.GREY, rect.x + 16,
                      y + 22 + i * 18, self.small_font)
        if not spells:
            self.text("none yet", S.DARK_GREY, rect.x + 16, y + 22, self.small_font)
        # Skill tree: two branches side by side, four tiers each.
        keys = [k for _, branch in p.cls.branches for k in branch]
        selected = keys[app.char_index % len(keys)]
        for b, (branch_name, branch) in enumerate(p.cls.branches):
            bx = rect.x + 330 + b * 280
            self.text(branch_name, S.YELLOW, bx, rect.y + 48)
            for tier, key in enumerate(branch):
                skill = SKILLS[key]
                rank = p.skills.get(key, 0)
                ok, _why = g.skill_status(key)
                box = pygame.Rect(bx, rect.y + 78 + tier * 76, 256, 60)
                color = S.GREEN if rank else (S.WHITE if ok else S.DARK_GREY)
                pygame.draw.rect(self.screen, (30, 30, 44), box)
                pygame.draw.rect(self.screen, S.YELLOW if key == selected else (70, 70, 90), box,
                                 2 if key == selected else 1)
                self.text(f"{skill.name}", color, box.x + 8, box.y + 6)
                self.text(f"{rank}/{skill.max_rank}", color, box.right - 40, box.y + 6)
                self.text(f"lvl {TIER_LEVELS[tier]}" + ("  [active]" if skill.spell else ""),
                          S.DARK_GREY, box.x + 8, box.y + 30, self.small_font)
                if tier < 3:
                    pygame.draw.line(self.screen, (70, 70, 90), (box.centerx, box.bottom),
                                     (box.centerx, box.bottom + 16))
        skill = SKILLS[selected]
        ok, why = g.skill_status(selected)
        desc_y = rect.bottom - 112
        self.text(skill.name, S.YELLOW, rect.x + 330, desc_y)
        detail = skill.description
        if skill.spell:
            rank = max(1, p.skills.get(selected, 0))
            detail += " " + describe_spell(skill.spell, rank, p.spell_power)
        for i, line in enumerate(wrap(detail, self.small_font, 550)[:2]):
            self.text(line, S.WHITE, rect.x + 330, desc_y + 22 + i * 17, self.small_font)
        self.text("Enter: learn a rank" if ok else why, S.GREEN if ok else S.GREY, rect.x + 330, desc_y + 58,
                  self.small_font)
        self.text("Up/Down: choose   Left/Right: other branch   Enter: learn   Esc: close", S.DARK_GREY,
                  rect.x + 16, rect.bottom - 22, self.small_font)

    def _pause_panel(self, app: App) -> None:
        g = app.game
        rect = self._menu_panel(520, 120 + 34 * len(PAUSE_ROWS))
        self.text("Paused", S.YELLOW, rect.x + 20, rect.y + 14)
        self.text(f"Seed {g.seed}", S.CYAN, rect.right - 20 - self.ui_font.size(f"Seed {g.seed}")[0], rect.y + 14)
        for i, label in enumerate(PAUSE_ROWS):
            y = rect.y + 52 + i * 34
            if i == app.pause_index:
                pygame.draw.rect(self.screen, (40, 40, 60), (rect.x + 12, y - 5, rect.w - 24, 28))
                pygame.draw.rect(self.screen, S.YELLOW, (rect.x + 12, y - 5, rect.w - 24, 28), 1)
            self.text(label, S.YELLOW if i == app.pause_index else S.WHITE, rect.x + 28, y)
        hint = app.notice or f"Share this run: {replay_command(g)}"
        for i, line in enumerate(wrap(hint, self.small_font, rect.w - 40)[:2]):
            self.text(line, S.GREEN if app.notice else S.DARK_GREY, rect.x + 20, rect.bottom - 48 + i * 17,
                      self.small_font)

    def _slots_panel(self, app: App) -> None:
        rect = self._menu_panel(760, 230)
        verb = "Save to" if app.slot_action == "save" else "Load from"
        self.text(f"{verb} which slot?", S.YELLOW, rect.x + 20, rect.y + 14)
        for i, slot in enumerate(saves.SLOTS):
            info = saves.read_info(slot)
            y = rect.y + 52 + i * 40
            if info is None:
                text, color = "(empty)", S.DARK_GREY
            elif not info.compatible:
                text, color = f"(from an incompatible version) {info.saved_at}", S.RED
            else:
                text, color = info.summary, S.WHITE
            if app.slot_action == "save" and info is not None:
                text += "  - overwrite"
            self.text(f"{slot})", S.CYAN, rect.x + 20, y)
            self.text(_clip(self.small_font, text, rect.w - 80), color, rect.x + 50, y + 2, self.small_font)
        footer = app.notice or "1-3: choose a slot   Esc: back"
        self.text(footer, S.RED if app.notice else S.DARK_GREY, rect.x + 20, rect.bottom - 26, self.small_font)

    def _journal_panel(self, app: App) -> None:
        g = app.game
        quests = g.quests
        rect = self._menu_panel(760, 100 + 64 * max(1, len(quests)))
        self.text("Journal", S.YELLOW, rect.x + 20, rect.y + 14)
        if not quests:
            self.text("No quests yet. Guild envoys (yellow @) have work for you.", S.DARK_GREY, rect.x + 20,
                      rect.y + 52)
        for i, q in enumerate(quests):
            y = rect.y + 50 + i * 64
            done = q.state == "rewarded"
            self.text(q.title, S.DARK_GREY if done else S.WHITE, rect.x + 20, y)
            self.text(f"floor {q.depth}, from {q.giver.name}", S.GREY, rect.right - 230, y, self.small_font)
            self.text(q.status(g.player), S.GREEN if q.is_done(g.player) else S.CYAN, rect.x + 36, y + 22,
                      self.small_font)
        self.text("J or Esc: close", S.DARK_GREY, rect.x + 20, rect.bottom - 26, self.small_font)

    def _spells_panel(self, app: App) -> None:
        g = app.game
        p = g.player
        spells = app.known_spells()
        rect = self._menu_panel(640, 90 + 46 * len(spells))
        self.text("Cast which spell or ability?", S.YELLOW, rect.x + 16, rect.y + 12)
        self.text(f"Mana {p.mana}/{p.max_mana}", S.BLUE, rect.right - 150, rect.y + 12)
        for i, key in enumerate(spells):
            spell = SPELLS[key]
            rank = p.spells[key]
            y = rect.y + 46 + i * 46
            usable = p.mana >= spell.cost
            self.text(f"{chr(ord('a') + i)})  {spell.name}  (rank {rank})", S.WHITE if usable else S.DARK_GREY,
                      rect.x + 16, y)
            self.text(f"{spell.cost} mana", S.BLUE if usable else S.DARK_GREY, rect.right - 110, y)
            self.text(describe_spell(key, rank, p.spell_power), S.GREY, rect.x + 46, y + 20, self.small_font)
        self.text("letter: cast   Esc: close", S.DARK_GREY, rect.x + 16, rect.bottom - 22, self.small_font)

    def _big_map(self, app: App) -> None:
        self._panel(pygame.Rect(0, 0, VIEW_PX_W, VIEW_PX_H), alpha=240)
        game = app.game
        self.text(f"Floor {game.depth} map ({game.level.style}) - click a tile to inspect it, M to close",
                  S.WHITE, BIGMAP_RECT.x, BIGMAP_RECT.y - 24)
        pygame.draw.rect(self.screen, MINIMAP_BACKGROUND, BIGMAP_RECT)
        self.screen.blit(self.minimap_image(game, S.BIGMAP_SCALE), BIGMAP_RECT.topleft)
        legend = [("you", S.YELLOW), ("monster", S.RED), ("npc", S.GREEN), ("stairs", S.CYAN),
                  ("door", S.BROWN), ("lock", S.YELLOW), ("lever", (220, 220, 230)), ("shrine", S.CYAN),
                  ("water", (80, 140, 230)), ("fountain", S.BLUE), ("chest", S.AMBER), ("trap", S.RED)]
        x = BIGMAP_RECT.x
        for name, color in legend:
            pygame.draw.rect(self.screen, color, (x, BIGMAP_RECT.bottom + 8, 10, 10))
            self.text(name, S.GREY, x + 14, BIGMAP_RECT.bottom + 5, self.small_font)
            x += 24 + self.small_font.size(name)[0]

    def _help(self) -> None:
        key_x = 16 + max(self.ui_font.size(what)[0] for what, _ in HELP_LINES) + 30
        width = key_x + max(self.ui_font.size(keys)[0] for _, keys in HELP_LINES) + 20
        rect = pygame.Rect(0, 0, width, 60 + 24 * len(HELP_LINES))
        rect.center = (VIEW_PX_W // 2, VIEW_PX_H // 2)
        self._panel(rect, alpha=240)
        self.text("Controls (any key to close)", S.YELLOW, rect.x + 16, rect.y + 14)
        for i, (what, keys) in enumerate(HELP_LINES):
            self.text(what, S.WHITE, rect.x + 16, rect.y + 46 + i * 24)
            self.text(keys, S.CYAN, rect.x + key_x, rect.y + 46 + i * 24)

    def _dialogue(self, game: Game) -> None:
        d = game.dialogue
        assert d is not None
        width = 600
        text_lines = wrap(d.text, self.ui_font, width - 32)
        rect = pygame.Rect(0, 0, width, 70 + 20 * len(text_lines) + 22 * len(d.options))
        rect.center = (VIEW_PX_W // 2, VIEW_PX_H // 2)
        self._panel(rect, alpha=245)
        self.text(d.npc.display_name, d.npc.color, rect.x + 16, rect.y + 12)
        self.text(f"Gold: {game.player.gold}", S.YELLOW, rect.right - 110, rect.y + 12)
        y = rect.y + 40
        for line in text_lines:
            self.text(line, S.WHITE, rect.x + 16, y)
            y += 20
        y += 8
        for i, opt in enumerate(d.options):
            self.text(f"{i + 1}) {opt.label}", S.WHITE if opt.enabled else S.DARK_GREY, rect.x + 24, y)
            y += 22

    def _banner(self, title: str, color: tuple[int, int, int], app: App) -> None:
        overlay = pygame.Surface((S.SCREEN_W, S.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))
        t = self.big_font.render(title, True, color)
        self.screen.blit(t, t.get_rect(center=(S.SCREEN_W // 2, S.SCREEN_H // 2 - 60)))
        for i, (line, c) in enumerate(banner_lines(app)):
            s = self.ui_font.render(line, True, c)
            self.screen.blit(s, s.get_rect(center=(S.SCREEN_W // 2, S.SCREEN_H // 2 - 10 + i * 26)))

    # ---------------------------------------------------------- title screen
    def _title_screen(self, app: App) -> None:
        self.screen.fill((10, 10, 16))
        cx = S.SCREEN_W // 2
        title = self.big_font.render("ROGUE GAME", True, S.YELLOW)
        self.screen.blit(title, title.get_rect(center=(cx, 70)))
        # A parade of the cast.
        cast = ["player", "warrior", "ranger", "mage", "rat", "goblin", "jackal", "bat", "goblin archer",
                "cave spider", "goblin shaman", "orc", "ogre", "troll", "orc warlord", "lich"]
        size = 40
        x0 = cx - len(cast) * (size + 6) // 2
        for i, key in enumerate(cast):
            sprite = self.sprites.get(key)
            if sprite is not None:
                self.screen.blit(pygame.transform.scale(sprite, (size, size)), (x0 + i * (size + 6), 110))

        o = app.menu_options
        rows = [
            ("Mode", o.mode.capitalize(), MODE_DESCRIPTIONS[o.mode]),
            ("Difficulty", o.difficulty.capitalize(), DIFFICULTIES[o.difficulty].description),
            ("Class", CLASSES[o.player_class].name, CLASSES[o.player_class].description),
            ("Seed", (app.seed_text + ("_" if app.editing_seed else "")) or "random",
             "Enter to type a seed (a number or any word) - share it to share a dungeon. Backspace: random."
             if app.menu_rows()[min(app.menu_index, len(app.menu_rows()) - 1)] == "seed" else ""),
            ("Start game", "", ""),
        ]
        if "load" in app.menu_rows():
            rows.append(("Load game", "", ""))
        y = 176
        for i, (label, value, desc) in enumerate(rows):
            selected = i == app.menu_index
            rect = pygame.Rect(cx - 300, y - 6, 600, 34)
            if selected:
                pygame.draw.rect(self.screen, (40, 40, 60), rect)
                pygame.draw.rect(self.screen, S.YELLOW, rect, 1)
            color = S.YELLOW if selected else S.WHITE
            if value:
                self.text(label, color, rect.x + 16, y)
                shown = value if label == "Seed" else f"<  {value}  >"
                self.text(shown, S.CYAN if selected else S.GREY, rect.x + 220, y)
            else:
                t = self.ui_font.render(label, True, color)
                self.screen.blit(t, t.get_rect(center=rect.center))
            y += 36
            if desc:
                for line in wrap(desc, self.small_font, 560):
                    self.text(line, S.DARK_GREY, rect.x + 16, y - 8, self.small_font)
                    y += 17
                y += 6

        y += 14
        self.text(f"Best runs - {o.label}", S.WHITE, cx - 300, y)
        y += 26
        table = app.scores.top(o) if app.scores else []
        if not table:
            self.text("No runs yet. Be the first!", S.DARK_GREY, cx - 300, y)
        for i, e in enumerate(table[:5]):
            outcome = "VICTORY" if e.outcome == "won" else e.outcome
            seed = f"  seed {e.seed}" if e.seed is not None else ""
            self.text(_clip(self.small_font, f"{i + 1}. {e.score:>6}   floor {e.depth:<3} lv {e.level:<3} "
                            f"{CLASSES[e.player_class].name:<10} {outcome}{seed}", 620),
                      S.YELLOW if i == 0 else S.GREY, cx - 300, y + i * 20, self.small_font)
        help_line = "Up/Down: choose   Left/Right: change   Enter: start   Esc: quit"
        t = self.small_font.render(help_line, True, S.DARK_GREY)
        self.screen.blit(t, t.get_rect(center=(cx, S.SCREEN_H - 24)))


MINIMAP_BACKGROUND = (10, 10, 14)


def paint_minimap(mm: Minimap, scale: int) -> pygame.Surface:
    """Render a minimap model as an image, ``scale`` pixels per tile."""
    w, h = mm.width, mm.height
    pixels = bytearray(bytes(MINIMAP_BACKGROUND) * (w * h))
    for y, row in enumerate(mm.cells):
        base = y * w * 3
        for x, color in enumerate(row):
            if color is not None:
                i = base + x * 3
                pixels[i:i + 3] = bytes(color)
    native = pygame.image.frombuffer(bytes(pixels), (w, h), "RGB")
    image = pygame.transform.scale(native, (w * scale, h * scale))
    pad = 1 if scale < 6 else 0
    for (x, y), color in mm.markers:
        pygame.draw.rect(image, color, (x * scale - pad, y * scale - pad, scale + 2 * pad, scale + 2 * pad))
    return image


def banner_lines(app: App) -> list[tuple[str, tuple[int, int, int]]]:
    """The text under "YOU DIED" / "VICTORY!": how it went, the score, and
    the seed with the command to replay it."""
    game = app.game
    p = game.player
    lines: list[tuple[str, tuple[int, int, int]]] = []
    if game.death_cause:
        lines.append((game.death_cause.capitalize(), S.WHITE))
    lines.append((f"{game.options.label}   Deepest floor {game.deepest}   Level {p.level}   "
                  f"Kills {p.kills}   Turns {game.turns}", S.WHITE))
    score = f"Score {game.score}"
    if app.rank == 1:
        score += "  -  NEW BEST!"
    elif app.rank:
        score += f"  -  #{app.rank} on the {game.options.label} table"
    lines.append((score, S.YELLOW))
    lines.append((f"Seed {game.seed}  -  replay it: {replay_command(game)}", S.CYAN))
    lines.append(("R: play again   Enter: title screen   Esc: menu", S.GREY))
    return lines


def _clip(font: pygame.font.Font, text: str, width: int) -> str:
    """Shorten ``text`` with an ellipsis so it renders within ``width`` px."""
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "...")[0] > width:
        text = text[:-1]
    return text + "..."


def _dim(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(c * 5 // 10 for c in color)  # type: ignore[return-value]


def wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
    """Greedy word-wrap of ``text`` so each line renders within ``width`` px."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if font.size(candidate)[0] <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def run(options: GameOptions | None = None, seed: int | None = None, menu: bool = True) -> None:
    """Open the window and play. With ``menu`` the title screen comes first
    (pre-set to ``options``); otherwise a game starts immediately."""
    pygame.init()
    pygame.display.set_caption("Rogue Game")
    screen = pygame.display.set_mode((S.SCREEN_W, S.SCREEN_H))
    pygame.key.set_repeat(220, 70)
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    app = App(seed=seed, options=options, menu=menu, scores=ScoreBoard())

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                running = app.handle_key(event.key, event.unicode, event.mod)
            elif event.type == pygame.MOUSEMOTION:
                app.handle_mouse_motion(event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                app.handle_click(event.pos, event.button)
        renderer.draw(app)
        pygame.display.flip()
        clock.tick(S.FPS)
    pygame.quit()
