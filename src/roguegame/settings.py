"""Global constants for the game."""

TILE = 24
MAP_W = 100
MAP_H = 64

VIEW_W = 40  # tiles visible horizontally
VIEW_H = 26  # tiles visible vertically
HUD_H = 172

SCREEN_W = VIEW_W * TILE
SCREEN_H = VIEW_H * TILE + HUD_H
FPS = 60

FOV_RADIUS = 8
MAX_DEPTH = 5  # the Amulet is on this floor
MAX_INVENTORY = 5  # per consumable type

# Minimap (drawn in the right-hand side of the HUD)
MINIMAP_SCALE = 2  # pixels per map tile
MINIMAP_W = MAP_W * MINIMAP_SCALE
MINIMAP_H = MAP_H * MINIMAP_SCALE

# Full-screen map overlay (toggled with M): as large as fits the view.
BIGMAP_SCALE = min(VIEW_W * TILE // MAP_W, (VIEW_H * TILE - 60) // MAP_H)

# Colors
BLACK = (0, 0, 0)
WHITE = (235, 235, 235)
GREY = (140, 140, 150)
DARK_GREY = (90, 90, 100)
RED = (220, 60, 60)
GREEN = (80, 200, 100)
BLUE = (80, 140, 230)
YELLOW = (240, 210, 70)
ORANGE = (240, 140, 50)
PURPLE = (170, 90, 210)
CYAN = (80, 210, 220)
BROWN = (150, 100, 50)
AMBER = (215, 150, 65)
DOOR_PANEL = (92, 62, 32)
PINK = (230, 130, 190)

WALL_LIT = (95, 90, 120)
WALL_DIM = (38, 36, 52)
FLOOR_LIT = (58, 52, 46)
FLOOR_DIM = (26, 24, 22)
