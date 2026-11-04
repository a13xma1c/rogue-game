"""Headless tests for input handling and rendering (SDL dummy video driver)."""

import pygame
import pytest

from roguegame import settings as S
from roguegame.game import Game, State
from roguegame.look import interesting_targets
from roguegame.ui import (
    BIGMAP_RECT,
    MINIMAP_RECT,
    VIEW_PX_W,
    App,
    Mode,
    Renderer,
    camera_origin,
    wrap,
)


ROOM = """
    ##########################################################################
    #........................................................................#
    #...@....................................................................#
    #........................................................................#
    ##########################################################################
"""


@pytest.fixture(scope="module")
def screen():
    pygame.init()
    surf = pygame.display.set_mode((S.SCREEN_W, S.SCREEN_H))
    yield surf
    pygame.quit()


@pytest.fixture
def renderer(screen):
    return Renderer(screen)


def press(app: App, key: int, unicode: str = "", mod: int = 0) -> bool:
    return app.handle_key(key, unicode, mod)


# ------------------------------------------------------------------ camera
def test_camera_clamps_to_map_edges():
    assert camera_origin(0, 0) == (0, 0)
    assert camera_origin(S.MAP_W - 1, S.MAP_H - 1) == (S.MAP_W - S.VIEW_W, S.MAP_H - S.VIEW_H)
    assert camera_origin(35, 22) == (35 - S.VIEW_W // 2, 22 - S.VIEW_H // 2)


def test_camera_follows_player_and_look_cursor():
    app = App(Game(seed=1))
    p = app.game.player
    assert app.camera() == camera_origin(p.x, p.y)
    app.start_look()
    app.cursor = (0, 0)
    assert app.camera() == (0, 0), "view jumps when the cursor leaves it"
    app.mode = Mode.NORMAL
    assert app.camera() == camera_origin(p.x, p.y)


def test_camera_stays_put_while_cursor_is_in_view():
    app = App(Game(seed=1))
    app.start_look()
    app.cursor = (app.game.player.x, app.game.player.y)
    before = app.camera()
    app.move_cursor(1, 0)
    assert app.camera() == before


# ------------------------------------------------------------- normal mode
def test_movement_keys(arena):
    app = App(arena(ROOM))
    for key, delta in [(pygame.K_RIGHT, (1, 0)), (pygame.K_l, (1, 0)), (pygame.K_KP3, (1, 1)),
                       (pygame.K_y, (-1, -1)), (pygame.K_w, (0, -1)), (pygame.K_s, (0, 1))]:
        x, y = app.game.player.x, app.game.player.y
        assert press(app, key)
        assert (app.game.player.x, app.game.player.y) == (x + delta[0], y + delta[1]), key


def test_wait_keys(arena):
    app = App(arena(ROOM))
    for key in (pygame.K_SPACE, pygame.K_PERIOD, pygame.K_KP5):
        press(app, key, ".")
    assert app.game.turns == 3


def test_escape_opens_the_pause_menu_which_can_quit(arena):
    app = App(arena(ROOM))
    assert press(app, pygame.K_ESCAPE) is True and app.mode is Mode.PAUSE
    assert press(app, pygame.K_ESCAPE) is True and app.mode is Mode.NORMAL, "Esc again resumes"
    press(app, pygame.K_ESCAPE)
    for _ in range(5):
        press(app, pygame.K_DOWN)
    assert press(app, pygame.K_RETURN) is False, "Quit game"


def test_quick_item_keys_open_filtered_menus(arena):
    app = App(arena(ROOM))
    g = app.game
    g.player.hp = 5
    press(app, pygame.K_p)  # P (or Q): quaff menu, potions only
    assert app.mode is Mode.INVENTORY and app.inv_action == "quaff"
    assert all(it.kind == "potion" for it in app.inventory_entries())
    press(app, pygame.K_a, "a")
    assert g.player.potions == 0 and app.mode is Mode.NORMAL and g.turns == 1
    press(app, pygame.K_r)  # nothing to read: no menu, just a message
    assert app.mode is Mode.NORMAL and "nothing to read" in g.log[-1][0]
    press(app, pygame.K_e)
    assert app.mode is Mode.INVENTORY and app.inv_action == "eat"
    press(app, pygame.K_ESCAPE)
    assert app.mode is Mode.NORMAL and g.turns == 1


def test_stairs_keys():
    app = App(Game(seed=2))
    g = app.game
    g.player.x, g.player.y = g.level.down_stairs
    press(app, pygame.K_PERIOD, ">")  # shift+. is '>' - must not be read as "wait"
    assert g.depth == 2 and g.turns == 0
    press(app, pygame.K_COMMA, "<")
    assert g.depth == 1
    press(app, pygame.K_RETURN)
    assert g.depth == 2


def test_restart_only_after_game_over(arena):
    g = arena(ROOM)
    app = App(g)
    press(app, pygame.K_r)
    assert app.game is g
    g.state = State.DEAD
    press(app, pygame.K_r)
    assert app.game is not g and app.game.state is State.PLAYING and app.mode is Mode.NORMAL


# -------------------------------------------------------------- look mode
def test_look_mode_starts_on_best_target(arena, spawn):
    g = arena(ROOM)
    spawn(g, "orc", 8, 2)
    g._update_fov()
    app = App(g)
    press(app, pygame.K_x)
    assert app.mode is Mode.LOOK and app.cursor == (8, 2)
    assert "Orc" in app.inspection().title


def test_look_mode_without_targets_starts_on_player(arena):
    app = App(arena(ROOM))
    press(app, pygame.K_x)
    assert app.cursor == (4, 2)


def test_look_cursor_moves_and_clamps(arena):
    app = App(arena(ROOM))
    press(app, pygame.K_x)
    turns = app.game.turns
    press(app, pygame.K_RIGHT)
    press(app, pygame.K_j)
    assert app.cursor == (5, 3)
    assert (app.game.player.x, app.game.player.y) == (4, 2) and app.game.turns == turns, "looking is free"
    for _ in range(10):
        press(app, pygame.K_y)
    assert app.cursor == (0, 0)


def test_tab_cycles_targets(arena, spawn, item):
    g = arena(ROOM)
    spawn(g, "orc", 8, 2)
    item(g, "potion", 6, 1)
    app = App(g)
    press(app, pygame.K_TAB)
    targets = interesting_targets(g)
    assert app.mode is Mode.LOOK and app.cursor == targets[0]
    press(app, pygame.K_TAB)
    assert app.cursor == targets[1]
    press(app, pygame.K_TAB)
    assert app.cursor == targets[0], "wraps around"
    press(app, pygame.K_TAB, mod=pygame.KMOD_SHIFT)
    assert app.cursor == targets[1]


@pytest.mark.parametrize("key", [pygame.K_ESCAPE, pygame.K_x, pygame.K_RETURN])
def test_leaving_look_mode(arena, key):
    app = App(arena(ROOM))
    press(app, pygame.K_x)
    assert press(app, key) is True, "Esc leaves look mode rather than quitting"
    assert app.mode is Mode.NORMAL


# ------------------------------------------------------ map / help / dialog
def test_map_toggle(arena):
    app = App(arena(ROOM))
    press(app, pygame.K_m)
    assert app.mode is Mode.MAP
    press(app, pygame.K_RIGHT)
    assert app.mode is Mode.MAP and app.game.turns == 0, "keys don't leak through the map"
    press(app, pygame.K_m)
    assert app.mode is Mode.NORMAL


def test_help_closes_on_any_key(arena):
    app = App(arena(ROOM))
    press(app, pygame.K_SLASH, "?")
    assert app.mode is Mode.HELP
    press(app, pygame.K_a)
    assert app.mode is Mode.NORMAL and app.game.turns == 0


def test_dialogue_keys(arena, npc):
    g = arena(ROOM)
    npc(g, "merchant", 5, 2)
    g.player.gold = 100
    app = App(g)
    press(app, pygame.K_RIGHT)
    assert g.dialogue is not None
    press(app, pygame.K_RIGHT)  # ignored while talking
    assert g.player.x == 4
    press(app, pygame.K_1)
    assert g.player.potions == 2
    press(app, pygame.K_KP2)
    assert g.player.scrolls == 1
    assert press(app, pygame.K_ESCAPE) is True
    assert g.dialogue is None


# ------------------------------------------------------------------- mouse
def test_click_on_minimap_inspects_that_tile():
    app = App(Game(seed=3))
    app.handle_click((MINIMAP_RECT.x + 10 * S.MINIMAP_SCALE + 1, MINIMAP_RECT.y + 7 * S.MINIMAP_SCALE + 1))
    assert app.mode is Mode.LOOK and app.cursor == (10, 7)
    ox, oy = app.camera()
    assert ox <= 10 < ox + S.VIEW_W and oy <= 7 < oy + S.VIEW_H, "view jumps to the clicked spot"


def test_click_on_big_map():
    app = App(Game(seed=3))
    app.mode = Mode.MAP
    app.handle_click((BIGMAP_RECT.x + 20 * S.BIGMAP_SCALE + 2, BIGMAP_RECT.y + 30 * S.BIGMAP_SCALE + 2))
    assert app.mode is Mode.LOOK and app.cursor == (20, 30)


def test_mouse_hover_moves_look_cursor(arena):
    app = App(arena(ROOM))
    app.handle_mouse_motion((5, 5))
    assert app.mode is Mode.NORMAL, "hovering alone doesn't start look mode"
    press(app, pygame.K_x)
    ox, oy = app.camera()
    app.handle_mouse_motion((3 * S.TILE + 5, 1 * S.TILE + 5))
    assert app.cursor == (ox + 3, oy + 1)


def test_clicks_in_the_hud_text_do_nothing(arena):
    app = App(arena(ROOM))
    app.handle_click((20, S.SCREEN_H - 10))
    assert app.mode is Mode.NORMAL


def test_right_click_leaves_look_mode(arena):
    app = App(arena(ROOM))
    press(app, pygame.K_x)
    app.handle_click((10, 10), button=3)
    assert app.mode is Mode.NORMAL


def test_mouse_ignored_during_dialogue(arena, npc):
    g = arena(ROOM)
    g.talk(npc(g, "sage", 6, 2))
    app = App(g)
    app.handle_click((MINIMAP_RECT.x + 3, MINIMAP_RECT.y + 3))
    assert app.mode is Mode.NORMAL


# --------------------------------------------------------------- rendering
def pixel(screen, pos):
    return tuple(screen.get_at(pos))[:3]


def test_render_every_mode(renderer, screen, arena, spawn, npc, item):
    g = arena(ROOM)
    spawn(g, "orc", 8, 2)
    item(g, "potion", 6, 1)
    g.map.traps.clear()
    app = App(g)
    for mode in Mode:
        app.mode = mode
        renderer.draw(app)
    app.mode = Mode.NORMAL
    g.talk(npc(g, "merchant", 4, 1))
    renderer.draw(app)
    g.close_dialogue()
    for state in (State.DEAD, State.WON):
        g.state = state
        g.death_cause = "killed by a test"
        renderer.draw(app)


def test_render_real_levels_on_every_floor(renderer):
    app = App(Game(seed=4))
    g = app.game
    for _ in range(S.MAX_DEPTH - 1):
        g.map.reveal()
        renderer.draw(app)
        app.mode = Mode.MAP
        renderer.draw(app)
        app.start_look()
        renderer.draw(app)
        app.mode = Mode.NORMAL
        g.player.x, g.player.y = g.level.down_stairs
        g.use_stairs()
    renderer.draw(app)


def test_minimap_is_painted(renderer, screen, arena):
    app = App(arena(ROOM))
    renderer.draw(app)
    px = (MINIMAP_RECT.x + 4 * S.MINIMAP_SCALE + 1, MINIMAP_RECT.y + 2 * S.MINIMAP_SCALE + 1)
    assert pixel(screen, px) == S.YELLOW, "player marker on the minimap"
    far = (MINIMAP_RECT.right - 3, MINIMAP_RECT.bottom - 3)
    assert pixel(screen, far) == (10, 10, 14), "unexplored area stays blank"


def test_look_cursor_is_drawn(renderer, screen, arena):
    app = App(arena(ROOM))
    press(app, pygame.K_x)
    press(app, pygame.K_RIGHT)
    renderer.draw(app)
    ox, oy = app.camera()
    x, y = app.cursor
    assert pixel(screen, ((x - ox) * S.TILE, (y - oy) * S.TILE)) == S.YELLOW


def tile_colors(screen, app, x, y):
    ox, oy = app.camera()
    px, py = (x - ox) * S.TILE, (y - oy) * S.TILE
    return {pixel(screen, (px + dx, py + dy)) for dx in range(S.TILE) for dy in range(S.TILE)}


def test_player_sprite_and_glyph_modes(renderer, screen, arena):
    from roguegame.sprites import PALETTE

    app = App(arena(ROOM))
    renderer.draw(app)
    colors = tile_colors(screen, app, 4, 2)
    assert PALETTE["b"] in colors and PALETTE["h"] in colors, "blue tunic and brown hair of the sprite"
    press(app, pygame.K_g)
    assert not app.use_sprites
    renderer.draw(app)
    assert S.YELLOW in tile_colors(screen, app, 4, 2), "classic yellow @"


def test_inspection_is_cached_per_turn(arena):
    app = App(arena(ROOM))
    press(app, pygame.K_x)
    app.inspection()
    key = app._dist_key
    app.move_cursor(1, 0)
    app.inspection()
    assert app._dist_key == key, "moving the cursor reuses the route search"
    app.game.wait()
    app.inspection()
    assert app._dist_key != key


def test_wrap(renderer):
    font = renderer.ui_font
    text = "the quick brown fox jumps over the lazy dog " * 4
    lines = wrap(text, font, 200)
    assert len(lines) > 1
    assert all(font.size(line)[0] <= 200 for line in lines)
    assert " ".join(lines) == text.strip()
    assert wrap("", font, 100) == [""]
    assert wrap("supercalifragilistic", font, 10) == ["supercalifragilistic"], "long words aren't lost"


def test_click_on_main_view_inspects(arena):
    app = App(arena(ROOM))
    ox, oy = app.camera()
    app.handle_click((6 * S.TILE + 3, 2 * S.TILE + 3))
    assert app.mode is Mode.LOOK and app.cursor == (ox + 6, oy + 2)


def test_main_loop_wires_events_to_the_app(monkeypatch):
    """Drive ui.run() with a scripted event queue and check it exits cleanly."""
    from roguegame import ui

    apps = []
    real_app = ui.App

    def spy_app(*args, **kwargs):
        app = real_app(Game(seed=21))
        apps.append(app)
        return app

    def key(k, uni=""):
        return pygame.event.Event(pygame.KEYDOWN, key=k, unicode=uni, mod=0)

    script = [
        [key(pygame.K_SPACE, " ")],
        [key(pygame.K_x, "x")],
        [pygame.event.Event(pygame.MOUSEMOTION, pos=(30, 30), rel=(0, 0), buttons=(0, 0, 0))],
        [key(pygame.K_ESCAPE)],  # leaves look mode...
        [pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(MINIMAP_RECT.x + 1, MINIMAP_RECT.y + 1), button=1)],
        [key(pygame.K_ESCAPE)],  # ...leaves look mode again...
        [key(pygame.K_ESCAPE)],  # ...opens the pause menu...
        [key(pygame.K_UP)],  # ...moves to "Quit game"...
        [key(pygame.K_RETURN)],  # ...and quits.
        [pygame.event.Event(pygame.QUIT)],  # never reached
    ]
    calls = iter(script)
    monkeypatch.setattr(ui, "App", spy_app)
    monkeypatch.setattr(pygame.event, "get", lambda: next(calls))
    monkeypatch.setattr(pygame.display, "flip", lambda: None)
    monkeypatch.setattr(pygame, "quit", lambda: None)  # keep the shared test display alive
    ui.run()
    app = apps[0]
    assert app.game.turns == 1
    assert app.mode is Mode.PAUSE
    assert next(calls)[0].type == pygame.QUIT, "quit before the QUIT event"


