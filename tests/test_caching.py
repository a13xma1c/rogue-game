"""Caching: field of view, the map view, the HUD and the minimap are only
recomputed or redrawn when something they depend on changed."""

import pygame
import pytest

from roguegame import settings as S
from roguegame.dungeon import DungeonMap
from roguegame.game import Game
from roguegame.tiles import DOOR_CLOSED, DOOR_OPEN, FLOOR, WALL
from roguegame.ui import App, Mode, Renderer

from conftest import parse_map

ROOM = """
    ####################
    #..................#
    #..@...............#
    #..................#
    ####################
"""


# ------------------------------------------------------------------- FOV
def open_map(w=40, h=30) -> DungeonMap:
    m = DungeonMap(w, h)
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            m.tiles[y][x] = FLOOR
    return m


def test_fov_is_cached_until_something_relevant_changes():
    m = open_map()
    assert m.compute_fov(10, 10, 6) is True
    assert m.compute_fov(10, 10, 6) is False, "same origin, radius and surroundings: cached"
    assert m.fov_computations == 1
    assert m.compute_fov(11, 10, 6) is True, "moved"
    assert m.compute_fov(11, 10, 4) is True, "radius changed (blindness, eagle eye)"
    assert m.fov_computations == 3


def test_fov_notices_tile_changes_however_they_are_made():
    m, p = parse_map("""
        #########
        #@..+...#
        #########
    """)
    m.compute_fov(*p, 8)
    assert not m.visible[1][6]
    m.tiles[1][4] = DOOR_OPEN  # a direct write, no special API
    assert m.compute_fov(*p, 8) is True
    assert m.visible[1][6]
    m.tiles[1][4] = DOOR_CLOSED
    m.compute_fov(*p, 8)
    assert not m.visible[1][6]


def test_changes_out_of_sight_range_keep_the_cache():
    m = open_map()
    m.compute_fov(10, 10, 5)
    m.tiles[25][35] = WALL  # far outside the radius
    assert m.compute_fov(10, 10, 5) is False


def test_recomputing_clears_what_is_no_longer_visible():
    m = open_map(60, 20)
    m.compute_fov(5, 10, 4)
    assert m.visible[10][8]
    m.compute_fov(50, 10, 4)
    assert not m.visible[10][8] and m.visible[10][52]
    assert sum(map(sum, m.visible)) == len(m._fov_lit)
    assert m.explored[10][8], "explored is never forgotten"


def test_invalidate_forces_a_recompute():
    m = open_map()
    m.compute_fov(10, 10, 6)
    m.invalidate_fov()
    assert m.compute_fov(10, 10, 6) is True


def test_standing_still_costs_no_fov_work(arena):
    g = arena(ROOM)
    before = g.map.fov_computations
    for _ in range(10):
        g.wait()
    assert g.map.fov_computations == before
    g.player_move(1, 0)
    assert g.map.fov_computations == before + 1, "one recompute per move, not one per round"


def test_fov_matches_a_fresh_computation_after_lots_of_play():
    """The cached, incrementally cleared FOV must always equal a from-scratch one."""
    import random

    from roguegame.dungeon import DIRS8

    g = Game(seed=21)
    rng = random.Random(3)
    for _ in range(300):
        g.player_move(*rng.choice(DIRS8))
        if g.state.name != "PLAYING":
            break
        fresh = DungeonMap(g.map.width, g.map.height)
        fresh.tiles = g.map.tiles
        fresh.compute_fov(g.player.x, g.player.y, g.fov_radius)
        assert fresh.visible == g.map.visible


# --------------------------------------------------------------- revisions
def test_revision_tracks_game_changes(arena):
    g = arena(ROOM)
    r = g.revision
    g.wait()
    assert g.revision > r
    r = g.revision
    g.say("hello")
    assert g.revision > r
    r = g.revision
    g.touch()
    assert g.revision == r + 1


