import argparse

from .classes import CLASS_NAMES
from .difficulty import CLASSIC, DIFFICULTY_NAMES, ENDLESS, GameOptions


def parse_args(argv: list[str] | None = None) -> tuple[GameOptions, int | None, bool]:
    """Parse command-line options into (options, seed, show_menu).

    Choosing a mode, difficulty or class on the command line skips the title screen.
    """
    parser = argparse.ArgumentParser(prog="roguegame", description="A 2D turn-based roguelike.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--classic", dest="mode", action="store_const", const=CLASSIC,
                      help="five floors and the Amulet of Yendor (default)")
    mode.add_argument("--endless", dest="mode", action="store_const", const=ENDLESS,
                      help="descend forever; bosses return stronger every five floors")
    parser.add_argument("--difficulty", "-d", choices=DIFFICULTY_NAMES, help="default: normal")
    parser.add_argument("--class", "-c", dest="player_class", choices=CLASS_NAMES, help="default: adventurer")
    parser.add_argument("--seed", type=int, help="dungeon seed, for replaying the same dungeon")
    args = parser.parse_args(argv)
    options = GameOptions(args.mode or CLASSIC, args.difficulty or "normal", args.player_class or "adventurer")
    show_menu = args.mode is None and args.difficulty is None and args.player_class is None
    return options, args.seed, show_menu


def main(argv: list[str] | None = None) -> None:
    options, seed, show_menu = parse_args(argv)
    from .ui import run

    run(options=options, seed=seed, menu=show_menu)
