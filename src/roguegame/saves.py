"""Saving and loading games.

A save file is one line of JSON (the header: format version, a summary for
the load menu, and a checksum) followed by the zlib-compressed pickle of the
whole :class:`~roguegame.game.Game`. The header can be read without
unpickling anything, so listing saves is cheap and safe; the payload is only
unpickled after the version and checksum match.

Saves live in ``<data dir>/saves/slot<N>.sav`` (see :mod:`roguegame.scores`
for where the data dir is). Note that, like any pickle, a save file should
only be loaded if you trust where it came from - these are your own saves.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .scores import default_path

if TYPE_CHECKING:
    from .game import Game

MAGIC = "ROGUEGAME-SAVE"
SAVE_VERSION = 2  # bump whenever the game's classes change incompatibly (2: FOV cache, revisions)
SLOTS = (1, 2, 3)


class SaveError(Exception):
    """A save file couldn't be written or read."""


@dataclass
class SaveInfo:
    slot: int
    path: Path
    version: int
    saved_at: str
    seed: int
    mode: str
    difficulty: str
    player_class: str
    depth: int
    level: int
    turns: int

    @property
    def compatible(self) -> bool:
        return self.version == SAVE_VERSION

    @property
    def summary(self) -> str:
        return (f"{self.player_class.capitalize()} lv {self.level}, floor {self.depth}, turn {self.turns}  "
                f"({self.mode} / {self.difficulty})  seed {self.seed}  {self.saved_at}")


def save_dir() -> Path:
    return default_path().parent / "saves"


def slot_path(slot: int) -> Path:
    return save_dir() / f"slot{slot}.sav"


def save_game(game: Game, slot: int) -> Path:
    """Write ``game`` to ``slot``. Raises SaveError if it can't."""
    if slot not in SLOTS:
        raise SaveError(f"no such slot: {slot}")
    payload = zlib.compress(pickle.dumps(game, protocol=pickle.HIGHEST_PROTOCOL), 6)
    header = {
        "magic": MAGIC,
        "version": SAVE_VERSION,
        "saved_at": time.strftime("%Y-%m-%d %H:%M"),
        "seed": game.seed,
        "mode": game.options.mode,
        "difficulty": game.options.difficulty,
        "player_class": game.options.player_class,
        "depth": game.depth,
        "level": game.player.level,
        "turns": game.turns,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    path = slot_path(slot)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(json.dumps(header).encode() + b"\n" + payload)
        tmp.replace(path)  # atomic: a crash mid-save never destroys the old save
    except OSError as e:
        raise SaveError(f"couldn't write {path}: {e}") from e
    return path


def _read(path: Path) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise SaveError(f"couldn't read {path}: {e}") from e
    head, sep, payload = raw.partition(b"\n")
    try:
        header = json.loads(head)
    except ValueError as e:
        raise SaveError("not a save file") from e
    if not sep or not isinstance(header, dict) or header.get("magic") != MAGIC:
        raise SaveError("not a save file")
    return header, payload


def read_info(slot: int) -> SaveInfo | None:
    """Summary of the save in ``slot``, or None if the slot is empty/unreadable."""
    path = slot_path(slot)
    if not path.exists():
        return None
    try:
        h, _ = _read(path)
        return SaveInfo(slot, path, int(h["version"]), str(h["saved_at"]), int(h["seed"]), str(h["mode"]),
                        str(h["difficulty"]), str(h["player_class"]), int(h["depth"]), int(h["level"]),
                        int(h["turns"]))
    except (SaveError, KeyError, TypeError, ValueError):
        return None


def list_saves() -> list[SaveInfo]:
    return [info for slot in SLOTS if (info := read_info(slot)) is not None]


def load_game(slot: int) -> Game:
    """Load the game in ``slot``. Raises SaveError if it's missing, from an
    incompatible version, or damaged."""
    from .game import Game

    path = slot_path(slot)
    if not path.exists():
        raise SaveError(f"slot {slot} is empty")
    header, payload = _read(path)
    if header.get("version") != SAVE_VERSION:
        raise SaveError(f"save is from an incompatible version ({header.get('version')} != {SAVE_VERSION})")
    if hashlib.sha256(payload).hexdigest() != header.get("sha256"):
        raise SaveError("save file is damaged (checksum mismatch)")
    try:
        game = pickle.loads(zlib.decompress(payload))
    except Exception as e:  # noqa: BLE001 - any unpickling failure means a bad save
        raise SaveError(f"save file is damaged: {e}") from e
    if not isinstance(game, Game):
        raise SaveError("save file doesn't contain a game")
    game.fx.clear()  # stale animations
    return game


def delete_save(slot: int) -> None:
    slot_path(slot).unlink(missing_ok=True)
