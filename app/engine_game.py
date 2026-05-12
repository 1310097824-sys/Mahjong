"""新建对局和开局发牌。

这个模块负责创建完整 game 字典、初始化玩家、生成洗牌种子、开新局、分配座位、
发牌、设置宝牌和生成第一份公开状态。它不处理具体出牌策略，只保证初始状态合法。
"""

from __future__ import annotations

import random
import sys
import uuid
from typing import Any

from app.engine_common import now_iso, stable_seed
from app.engine_constants import MINIMUM_HAN_OPTIONS, MODE_POINTS, RULE_PROFILES, SANMA_SCORING_MODES, TARGET_POINTS
from app.engine_rules import ensure_game_defaults, max_round_count, player_count, round_label, round_target_count, state_hash
from app.engine_state import build_public_state, replay_snapshot_state
from app.engine_tiles import build_wall, default_aka_dora_count, sort_tiles, tile_label


def _public_engine_function(name: str, fallback: Any) -> Any:
    module = sys.modules.get("app.engine")
    candidate = getattr(module, name, None) if module is not None else None
    if callable(candidate) and candidate is not fallback:
        return candidate
    return fallback


def _missing_engine_hook(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("app.engine hook is not available yet")


def auto_advance(*args: Any, **kwargs: Any) -> None:
    return _public_engine_function("auto_advance", _missing_engine_hook)(*args, **kwargs)

def record_action(game: dict[str, Any], seat: int, action_type: str, *, tile_id: int | None = None, details: str = "") -> None:
    round_state = game["round_state"]
    entry = {
        "seq": len(game["action_log"]) + 1,
        "round": round_label(round_state["prevalent_wind"], round_state["hand_number"], round_state["honba"]),
        "seat": seat,
        "actor": "SYSTEM" if seat < 0 else game["players"][seat]["name"],
        "type": action_type,
        "tile": tile_label(tile_id, game) if tile_id is not None else "",
        "details": details,
        "timestamp": now_iso(),
        "state_hash": state_hash(round_state),
    }
    game["action_log"].append(entry)
    game["public_state"] = build_public_state(game, include_hint=False)
    game["snapshots"].append({"seq": entry["seq"], "type": action_type, "round": entry["round"], "state": replay_snapshot_state(game["public_state"])})

def build_round(game: dict[str, Any]) -> dict[str, Any]:
    ensure_game_defaults(game)
    count = player_count(game["mode"])
    round_cursor = game["round_cursor"]
    wind_order = ["E", "S", "W", "N"]
    prevalent = wind_order[min(round_cursor // count, len(wind_order) - 1)]
    hand_number = round_cursor % count + 1
    dealer = round_cursor % count
    seed = stable_seed(game["seed"], round_cursor, game["honba"], game["riichi_sticks"])
    rng = random.Random(seed)
    wall = build_wall(game["mode"], rng)
    dead_wall_size = 18 if game["mode"] == "3P" else 14
    dead_wall = wall[-dead_wall_size:]
    live_wall = wall[:-dead_wall_size]
    hands = [[] for _ in range(count)]
    for _ in range(13):
        for seat in range(count):
            hands[seat].append(live_wall.pop(0))
    current_draw = live_wall.pop(0)
    hands[dealer].append(current_draw)
    hands = [sort_tiles(hand) for hand in hands]
    indicator_pairs = []
    for index in range(0, 10, 2):
        indicator_pairs.append([dead_wall[index], dead_wall[index + 1]])
    rinshan_start = 10
    round_state = {
        "round_seed": seed,
        "player_count": count,
        "prevalent_wind": prevalent,
        "hand_number": hand_number,
        "dealer_seat": dealer,
        "turn_seat": dealer,
        "phase": "DISCARD",
        "honba": game["honba"],
        "riichi_sticks": game["riichi_sticks"],
        "hands": hands,
        "melds": [[] for _ in range(count)],
        "discards": [[] for _ in range(count)],
        "riichi": [False] * count,
        "double_riichi": [False] * count,
        "double_riichi_pending": [False] * count,
        "riichi_furiten": [False] * count,
        "ippatsu": [False] * count,
        "temporary_furiten": [False] * count,
        "reaction_passed": [False] * count,
        "kuikae_forbidden_types": [[] for _ in range(count)],
        "pending_abortive_draw": None,
        "pending_kan": None,
        "pending_kita": None,
        "pending_dora_reveals": 0,
        "liability_payments": [{} for _ in range(count)],
        "nuki_count": [0] * count,
        "kita_blocked": [False] * count,
        "kan_count": 0,
        "live_wall": live_wall,
        "rinshan_tiles": dead_wall[rinshan_start:],
        "indicator_pairs": indicator_pairs,
        "dora_revealed": 1,
        "current_draw": current_draw,
        "current_draw_source": "wall",
        "last_draw_source": [""] * count,
        "last_discard": None,
        "round_result": None,
        "wind_type_map": {"E": 27, "S": 28, "W": 29, "N": 30},
    }
    round_state["last_draw_source"][dealer] = "wall"
    return round_state

def new_game(
    player_name: str,
    mode: str,
    round_length: str,
    ai_levels: list[int],
    enable_koyaku: bool = False,
    sanma_scoring: str = "TSUMO_LOSS",
    rule_profile_name: str = "RANKED",
    minimum_han: int = 1,
    aka_dora_count: int | None = None,
) -> dict[str, Any]:
    count = player_count(mode)
    ai_levels = (ai_levels + [2] * count)[: count - 1]
    seed = stable_seed(player_name, mode, round_length, now_iso(), uuid.uuid4().hex)
    players = [
        {"seat": 0, "name": player_name or "访客", "is_human": True, "ai_level": 0, "points": MODE_POINTS[mode], "last_reason": ""}
    ]
    for seat in range(1, count):
        players.append(
            {
                "seat": seat,
                "name": f"电脑{seat}（L{ai_levels[seat - 1]}）",
                "is_human": False,
                "ai_level": ai_levels[seat - 1],
                "points": MODE_POINTS[mode],
                "last_reason": "",
            }
        )
    game = {
        "game_id": str(uuid.uuid4()),
        "player_name": player_name or "访客",
        "mode": mode,
        "round_length": round_length,
        "rule_profile": rule_profile_name if rule_profile_name in RULE_PROFILES else "RANKED",
        "koyaku_enabled": bool(enable_koyaku),
        "minimum_han": minimum_han if minimum_han in MINIMUM_HAN_OPTIONS else 1,
        "aka_dora_count": default_aka_dora_count(mode) if aka_dora_count is None else aka_dora_count,
        "sanma_scoring_mode": sanma_scoring if mode == "3P" and sanma_scoring in SANMA_SCORING_MODES else "TSUMO_LOSS",
        "seed": seed,
        "status": "RUNNING",
        "human_seat": 0,
        "round_cursor": 0,
        "base_rounds": round_target_count(mode, round_length),
        "max_rounds": max_round_count(mode, round_length),
        "target_score": TARGET_POINTS.get(mode, 30000),
        "honba": 0,
        "riichi_sticks": 0,
        "players": players,
        "round_state": {},
        "action_log": [],
        "snapshots": [],
        "result_summary": None,
        "public_state": {},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    ensure_game_defaults(game)
    game["round_state"] = build_round(game)
    game["public_state"] = build_public_state(game)
    record_action(game, -1, "ROUND_START", details=game["public_state"]["round_label"])
    auto_advance(game)
    return game

def start_next_round(game: dict[str, Any]) -> None:
    ensure_game_defaults(game)
    if game["status"] == "FINISHED":
        return
    game["round_state"] = build_round(game)
    game["round_state"]["honba"] = game["honba"]
    game["round_state"]["riichi_sticks"] = game["riichi_sticks"]
    game["public_state"] = build_public_state(game)
    record_action(game, -1, "ROUND_START", details=game["public_state"]["round_label"])
    auto_advance(game)

__all__ = [
    "record_action",
    "build_round",
    "new_game",
    "start_next_round",
]
