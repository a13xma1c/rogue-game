"""Mana, spells and the skill tree. Mixed into :class:`roguegame.game.Game`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import settings as S
from . import spells as sp
from .classes import SKILLS, can_learn

if TYPE_CHECKING:
    from .game import Game, ShotPlan


class Magic:
    # ------------------------------------------------------------- skills
    def skill_status(self: Game, key: str) -> tuple[bool, str]:
        p = self.player
        if p.skill_points <= 0:
            ok, why = can_learn(p.cls, p.skills, p.level, key)
            return False, why or "No skill points left - gain a level."
        return can_learn(p.cls, p.skills, p.level, key)

    def learn_skill(self: Game, key: str) -> bool:
        """Spend a skill point on ``key`` (free action)."""
        if self.state.name != "PLAYING":
            return False
        ok, why = self.skill_status(key)
        if not ok:
            self.say(why, S.GREY)
            return False
        p = self.player
        before_hp, before_mana = p.max_hp, p.max_mana
        p.skill_points -= 1
        p.skills[key] = p.skills.get(key, 0) + 1
        # New max HP/mana from a passive comes with the matching current HP/mana.
        p.hp += max(0, p.max_hp - before_hp)
        p.mana += max(0, p.max_mana - before_mana)
        skill = SKILLS[key]
        rank = p.skills[key]
        extra = " (Z to use it)" if skill.spell and rank == 1 else ""
        self.say(f"You learn {skill.name} (rank {rank}/{skill.max_rank}).{extra}", S.CYAN)
        return True

    # ------------------------------------------------------------- spells
    def plan_cast(self: Game, key: str, x: int, y: int) -> ShotPlan:
        return sp.plan(self, key, x, y)

    def cast(self: Game, key: str, x: int | None = None, y: int | None = None) -> bool:
        """Cast ``key`` (at (x, y) for targeted spells). Returns True if time passed."""
        if not self._can_act():
            return False
        p = self.player
        spell = sp.SPELLS.get(key)
        rank = p.spells.get(key, 0)
        if spell is None or rank <= 0:
            self.say("You don't know that spell.", S.GREY)
            return False
        if p.mana < spell.cost:
            self.say(f"Not enough mana for {spell.name} ({p.mana}/{spell.cost}).", S.GREY)
            return False
        plan_: ShotPlan | None = None
        target = None
        if spell.target in sp.TARGETED:
            if x is None or y is None:
                self.say(f"{spell.name} needs a target.", S.GREY)
                return False
            plan_ = self.plan_cast(key, x, y)
            if not plan_.ok:
                self.say(plan_.reason, S.GREY)
                return False
            target = (x, y)
        elif spell.target == "volley" and (not p.launcher or p.arrows <= 0):
            self.say("You need a bow and arrows for that.", S.GREY)
            return False
        p.mana -= spell.cost
        if not sp.cast(self, key, rank, target, plan_):
            p.mana += spell.cost  # fizzled with no effect: no cost, no time
            return False
        self._end_turn()
        return True

    def _tick_mana(self: Game) -> None:
        p = self.player
        interval = max(1, p.cls.mana_regen - p.skill_bonus("mana_regen"))
        if self.turns % interval == 0 and p.mana < p.max_mana:
            p.mana += 1

    # ---------------------------------------------- helpers used by spells
    def fx_shot(self: Game, path, color) -> None:
        from .entities import Fx

        if path:
            self._fx(Fx("shot", list(path), color=color))

    def hurt_monster(self: Game, m, amount: int) -> None:
        self._popup(m, str(amount), S.WHITE)
        self._damage(m, amount, self.player)

    def alert_monster(self: Game, m) -> None:
        m.alert = True

    def inflict(self: Game, target, status: str, turns: int, potency: int = 1) -> None:
        self._inflict(target, status, turns, potency)

    def on_player_moved(self: Game) -> None:
        self._update_fov()
        self._pickup()
