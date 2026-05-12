"""公开状态序列化。

后端内部状态包含所有玩家手牌和完整牌山，不能直接暴露给前端。这个模块负责把内部
game 转换成前端可见的 public_state：人类玩家看自己的手牌，其他玩家只看手牌数量；
终局时再根据规则展示所有手牌和结算信息。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.config import settings
from app.engine_constants import KAN_DETAIL_LABELS
from app.engine_actions import legal_actions_for_human
from app.engine_ai import build_hint_block
from app.engine_rules import (
    aka_dora_count,
    copy_public_tiles,
    current_dora_indicators,
    ensure_game_defaults,
    ensure_round_state_defaults,
    minimum_han,
    round_label,
    rule_profile,
    sanma_scoring_mode,
    seat_wind_label,
)
from app.engine_tiles import tile_label

def build_player_summary(game: dict[str, Any], seat: int, reveal: bool) -> dict[str, Any]:
    round_state = game["round_state"]
    player = game["players"][seat]
    return {
        "seat": seat,
        "name": player["name"],
        "is_human": player["is_human"],
        "ai_level": player["ai_level"],
        "points": player["points"],
        "dealer": seat == round_state["dealer_seat"],
        "riichi": round_state["riichi"][seat],
        "seat_wind": seat_wind_label(round_state, seat),
        "hand_size": len(round_state["hands"][seat]),
        "hand": copy_public_tiles(game, round_state["hands"][seat], reveal),
        "melds": [
            {
                "type": meld["type"],
                "opened": meld["opened"],
                "tiles": [tile_label(tile, game) for tile in meld["tiles"]],
                "from_seat": meld.get("from_seat"),
            }
            for meld in round_state["melds"][seat]
        ],
        "discards": [
            {"tile": tile_label(item["tile"], game), "riichi": item.get("riichi", False), "called": item.get("called", False)}
            for item in round_state["discards"][seat]
        ],
        "nuki_count": round_state["nuki_count"][seat],
        "last_reason": player.get("last_reason", ""),
    }

def build_public_state(game: dict[str, Any], *, include_hint: bool = True) -> dict[str, Any]:
    ensure_game_defaults(game)
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    reveal_all = round_state["phase"] == "ROUND_END"
    players = [
        build_player_summary(game, seat, reveal_all or seat == game["human_seat"]) for seat in range(round_state["player_count"])
    ]
    prompt = ""
    if game["status"] == "FINISHED":
        prompt = "对局已结束。"
    elif round_state["phase"] == "ROUND_END":
        prompt = round_state["round_result"]["headline"]
    elif round_state["phase"] == "REACTION":
        discard = round_state["last_discard"]
        if discard is not None and discard.get("source") == "kan":
            prompt = f"请响应 {game['players'][discard['seat']]['name']} 的{KAN_DETAIL_LABELS.get(discard.get('kan_type', ''), '杠')}。"
        else:
            prompt = f"请响应 {game['players'][discard['seat']]['name']} 打出的 {tile_label(discard['tile'], game)}。"
    elif round_state["turn_seat"] == game["human_seat"]:
        prompt = "轮到你行动。"
    else:
        prompt = f"{game['players'][round_state['turn_seat']]['name']} 思考中。"
    return {
        "game_id": game["game_id"],
        "status": game["status"],
        "mode": game["mode"],
        "round_length": game["round_length"],
        "rule_profile": rule_profile(game),
        "koyaku_enabled": bool(game.get("koyaku_enabled", False)),
        "minimum_han": minimum_han(game),
        "aka_dora_count": aka_dora_count(game),
        "sanma_scoring_mode": sanma_scoring_mode(game),
        "round_label": round_label(round_state["prevalent_wind"], round_state["hand_number"], round_state["honba"]),
        "phase": round_state["phase"],
        "human_seat": game["human_seat"],
        "turn_seat": round_state["turn_seat"],
        "dealer_seat": round_state["dealer_seat"],
        "remaining_tiles": len(round_state["live_wall"]),
        "riichi_sticks": round_state["riichi_sticks"],
        "honba": round_state["honba"],
        "players": players,
        "human_hand": copy_public_tiles(game, round_state["hands"][game["human_seat"]], True),
        "dora_indicators": [tile_label(tile, game) for tile in current_dora_indicators(round_state)],
        "last_discard": None
        if round_state["last_discard"] is None
        else {"seat": round_state["last_discard"]["seat"], "tile": tile_label(round_state["last_discard"]["tile"], game)},
        "legal_actions": [action.to_dict() for action in legal_actions_for_human(game)],
        "prompt": prompt,
        "log_tail": game["action_log"][-settings.replay_tail_limit :],
        "replay_steps": len(game["snapshots"]),
        "round_result": deepcopy(round_state["round_result"]),
        "hint": build_hint_block(game, deep_search=False) if include_hint else None,
    }

def replay_snapshot_state(public_state: dict[str, Any]) -> dict[str, Any]:
    snapshot = deepcopy(public_state)
    # 回放只需要牌桌状态；AI 提示很重，放进每一帧会让 /replay 载荷暴涨。
    snapshot["hint"] = None
    return snapshot

__all__ = [
    "build_player_summary",
    "build_public_state",
    "replay_snapshot_state",
]