# ------------------------------------------------------------------ aiming
def test_t_starts_aiming_at_the_best_shot(arena, spawn):
    g = arena(ROOM)
    spawn(g, "orc", 8, 2)
    g._update_fov()
    app = App(g)
    press(app, pygame.K_t)
    assert app.mode is Mode.TARGET and app.cursor == (8, 2)
    plan = app.shot_plan()
    assert plan.ok and plan.target is not None


def test_aim_and_fire(arena, spawn, sure_hits):
    g = arena(ROOM)
    orc = spawn(g, "orc", 8, 2, hp=100, max_hp=100)
    g._update_fov()
    app = App(g)
    arrows = g.player.arrows
    press(app, pygame.K_t)
    press(app, pygame.K_t)  # T again fires
    assert orc.hp < 100 and g.player.arrows == arrows - 1 and app.mode is Mode.NORMAL


def test_fire_with_enter_and_cancel_with_escape(arena, spawn):
    g = arena(ROOM)
    spawn(g, "orc", 8, 2)
    g._update_fov()
    app = App(g)
    press(app, pygame.K_t)
    assert press(app, pygame.K_ESCAPE) is True and app.mode is Mode.NORMAL
    assert g.turns == 0
    press(app, pygame.K_t)
    press(app, pygame.K_RETURN)
    assert g.turns == 1


