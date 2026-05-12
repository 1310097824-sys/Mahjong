"""局面变更的底层操作。

这里封装对 `game` / `round_state` 的直接修改，例如摸牌、弃牌、移动牌到副露、
揭宝牌、记录快照等。动作执行层调用这些小操作组合成完整动作，避免到处手写
状态字段修改而产生难查的同步错误。
"""

from __future__ import annotations

import sys
from typing import Any

from app.engine_actions import can_double_riichi, kuikae_forbidden_tile_types
from app.engine_constants import KAN_DETAIL_LABELS
from app.engine_game import record_action as _record_action
from app.engine_round import (
    evaluate_pending_abortive_draw_after_discard,
    four_kan_abortive_draw_payload,
    kan_reaction_tile,
    kita_reaction_tile,
    should_abort_for_four_kans,
)
from app.engine_rules import (
    apply_kan_dora_timing,
    clear_ippatsu,
    ensure_round_state_defaults,
    flush_pending_kan_dora,
    invalidate_pending_double_riichi,
    next_seat,
    settle_pending_double_riichi,
)
from app.engine_scoring import register_liability_for_call
from app.engine_settlement import settle_exhaustive_draw
from app.engine_tiles import pop_specific_tiles, sort_tiles


def _public_engine_function(name: str, fallback: Any) -> Any:
    module = sys.modules.get("app.engine")
    candidate = getattr(module, name, None) if module is not None else None
    if callable(candidate) and candidate is not fallback:
        return candidate
    return fallback


def record_action(*args: Any, **kwargs: Any) -> None:
    return _public_engine_function("record_action", _record_action)(*args, **kwargs)

def begin_kan_reaction(
    game: dict[str, Any],
    seat: int,
    action_type: str,
    tile_id: int,
    consumed_ids: list[int],
    meld_index: int | None = None,
) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    flush_pending_kan_dora(round_state)
    invalidate_pending_double_riichi(round_state)
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = {
        "seat": seat,
        "action_type": action_type,
        "tile_id": tile_id,
        "consumed_ids": list(consumed_ids),
        "meld_index": meld_index,
    }
    round_state["last_discard"] = kan_reaction_tile(round_state)
    round_state["phase"] = "REACTION"
    round_state["reaction_passed"] = [False] * round_state["player_count"]

def begin_kita_reaction(game: dict[str, Any], seat: int, tile_id: int) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    invalidate_pending_double_riichi(round_state)
    round_state["hands"][seat].remove(tile_id)
    round_state["hands"][seat] = sort_tiles(round_state["hands"][seat])
    round_state["melds"][seat].append(
        {"type": "kita", "tiles": [tile_id], "opened": False, "called_tile": tile_id, "from_seat": seat}
    )
    round_state["pending_abortive_draw"] = None
    round_state["pending_kita"] = {"seat": seat, "tile_id": tile_id}
    round_state["last_discard"] = kita_reaction_tile(round_state)
    round_state["current_draw"] = None
    round_state["phase"] = "REACTION"
    round_state["reaction_passed"] = [False] * round_state["player_count"]
    record_action(game, seat, "KITA", tile_id=tile_id, details="拔北宝牌")

def resolve_pending_kan(game: dict[str, Any]) -> bool:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    pending_kan = round_state.get("pending_kan")
    if not isinstance(pending_kan, dict):
        return False

    seat = pending_kan["seat"]
    action_type = pending_kan["action_type"]
    tile_id = pending_kan["tile_id"]
    consumed_ids = list(pending_kan["consumed_ids"])
    meld_index = pending_kan.get("meld_index")

    clear_ippatsu(round_state)
    if action_type == "closed_kan":
        pop_specific_tiles(round_state["hands"][seat], consumed_ids)
        round_state["hands"][seat] = sort_tiles(round_state["hands"][seat])
        round_state["melds"][seat].append(
            {"type": "closed_kan", "tiles": sort_tiles(consumed_ids), "opened": False, "called_tile": None, "from_seat": seat}
        )
    elif action_type == "added_kan":
        round_state["hands"][seat].remove(tile_id)
        round_state["hands"][seat] = sort_tiles(round_state["hands"][seat])
        meld = round_state["melds"][seat][meld_index]
        meld["type"] = "added_kan"
        meld["tiles"] = sort_tiles(meld["tiles"] + [tile_id])
        meld["opened"] = True
        meld["called_tile"] = tile_id
        meld["from_seat"] = seat
    else:
        return False

    round_state["pending_kan"] = None
    round_state["last_discard"] = None
    round_state["turn_seat"] = seat
    round_state["phase"] = "DISCARD"
    round_state["current_draw"] = None
    round_state["kuikae_forbidden_types"][seat] = []
    round_state["reaction_passed"] = [False] * round_state["player_count"]
    round_state["kan_count"] += 1
    apply_kan_dora_timing(round_state, action_type)
    record_action(game, seat, "KAN", tile_id=tile_id, details=KAN_DETAIL_LABELS[action_type])
    draw_from_rinshan(game, seat, "岭上摸牌")
    if should_abort_for_four_kans(round_state):
        round_state["pending_abortive_draw"] = four_kan_abortive_draw_payload()
    return True

