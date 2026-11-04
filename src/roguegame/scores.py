"""High scores, kept per mode and difficulty in a small JSON file.

Failures to read or write the file (corrupt JSON, read-only disk, ...) never
interrupt play: the table simply starts empty or isn't saved.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .difficulty import GameOptions
    from .game import Game

MAX_ENTRIES = 10


@dataclass
class ScoreEntry:
    score: int
    depth: int
    level: int
    kills: int
    turns: int
    outcome: str  # "won", or how the run ended ("killed by an ogre")
    date: str = ""
    player_class: str = "adventurer"  # (older score files predate classes)
    seed: int | None = None  # (and seeds) - lets you replay or share a great run


def default_path() -> Path:
    """Where scores live: $ROGUEGAME_DATA, else the platform's user data dir."""
    if override := os.environ.get("ROGUEGAME_DATA"):
        return Path(override) / "scores.json"
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "roguegame" / "scores.json"


def table_key(options: GameOptions) -> str:
    return f"{options.mode}/{options.difficulty}"


def entry_for(game: Game) -> ScoreEntry:
    from .game import State

    p = game.player
    outcome = "won" if game.state is State.WON else (game.death_cause or "gave up")
    return ScoreEntry(game.score, game.deepest, p.level, p.kills, game.turns, outcome,
                      time.strftime("%Y-%m-%d"), p.cls.key, game.seed)


class ScoreBoard:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()
        self.tables: dict[str, list[ScoreEntry]] = self._load()

    def _load(self) -> dict[str, list[ScoreEntry]]:
        try:
            raw = json.loads(self.path.read_text())
            return {
                key: [ScoreEntry(**entry) for entry in entries][:MAX_ENTRIES]
                for key, entries in raw.items()
            }
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    def top(self, options: GameOptions) -> list[ScoreEntry]:
        return self.tables.get(table_key(options), [])

    def best(self, options: GameOptions) -> ScoreEntry | None:
        table = self.top(options)
        return table[0] if table else None

    def record(self, game: Game) -> int | None:
        """Add a finished run. Returns its 1-based rank, or None if it didn't
        make the table."""
        entry = entry_for(game)
        table = self.tables.setdefault(table_key(game.options), [])
        table.append(entry)
        table.sort(key=lambda e: (-e.score, -e.depth, e.turns))
        rank = table.index(entry) + 1
        del table[MAX_ENTRIES:]
        self.save()
        return rank if rank <= MAX_ENTRIES else None

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {key: [asdict(e) for e in entries] for key, entries in self.tables.items()}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1))
            tmp.replace(self.path)  # atomic: a crash mid-write can't corrupt the table
            return True
        except OSError:
            return False