def test_tab_cycles_shootable_targets_only(arena, spawn, npc):
    g = arena(ROOM)
    a = spawn(g, "orc", 8, 2)
    b = spawn(g, "goblin", 6, 1)
    npc(g, "merchant", 4, 3)  # not a target
    g._update_fov()
    app = App(g)
    press(app, pygame.K_t)
    seen = {app.cursor}
    press(app, pygame.K_TAB)
    seen.add(app.cursor)
    press(app, pygame.K_TAB)
    assert seen == {(a.x, a.y), (b.x, b.y)}


def test_aiming_without_arrows(arena):
    g = arena(ROOM)
    g.player.arrows = 0
    app = App(g)
    press(app, pygame.K_t)
    assert app.mode is Mode.NORMAL and "out of arrows" in g.log[-1][0]


def test_refused_shot_keeps_aiming(arena):
    g = arena(ROOM)
    app = App(g)
    press(app, pygame.K_t)
    assert app.cursor == (4, 2), "no targets: aim starts on you"
    press(app, pygame.K_RETURN)  # can't shoot yourself
    assert app.mode is Mode.TARGET and g.turns == 0


def test_click_to_fire(arena, spawn, sure_hits):
    g = arena(ROOM)
    orc = spawn(g, "orc", 8, 2, hp=100, max_hp=100)
    g._update_fov()
    app = App(g)
    press(app, pygame.K_t)
    ox, oy = app.camera()
    app.handle_click(((8 - ox) * S.TILE + 5, (2 - oy) * S.TILE + 5))
    assert orc.hp < 100


