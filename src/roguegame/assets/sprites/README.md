# Sprite overrides

Drop PNG files here to replace the built-in pixel-art sprites. Name each file
after the sprite key with spaces turned into underscores, for example:

    player.png  merchant.png  healer.png  sage.png  wanderer.png
    rat.png  goblin.png  jackal.png  bat.png  goblin_archer.png  orc.png
    cave_spider.png  goblin_shaman.png  ogre.png  skeleton.png  troll.png
    mimic.png  orc_warlord.png  lich.png

Any size works (it is scaled to the tile size with nearest-neighbour scaling),
and transparency is respected. Unreadable files fall back to the built-in art.

To get the built-in sprites as editable templates:

    uv run python -m roguegame.sprites some/dir 4    # 4x scale
