"""局内特殊状态判断。

这个模块存放与“当前这一局的时机”有关的判断，例如天和、地和、人和、海底、
河底、抢杠、九种九牌、四风连打等。它们通常不是普通牌型计算能解决的问题，
需要结合摸牌来源、第一巡、是否有鸣牌、最后弃牌来源等局内上下文。
"""

from __future__ import annotations

from typing import Any

from app.engine_constants import ABORTIVE_DRAW_HEADLINES
from app.engine_rules import ensure_game_defaults, ensure_round_state_defaults
from app.engine_shape import unique_terminal_honor_types
from app.engine_tiles import tile_type


def round_has_any_calls(round_state: dict[str, Any]) -> bool:
    return any(round_state["melds"][seat] for seat in range(round_state["player_count"]))

def seat_is_on_first_turn(round_state: dict[str, Any], seat: int) -> bool:
    return not round_state["discards"][seat]

def round_is_uninterrupted(round_state: dict[str, Any]) -> bool:
    return not round_has_any_calls(round_state)

def is_tenhou_state(round_state: dict[str, Any], seat: int, *, is_tsumo: bool) -> bool:
    if not is_tsumo or seat != round_state["dealer_seat"]:
        return False
    if not round_is_uninterrupted(round_state):
        return False
    return not any(round_state["discards"][idx] for idx in range(round_state["player_count"]))

def is_chiihou_state(round_state: dict[str, Any], seat: int, *, is_tsumo: bool) -> bool:
    if not is_tsumo or seat == round_state["dealer_seat"]:
        return False
    if not round_is_uninterrupted(round_state):
        return False
    return seat_is_on_first_turn(round_state, seat)

def is_renhou_state(game: dict[str, Any], seat: int, *, is_tsumo: bool) -> bool:
    if is_tsumo or not bool(game.get("koyaku_enabled", False)):
        return False
    round_state = game["round_state"]
    if seat == round_state["dealer_seat"]:
        return False
    if not round_is_uninterrupted(round_state):
        return False
    if round_state["last_draw_source"][seat]:
        return False
    discard = round_state["last_discard"]
    if discard is None or discard["seat"] == seat or discard.get("source") in {"kan", "kita"}:
        return False
    return seat_is_on_first_turn(round_state, seat)

def is_haitei_state(round_state: dict[str, Any], seat: int, *, is_tsumo: bool) -> bool:
    if not is_tsumo or round_state["current_draw"] is None:
        return False
    return round_state["current_draw_source"] == "wall" and round_state["turn_seat"] == seat and not round_state["live_wall"]

def is_houtei_state(round_state: dict[str, Any], *, is_tsumo: bool) -> bool:
    if is_tsumo:
        return False
    discard = round_state["last_discard"]
    if discard is None or discard.get("source") in {"kan", "kita"}:
        return False
    return round_state["last_draw_source"][discard["seat"]] == "wall" and not round_state["live_wall"]

def is_chankan_state(round_state: dict[str, Any], *, is_tsumo: bool) -> bool:
    if is_tsumo:
        return False
    discard = round_state["last_discard"]
    if discard is None or discard.get("source") != "kan":
        return False
    return discard.get("kan_type") != "closed_kan"

def can_abortive_draw_nine_terminals(game: dict[str, Any], seat: int) -> bool:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    if round_state["phase"] != "DISCARD" or round_state["turn_seat"] != seat or round_state["current_draw"] is None:
        return False
    if round_state["discards"][seat]:
        return False
    if round_has_any_calls(round_state):
        return False
    return len(unique_terminal_honor_types(round_state["hands"][seat])) >= 9

def top_player_entry(game: dict[str, Any]) -> dict[str, Any]:
    return min(game["players"], key=lambda player: (-player["points"], player["seat"]))

def goal_score_reached(game: dict[str, Any]) -> bool:
    ensure_game_defaults(game)
    return any(player["points"] >= game["target_score"] for player in game["players"])

def round_result_kind(game: dict[str, Any]) -> str:
    round_state = game["round_state"]
    round_result = round_state.get("round_result")
    if isinstance(round_result, dict):
        kind = round_result.get("kind")
        if isinstance(kind, str):
            return kind
    return ""

def round_result_subtype(game: dict[str, Any]) -> str:
    round_state = game["round_state"]
    round_result = round_state.get("round_result")
    if isinstance(round_result, dict):
        subtype = round_result.get("subtype")
        if isinstance(subtype, str):
            return subtype
    return ""

