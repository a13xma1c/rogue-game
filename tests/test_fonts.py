"""Robust monospace font lookup."""

import shutil
import subprocess

import pygame

from roguegame import fonts


def setup_function():
    fonts.monospace_path.cache_clear()


def teardown_function():
    fonts.monospace_path.cache_clear()


def test_finds_a_monospace_font():
    pygame.init()
    f = fonts.font(15)
    assert f.size("iiii") == f.size("MMMM"), "every glyph the same width"


def test_recovers_when_pygame_cannot_list_fonts(monkeypatch):
    """pygame gives fc-list one second and never retries; we ask fc-match."""
    monkeypatch.setattr(pygame.font, "match_font", lambda *a, **k: None)
    if shutil.which("fc-match"):
        path = fonts.monospace_path()
        assert path and path.endswith((".ttf", ".otf", ".ttc", ".pcf.gz", ".pfb"))
    else:
        assert fonts.monospace_path() is None


def test_falls_back_to_the_default_font(monkeypatch):
    monkeypatch.setattr(pygame.font, "match_font", lambda *a, **k: None)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert fonts.monospace_path() is None
    pygame.init()
    assert fonts.font(15).size("hello")[0] > 0, "pygame's bundled font still works"


def test_fc_match_failures_are_tolerated(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired("fc-match", 10)

    monkeypatch.setattr(pygame.font, "match_font", lambda *a, **k: None)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/fc-match")
    monkeypatch.setattr(subprocess, "run", boom)
    assert fonts.monospace_path() is None
