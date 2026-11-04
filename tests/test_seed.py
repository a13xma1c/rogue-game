"""Seeds: shareable, typed on the title screen, shown in the game."""

import pygame
import pytest

from roguegame import ui
from roguegame.difficulty import GameOptions
from roguegame.game import Game
from roguegame.ui import App, Mode, Renderer, replay_command, seed_from_text


def test_seed_from_text():
    assert seed_from_text("12345") == 12345
    assert seed_from_text("  42 ") == 42
    assert seed_from_text("dragon") == seed_from_text("dragon"), "stable"
    assert seed_from_text("dragon") != seed_from_text("Dragon")
    assert 0 <= seed_from_text("any words at all") < 2**32


def test_the_same_seed_makes_the_same_dungeon_every_floor():
    from conftest import slay_boss

    def floors(seed, options):
        g = Game(seed=seed, options=options)
        out = []
        while g.depth < 5:
            out.append([row[:] for row in g.map.tiles])
            slay_boss(g)
            g.player.x, g.player.y = g.level.down_stairs
            g.use_stairs()
        return out

    opts = GameOptions("classic", "normal", "warrior")
    assert floors(777, opts) == floors(777, opts)
    assert floors(777, opts) != floors(778, opts)
    # The class doesn't change the map: friends can race the same dungeon as different classes.
    assert floors(777, opts) == floors(777, GameOptions("classic", "normal", "mage"))


def test_replay_command():
    g = Game(seed=99, options=GameOptions("endless", "hard", "ranger"))
    assert replay_command(g) == "roguegame --endless -d hard -c ranger --seed 99"
    from roguegame import parse_args

    options, seed, menu = parse_args(replay_command(g).split()[1:])
    assert (options, seed, menu) == (g.options, 99, False), "the command really replays it"


# ------------------------------------------------------------- title screen
def press(app, key, uni=""):
    return app.handle_key(key, uni)


def test_typing_a_seed_on_the_title_screen():
    app = App(menu=True)
    app.menu_index = app.menu_rows().index("seed")
    press(app, pygame.K_RETURN)
    assert app.editing_seed
    for ch in "dragon":
        press(app, 0, ch)
    press(app, pygame.K_BACKSPACE)
    press(app, 0, "n")
    press(app, pygame.K_RETURN)
    assert not app.editing_seed and app.seed_text == "dragon"
    app.menu_index = app.menu_rows().index("start")
    press(app, pygame.K_RETURN)
    assert app.game.seed == seed_from_text("dragon")


def test_keys_typed_into_the_seed_are_not_commands():
    app = App(menu=True)
    app.menu_index = app.menu_rows().index("seed")
    press(app, pygame.K_RETURN)
    press(app, pygame.K_ESCAPE)  # stops editing - doesn't quit
    assert app.mode is Mode.MENU and not app.editing_seed
    press(app, pygame.K_RETURN)
    press(app, pygame.K_s, "s")  # 's' would move the selection if it weren't typed
    assert app.seed_text == "s" and app.menu_rows()[app.menu_index] == "seed"


def test_backspace_on_the_seed_row_goes_back_to_random():
    app = App(menu=True, seed=5)
    assert app.seed_text == "5"
    app.menu_index = app.menu_rows().index("seed")
    press(app, pygame.K_BACKSPACE)
    assert app.seed_text == ""


def test_a_typed_seed_sticks_for_the_next_run_but_R_rerolls():
    app = App(menu=True)
    app.seed_text = "31337"
    app.start_game()
    assert app.game.seed == 31337
    app.game._player_died("killed by a test")
    press(app, pygame.K_r)
    assert app.game.seed != 31337, "R plays again on a fresh dungeon"
    app.open_menu()
    app.start_game()
    assert app.game.seed == 31337, "the title screen remembers the seed you typed"


# ------------------------------------------------------------------ display
@pytest.fixture
def renderer():
    pygame.init()
    return Renderer(pygame.display.set_mode((960, 796)))


def captured_text(renderer, app, monkeypatch):
    texts = []
    real = renderer.text

    def spy(s, *a, **k):
        texts.append(s)
        return real(s, *a, **k)

    monkeypatch.setattr(renderer, "text", spy)
    renderer.draw(app)
    return texts


def test_seed_in_the_hud_and_end_screen(renderer, monkeypatch):
    g = Game(seed=4242)
    app = App(g)
    assert any("Seed 4242" in t for t in captured_text(renderer, app, monkeypatch))
    g._player_died("killed by a test")
    renderer.draw(app)
    assert any("--seed 4242" in text for text, _ in ui.banner_lines(app))


def test_copy_seed_from_the_pause_menu(monkeypatch):
    copied = []
    monkeypatch.setattr(ui, "copy_to_clipboard", lambda text: copied.append(text) or True)
    app = App(Game(seed=555))
    press(app, pygame.K_ESCAPE)
    app.pause_index = ui.PAUSE_ROWS.index("Copy seed to clipboard")
    press(app, pygame.K_RETURN)
    assert copied == ["555"] and "copied" in app.notice


def test_copy_seed_without_a_clipboard(monkeypatch):
    monkeypatch.setattr(ui, "copy_to_clipboard", lambda text: False)
    app = App(Game(seed=556))
    app.mode = Mode.PAUSE
    app.pause_index = ui.PAUSE_ROWS.index("Copy seed to clipboard")
    press(app, pygame.K_RETURN)
    assert "the seed is 556" in app.notice


def test_clipboard_helper_never_raises():
    assert ui.copy_to_clipboard("123") in (True, False)