def resolve_pending_kita(game: dict[str, Any]) -> bool:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    pending_kita = round_state.get("pending_kita")
    if not isinstance(pending_kita, dict):
        return False

    seat = pending_kita["seat"]
    round_state["pending_kita"] = None
    round_state["last_discard"] = None
    round_state["turn_seat"] = seat
    round_state["phase"] = "DISCARD"
    round_state["current_draw"] = None
    round_state["reaction_passed"] = [False] * round_state["player_count"]
    round_state["pending_abortive_draw"] = None
    round_state["kuikae_forbidden_types"][seat] = []
    round_state["nuki_count"][seat] += 1
    clear_ippatsu(round_state)
    draw_from_rinshan(game, seat, "拔北后补牌")
    return True

def draw_from_live_wall(game: dict[str, Any], seat: int) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    if not round_state["live_wall"]:
        settle_exhaustive_draw(game)
        return
    tile_id = round_state["live_wall"].pop(0)
    round_state["hands"][seat].append(tile_id)
    round_state["hands"][seat] = sort_tiles(round_state["hands"][seat])
    round_state["current_draw"] = tile_id
    round_state["current_draw_source"] = "wall"
    round_state["last_draw_source"][seat] = "wall"
    round_state["kuikae_forbidden_types"][seat] = []
    round_state["kita_blocked"][seat] = False
    settle_pending_double_riichi(round_state, seat)
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = None
    round_state["pending_kita"] = None
    round_state["phase"] = "DISCARD"
    record_action(game, seat, "DRAW", tile_id=tile_id, details="从牌山摸牌")

def draw_from_rinshan(game: dict[str, Any], seat: int, details: str) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    tile_id = round_state["rinshan_tiles"].pop(0) if round_state["rinshan_tiles"] else round_state["live_wall"].pop(0)
    round_state["hands"][seat].append(tile_id)
    round_state["hands"][seat] = sort_tiles(round_state["hands"][seat])
    round_state["current_draw"] = tile_id
    round_state["current_draw_source"] = "rinshan"
    round_state["last_draw_source"][seat] = "rinshan"
    round_state["kuikae_forbidden_types"][seat] = []
    round_state["kita_blocked"][seat] = False
    settle_pending_double_riichi(round_state, seat)
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = None
    round_state["pending_kita"] = None
    round_state["phase"] = "DISCARD"
    record_action(game, seat, "DRAW", tile_id=tile_id, details=details)

def rotate_turn(game: dict[str, Any]) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    flush_pending_kan_dora(round_state)
    round_state["last_discard"] = None
    round_state["pending_abortive_draw"] = None
    round_state["reaction_passed"] = [False] * round_state["player_count"]
    round_state["turn_seat"] = next_seat(round_state["turn_seat"], round_state["player_count"])
    draw_from_live_wall(game, round_state["turn_seat"])

def apply_discard(game: dict[str, Any], seat: int, tile_id: int, *, declare_riichi: bool = False) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    declare_double_riichi = declare_riichi and can_double_riichi(round_state, seat)
    round_state["hands"][seat].remove(tile_id)
    round_state["hands"][seat] = sort_tiles(round_state["hands"][seat])
    round_state["kuikae_forbidden_types"][seat] = []
    round_state["kita_blocked"][seat] = False
    round_state["temporary_furiten"][seat] = False
    round_state["discards"][seat].append({"tile": tile_id, "riichi": declare_riichi, "called": False})
    round_state["last_discard"] = {"seat": seat, "tile": tile_id}
    round_state["current_draw"] = None
    round_state["phase"] = "REACTION"
    round_state["reaction_passed"] = [False] * round_state["player_count"]
    round_state["pending_kita"] = None
    if declare_riichi:
        game["players"][seat]["points"] -= 1000
        round_state["riichi_sticks"] += 1
        round_state["riichi"][seat] = True
        round_state["double_riichi"][seat] = declare_double_riichi
        round_state["double_riichi_pending"][seat] = declare_double_riichi
        round_state["ippatsu"][seat] = True
        record_action(game, seat, "RIICHI", tile_id=tile_id, details="宣告两立直" if declare_double_riichi else "宣告立直")
    record_action(game, seat, "DISCARD", tile_id=tile_id, details="打出手牌")
    pending_abortive_draw = round_state.get("pending_abortive_draw")
    if isinstance(pending_abortive_draw, dict) and pending_abortive_draw.get("kind") == "SUUKAIKAN":
        round_state["pending_abortive_draw"] = pending_abortive_draw
    else:
        round_state["pending_abortive_draw"] = evaluate_pending_abortive_draw_after_discard(game)

