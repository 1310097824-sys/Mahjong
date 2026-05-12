"""玩家动作执行入口。

API 收到 action_id 后会走到这里：先匹配当前合法动作，再根据动作类型调用相应的
状态变更、计分或结算流程。执行完成后会刷新公开状态并继续自动推进 AI 回合。
"""

from __future__ import annotations

import sys
from typing import Any

from app.engine_actions import (
    apply_forced_furiten_for_current_discard,
    build_reaction_actions as _build_reaction_actions,
    build_turn_actions as _build_turn_actions,
    forced_riichi_tsumogiri_action as _forced_riichi_tsumogiri_action,
)
from app.engine_ai import choose_ai_reaction as _choose_ai_reaction, choose_ai_turn_action as _choose_ai_turn_action
from app.engine_common import ActionChoice, now_iso
from app.engine_constants import ABORTIVE_DRAW_HEADLINES
from app.engine_game import start_next_round
from app.engine_mutations import apply_discard, perform_call, perform_kita, resolve_pending_kan, resolve_pending_kita, rotate_turn
from app.engine_round import should_abort_for_triple_ron
from app.engine_rules import ensure_game_defaults
from app.engine_settlement import (
    build_ron_winners as _build_ron_winners,
    settle_abortive_draw,
    settle_ron,
    settle_tsumo,
)
from app.engine_state import build_public_state
from app.engine_tiles import is_red, tile_type


def _public_engine_function(name: str, fallback: Any) -> Any:
    module = sys.modules.get("app.engine")
    candidate = getattr(module, name, None) if module is not None else None
    if callable(candidate) and candidate is not fallback:
        return candidate
    return fallback


def build_turn_actions(*args: Any, **kwargs: Any) -> list[ActionChoice]:
    return _public_engine_function("build_turn_actions", _build_turn_actions)(*args, **kwargs)


def build_reaction_actions(*args: Any, **kwargs: Any) -> list[ActionChoice]:
    return _public_engine_function("build_reaction_actions", _build_reaction_actions)(*args, **kwargs)


def forced_riichi_tsumogiri_action(*args: Any, **kwargs: Any) -> ActionChoice | None:
    return _public_engine_function("forced_riichi_tsumogiri_action", _forced_riichi_tsumogiri_action)(*args, **kwargs)


def choose_ai_turn_action(*args: Any, **kwargs: Any) -> tuple[ActionChoice, str]:
    return _public_engine_function("choose_ai_turn_action", _choose_ai_turn_action)(*args, **kwargs)


def choose_ai_reaction(*args: Any, **kwargs: Any) -> tuple[ActionChoice | None, str | None]:
    return _public_engine_function("choose_ai_reaction", _choose_ai_reaction)(*args, **kwargs)


def build_ron_winners(*args: Any, **kwargs: Any) -> list[int]:
    return _public_engine_function("build_ron_winners", _build_ron_winners)(*args, **kwargs)

def auto_advance(game: dict[str, Any]) -> None:
    ensure_game_defaults(game)
    while game["status"] == "RUNNING":
        round_state = game["round_state"]
        if round_state["phase"] == "ROUND_END":
            break
        if round_state["phase"] == "DISCARD":
            seat = round_state["turn_seat"]
            if seat == game["human_seat"]:
                human_actions = build_turn_actions(game, seat)
                forced_tsumogiri = forced_riichi_tsumogiri_action(game, seat, human_actions)
                if forced_tsumogiri is not None:
                    execute_action(game, forced_tsumogiri.action_id, actor_seat=seat, advance=False)
                    continue
                break
            action, reason = choose_ai_turn_action(game, seat)
            game["players"][seat]["last_reason"] = reason
            execute_action(game, action.action_id, actor_seat=seat, advance=False)
            continue
        if round_state["phase"] == "REACTION":
            human_choices = build_reaction_actions(game, game["human_seat"])
            if human_choices:
                break
            action, reason = choose_ai_reaction(game)
            if reason == "ron":
                winners = build_ron_winners(game, include_human=False)
                if winners:
                    if should_abort_for_triple_ron(game, winners):
                        settle_abortive_draw(game, "SANCHAHOU")
                    else:
                        settle_ron(game, winners)
                else:
                    apply_forced_furiten_for_current_discard(game)
                    if resolve_pending_kan(game):
                        pass
                    elif resolve_pending_kita(game):
                        pass
                    elif round_state["pending_abortive_draw"] is not None:
                        settle_abortive_draw(
                            game,
                            round_state["pending_abortive_draw"]["kind"],
                            round_state["pending_abortive_draw"]["headline"],
                        )
                    else:
                        rotate_turn(game)
                continue
            if action is None:
                apply_forced_furiten_for_current_discard(game)
                if resolve_pending_kan(game):
                    pass
                elif resolve_pending_kita(game):
                    pass
                elif round_state["pending_abortive_draw"] is not None:
                    settle_abortive_draw(
                        game,
                        round_state["pending_abortive_draw"]["kind"],
                        round_state["pending_abortive_draw"]["headline"],
                    )
                else:
                    rotate_turn(game)
                continue
            game["players"][action.seat]["last_reason"] = reason or ""
            apply_forced_furiten_for_current_discard(game, exclude_seat=action.seat)
            execute_action(game, action.action_id, actor_seat=action.seat, advance=False)
            continue
        break
    game["public_state"] = build_public_state(game)
    game["updated_at"] = now_iso()