def test_ui_only_actions_do_not_touch_the_game(arena):
    app = App(arena(ROOM))
    g = app.game
    r = g.revision
    for key, uni in ((pygame.K_i, ""), (pygame.K_ESCAPE, ""), (pygame.K_x, "x"), (pygame.K_RIGHT, ""),
                     (pygame.K_ESCAPE, ""), (pygame.K_c, "c"), (pygame.K_c, "c"), (pygame.K_g, "g")):
        app.handle_key(key, uni)
    assert g.revision == r, "browsing menus, looking around and toggling sprites change nothing in the game"


# ----------------------------------------------------------------- drawing
@pytest.fixture
def renderer():
    pygame.init()
    return Renderer(pygame.display.set_mode((S.SCREEN_W, S.SCREEN_H)))


def test_idle_frames_redraw_nothing(renderer, monkeypatch):
    from roguegame import ui

    app = App(Game(seed=2))
    builds = []
    monkeypatch.setattr(ui, "build_minimap", lambda game: builds.append(1) or ui_build(game))
    for frame in range(30):
        renderer.draw(app, now=frame * 16)
    assert renderer.map_layer.redraws == 1
    assert renderer.hud_layer.redraws == 1
    assert len(builds) == 1, "the minimap is built once, not every frame"


def ui_build(game):
    from roguegame.minimap import build_minimap

    return build_minimap(game)


def test_a_turn_redraws_once(renderer):
    app = App(Game(seed=2))
    renderer.draw(app)
    app.game.wait()
    for _ in range(5):
        renderer.draw(app)
    assert renderer.map_layer.redraws == 2 and renderer.hud_layer.redraws == 2
    assert renderer.minimap_builds == 2


def test_moving_the_view_redraws_the_map_but_not_the_minimap(renderer):
    app = App(Game(seed=2))
    renderer.draw(app)
    app.start_look()
    app.cursor = (0, 0)  # far away: the view jumps
    renderer.draw(app)
    assert renderer.map_layer.redraws == 2
    assert renderer.minimap_builds == 1 and renderer.hud_layer.redraws == 1


def test_moving_the_cursor_inside_the_view_redraws_nothing(renderer):
    app = App(Game(seed=2))
    app.start_look()
    renderer.draw(app)
    app.move_cursor(1, 0)
    renderer.draw(app)
    assert renderer.map_layer.redraws == 1


def test_toggling_sprites_redraws_the_map(renderer):
    app = App(Game(seed=2))
    renderer.draw(app)
    app.handle_key(pygame.K_g, "g")
    renderer.draw(app)
    assert renderer.map_layer.redraws == 2 and renderer.hud_layer.redraws == 1


def test_hud_minimap_and_full_map_share_one_minimap_build(renderer):
    app = App(Game(seed=2))
    renderer.draw(app)
    app.mode = Mode.MAP
    renderer.draw(app)
    renderer.draw(app)
    assert renderer.minimap_builds == 1
    assert set(renderer._minimap_images) == {S.MINIMAP_SCALE, S.BIGMAP_SCALE}


def test_a_new_or_loaded_game_is_redrawn(renderer):
    app = App(Game(seed=2))
    renderer.draw(app)
    app.restart(Game(seed=3))
    renderer.draw(app)
    assert renderer.map_layer.redraws == 2 and renderer.minimap_builds == 2


def test_what_is_shown_is_never_stale(renderer, arena, spawn):
    """After a monster moves, the screen shows it where it is now."""
    g = arena(ROOM)
    orc = spawn(g, "orc", 9, 2, alert=True)  # in view (sight radius 8)
    g._update_fov()
    app = App(g)
    renderer.draw(app)
    ox, oy = app.camera()

    def colors_at(x, y):
        px, py = (x - ox) * S.TILE, (y - oy) * S.TILE
        return {tuple(renderer.screen.get_at((px + dx, py + dy)))[:3] for dx in range(S.TILE) for dy in range(S.TILE)}

    before = colors_at(9, 2)
    assert len(before) > 3, "the orc is drawn"
    g.wait()
    assert (orc.x, orc.y) != (9, 2)
    renderer.draw(app)
    assert colors_at(9, 2) != before, "the orc is no longer drawn where it was"
    assert colors_at(orc.x, orc.y) != colors_at(17, 2)