def test_render_aim_mode(renderer, screen, arena, spawn):
    g = arena(ROOM)
    spawn(g, "orc", 8, 2)
    g._update_fov()
    app = App(g)
    press(app, pygame.K_t)
    renderer.draw(app)
    ox, oy = app.camera()
    # Green line-of-fire dots between you and the orc, red aim box on it.
    assert S.GREEN in tile_colors(screen, app, 6, 2)
    assert pixel(screen, ((8 - ox) * S.TILE, (2 - oy) * S.TILE)) == S.RED


# ----------------------------------------------------------------- effects
def test_effects_are_collected_and_expire(arena, spawn, sure_hits):
    from roguegame.ui import SHOT_FX_MS, TEXT_FX_MS

    g = arena(ROOM)
    spawn(g, "orc", 8, 2, hp=100, max_hp=100)
    g._update_fov()
    app = App(g)
    g.shoot(8, 2)
    live = app.update_effects(1000)
    kinds = {fx.kind for fx, _ in live}
    assert kinds == {"shot", "text"} and not g.fx, "effects move from the game to the UI"
    assert {fx.kind for fx, _ in app.update_effects(1000 + SHOT_FX_MS + 1)} == {"text"}
    assert app.update_effects(1000 + TEXT_FX_MS + 1) == []


