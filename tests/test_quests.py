"""Quests from guild envoys: slay a champion, fetch a relic, cull monsters."""

import functools

import pytest

from roguegame.game import Game
from roguegame.level import build_level, level_rng
from roguegame.quests import plural

from conftest import cached_level


@functools.lru_cache(maxsize=None)
def seed_for(kind: str, depth: int = 1) -> int:
    for seed in range(400):
        q = build_level(depth, level_rng(seed, depth)).quest
        if q is not None and q.kind == kind:
            return seed
    raise AssertionError(f"no {kind} quest found")


def game_with(kind: str) -> Game:
    """A fresh game whose first floor offers a quest of ``kind``."""
    g = Game(seed=seed_for(kind))
    assert g.level.quest.kind == kind
    return g


def options(g):
    return [o.action for o in g.dialogue.options]


def talk_to_envoy(g):
    npc = next(n for n in g.npcs if n.role == "questgiver")
    g.talk(npc)
    return npc


def accept(g):
    talk_to_envoy(g)
    assert options(g)[:2] == ["quest_ask", "quest_accept"]
    g.choose(0)
    assert "gold" in g.dialogue.text
    g.choose(1)
    g.close_dialogue()
    return g.level.quest


# -------------------------------------------------------------- offering
def test_quests_are_generated_with_their_floor():
    kinds = set()
    for seed in range(60):
        lvl = cached_level(seed, 2)
        if lvl.quest:
            kinds.add(lvl.quest.kind)
            q = lvl.quest
            assert q.giver in lvl.npcs and q.state == "offered" and q.reward_gold > 0 and q.reward_xp > 0
            assert q.reward_item.identified and not q.reward_item.cursed
    assert kinds == {"slay", "fetch", "cull"}


def test_quests_are_part_of_the_seed():
    a, b = build_level(2, level_rng(5, 2)), build_level(2, level_rng(5, 2))
    assert (a.quest is None) == (b.quest is None)
    if a.quest:
        assert (a.quest.kind, a.quest.title) == (b.quest.kind, b.quest.title)


def test_accepting_adds_to_the_journal():
    g = game_with("fetch")
    quest = accept(g)
    assert quest.state == "active" and g.quests == [quest]
    talk_to_envoy(g)
    assert options(g)[0] == "quest_ask", "no reward before the job is done"
    g.choose(0)
    assert "Not found yet" in g.dialogue.text


# ------------------------------------------------------------------ slay
def test_slay_quest():
    g = game_with("slay")
    quest = accept(g)
    champ = quest.target
    assert champ.title and champ in g.monsters and champ.xp_value > 0
    assert champ.display_name.startswith(champ.title)
    gold, xp = g.player.gold, g.player.xp + g.player.level * 1000
    champ.hp = 0
    g._kill(champ)
    assert quest.is_done(g.player) and "Return to" in quest.status(g.player)
    assert any(champ.title in m for m, _ in g.log)
    talk_to_envoy(g)
    g.choose(options(g).index("quest_claim"))
    assert quest.state == "rewarded" and g.player.gold == gold + quest.reward_gold
    assert quest.reward_item in g.player.pack or quest.reward_item in g.items
    assert g.player.xp + g.player.level * 1000 > xp
    talk_to_envoy(g)
    assert options(g)[0] == "rumour", "nothing more to claim"


# ----------------------------------------------------------------- fetch
def test_fetch_quest():
    g = game_with("fetch")
    quest = accept(g)
    relic = quest.relic
    assert relic in g.items and relic.kind == "quest"
    assert not quest.is_done(g.player)
    g.items.remove(relic)
    g.player.add_to_pack(relic)
    assert quest.is_done(g.player)
    g.player.pack.remove(relic)
    assert not quest.is_done(g.player), "dropping it undoes the job"
    g.player.add_to_pack(relic)
    talk_to_envoy(g)
    g.choose(options(g).index("quest_claim"))
    assert relic not in g.player.pack and quest.state == "rewarded"


@pytest.mark.slow
def test_relics_are_often_hidden_in_secret_rooms_or_vaults():
    hidden = 0
    total = 0
    for seed in range(120):
        lvl = build_level(2, level_rng(seed, 2))
        q = lvl.quest
        if q is None or q.kind != "fetch":
            continue
        total += 1
        hidden += any(pc.room.contains(q.relic.x, q.relic.y) for pc in lvl.pieces)
    assert total and hidden > 0


def test_picking_up_a_relic_explains_itself(arena, item):
    from roguegame.items import make_relic

    g = arena("""
        #######
        #.@...#
        #######
    """)
    g.items.append(make_relic(3, 1, "Maud's silver locket"))
    g._update_fov()
    g.player_move(1, 0)
    assert "guild envoy" in g.log[-1][0]


# ------------------------------------------------------------------ cull
def test_cull_quest_counts_only_after_accepting_and_on_its_floor():
    g = game_with("cull")
    quest = g.level.quest
    victims = [m for m in g.monsters if m.kind.name == quest.monster_kind]
    g._kill(victims[0])
    assert quest.progress == 0, "kills before accepting don't count"
    accept(g)
    for m in victims[1: 1 + quest.needed]:
        g._kill(m)
    assert quest.progress == min(quest.needed, len(victims) - 1)
    g.depth, saved = 99, g.depth
    quest.note_kill(victims[1], 99)
    g.depth = saved
    assert quest.progress <= quest.needed
    if quest.is_done(g.player):
        talk_to_envoy(g)
        g.choose(options(g).index("quest_claim"))
        assert quest.state == "rewarded"


@pytest.mark.parametrize("word, expected", [("goblin", "goblins"), ("bat", "bats"), ("goblin archer",
                                                                                       "goblin archers")])
def test_plurals(word, expected):
    assert plural(word) == expected


def test_journal_panel_and_key():
    import pygame

    from roguegame.ui import App, Mode, Renderer

    g = game_with("slay")
    accept(g)
    app = App(g)
    app.handle_key(pygame.K_j, "J")
    assert app.mode is Mode.JOURNAL
    pygame.init()
    Renderer(pygame.display.set_mode((960, 796))).draw(app)
    app.handle_key(pygame.K_j, "J")
    assert app.mode is Mode.NORMAL
    app.handle_key(pygame.K_j, "j")
    assert app.mode is Mode.NORMAL, "plain j still moves"


def test_champions_glow_gold(arena):
    import pygame

    from roguegame import settings as S
    from roguegame.sprites import SpriteSheet

    pygame.init()
    pygame.display.set_mode((10, 10))
    gold = SpriteSheet(S.TILE).get("goblin", outline=S.YELLOW)
    colors = {tuple(gold.get_at((x, y)))[:3] for x in range(S.TILE) for y in range(S.TILE)}
    assert S.YELLOW in colors
