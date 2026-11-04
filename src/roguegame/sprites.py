"""Character sprites.

Sprites are 12x12 pixel art written as strings (one character per pixel,
``.`` = transparent) plus a palette. At load time each gets a dark 1px
outline (so it reads on any floor colour) and is scaled up to the tile size
with nearest-neighbour scaling.

To use your own art, drop PNGs into ``roguegame/assets/sprites/`` named after
the sprite key (spaces become underscores, e.g. ``goblin_archer.png``); they
are scaled to the tile size and replace the built-in sprite. Run
``python -m roguegame.sprites DIR`` to export the built-in sprites as a
starting point.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pygame

    from .entities import Actor

SIZE = 12
SPRITE_DIR = Path(__file__).parent / "assets" / "sprites"
OUTLINE = (14, 12, 18)

PALETTE: dict[str, tuple[int, int, int]] = {
    "k": (20, 18, 24),  # black / eyes
    "w": (240, 240, 240),  # white
    "l": (200, 200, 212),  # light grey / steel
    "e": (150, 150, 162),  # grey
    "E": (88, 88, 100),  # dark grey
    "s": (232, 184, 140),  # skin
    "S": (196, 140, 110),  # ruddy skin
    "h": (120, 72, 40),  # hair
    "n": (140, 95, 55),  # brown / wood
    "N": (84, 56, 34),  # dark brown / boots
    "y": (240, 200, 60),  # gold
    "o": (245, 140, 40),  # orange / flame
    "r": (215, 50, 50),  # red
    "m": (230, 140, 170),  # pink
    "g": (96, 190, 86),  # goblin green
    "G": (40, 112, 52),  # dark green
    "v": (128, 150, 88),  # orc / troll olive
    "b": (70, 120, 220),  # blue
    "B": (40, 60, 140),  # dark blue
    "c": (90, 210, 220),  # cyan
    "p": (150, 80, 200),  # purple
    "P": (86, 44, 124),  # dark purple
    "t": (232, 226, 200),  # bone
    "a": (200, 160, 90),  # tan fur
    "Y": (180, 140, 30),  # dark gold
    # "L" and "D" are tint placeholders: the item's colour and a darker shade
    # of it (potion liquid, tome cover, ring gem). Untinted they're grey.
    "L": (170, 170, 180),
    "D": (110, 110, 120),
}
TINTABLE = ("L", "D")

SPRITES: dict[str, list[str]] = {
    "player": [
        "............",
        "....hhhh....",
        "...hhhhhh...",
        "...hkssk..l.",
        "....ssss..l.",
        "...bbbbbb.l.",
        "..sbbbbbbsl.",
        "..sbbyybb.n.",
        "...bbbbbb...",
        "...BB..BB...",
        "...BB..BB...",
        "..NNN..NNN..",
    ],
    "merchant": [
        "............",
        "....GGGG....",
        "...GggggG...",
        "...GksskG...",
        "...GssssG...",
        "..GGggggGG..",
        ".sGggggggGs.",
        "..GggyyggGyy",
        "..GggyyggGyy",
        "..GgggggggG.",
        "...gg..gg...",
        "...NN..NN...",
    ],
    "healer": [
        "............",
        "....wwww....",
        "...wwwwww...",
        "...wksskw...",
        "...wsssssw..",
        "..wwwwwwww..",
        ".swwwrrwwws.",
        "..wwrrrrww..",
        "..wwwrrwww..",
        "..wwwwwwww..",
        "...ww..ww...",
        "...NN..NN...",
    ],
    "sage": [
        "..........c.",
        "....PPPP.ccc",
        "...PPPPPP.c.",
        "...PksskP.n.",
        "...PllllP.n.",
        "..PPllllPPn.",
        ".sPPPllPPPs.",
        "..PPPPPPPPn.",
        "..PPPPPPP.n.",
        "..PPPPPPP.n.",
        "...PP..PP...",
        "...NN..NN...",
    ],
    "wanderer": [
        "............",
        "....hhhh....",
        "...hhhhhh...",
        "...hksskh...",
        "....ssss..o.",
        "...EEEEEE.o.",
        "..sEEeeEEsn.",
        "..sEEeeEE.n.",
        "...EEeeEE...",
        "...EEEEEE...",
        "...nn..nn...",
        "..NNN..NNN..",
    ],
    "rat": [
        "............",
        "............",
        "............",
        "............",
        "......EE....",
        ".....eeeee..",
        "..eeeeeekem.",
        ".eeeeeeeeee.",
        "m.eeeeeeee..",
        ".m.E..E.E...",
        "............",
        "............",
    ],
    "goblin": [
        "............",
        "............",
        "g...gggg...g",
        "gg.gggggg.gg",
        ".gggrggrggg.",
        "...gggggg...",
        "...gGkkGg...",
        "..gnnnnnng..",
        "..g.nnnn.g..",
        "....gggg....",
        "....g..g....",
        "...GG..GG...",
    ],
    "jackal": [
        "............",
        "............",
        "............",
        "..a.........",
        ".aaa........",
        "aakaa.......",
        "kaaaaaaaaa.a",
        "..aaaaaaaaa.",
        "...aaaaaaa..",
        "...a.a..a.a.",
        "...a.a..a.a.",
        "............",
    ],
    "bat": [
        "............",
        "............",
        "............",
        "p....pp....p",
        "pp..pppp..pp",
        "ppppprrppppp",
        "pPppppppppPp",
        "P.Ppppppp.P.",
        "....pppp....",
        ".....pp.....",
        "............",
        "............",
    ],
    "goblin archer": [
        "............",
        "....GGGG..n.",
        "...GGGGGG..n",
        "..gGrggrG..n",
        "...gggggg..n",
        "...GGGGGG..n",
        "..gGGGGGGggn",
        "...GGGGGG..n",
        "....nnnn..n.",
        "....g..g....",
        "....g..g....",
        "...GG..GG...",
    ],
    "orc": [
        "............",
        "....vvvv....",
        "...vvvvvv...",
        "...vrvvrv...",
        "...vwvvwv...",
        "..EEEEEEEE..",
        ".vEEEEEEEEv.",
        ".vEEoEEoEEv.",
        "..EEEEEEEE..",
        "...nn..nn...",
        "...vv..vv...",
        "..NNN..NNN..",
    ],
    "cave spider": [
        "............",
        "............",
        "e..........e",
        ".e..eeee..e.",
        "..eeeeeeee..",
        "eeeeerreeeee",
        "..eEEEEEEe..",
        ".e.eEEEEe.e.",
        "e..e.EE.e..e",
        "...e....e...",
        "............",
        "............",
    ],
    "goblin shaman": [
        "..r.y.r...c.",
        "...ryyr..ccc",
        "...gggggg.c.",
        "..ggrggrgg.n",
        "...gggggg..n",
        "...cccccc..n",
        "..gcccccccgn",
        "...cccccc..n",
        "...cccccc..n",
        "...cc..cc..n",
        "....g..g....",
        "...GG..GG...",
    ],
    "ogre": [
        "...SSSSSS...",
        "..SSSSSSSS..",
        "..SkSSSSkS..",
        "..SSwSSwSS.N",
        "...SSSSSS.NN",
        ".SSnnnnnnSNN",
        "SSSnnnnnnSS.",
        "SS.nnnnnn...",
        "...nnnnnn...",
        "...SSS.SSS..",
        "...SSS.SSS..",
        "..NNNN.NNNN.",
    ],
    "skeleton": [
        "....tttt....",
        "...tttttt...",
        "...tkttkt...",
        "...tttttt...",
        "....tkkt....",
        ".....tt.....",
        "..tttttttt..",
        "..t.tttt.t..",
        "..t.t..t.t..",
        "....tttt....",
        "....t..t....",
        "...tt..tt...",
    ],
    "troll": [
        "...GGGGGG...",
        "..GvvvvvvG..",
        "..vrvvvvrv..",
        "..vvvwwvvv..",
        "...vvvvvv...",
        ".vvvvvvvvvv.",
        "vvvvGGGGvvvv",
        "vv.vGGGGv.vv",
        "vv.vvvvvv.vv",
        "...vvv.vvv..",
        "...vv...vv..",
        "..vvv...vvv.",
    ],
    "mimic": [
        "............",
        "............",
        "..NNNNNNNN..",
        ".NnnnnnnnnN.",
        ".NnyyyyyynN.",
        ".wkwkwkwkwk.",
        ".kkkrrrrkkk.",
        ".wkwkwkwkwk.",
        ".NnnnyynnnN.",
        ".NnnnnnnnnN.",
        ".NNNNNNNNNN.",
        "............",
    ],
    "orc warlord": [
        "...y.y.y....",
        "...yyyyy....",
        "...vvvvv..ll",
        "...rvvrv.lll",
        "...wvvvw..n.",
        ".rEEEEEEr.n.",
        "rrEEyyEEvvn.",
        "rrEEEEEEr.n.",
        "r.EEEEEE..n.",
        "...nn.nn....",
        "...vv.vv....",
        "..NNN.NNN...",
    ],
    "lich": [
        "..y.y.y...o.",
        "..yyyyy..oyo",
        "..ttttt...o.",
        "..tgtgt...n.",
        "...tkt....n.",
        ".PPpppPP..n.",
        "PPpppppPPttn",
        "P.ppyppp..n.",
        "..ppppppp.n.",
        ".pppppppp.n.",
        ".ppppppppp..",
        "PPPPPPPPPP..",
    ],
}

# Player sprites for the non-default classes (the Adventurer uses "player"),
# plus the guild envoy who hands out quests.
SPRITES.update({
    "questgiver": [
        "............",
        "....yyyy....",
        "...yBBBBy...",
        "...BksskB...",
        "....ssss..t.",
        "...BBBBBB.t.",
        "..sBByyBBst.",
        "..sBBBBBB.t.",
        "...BByyBB...",
        "...BBBBBB...",
        "...NN..NN...",
        "..NNN..NNN..",
    ],
    "warrior": [
        "............",
        "....llll....",
        "...llllll...",
        "...lksskl...",
        "....ssss..l.",
        "..rllllll.l.",
        ".rsllyyllsl.",
        ".r.llllll.n.",
        "...llllll...",
        "...EE..EE...",
        "...EE..EE...",
        "..NNN..NNN..",
    ],
    "ranger": [
        "............",
        "....GGGG....",
        "...GGGGGG...",
        "...GksskG.n.",
        "....ssss.n.l",
        "...GGGGGGn.l",
        "..sGGGGGGsnl",
        "...GGnnGG.nl",
        "...GGGGGG.n.",
        "...nn..nn...",
        "...nn..nn...",
        "..NNN..NNN..",
    ],
    "mage": [
        ".....B......",
        "....BbB...c.",
        "...BBBBB.ccc",
        "..BBBBBBB.c.",
        "....kssk..n.",
        "....llll..n.",
        "...BlllBB.n.",
        "..sBBllBBsn.",
        "...BBBBBB.n.",
        "...BBBBBB.n.",
        "..BBBBBBBB..",
        "..NN....NN..",
    ],
})

# Item sprites. Keys are item subtypes (weapon/armor/bow/food names) or kinds.
ITEM_SPRITES: dict[str, list[str]] = {
    "gold": [
        "............",
        "............",
        "............",
        "............",
        ".....yy.....",
        "....yYYy....",
        "...yyyyyy...",
        "..yYyyyYyy..",
        "..yyyYyyyy..",
        "...YyyyyY...",
        "............",
        "............",
    ],
    "potion": [
        "............",
        "....nnnn....",
        ".....ee.....",
        ".....ee.....",
        "....eLLe....",
        "...eLLLLe...",
        "..eLLwLLLe..",
        "..eLLLLLLe..",
        "..eDDDDDDe..",
        "...eDDDDe...",
        "....eeee....",
        "............",
    ],
    "scroll": [
        "............",
        "..nn....nn..",
        "..nttttttn..",
        "..ntEEEEtn..",
        "..nttttttn..",
        "..ntEEEttn..",
        "..nttttttn..",
        "..ntEEEEtn..",
        "..nttttttn..",
        "..nn....nn..",
        "............",
        "............",
    ],
    "book": [
        "............",
        "..DLLLLLLL..",
        "..DLLLLLLLt.",
        "..DLLyyLLLt.",
        "..DLyLLyLLt.",
        "..DLLyyLLLt.",
        "..DLLLLLLLt.",
        "..DLLLLLLLt.",
        "..DLLLLLLLt.",
        "..DDDDDDDDt.",
        "...tttttttt.",
        "............",
    ],
    "apple": [
        "............",
        "......n.....",
        "......nGG...",
        "...rrrnrr...",
        "..rrrrrrrr..",
        "..rwrrrrrr..",
        "..rrrrrrrr..",
        "..rrrrrrrr..",
        "...rrrrrr...",
        "....rrrr....",
        "............",
        "............",
    ],
    "bread": [
        "............",
        "............",
        "............",
        "....nnnn....",
        "..nnnnnnnn..",
        ".nnannanann.",
        ".nnnnnnnnnn.",
        ".NnnnnnnnnN.",
        "..NNNNNNNN..",
        "............",
        "............",
        "............",
    ],
    "ration": [
        "............",
        "............",
        "..aaaanaaa..",
        "..aaaanaaa..",
        "..aaaanaaa..",
        "..nnnnnnnn..",
        "..aaaanaaa..",
        "..aaaanaaa..",
        "..aaaanaaa..",
        "............",
        "............",
        "............",
    ],
    "dagger": [
        "............",
        "............",
        "........l...",
        ".......ll...",
        "......ll....",
        ".....ll.....",
        "....ll......",
        "..yyl.......",
        "...n........",
        "..n.........",
        "............",
        "............",
    ],
    "sword": [
        "..........l.",
        ".........ll.",
        "........ll..",
        ".......ll...",
        "......ll....",
        ".....ll.....",
        "....ll......",
        "..yyl.......",
        "...yy.......",
        "..n.y.......",
        ".n..........",
        "............",
    ],
    "axe": [
        "............",
        "......lll...",
        ".....lllll..",
        "....llnlll..",
        ".....lnl....",
        "......n.....",
        ".....n......",
        "....n.......",
        "...n........",
        "..n.........",
        "............",
        "............",
    ],
    "warhammer": [
        "............",
        "...lllll....",
        "...lEEEl....",
        "...lllll....",
        ".....n......",
        ".....n......",
        ".....n......",
        ".....n......",
        ".....n......",
        ".....N......",
        "............",
        "............",
    ],
    "leather armor": [
        "............",
        "...n....n...",
        "..nnn..nnn..",
        "..nnnnnnnn..",
        "...nnNNnn...",
        "...nnnnnn...",
        "...nNnnNn...",
        "...nnnnnn...",
        "...nnnnnn...",
        "...NNNNNN...",
        "............",
        "............",
    ],
    "chain mail": [
        "............",
        "...e....e...",
        "..eee..eee..",
        "..elelelel..",
        "...eleele...",
        "...lelele...",
        "...elelel...",
        "...lelele...",
        "...elelel...",
        "...EEEEEE...",
        "............",
        "............",
    ],
    "plate mail": [
        "............",
        "...l....l...",
        "..lll..lll..",
        "..llllllll..",
        "...lwllll...",
        "...llllll...",
        "...eeeeee...",
        "...llllll...",
        "...llllll...",
        "...eeeeee...",
        "............",
        "............",
    ],
    "dragon scale": [
        "............",
        "...G....G...",
        "..GGG..GGG..",
        "..GgGgGgGG..",
        "...gGgGgG...",
        "...GgGgGg...",
        "...gGrGgG...",
        "...GgGgGg...",
        "...gGgGgG...",
        "...GGGGGG...",
        "............",
        "............",
    ],
    "shortbow": [
        "............",
        "....nn......",
        "...n..l.....",
        "..n...l.....",
        "..n...l.....",
        "..n...l.....",
        "..n...l.....",
        "..n...l.....",
        "...n..l.....",
        "....nn......",
        "............",
        "............",
    ],
    "longbow": [
        "....nn......",
        "...n..l.....",
        "..n...l.....",
        "..n...l.....",
        ".n....l.....",
        ".n....l.....",
        ".n....l.....",
        ".n....l.....",
        "..n...l.....",
        "..n...l.....",
        "...n..l.....",
        "....nn......",
    ],
    "crossbow": [
        "............",
        "............",
        "..n......n..",
        "...n....n...",
        "....nnnn....",
        "NNNNNNNNNNN.",
        "....llll....",
        ".....NN.....",
        ".....NN.....",
        "............",
        "............",
        "............",
    ],
    "arrows": [
        "............",
        "..........w.",
        ".........lw.",
        "........l...",
        ".......l....",
        "......n.....",
        ".....n......",
        "....n.......",
        "..rrn.......",
        "..rr........",
        "............",
        "............",
    ],
    "ring": [
        "............",
        "............",
        ".....LL.....",
        "....LwLL....",
        ".....DD.....",
        "....y..y....",
        "...y....y...",
        "...y....y...",
        "...y....y...",
        "....y..y....",
        ".....yy.....",
        "............",
    ],
    "key": [
        "............",
        "............",
        "............",
        "...yyy......",
        "..y...y.....",
        "..y...yyyyy.",
        "..y...y..Y.Y",
        "...yyy...Y.Y",
        "............",
        "............",
        "............",
        "............",
    ],
    "relic": [
        "............",
        ".....yy.....",
        "....y..y....",
        "....y..y....",
        ".....yy.....",
        "....llll....",
        "...lmmmml...",
        "...lmwmml...",
        "...lmmmml...",
        "....llll....",
        "............",
        "............",
    ],
    "amulet": [
        "............",
        "..y......y..",
        "...y....y...",
        "....y..y....",
        ".....yy.....",
        "....pPPp....",
        "...pPwPPp...",
        "...pPPPPp...",
        "....pPPp....",
        ".....pp.....",
        "............",
        "............",
    ],
}
SPRITES.update(ITEM_SPRITES)


def item_sprite(item, ident=None) -> tuple[str, tuple[int, int, int] | None, tuple[int, int, int] | None]:
    """(sprite key, tint, outline) for an item. Potions are tinted with their
    (per-game) liquid colour, tomes and rings with theirs; magic gear gets a
    rarity-coloured outline."""
    from .items import RARITIES

    tint = None
    outline = None
    if item.kind == "potion":
        key = "potion"
        tint = ident.potion_looks[item.subtype][1] if ident else item.color
    elif item.kind in ("book", "ring"):
        key, tint = item.kind, item.color
    elif item.kind == "ammo":
        key = "arrows"
    elif item.kind == "quest":
        key = "relic"
    elif item.kind in ("food", "weapon", "armor", "launcher"):
        key = item.subtype
    else:
        key = item.kind  # gold, scroll, amulet
    if item.is_gear and item.rarity != "common":
        outline = RARITIES[item.rarity].color
    return key, tint, outline


def sprite_key(actor: Actor) -> str:
    """Which sprite represents ``actor``."""
    from .entities import NPC, Monster, Player

    if isinstance(actor, Player):
        return "player" if actor.cls.key == "adventurer" else actor.cls.key
    if isinstance(actor, NPC):
        return actor.role
    if isinstance(actor, Monster):
        return actor.kind.name
    return actor.name


def validate() -> list[str]:
    """Problems with the built-in sprite data (empty list = all good)."""
    problems = []
    for key, rows in SPRITES.items():
        if len(rows) != SIZE:
            problems.append(f"{key}: {len(rows)} rows, expected {SIZE}")
        for i, row in enumerate(rows):
            if len(row) != SIZE:
                problems.append(f"{key}: row {i} has {len(row)} pixels, expected {SIZE}")
            bad = {ch for ch in row if ch != "." and ch not in PALETTE}
            if bad:
                problems.append(f"{key}: row {i} uses unknown colours {sorted(bad)}")
    return problems


def _shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(c * factor))) for c in color)  # type: ignore[return-value]


def pixels(
    key: str, tint: tuple[int, int, int] | None = None, outline: tuple[int, int, int] | None = None
) -> list[list[tuple[int, int, int] | None]]:
    """The sprite as a colour grid, with the automatic outline applied.

    ``tint`` recolours the L/D placeholder pixels; ``outline`` replaces the
    dark outline colour (used for item rarity)."""
    palette = dict(PALETTE)
    if tint is not None:
        palette["L"] = tint
        palette["D"] = _shade(tint, 0.6)
    rows = SPRITES[key]
    grid: list[list[tuple[int, int, int] | None]] = [
        [None if ch == "." else palette[ch] for ch in row] for row in rows
    ]
    out = [row[:] for row in grid]
    for y in range(SIZE):
        for x in range(SIZE):
            if grid[y][x] is not None:
                continue
            if any(
                0 <= x + dx < SIZE and 0 <= y + dy < SIZE and grid[y + dy][x + dx] is not None
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                out[y][x] = outline or OUTLINE
    return out


def native_surface(key: str, tint=None, outline=None) -> pygame.Surface:
    import pygame

    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    for y, row in enumerate(pixels(key, tint, outline)):
        for x, color in enumerate(row):
            if color is not None:
                surf.set_at((x, y), (*color, 255))
    return surf


def override_path(key: str) -> Path:
    return SPRITE_DIR / f"{key.replace(' ', '_')}.png"


class SpriteSheet:
    """Loads and caches scaled sprite surfaces."""

    def __init__(self, tile: int) -> None:
        self.tile = tile
        self._cache: dict[tuple, pygame.Surface | None] = {}

    def get(self, key: str, tint=None, outline=None, size: int | None = None) -> pygame.Surface | None:
        size = size or self.tile
        cache_key = (key, tint, outline, size)
        if cache_key in self._cache:
            return self._cache[cache_key]
        import pygame

        surf = None
        path = override_path(key)
        if path.exists() and tint is None:
            try:
                surf = pygame.image.load(str(path))
                if pygame.display.get_surface() is not None:
                    surf = surf.convert_alpha()
            except pygame.error:
                surf = None  # unreadable override: fall back to the built-in art
        if surf is None and key in SPRITES:
            surf = native_surface(key, tint, outline)
        if surf is not None:
            surf = pygame.transform.scale(surf, (size, size))
        self._cache[cache_key] = surf
        return surf


def export(directory: str | Path, scale: int = 1) -> list[Path]:
    """Write every built-in sprite as a PNG (for editing / as templates)."""
    import pygame

    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for key in SPRITES:
        surf = native_surface(key)
        if scale != 1:
            surf = pygame.transform.scale(surf, (SIZE * scale, SIZE * scale))
        path = out_dir / f"{key.replace(' ', '_')}.png"
        pygame.image.save(surf, str(path))
        written.append(path)
    return written


if __name__ == "__main__":  # pragma: no cover - tiny CLI
    target = sys.argv[1] if len(sys.argv) > 1 else "sprites"
    for p in export(target, scale=int(sys.argv[2]) if len(sys.argv) > 2 else 1):
        print(p)