def parse_action_id(action_id: str) -> tuple[str, list[str]]:
    parts = action_id.split("|")
    return parts[0], parts[1:]

def current_legal_action_ids(game: dict[str, Any], seat: int) -> set[str]:
    if game["status"] == "FINISHED":
        return set()

    round_state = game["round_state"]
    if round_state["phase"] == "ROUND_END":
        return {"next_round"} if seat == game["human_seat"] else set()

    if round_state["phase"] == "DISCARD":
        if round_state["turn_seat"] != seat:
            return set()
        return {action.action_id for action in build_turn_actions(game, seat)}

    if round_state["phase"] == "REACTION":
        actions = build_reaction_actions(game, seat)
        legal_ids = {action.action_id for action in actions}
        if actions:
            legal_ids.add("pass")
        return legal_ids

    return set()

def normalize_equivalent_turn_action_id(game: dict[str, Any], seat: int, action_id: str) -> str:
    round_state = game["round_state"]
    if round_state["phase"] != "DISCARD" or round_state["turn_seat"] != seat:
        return action_id

    action_type, parts = parse_action_id(action_id)
    if action_type not in {"discard", "riichi", "kita"} or not parts:
        return action_id
    try:
        requested_tile = int(parts[0])
    except ValueError:
        return action_id

    requested_key = (tile_type(requested_tile), is_red(requested_tile, game))
    for action in build_turn_actions(game, seat):
        if action.type != action_type or action.tile_id is None:
            continue
        if (tile_type(action.tile_id), is_red(action.tile_id, game)) == requested_key:
            return action.action_id
    return action_id

def execute_action(
    game: dict[str, Any], action_id: str, *, actor_seat: int | None = None, advance: bool = True
) -> dict[str, Any]:
    ensure_game_defaults(game)
    seat = actor_seat if actor_seat is not None else game["human_seat"]
    action_id = normalize_equivalent_turn_action_id(game, seat, action_id)
    legal_ids = current_legal_action_ids(game, seat)
    if action_id not in legal_ids:
        if seat == game["human_seat"]:
            game["public_state"] = build_public_state(game)
            game["updated_at"] = now_iso()
            return game
        raise ValueError(f"Illegal action for current phase: {action_id}")

    round_state = game["round_state"]
    action_type, parts = parse_action_id(action_id)
    if action_type == "next_round":
        start_next_round(game)
        return game
    if action_type == "pass":
        had_ron = any(action.type == "ron" for action in build_reaction_actions(game, seat))
        round_state["reaction_passed"][seat] = True
        if had_ron:
            if round_state.get("last_discard", {}).get("source") != "kita":
                if round_state["riichi"][seat]:
                    round_state["riichi_furiten"][seat] = True
                else:
                    round_state["temporary_furiten"][seat] = True
        if advance:
            auto_advance(game)
        return game
    if round_state["phase"] == "DISCARD":
        if action_type == "abortive_draw":
            settle_abortive_draw(game, parts[0], ABORTIVE_DRAW_HEADLINES.get(parts[0]))
        elif action_type == "tsumo":
            settle_tsumo(game, seat)
        elif action_type == "discard":
            apply_discard(game, seat, int(parts[0]), declare_riichi=False)
        elif action_type == "riichi":
            apply_discard(game, seat, int(parts[0]), declare_riichi=True)
        elif action_type == "kita":
            perform_kita(game, seat, int(parts[0]))
        elif action_type == "closed_kan":
            consumed = [int(item) for item in parts[1].split(",")]
            perform_call(game, seat, "closed_kan", consumed[0], consumed)
        elif action_type == "added_kan":
            meld_index = int(parts[1])
            tile_id = int(parts[2])
            perform_call(game, seat, "added_kan", tile_id, [tile_id], meld_index=meld_index)
        else:
            raise ValueError(f"Unsupported turn action {action_type}")
    elif round_state["phase"] == "REACTION":
        if action_type == "ron":
            winners = build_ron_winners(game, include_human=True)
            if seat not in winners:
                winners.append(seat)
            if should_abort_for_triple_ron(game, winners):
                settle_abortive_draw(game, "SANCHAHOU")
            else:
                settle_ron(game, winners)
        elif action_type in {"chi", "pon", "open_kan"}:
            apply_forced_furiten_for_current_discard(game, exclude_seat=seat)
            discard_tile = int(parts[0])
            consumed = [int(item) for item in parts[1].split(",")]
            perform_call(game, seat, action_type, discard_tile, consumed)
        else:
            raise ValueError(f"Unsupported reaction action {action_type}")
    if advance:
        auto_advance(game)
    return game

__all__ = [
    "auto_advance",
    "parse_action_id",
    "current_legal_action_ids",
    "normalize_equivalent_turn_action_id",
    "execute_action",
]
