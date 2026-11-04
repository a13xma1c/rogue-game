"""The tile table is the single source of truth for terrain behaviour."""

import pytest

from roguegame import tiles as T


ALL_TILES = [T.WALL, T.FLOOR, T.STAIRS_DOWN, T.STAIRS_UP, T.DOOR_CLOSED, T.DOOR_OPEN,
             T.TRAP, T.FOUNTAIN, T.FOUNTAIN_DRY, T.CHEST, T.CHEST_OPEN, T.DOOR_LOCKED, T.PORTCULLIS,
             T.PORTCULLIS_OPEN, T.LEVER, T.LEVER_PULLED, T.SECRET_DOOR, T.SHRINE, T.SHRINE_USED,
             T.BOOKSHELF, T.BOOKSHELF_EMPTY, T.WATER, T.DEEP_WATER]


def test_every_tile_constant_has_a_definition():
    assert set(ALL_TILES) == set(T.TILES)
    assert len(set(ALL_TILES)) == len(ALL_TILES), "tile ids must be unique"


def test_stairs_alias_is_down_stairs():
    assert T.STAIRS == T.STAIRS_DOWN


@pytest.mark.parametrize(
    "tile, walkable, transparent",
    [
        (T.WALL, False, False),
        (T.FLOOR, True, True),
        (T.STAIRS_DOWN, True, True),
        (T.STAIRS_UP, True, True),
        (T.DOOR_CLOSED, False, False),
        (T.DOOR_OPEN, True, True),
        (T.TRAP, True, True),
        (T.FOUNTAIN, False, True),
        (T.FOUNTAIN_DRY, False, True),
        (T.CHEST, False, True),
        (T.CHEST_OPEN, True, True),
        (T.DOOR_LOCKED, False, False),
        (T.PORTCULLIS, False, True),
        (T.PORTCULLIS_OPEN, True, True),
        (T.SECRET_DOOR, False, False),
        (T.WATER, True, True),
        (T.DEEP_WATER, False, True),
    ],
)
def test_walkable_and_transparent(tile, walkable, transparent):
    tt = T.tile_type(tile)
    assert tt.walkable is walkable
    assert tt.transparent is transparent


def test_closed_doors_are_pathable_but_not_walkable():
    door = T.TILES[T.DOOR_CLOSED]
    assert not door.walkable and door.can_path
    # Furniture is neither walkable nor something monsters route through.
    for tile in (T.FOUNTAIN, T.CHEST, T.WALL, T.DOOR_LOCKED, T.PORTCULLIS, T.SECRET_DOOR, T.DEEP_WATER):
        assert not T.TILES[tile].can_path, "monsters can't open locks, raise gates or swim"


def test_interactive_tiles():
    interactive = {t for t, tt in T.TILES.items() if tt.interactive}
    assert interactive == {T.DOOR_CLOSED, T.FOUNTAIN, T.CHEST, T.DOOR_LOCKED, T.PORTCULLIS, T.LEVER,
                           T.LEVER_PULLED, T.SHRINE, T.BOOKSHELF}


def test_every_tile_has_a_name_and_description():
    for tt in T.TILES.values():
        assert tt.name and tt.description


def test_trap_kinds():
    assert set(T.TRAP_KINDS) == {"spike", "alarm", "teleport"}
    for name, color, desc in T.TRAP_KINDS.values():
        assert "trap" in name and len(color) == 3 and desc
