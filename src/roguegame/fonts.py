"""Finding a monospace font, robustly.

pygame's SysFont asks ``fc-list`` for the system's fonts with a one-second
timeout and never retries; on a cold font cache or a busy machine that call
can time out, and every font request then silently falls back to pygame's
default (proportional) font. This module resolves a monospace font file
once, with a more patient fallback, and caches it.
"""

from __future__ import annotations

import shutil
import subprocess
import warnings
from functools import lru_cache

import pygame

PREFERRED = "menlo,dejavusansmono,couriernew,monospace"


@lru_cache(maxsize=1)
def monospace_path() -> str | None:
    """Path of a monospace font file, or None to use pygame's default font."""
    with warnings.catch_warnings():
        # pygame warns when fc-list times out; we handle that case below.
        warnings.simplefilter("ignore")
        path = pygame.font.match_font(PREFERRED)
    if path:
        return path
    fc_match = shutil.which("fc-match")
    if fc_match:
        try:
            out = subprocess.run([fc_match, "-f", "%{file}", "monospace"], capture_output=True, text=True,
                                 timeout=10, check=True)
            if out.stdout.strip():
                return out.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            pass
    return None


def font(size: int, bold: bool = False) -> pygame.font.Font:
    f = pygame.font.Font(monospace_path(), size)
    f.bold = bold
    return f
