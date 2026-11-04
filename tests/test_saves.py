"""Saving and loading games."""

import json
import os
import random

import pygame
import pytest

from roguegame import saves
from roguegame.difficulty import GameOptions
from roguegame.game import Game, State
from roguegame.saves import SAVE_VERSION, SaveError, list_saves, load_game, read_info, save_game, slot_path

from conftest import slay_boss


def play(g: Game, rng: random.Random, actions: int) -> None:
    """A deterministic little bot: wander, fight, wait, use stairs."""
    from roguegame.dungeon import DIRS8
    from roguegame.tiles import STAIRS_DOWN

    for _ in range(actions):
        if g.state is not State.PLAYING:
            return
        if g.dialogue:
            g.close_dialogue()
        if g.map.tile(g.player.x, g.player.y) == STAIRS_DOWN and rng.random() < 0.5:
            g.use_stairs()
        elif rng.random() < 0.1:
            g.wait()
        else:
            g.player_move(*rng.choice(DIRS8))


def snapshot(g: Game) -> tuple:
    p = g.player
    return (g.turns, g.depth, p.x, p.y, p.hp, p.xp, p.gold, p.satiation, len(p.pack), sorted(g.levels),
            [(m.name, m.x, m.y, m.hp) for m in g.monsters], g.log[-5:], g.rng.random())


# -------------------------------------------------------------- round trip
def test_round_trip_preserves_everything():
    g = Game(seed=3, options=GameOptions("endless", "hard", "mage"))
    play(g, random.Random(1), 200)
    save_game(g, 1)
    h = load_game(1)
    assert snapshot(h)[:-1] == snapshot(g)[:-1]
    assert h.options == g.options and h.seed == g.seed
    assert [lvl.map.tiles for lvl in h.levels.values()] == [lvl.map.tiles for lvl in g.levels.values()]
    assert [lvl.map.explored for lvl in h.levels.values()] == [lvl.map.explored for lvl in g.levels.values()]
    assert h.ident.known == g.ident.known and h.ident.potion_looks == g.ident.potion_looks
    assert h.player.spells == g.player.spells


def test_a_loaded_game_continues_exactly_like_the_original():
    """Save, load, and keep playing: identical to never having saved - the
    random number generator comes along too."""
    original = Game(seed=8)
    play(original, random.Random(2), 150)
    save_game(original, 2)
    loaded = load_game(2)
    play(original, random.Random(3), 300)
    play(loaded, random.Random(3), 300)
    assert snapshot(loaded) == snapshot(original)


def test_object_identity_survives_a_save():
    """Quests point at NPCs, relics and champions; bosses at monsters in the
    level's list. Those links must still be the same objects after loading."""
    from roguegame.level import build_level, level_rng

    seed = next(s for s in range(200) if (q := build_level(1, level_rng(s, 1)).quest) and q.kind == "slay")
    g = Game(seed=seed)
    quest = g.level.quest
    save_game(g, 1)
    h = load_game(1)
    q = h.level.quest
    assert q.giver in h.npcs and q.target in h.monsters
    while h.depth < 3:  # floor 3's boss is alive when we arrive
        slay_boss(h)
        h.player.x, h.player.y = h.level.down_stairs
        h.use_stairs()
    save_game(h, 2)
    k = load_game(2)
    assert any(m is k.level.boss for m in k.monsters), "the boss is the very monster in the list"
    assert k.level.sealed
    slay_boss(k)
    assert not k.level.sealed, "killing it after loading unseals the stairs"
    assert quest is not q, "a real copy, not the same object"


def test_loaded_games_have_no_stale_animations():
    g = Game(seed=1)
    from roguegame.entities import Fx

    g.fx.append(Fx("text", [(1, 1)], "x"))
    save_game(g, 1)
    assert load_game(1).fx == []


# ----------------------------------------------------------------- slots
def test_slots_and_listing():
    assert list_saves() == [] and read_info(2) is None
    save_game(Game(seed=5, options=GameOptions(player_class="ranger")), 2)
    infos = list_saves()
    assert [i.slot for i in infos] == [2]
    info = infos[0]
    assert (info.seed, info.player_class, info.depth, info.version) == (5, "ranger", 1, SAVE_VERSION)
    assert info.compatible and "seed 5" in info.summary and "Ranger" in info.summary
    save_game(Game(seed=6), 2)  # overwriting is allowed
    assert read_info(2).seed == 6
    saves.delete_save(2)
    assert list_saves() == []


