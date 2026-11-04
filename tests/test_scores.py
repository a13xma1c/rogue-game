"""The high-score table."""

import json
import os
import sys

import pytest

from roguegame.difficulty import ENDLESS, GameOptions
from roguegame.game import Game, State
from roguegame.scores import MAX_ENTRIES, ScoreBoard, default_path, entry_for, table_key


def finished(score_gold: int, options: GameOptions | None = None, depth: int = 1, won: bool = False) -> Game:
    """A finished game whose score is driven by its gold."""
    g = Game(seed=1, options=options)
    for d in range(2, depth + 1):
        g.levels[d] = g.levels[1]
    g.player.gold = score_gold
    if won:
        g.state = State.WON
    else:
        g._player_died("killed by a test")
    return g


def test_default_path_respects_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ROGUEGAME_DATA", str(tmp_path))
    assert default_path() == tmp_path / "scores.json"


def test_default_path_per_platform(monkeypatch, tmp_path):
    monkeypatch.delenv("ROGUEGAME_DATA", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_path() == tmp_path / "roguegame" / "scores.json"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert default_path() == tmp_path / "roaming" / "roguegame" / "scores.json"


def test_entry_for_a_run():
    e = entry_for(finished(123, depth=4))
    assert e.depth == 4 and e.outcome == "killed by a test"
    assert e.score == 3 * 250 + 1 * 25 + 123  # three floors down, level 1, 123 gold
    assert entry_for(finished(0, won=True)).outcome == "won"


def test_record_ranks_and_persists(tmp_path):
    path = tmp_path / "s.json"
    board = ScoreBoard(path)
    assert board.record(finished(100)) == 1
    assert board.record(finished(300)) == 1
    assert board.record(finished(200)) == 2
    assert [e.score for e in board.top(GameOptions())] == sorted((e.score for e in board.top(GameOptions())),
                                                                 reverse=True)
    reloaded = ScoreBoard(path)
    assert [e.score for e in reloaded.top(GameOptions())] == [e.score for e in board.top(GameOptions())]
    assert reloaded.best(GameOptions()).score == board.top(GameOptions())[0].score


def test_tables_are_kept_per_mode_and_difficulty(tmp_path):
    board = ScoreBoard(tmp_path / "s.json")
    hard_endless = GameOptions(ENDLESS, "hard")
    board.record(finished(100))
    board.record(finished(100, hard_endless))
    assert len(board.top(GameOptions())) == 1 and len(board.top(hard_endless)) == 1
    assert board.top(GameOptions(ENDLESS, "easy")) == [] and board.best(GameOptions(ENDLESS, "easy")) is None
    assert table_key(hard_endless) == "endless/hard"
    data = json.loads((tmp_path / "s.json").read_text())
    assert set(data) == {"classic/normal", "endless/hard"}


def test_only_the_top_ten_are_kept(tmp_path):
    board = ScoreBoard(tmp_path / "s.json")
    for gold in range(100, 100 + 10 * MAX_ENTRIES, 10):
        board.record(finished(gold))
    assert board.record(finished(0)) is None, "too low to make the table"
    assert len(board.top(GameOptions())) == MAX_ENTRIES
    assert board.record(finished(10_000)) == 1
    assert len(board.top(GameOptions())) == MAX_ENTRIES


@pytest.mark.parametrize("content", ["not json", "[1, 2, 3]", '{"classic/normal": [{"bogus": 1}]}'])
def test_corrupt_files_start_fresh(tmp_path, content):
    path = tmp_path / "s.json"
    path.write_text(content)
    board = ScoreBoard(path)
    assert board.top(GameOptions()) == []
    assert board.record(finished(50)) == 1
    assert ScoreBoard(path).best(GameOptions()) is not None, "and the file is repaired"


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as a normal user")
def test_unwritable_location_does_not_crash(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        board = ScoreBoard(locked / "sub" / "s.json")
        assert board.record(finished(50)) == 1, "the run still ranks for this session"
        assert board.save() is False
    finally:
        locked.chmod(0o700)


def test_entries_remember_the_class_and_old_files_still_load(tmp_path):
    board = ScoreBoard(tmp_path / "s.json")
    g = Game(seed=1, options=GameOptions(player_class="mage"))
    g._player_died("killed by a test")
    board.record(g)
    assert board.best(g.options).player_class == "mage"
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"classic/normal": [
        {"score": 5, "depth": 1, "level": 1, "kills": 0, "turns": 9, "outcome": "won", "date": ""}]}))
    assert ScoreBoard(old).best(GameOptions()).player_class == "adventurer"


def test_entries_remember_the_seed(tmp_path):
    board = ScoreBoard(tmp_path / "s.json")
    g = Game(seed=8675309)
    g._player_died("killed by a test")
    board.record(g)
    assert ScoreBoard(tmp_path / "s.json").best(g.options).seed == 8675309