def test_render_with_effects_in_flight(renderer, arena, spawn, sure_hits):
    g = arena(ROOM)
    spawn(g, "orc", 8, 2, hp=100, max_hp=100)
    g._update_fov()
    app = App(g)
    g.shoot(8, 2)
    for t in (0, 50, 120, 400):
        renderer.draw(app, now=10_000 + t)


def test_boss_health_bar(renderer, screen, arena):
    from conftest import add_monster

    g = arena(ROOM, depth=3)
    boss = add_monster(g, "orc warlord", 12, 2, alert=True)
    g.level.boss = boss
    app = App(g)
    renderer.draw(app)
    assert pixel(screen, (VIEW_PX_W // 2, 12)) == S.RED
    boss.hp = 1
    renderer.draw(app)
    assert pixel(screen, (VIEW_PX_W // 2, 12)) != S.RED, "the bar empties"


def test_status_pips_and_hud(renderer, screen, arena):
    from roguegame.status import STATUS_SPECS

    g = arena(ROOM)
    g.player.add_status("poisoned", 3)
    app = App(g)
    renderer.draw(app)
    assert STATUS_SPECS["poisoned"].color in tile_colors(screen, app, 4, 2)


def test_effects_queued_before_the_app_exists_are_kept(arena, spawn, sure_hits):
    """Regression: App.restart() used to clear game.fx, dropping pending animations."""
    g = arena(ROOM)
    spawn(g, "orc", 8, 2, hp=100, max_hp=100)
    g._update_fov()
    g.shoot(8, 2)
    app = App(g)
    assert any(fx.kind == "shot" for fx, _ in app.update_effects(0))


# -------------------------------------------------------------- title menu
def test_app_can_start_on_the_title_screen(renderer):
    app = App(menu=True)
    assert app.mode is Mode.MENU and app.game is None
    renderer.draw(app)
    app.handle_mouse_motion((10, 10))
    app.handle_click((10, 10))
    assert app.mode is Mode.MENU, "the mouse does nothing on the title screen"


def test_menu_navigation_and_options():
    from roguegame.difficulty import GameOptions

    app = App(menu=True)
    assert app.menu_options == GameOptions() and app.menu_index == 0
    press(app, pygame.K_RIGHT)
    assert app.menu_options.mode == "endless"
    press(app, pygame.K_RIGHT)
    assert app.menu_options.mode == "classic", "wraps around"
    press(app, pygame.K_LEFT)
    press(app, pygame.K_DOWN)
    assert app.menu_index == 1
    press(app, pygame.K_LEFT)
    assert app.menu_options.difficulty == "easy"
    press(app, pygame.K_LEFT)
    assert app.menu_options.difficulty == "hard"
    press(app, pygame.K_DOWN)
    press(app, pygame.K_RIGHT)
    assert app.menu_options.player_class == "warrior"
    press(app, pygame.K_DOWN)  # seed
    press(app, pygame.K_DOWN)  # start
    press(app, pygame.K_RIGHT)  # the Start row has nothing to change
    assert app.menu_options == GameOptions("endless", "hard", "warrior")
    press(app, pygame.K_DOWN)
    assert app.menu_index == 0, "wraps around (no saves, so no Load row)"
    press(app, pygame.K_UP)
    assert app.menu_index == 4


def test_starting_from_the_menu_uses_the_chosen_options():
    from roguegame.difficulty import GameOptions

    app = App(menu=True, options=GameOptions("endless", "easy"), seed=77)
    press(app, pygame.K_RETURN)
    assert app.mode is Mode.NORMAL
    assert app.game.options == GameOptions("endless", "easy") and app.game.seed == 77
    assert app.game.player.max_hp == 40


def test_escape_quits_from_the_menu():
    assert press(App(menu=True), pygame.K_ESCAPE) is False


def test_after_a_run_r_replays_with_the_same_options_and_a_new_dungeon():
    from roguegame.difficulty import GameOptions

    app = App(options=GameOptions("endless", "hard"), seed=5)
    first = app.game
    first._player_died("killed by a test")
    press(app, pygame.K_r)
    assert app.game is not first and app.game.options == first.options
    assert app.game.seed != 5, "the fixed seed is only for the first game"


def test_after_a_run_enter_returns_to_the_title(renderer):
    from roguegame.difficulty import GameOptions

    app = App(options=GameOptions("endless", "hard"))
    app.game.state = State.WON
    press(app, pygame.K_RETURN)
    assert app.mode is Mode.MENU and app.game is None
    assert app.menu_options == GameOptions("endless", "hard"), "your last choice is remembered"
    assert app.menu_rows()[app.menu_index] == "start", "Start is preselected"
    renderer.draw(app)


def test_enter_still_takes_stairs_while_playing():
    app = App(Game(seed=2))
    g = app.game
    g.player.x, g.player.y = g.level.down_stairs
    press(app, pygame.K_RETURN)
    assert g.depth == 2 and app.mode is Mode.NORMAL


def test_finished_runs_are_recorded_once(tmp_path, arena, spawn, sure_hits, renderer, screen):
    from roguegame.scores import ScoreBoard

    board = ScoreBoard(tmp_path / "scores.json")
    g = arena(ROOM)
    g.player.hp = 1
    spawn(g, "troll", 5, 2, alert=True)
    app = App(g, scores=board)
    press(app, pygame.K_SPACE)
    assert g.state is State.DEAD and app.recorded and app.rank == 1
    press(app, pygame.K_SPACE)
    assert len(board.top(g.options)) == 1, "not recorded twice"
    renderer.draw(app)  # banner with "NEW BEST!"
    assert ScoreBoard(tmp_path / "scores.json").best(g.options).outcome == "killed by a troll"


def test_no_scoreboard_no_recording(arena):
    app = App(arena(ROOM))
    app.game._player_died("killed by a test")
    app.note_game_over()
    assert app.recorded and app.rank is None


def test_title_screen_lists_best_runs(renderer, screen, tmp_path):
    from roguegame.scores import ScoreBoard

    board = ScoreBoard(tmp_path / "s.json")
    g = Game(seed=3)
    g._player_died("killed by a test")
    board.record(g)
    app = App(menu=True, scores=board)
    renderer.draw(app)  # smoke: renders the table


def drawn_text(renderer, app, monkeypatch) -> list[str]:
    texts = []
    real = renderer.text

    def spy(s, *args, **kwargs):
        texts.append(s)
        return real(s, *args, **kwargs)

    monkeypatch.setattr(renderer, "text", spy)
    renderer.draw(app)
    return texts


def test_hud_shows_mode_and_difficulty(renderer, monkeypatch):
    from roguegame.difficulty import GameOptions

    endless = drawn_text(renderer, App(Game(seed=1, options=GameOptions("endless", "hard"))), monkeypatch)
    assert any("Endless - Hard" in t for t in endless)
    assert any(t.startswith("Floor 1 (") for t in endless), "no '/5' in endless mode"
    classic = drawn_text(renderer, App(Game(seed=1)), monkeypatch)
    assert any(t.startswith(f"Floor 1/{S.MAX_DEPTH} (") for t in classic)


def test_title_screen_shows_descriptions(renderer, monkeypatch):
    from roguegame.difficulty import DIFFICULTIES, GameOptions

    app = App(menu=True, options=GameOptions("classic", "hard"))
    texts = drawn_text(renderer, app, monkeypatch)
    assert "Best runs - Classic - Hard" in texts
    assert any("<  Hard  >" in t for t in texts)
    assert any(DIFFICULTIES["hard"].description.split()[0] in t for t in texts)


# --------------------------------------------------------------------- CLI
def test_command_line_options():
    from roguegame import parse_args
    from roguegame.difficulty import GameOptions

    assert parse_args([]) == (GameOptions(), None, True)
    assert parse_args(["--endless"]) == (GameOptions("endless", "normal"), None, False)
    assert parse_args(["-d", "hard", "--seed", "42"]) == (GameOptions("classic", "hard"), 42, False)
    assert parse_args(["--classic", "--difficulty", "easy"]) == (GameOptions("classic", "easy"), None, False)
    with pytest.raises(SystemExit):
        parse_args(["--difficulty", "nightmare"])
    with pytest.raises(SystemExit):
        parse_args(["--classic", "--endless"])


def test_main_passes_options_to_run(monkeypatch):
    import roguegame
    from roguegame import ui
    from roguegame.difficulty import GameOptions

    calls = []
    monkeypatch.setattr(ui, "run", lambda **kw: calls.append(kw))
    roguegame.main(["--endless", "-d", "easy"])
    assert calls == [{"options": GameOptions("endless", "easy"), "seed": None, "menu": False}]


# ---------------------------------------------------------------- inventory
def test_inventory_browse_equip_and_drop(arena, item):
    g = arena(ROOM)
    sword = item(g, "weapon", 5, 2, value=3)
    g.player_move(1, 0)
    app = App(g)
    press(app, pygame.K_i)
    assert app.mode is Mode.INVENTORY and app.inv_action is None
    entries = app.inventory_entries()
    letter = chr(ord("a") + entries.index(sword))
    press(app, getattr(pygame, f"K_{letter}"), letter)
    assert app.inv_selected is sword and app.mode is Mode.INVENTORY
    press(app, pygame.K_u, "u")
    assert g.player.weapon is sword and app.mode is Mode.NORMAL
    press(app, pygame.K_i)
    letter = chr(ord("a") + app.inventory_entries().index(sword))
    press(app, getattr(pygame, f"K_{letter}"), letter)
    press(app, pygame.K_d, "d")
    assert sword in g.items and g.player.weapon is None


def test_inventory_escape_steps_back(arena):
    app = App(arena(ROOM))
    press(app, pygame.K_i)
    press(app, pygame.K_a, "a")
    assert app.inv_selected is not None
    press(app, pygame.K_ESCAPE)
    assert app.inv_selected is None and app.mode is Mode.INVENTORY
    press(app, pygame.K_ESCAPE)
    assert app.mode is Mode.NORMAL and app.game.turns == 0


def test_letters_in_menus_are_not_commands(arena):
    from roguegame.items import make_weapon

    g = arena(ROOM)
    for _ in range(7):
        g.player.add_to_pack(make_weapon(0, 0, 1))
    app = App(g)
    press(app, pygame.K_i)
    press(app, pygame.K_g, "g")
    assert app.use_sprites, "g picks item g rather than toggling sprites"
    assert app.inv_selected is app.inventory_entries()[6]


def test_identify_prompt_opens_by_itself(arena):
    from roguegame import items as I

    g = arena(ROOM)
    for it in (I.make_potion(0, 0, "haste"), I.make_potion(0, 0, "might"), I.make_scroll(0, 0, "identify")):
        g.player.add_to_pack(it)
    g.ident.learn("scroll", "identify")
    app = App(g)
    press(app, pygame.K_r)
    press(app, pygame.K_a, "a")  # the only scroll
    assert g.pending == "identify" and app.mode is Mode.INVENTORY and app.inv_action == "identify"
    assert len(app.inventory_entries()) == 2
    press(app, pygame.K_b, "b")
    assert g.pending is None and app.mode is Mode.NORMAL and g.turns == 1
    assert len(g.unidentified_items()) == 1


def test_escaping_the_identify_prompt_wastes_the_scroll(arena):
    from roguegame import items as I

    g = arena(ROOM)
    for it in (I.make_potion(0, 0, "haste"), I.make_potion(0, 0, "might"), I.make_scroll(0, 0, "identify")):
        g.player.add_to_pack(it)
    app = App(g)
    g.read(g.player.find("scroll", "identify"))
    app.handle_key(pygame.K_SPACE, " ")  # any key: the prompt appears
    assert app.mode is Mode.INVENTORY
    press(app, pygame.K_ESCAPE)
    assert g.pending is None and app.mode is Mode.NORMAL and g.turns == 1


# --------------------------------------------------------- character & spells
def test_character_screen_learns_skills():
    from roguegame.difficulty import GameOptions

    app = App(Game(seed=1, options=GameOptions(player_class="warrior")))
    g = app.game
    press(app, pygame.K_c)
    assert app.mode is Mode.CHARACTER
    press(app, pygame.K_RIGHT)  # to the other branch: Toughness
    press(app, pygame.K_RETURN)
    assert g.player.skills.get("toughness") == 1 and g.player.skill_points == 0
    press(app, pygame.K_DOWN)
    press(app, pygame.K_RETURN)  # Iron Skin: no points left
    assert "iron skin" not in g.player.skills
    press(app, pygame.K_c)
    assert app.mode is Mode.NORMAL and g.turns == 0


def test_spell_menu_and_targeting(arena, spawn):
    from roguegame.difficulty import GameOptions

    g = arena(ROOM)
    g.options = GameOptions(player_class="mage")
    g.player.book_spells["magic missile"] = 1
    g.player.base_max_mana = g.player.mana = 20
    orc = spawn(g, "orc", 8, 2, hp=100, max_hp=100)
    g._update_fov()
    app = App(g)
    press(app, pygame.K_z)
    assert app.mode is Mode.SPELLS
    press(app, pygame.K_a, "a")
    assert app.mode is Mode.TARGET and app.aim == "magic missile" and app.cursor == (8, 2)
    press(app, pygame.K_RETURN)
    from roguegame.spells import SPELLS

    assert orc.hp < 100 and app.mode is Mode.NORMAL and g.player.mana == 20 - SPELLS["magic missile"].cost


def test_self_spells_cast_straight_from_the_menu(arena):
    g = arena(ROOM)
    g.player.book_spells["mend"] = 1
    g.player.base_max_mana = g.player.mana = 20
    g.player.hp = 5
    app = App(g)
    press(app, pygame.K_z)
    press(app, pygame.K_a, "a")
    assert g.player.hp > 5 and app.mode is Mode.NORMAL


def test_z_without_spells(arena):
    app = App(arena(ROOM))
    press(app, pygame.K_z)
    assert app.mode is Mode.NORMAL and "don't know any spells" in app.game.log[-1][0]


def test_render_new_panels_and_hud(renderer, screen, arena, item, monkeypatch):
    import random

    from roguegame import items as I

    g = arena(ROOM)
    g.player.add_to_pack(I.make_ring(0, 0, 5, random.Random(2)))
    g.player.book_spells["fireball"] = 1
    g.player.satiation = 100
    item(g, "potion", 6, 2, subtype="mana")
    app = App(g)
    texts = drawn_text(renderer, app, monkeypatch)
    assert any(t.startswith("MP ") for t in texts) and "Fainting  " in texts
    for mode in (Mode.INVENTORY, Mode.CHARACTER, Mode.SPELLS):
        app.mode = mode
        renderer.draw(app)
    app.mode = Mode.INVENTORY
    app.inv_selected = g.player.pack[-1]
    renderer.draw(app)
    app.use_sprites = False
    renderer.draw(app)


def test_items_on_the_floor_are_drawn_as_sprites(renderer, screen, arena, item):
    from roguegame.sprites import PALETTE

    g = arena(ROOM)
    item(g, "weapon", 7, 2, value=1, subtype="sword")
    app = App(g)
    renderer.draw(app)
    assert PALETTE["l"] in tile_colors(screen, app, 7, 2), "the steel blade of the sword sprite"


def test_title_screen_class_choice(renderer):
    app = App(menu=True)
    press(app, pygame.K_DOWN)
    press(app, pygame.K_DOWN)
    press(app, pygame.K_RIGHT)
    press(app, pygame.K_RIGHT)
    press(app, pygame.K_RIGHT)
    renderer.draw(app)
    press(app, pygame.K_RETURN)
    assert app.game.player.cls.key == "mage"


def test_minimap_clicks_match_what_is_drawn(renderer, screen, arena):
    """The minimap is drawn at its true scale, so the pixel you click is the
    tile you get - even on a map smaller than the minimap frame."""
    app = App(arena(ROOM))
    renderer.draw(app)
    x, y = 4, 2  # the player
    px = (MINIMAP_RECT.x + x * S.MINIMAP_SCALE, MINIMAP_RECT.y + y * S.MINIMAP_SCALE)
    assert pixel(screen, px) == S.YELLOW
    assert app.tile_at_screen(px) == (x, y)