def test_bad_slots_and_empty_slots():
    with pytest.raises(SaveError):
        save_game(Game(seed=1), 9)
    with pytest.raises(SaveError, match="empty"):
        load_game(3)


def test_saves_live_in_the_data_dir():
    assert str(slot_path(1)).startswith(os.environ["ROGUEGAME_DATA"])


# -------------------------------------------------------- damaged saves
def test_not_a_save_file():
    slot_path(1).parent.mkdir(parents=True, exist_ok=True)
    slot_path(1).write_bytes(b"hello world")
    with pytest.raises(SaveError, match="not a save"):
        load_game(1)
    assert read_info(1) is None, "unreadable saves are skipped in listings"


def test_version_mismatch():
    save_game(Game(seed=1), 1)
    raw = slot_path(1).read_bytes()
    head, _, payload = raw.partition(b"\n")
    header = json.loads(head)
    header["version"] = SAVE_VERSION + 1
    slot_path(1).write_bytes(json.dumps(header).encode() + b"\n" + payload)
    assert not read_info(1).compatible
    with pytest.raises(SaveError, match="incompatible"):
        load_game(1)


def test_corrupted_payload_is_caught_by_the_checksum():
    save_game(Game(seed=1), 1)
    raw = bytearray(slot_path(1).read_bytes())
    raw[-10] ^= 0xFF
    slot_path(1).write_bytes(bytes(raw))
    with pytest.raises(SaveError, match="damaged"):
        load_game(1)


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as a normal user")
def test_unwritable_disk(monkeypatch, tmp_path):
    locked = tmp_path / "ro"
    locked.mkdir()
    locked.chmod(0o500)
    monkeypatch.setenv("ROGUEGAME_DATA", str(locked / "sub"))
    try:
        with pytest.raises(SaveError, match="couldn't write"):
            save_game(Game(seed=1), 1)
    finally:
        locked.chmod(0o700)


def test_atomic_write_leaves_no_temp_files():
    save_game(Game(seed=1), 1)
    save_game(Game(seed=2), 1)
    assert sorted(p.name for p in slot_path(1).parent.iterdir()) == ["slot1.sav"]


# ------------------------------------------------------------------- UI
def key(app, k, uni=""):
    return app.handle_key(k, uni)


def test_save_and_load_through_the_pause_menu():
    from roguegame.ui import App, Mode

    app = App(Game(seed=4))
    g = app.game
    g.wait()
    key(app, pygame.K_ESCAPE)
    assert app.mode is Mode.PAUSE
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)  # Save game
    assert app.mode is Mode.SLOTS and app.slot_action == "save"
    key(app, pygame.K_1)
    assert app.mode is Mode.NORMAL and read_info(1).turns == 1
    assert "saved to slot 1" in g.log[-1][0]
    g.wait()
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_DOWN)
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)  # Load game
    key(app, pygame.K_1)
    assert app.game is not g and app.game.turns == 1 and app.mode is Mode.NORMAL


def test_loading_an_empty_slot_explains_why():
    from roguegame.ui import App, Mode

    app = App(Game(seed=4))
    app.open_slots("load")
    key(app, pygame.K_2)
    assert app.mode is Mode.SLOTS and "empty" in app.notice
    key(app, pygame.K_ESCAPE)
    assert app.mode is Mode.PAUSE


def test_no_saving_a_finished_run():
    from roguegame.ui import App, Mode

    app = App(Game(seed=4))
    app.game._player_died("killed by a test")
    app.mode = Mode.PAUSE
    app.pause_index = 1
    key(app, pygame.K_RETURN)
    assert app.mode is Mode.PAUSE and "nothing to save" in app.notice


def test_loading_from_the_title_screen():
    from roguegame.ui import App, Mode, Renderer

    save_game(Game(seed=12, options=GameOptions(player_class="warrior")), 3)
    app = App(menu=True)
    assert app.menu_rows()[-1] == "load"
    app.menu_index = len(app.menu_rows()) - 1
    key(app, pygame.K_RETURN)
    assert app.mode is Mode.SLOTS and app.game is None
    pygame.init()
    Renderer(pygame.display.set_mode((960, 796))).draw(app)
    key(app, pygame.K_3)
    assert app.game.seed == 12 and app.game.player.cls.key == "warrior" and app.mode is Mode.NORMAL


def test_escape_from_title_load_returns_to_the_title():
    from roguegame.ui import App, Mode

    save_game(Game(seed=12), 1)
    app = App(menu=True)
    app.open_slots("load", back=Mode.MENU)
    key(app, pygame.K_ESCAPE)
    assert app.mode is Mode.MENU