def is_win_like_round_result(game: dict[str, Any]) -> bool:
    kind = round_result_kind(game)
    if kind in {"RON", "TSUMO"}:
        return True
    return kind == "DRAW" and round_result_subtype(game) == "NAGASHI_MANGAN"

def should_auto_stop_all_last_dealer(game: dict[str, Any], *, dealer_continues: bool) -> bool:
    ensure_game_defaults(game)
    if not dealer_continues:
        return False
    if game["round_cursor"] != game["base_rounds"] - 1:
        return False
    if round_result_kind(game) == "ABORTIVE_DRAW":
        return False
    dealer = game["round_state"]["dealer_seat"]
    return top_player_entry(game)["seat"] == dealer and goal_score_reached(game)

def evaluate_pending_abortive_draw_after_discard(game: dict[str, Any]) -> dict[str, str] | None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    if round_state["player_count"] != 4:
        return None

    if all(len(round_state["discards"][seat]) == 1 for seat in range(round_state["player_count"])):
        first_discard_types = {tile_type(round_state["discards"][seat][0]["tile"]) for seat in range(round_state["player_count"])}
        if len(first_discard_types) == 1 and next(iter(first_discard_types)) in {27, 28, 29, 30} and not round_has_any_calls(round_state):
            return {"kind": "SUUFON_RENDA", "headline": ABORTIVE_DRAW_HEADLINES["SUUFON_RENDA"]}

    if all(round_state["riichi"]):
        return {"kind": "SUUCHA_RIICHI", "headline": ABORTIVE_DRAW_HEADLINES["SUUCHA_RIICHI"]}

    return None

def kan_owner_count(round_state: dict[str, Any]) -> int:
    kan_types = {"open_kan", "closed_kan", "added_kan"}
    owners = {
        seat
        for seat in range(round_state["player_count"])
        if any(meld["type"] in kan_types for meld in round_state["melds"][seat])
    }
    return len(owners)

def should_abort_for_four_kans(round_state: dict[str, Any]) -> bool:
    ensure_round_state_defaults(round_state)
    return round_state["kan_count"] >= 4 and kan_owner_count(round_state) > 1

def four_kan_abortive_draw_payload() -> dict[str, str]:
    return {"kind": "SUUKAIKAN", "headline": ABORTIVE_DRAW_HEADLINES["SUUKAIKAN"]}

def should_abort_for_triple_ron(game: dict[str, Any], winners: list[int]) -> bool:
    return False

def is_kokushi_result(result: dict[str, Any] | None) -> bool:
    if result is None:
        return False
    if "yakuman_keys" in result:
        return "KOKUSHI" in result.get("yakuman_keys", {})
    return any("kokushi" in str(name).lower() or "国士" in str(name) for name in result.get("yaku", []))

def kan_reaction_tile(round_state: dict[str, Any]) -> dict[str, Any] | None:
    ensure_round_state_defaults(round_state)
    pending_kan = round_state.get("pending_kan")
    if not isinstance(pending_kan, dict):
        return None
    return {
        "seat": pending_kan["seat"],
        "tile": pending_kan["tile_id"],
        "source": "kan",
        "kan_type": pending_kan["action_type"],
    }

def kita_reaction_tile(round_state: dict[str, Any]) -> dict[str, Any] | None:
    ensure_round_state_defaults(round_state)
    pending_kita = round_state.get("pending_kita")
    if not isinstance(pending_kita, dict):
        return None
    return {
        "seat": pending_kita["seat"],
        "tile": pending_kita["tile_id"],
        "source": "kita",
    }

__all__ = [
    "round_has_any_calls",
    "seat_is_on_first_turn",
    "round_is_uninterrupted",
    "is_tenhou_state",
    "is_chiihou_state",
    "is_renhou_state",
    "is_haitei_state",
    "is_houtei_state",
    "is_chankan_state",
    "can_abortive_draw_nine_terminals",
    "top_player_entry",
    "goal_score_reached",
    "round_result_kind",
    "round_result_subtype",
    "is_win_like_round_result",
    "should_auto_stop_all_last_dealer",
    "evaluate_pending_abortive_draw_after_discard",
    "kan_owner_count",
    "should_abort_for_four_kans",
    "four_kan_abortive_draw_payload",
    "should_abort_for_triple_ron",
    "is_kokushi_result",
    "kan_reaction_tile",
    "kita_reaction_tile",
]
