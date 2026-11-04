"""Character sprites: data integrity, rendering, overrides and export."""

import random

import pygame
import pytest

from roguegame import settings as S
from roguegame import sprites
from roguegame.entities import MONSTER_KINDS, NPC, NPC_ROLES, Monster, Player
from roguegame.sprites import OUTLINE, PALETTE, SIZE, SPRITES, SpriteSheet, pixels, sprite_key, validate


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((S.SCREEN_W, S.SCREEN_H))
    yield


def test_sprite_data_is_valid():
    assert validate() == []


def test_every_character_has_a_sprite():
    from roguegame.classes import CLASSES

    characters = {"player"} | set(NPC_ROLES) | set(MONSTER_KINDS) | (set(CLASSES) - {"adventurer"})
    assert characters <= set(SPRITES)
    for cls in CLASSES:
        assert sprite_key(Player(0, 0, cls)) in SPRITES


def every_possible_item():
    """One of every item the game can create."""
    from roguegame import items as I

    yield I.make_gold(0, 0, 5)
    yield I.make_ammo(0, 0, 3)
    yield I.make_amulet(0, 0)
    for kind, table in I.CONSUMABLES.items():
        for subtype in table:
            yield I.make_consumable(0, 0, kind, subtype)
    for bonus, (name, *_rest) in enumerate(I.WEAPONS, start=1):
        yield I.make_weapon(0, 0, bonus, base=name)
    for bonus, (name, *_rest) in enumerate(I.ARMORS, start=1):
        yield I.make_armor(0, 0, bonus, base=name)
    for name, bonus, reach, acc in I.LAUNCHERS:
        yield I.make_launcher(0, 0, name, bonus, reach, acc)
    yield I.make_ring(0, 0, 3, random.Random(1))


def test_every_item_has_a_sprite():
    from roguegame.items import Identification
    from roguegame.sprites import item_sprite

    ident = Identification(random.Random(0))
    seen = set()
    for item in every_possible_item():
        key, tint, _ = item_sprite(item, ident)
        assert key in SPRITES, f"no sprite for {item.kind} {item.subtype or item.name!r}"
        seen.add(key)
        assert SpriteSheet(S.TILE).get(key, tint) is not None
    assert len(seen) >= 20


def test_random_loot_always_has_a_sprite():
    from roguegame.items import Identification, random_item
    from roguegame.sprites import item_sprite

    rng = random.Random(5)
    ident = Identification(rng)
    for depth in range(1, 16):
        for _ in range(150):
            assert item_sprite(random_item(0, 0, depth, rng), ident)[0] in SPRITES


def test_potions_are_tinted_with_their_appearance_and_gear_outlined_by_rarity():
    from roguegame.items import RARITIES, Identification, make_potion, random_gear
    from roguegame.sprites import item_sprite

    ident = Identification(random.Random(3))
    key, tint, outline = item_sprite(make_potion(0, 0, "mana"), ident)
    assert key == "potion" and tint == ident.potion_looks["mana"][1] and outline is None
    rng = random.Random(2)
    for _ in range(200):
        gear = random_gear(0, 0, 8, rng)
        _, _, outline = item_sprite(gear, ident)
        assert outline == (None if gear.rarity == "common" else RARITIES[gear.rarity].color)
    tinted = pixels("potion", tint=(1, 2, 3))
    assert (1, 2, 3) in {c for row in tinted for c in row}
    assert pixels("sword", outline=(9, 9, 9))[0][9] == (9, 9, 9)


def test_sprite_keys():
    assert sprite_key(Player(0, 0)) == "player"
    assert sprite_key(NPC(0, 0, "sage", random.Random(0))) == "sage"
    assert sprite_key(Monster(0, 0, "goblin archer", 2)) == "goblin archer"


def test_sprites_are_distinct():
    seen = {}
    for key, rows in SPRITES.items():
        art = tuple(rows)
        assert art not in seen, f"{key} reuses {seen.get(art)}'s art"
        seen[art] = key


def test_outline_surrounds_the_figure():
    grid = pixels("rat")
    raw = SPRITES["rat"]
    for y in range(SIZE):
        for x in range(SIZE):
            if raw[y][x] != ".":
                assert grid[y][x] == PALETTE[raw[y][x]]
            elif grid[y][x] is not None:
                assert grid[y][x] == OUTLINE
                assert any(
                    0 <= x + dx < SIZE and 0 <= y + dy < SIZE and raw[y + dy][x + dx] != "."
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                )


def test_sheet_scales_and_caches():
    sheet = SpriteSheet(S.TILE)
    surf = sheet.get("orc")
    assert surf.get_size() == (S.TILE, S.TILE)
    assert sheet.get("orc") is surf
    assert sheet.get("no such thing") is None
    # Transparent corners, opaque body.
    assert surf.get_at((0, 0)).a == 0
    assert surf.get_at((S.TILE // 2, S.TILE // 2)).a == 255


def test_png_overrides_replace_built_in_art(tmp_path, monkeypatch):
    monkeypatch.setattr(sprites, "SPRITE_DIR", tmp_path)
    custom = pygame.Surface((16, 16))
    custom.fill((1, 200, 3))
    pygame.image.save(custom, str(tmp_path / "goblin_archer.png"))
    surf = SpriteSheet(S.TILE).get("goblin archer")
    assert surf.get_size() == (S.TILE, S.TILE)
    assert tuple(surf.get_at((5, 5)))[:3] == (1, 200, 3)


def test_broken_overrides_fall_back(tmp_path, monkeypatch):
    monkeypatch.setattr(sprites, "SPRITE_DIR", tmp_path)
    (tmp_path / "rat.png").write_bytes(b"not a png")
    surf = SpriteSheet(S.TILE).get("rat")
    assert surf is not None and surf.get_size() == (S.TILE, S.TILE)


def test_export(tmp_path):
    written = sprites.export(tmp_path, scale=2)
    assert (tmp_path / "potion.png").exists() and (tmp_path / "warrior.png").exists()
    assert len(written) == len(SPRITES)
    img = pygame.image.load(str(tmp_path / "orc_warlord.png"))
    assert img.get_size() == (SIZE * 2, SIZE * 2)