def perform_call(
    game: dict[str, Any],
    seat: int,
    action_type: str,
    discard_tile_id: int,
    consumed_ids: list[int],
    meld_index: int | None = None,
) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    flush_pending_kan_dora(round_state)
    if action_type in {"closed_kan", "added_kan"}:
        begin_kan_reaction(game, seat, action_type, discard_tile_id, consumed_ids, meld_index=meld_index)
        return
    discarder = round_state["last_discard"]["seat"] if round_state["last_discard"] is not None else seat
    if action_type in {"chi", "pon", "open_kan"}:
        round_state["discards"][discarder][-1]["called"] = True
    pop_specific_tiles(round_state["hands"][seat], consumed_ids)
    round_state["hands"][seat] = sort_tiles(round_state["hands"][seat])
    clear_ippatsu(round_state)
    invalidate_pending_double_riichi(round_state)
    if action_type == "chi":
        meld = {"type": "chi", "tiles": sort_tiles(consumed_ids + [discard_tile_id]), "opened": True, "called_tile": discard_tile_id, "from_seat": discarder}
    elif action_type == "pon":
        meld = {"type": "pon", "tiles": sort_tiles(consumed_ids + [discard_tile_id]), "opened": True, "called_tile": discard_tile_id, "from_seat": discarder}
    elif action_type == "open_kan":
        meld = {"type": "open_kan", "tiles": sort_tiles(consumed_ids + [discard_tile_id]), "opened": True, "called_tile": discard_tile_id, "from_seat": discarder}
    elif action_type == "closed_kan":
        meld = {"type": "closed_kan", "tiles": sort_tiles(consumed_ids), "opened": False, "called_tile": None, "from_seat": seat}
    elif action_type == "added_kan":
        meld = round_state["melds"][seat][meld_index]
        meld["type"] = "added_kan"
        meld["tiles"] = sort_tiles(meld["tiles"] + consumed_ids)
        meld["opened"] = True
        meld["called_tile"] = consumed_ids[0]
        meld["from_seat"] = seat
    else:
        raise ValueError(f"Unsupported call {action_type}")
    if action_type in {"chi", "pon", "open_kan", "closed_kan"}:
        round_state["melds"][seat].append(meld)
    register_liability_for_call(round_state, seat, action_type, discard_tile_id, discarder)
    round_state["last_discard"] = None
    round_state["turn_seat"] = seat
    round_state["phase"] = "DISCARD"
    round_state["current_draw"] = None
    round_state["kuikae_forbidden_types"][seat] = kuikae_forbidden_tile_types(action_type, discard_tile_id, consumed_ids)
    round_state["kita_blocked"][seat] = action_type == "pon"
    round_state["pending_abortive_draw"] = None
    round_state["pending_kita"] = None
    round_state["reaction_passed"] = [False] * round_state["player_count"]
    if action_type in {"open_kan", "closed_kan", "added_kan"}:
        round_state["kuikae_forbidden_types"][seat] = []
        round_state["kan_count"] += 1
        apply_kan_dora_timing(round_state, action_type)
        record_action(game, seat, "KAN", tile_id=discard_tile_id, details=KAN_DETAIL_LABELS[action_type])
        draw_from_rinshan(game, seat, "岭上摸牌")
        if should_abort_for_four_kans(round_state):
            round_state["pending_abortive_draw"] = four_kan_abortive_draw_payload()
    else:
        record_action(game, seat, action_type.upper(), tile_id=discard_tile_id, details={"chi": "吃牌", "pon": "碰牌"}[action_type])

def perform_kita(game: dict[str, Any], seat: int, tile_id: int) -> None:
    begin_kita_reaction(game, seat, tile_id)

__all__ = [
    "begin_kan_reaction",
    "begin_kita_reaction",
    "resolve_pending_kan",
    "resolve_pending_kita",
    "draw_from_live_wall",
    "draw_from_rinshan",
    "rotate_turn",
    "apply_discard",
    "perform_call",
    "perform_kita",
]
