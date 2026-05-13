"""对局规则配置与状态默认值。

本模块负责把游戏模式、规则档位和 round_state 的缺省字段整理成一致结构。
例如三麻/四麻人数、东风/半庄局数、古役开关、赤宝牌数量、宝牌指示牌、座风等
都在这里统一处理，避免动作执行和计分模块重复兜底。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules

from app import rust_core
from app.engine_constants import (
    DEFAULT_AKA_DORA_COUNTS,
    MINIMUM_HAN_OPTIONS,
    OPEN_MELD_TYPES,
    RULE_PROFILES,
    SANMA_SCORING_MODES,
    TARGET_POINTS,
)
from app.engine_tiles import default_aka_dora_count, is_red, normalize_aka_dora_count, sort_tiles, tile_label, tile_type

def player_count(mode: str) -> int:
    rust_value = rust_core.player_count(mode)
    if rust_value is not None:
        return rust_value
    return 4 if mode == "4P" else 3

def next_seat(seat: int, count: int) -> int:
    rust_value = rust_core.next_seat(seat, count)
    if rust_value is not None:
        return rust_value
    return (seat + 1) % count

def seat_distance(origin: int, target: int, count: int) -> int:
    rust_value = rust_core.seat_distance(origin, target, count)
    if rust_value is not None:
        return rust_value
    return (target - origin) % count

def round_target_count(mode: str, round_length: str) -> int:
    rust_value = rust_core.round_target_count(mode, round_length)
    if rust_value is not None:
        return rust_value
    base = player_count(mode)
    return base if round_length == "EAST" else base * 2

def max_round_count(mode: str, round_length: str) -> int:
    rust_value = rust_core.max_round_count(mode, round_length)
    if rust_value is not None:
        return rust_value
    return round_target_count(mode, round_length) + player_count(mode)

def ensure_game_defaults(game: dict[str, Any]) -> None:
    mode = game["mode"]
    round_length = game["round_length"]

    base_rounds = game.get("base_rounds")
    if not isinstance(base_rounds, int) or base_rounds <= 0:
        game["base_rounds"] = round_target_count(mode, round_length)

    max_rounds = game.get("max_rounds")
    if not isinstance(max_rounds, int) or max_rounds < game["base_rounds"]:
        game["max_rounds"] = max_round_count(mode, round_length)

    target_score = game.get("target_score")
    if not isinstance(target_score, int) or target_score <= 0:
        game["target_score"] = TARGET_POINTS.get(mode, 30000)

    rule_profile = game.get("rule_profile")
    if rule_profile not in RULE_PROFILES:
        game["rule_profile"] = "KOYAKU" if bool(game.get("koyaku_enabled", False)) else "RANKED"

    koyaku_enabled = game.get("koyaku_enabled")
    if not isinstance(koyaku_enabled, bool):
        game["koyaku_enabled"] = False
    if game["rule_profile"] == "RANKED":
        game["koyaku_enabled"] = False
    elif game["rule_profile"] == "KOYAKU":
        game["koyaku_enabled"] = True

    minimum_han = game.get("minimum_han")
    try:
        minimum_han = int(minimum_han)
    except (TypeError, ValueError):
        minimum_han = 1
    if game["rule_profile"] == "RANKED":
        game["minimum_han"] = 1
    else:
        game["minimum_han"] = minimum_han if minimum_han in MINIMUM_HAN_OPTIONS else 1

    game["aka_dora_count"] = normalize_aka_dora_count(mode, game["rule_profile"], game.get("aka_dora_count"))

    sanma_scoring_mode = game.get("sanma_scoring_mode")
    if game["mode"] == "3P":
        if game["rule_profile"] == "RANKED":
            game["sanma_scoring_mode"] = "TSUMO_LOSS"
        elif sanma_scoring_mode not in SANMA_SCORING_MODES:
            game["sanma_scoring_mode"] = "TSUMO_LOSS"
    else:
        game["sanma_scoring_mode"] = "TSUMO_LOSS"

def rule_profile(game: dict[str, Any]) -> str:
    ensure_game_defaults(game)
    return str(game.get("rule_profile", "RANKED"))

def sanma_scoring_mode(game: dict[str, Any]) -> str:
    ensure_game_defaults(game)
    return str(game.get("sanma_scoring_mode", "TSUMO_LOSS"))

def minimum_han(game: dict[str, Any]) -> int:
    ensure_game_defaults(game)
    return int(game.get("minimum_han", 1))

def aka_dora_count(game: dict[str, Any]) -> int:
    ensure_game_defaults(game)
    return int(game.get("aka_dora_count", default_aka_dora_count(game.get("mode", "4P"))))

def build_rule_options(game: dict[str, Any]) -> OptionalRules:
    enable_koyaku = bool(game.get("koyaku_enabled", False))
    return OptionalRules(
        has_open_tanyao=True,
        has_aka_dora=False,
        has_double_yakuman=True,
        kazoe_limit=HandConfig.KAZOE_LIMITED,
        kiriage=False,
        fu_for_open_pinfu=True,
        fu_for_pinfu_tsumo=False,
        renhou_as_yakuman=enable_koyaku,
        has_daisharin_other_suits=enable_koyaku,
        has_daichisei=enable_koyaku,
    )

def round_label(prevalent_wind: str, hand_number: int, honba: int) -> str:
    wind_text = {"E": "东", "S": "南", "W": "西", "N": "北"}[prevalent_wind]
    return f"{wind_text}{hand_number}局 {honba}本场"

def seat_wind_label(round_state: dict[str, Any], seat: int) -> str:
    count = round_state["player_count"]
    dealer = round_state["dealer_seat"]
    rust_code = rust_core.seat_wind_code(count, dealer, seat)
    if rust_code is not None:
        # Rust 只判断座位距离是否合法并返回风位编码；这里保留字符串映射，
        # 因为 public_state、日志和 mahjong 库配置都已经以 E/S/W/N 作为稳定接口。
        return ["E", "S", "W", "N"][rust_code]
    if count == 4:
        order = ["E", "S", "W", "N"]
    else:
        order = ["E", "S", "W"]
    return order[(seat - dealer) % count]

def is_closed_hand(round_state: dict[str, Any], seat: int) -> bool:
    for meld in round_state["melds"][seat]:
        if meld["type"] in OPEN_MELD_TYPES:
            return False
    return True

def current_dora_indicators(round_state: dict[str, Any]) -> list[int]:
    return [pair[0] for pair in round_state["indicator_pairs"][: round_state["dora_revealed"]]]

def current_ura_indicators(round_state: dict[str, Any]) -> list[int]:
    return [pair[1] for pair in round_state["indicator_pairs"][: round_state["dora_revealed"]]]

def reveal_next_dora_indicator(round_state: dict[str, Any]) -> bool:
    if round_state["dora_revealed"] >= len(round_state["indicator_pairs"]):
        return False
    round_state["dora_revealed"] += 1
    return True

def flush_pending_kan_dora(round_state: dict[str, Any]) -> int:
    ensure_round_state_defaults(round_state)
    pending = round_state.get("pending_dora_reveals", 0)
    if not isinstance(pending, int) or pending <= 0:
        round_state["pending_dora_reveals"] = 0
        return 0

    revealed = 0
    while pending > 0 and reveal_next_dora_indicator(round_state):
        pending -= 1
        revealed += 1
    round_state["pending_dora_reveals"] = max(0, pending)
    return revealed

def apply_kan_dora_timing(round_state: dict[str, Any], action_type: str) -> None:
    ensure_round_state_defaults(round_state)
    if action_type == "closed_kan":
        reveal_next_dora_indicator(round_state)
        return
    if action_type in {"open_kan", "added_kan"}:
        round_state["pending_dora_reveals"] += 1

def state_hash(round_state: dict[str, Any]) -> str:
    payload = json.dumps(round_state, ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def round_up_to_100(value: float) -> int:
    rust_value = rust_core.round_up_to_100(value)
    if rust_value is not None:
        return rust_value
    return int(((int(value) + (0 if float(value).is_integer() else 1)) + 99) // 100 * 100)

def copy_public_tiles(game: dict[str, Any], tiles: list[int], reveal: bool) -> list[dict[str, Any]]:
    if not reveal:
        return [{"label": "##"} for _ in tiles]
    return [{"id": tile, "label": tile_label(tile, game), "red": is_red(tile, game)} for tile in sort_tiles(tiles, game)]

def clear_ippatsu(round_state: dict[str, Any]) -> None:
    round_state["ippatsu"] = [False] * round_state["player_count"]

def invalidate_pending_double_riichi(round_state: dict[str, Any]) -> None:
    pending = round_state.get("double_riichi_pending")
    if not isinstance(pending, list) or len(pending) != round_state["player_count"]:
        round_state["double_riichi_pending"] = [False] * round_state["player_count"]
        return
    for seat, active in enumerate(pending):
        if active:
            pending[seat] = False

def settle_pending_double_riichi(round_state: dict[str, Any], seat: int) -> None:
    pending = round_state.get("double_riichi_pending")
    if not isinstance(pending, list) or len(pending) != round_state["player_count"]:
        round_state["double_riichi_pending"] = [False] * round_state["player_count"]
        return
    pending[seat] = False

def is_furiten(round_state: dict[str, Any], seat: int, win_tile_type: int) -> bool:
    own_discard_types = [tile_type(item["tile"]) for item in round_state["discards"][seat]]
    # 振听比较的是牌种而不是实体牌 ID，所以这里先把弃牌河转换成 0-33 的 tile type。
    # temporary_furiten / riichi_furiten 是状态位，和弃牌振听一起交给 Rust 纯函数判断。
    rust_value = rust_core.is_furiten(
        win_tile_type,
        own_discard_types,
        round_state["temporary_furiten"][seat],
        round_state["riichi_furiten"][seat],
    )
    if rust_value is not None:
        return rust_value
    own_discards = set(own_discard_types)
    return (
        win_tile_type in own_discards
        or round_state["temporary_furiten"][seat]
        or round_state["riichi_furiten"][seat]
    )

def ensure_round_state_defaults(round_state: dict[str, Any]) -> None:
    count = round_state["player_count"]
    double_riichi = round_state.get("double_riichi")
    if not isinstance(double_riichi, list) or len(double_riichi) != count:
        round_state["double_riichi"] = [False] * count
    double_riichi_pending = round_state.get("double_riichi_pending")
    if not isinstance(double_riichi_pending, list) or len(double_riichi_pending) != count:
        round_state["double_riichi_pending"] = [False] * count
    else:
        round_state["double_riichi_pending"] = [bool(item) for item in double_riichi_pending]
    riichi_furiten = round_state.get("riichi_furiten")
    if not isinstance(riichi_furiten, list) or len(riichi_furiten) != count:
        round_state["riichi_furiten"] = [False] * count
    pending_dora_reveals = round_state.get("pending_dora_reveals")
    if not isinstance(pending_dora_reveals, int) or pending_dora_reveals < 0:
        round_state["pending_dora_reveals"] = 0
    kuikae = round_state.get("kuikae_forbidden_types")
    if not isinstance(kuikae, list) or len(kuikae) != count:
        round_state["kuikae_forbidden_types"] = [[] for _ in range(count)]
    pending_abortive_draw = round_state.get("pending_abortive_draw")
    if pending_abortive_draw is not None and not isinstance(pending_abortive_draw, dict):
        round_state["pending_abortive_draw"] = None
    elif "pending_abortive_draw" not in round_state:
        round_state["pending_abortive_draw"] = None
    pending_kan = round_state.get("pending_kan")
    if pending_kan is not None and not isinstance(pending_kan, dict):
        round_state["pending_kan"] = None
    elif "pending_kan" not in round_state:
        round_state["pending_kan"] = None
    pending_kita = round_state.get("pending_kita")
    if pending_kita is not None and not isinstance(pending_kita, dict):
        round_state["pending_kita"] = None
    elif "pending_kita" not in round_state:
        round_state["pending_kita"] = None
    liability = round_state.get("liability_payments")
    if not isinstance(liability, list) or len(liability) != count:
        round_state["liability_payments"] = [{} for _ in range(count)]
    else:
        round_state["liability_payments"] = [item if isinstance(item, dict) else {} for item in liability]
    kita_blocked = round_state.get("kita_blocked")
    if not isinstance(kita_blocked, list) or len(kita_blocked) != count:
        round_state["kita_blocked"] = [False] * count
    else:
        round_state["kita_blocked"] = [bool(item) for item in kita_blocked]

__all__ = [
    "player_count",
    "next_seat",
    "seat_distance",
    "round_target_count",
    "max_round_count",
    "ensure_game_defaults",
    "ensure_round_state_defaults",
    "rule_profile",
    "sanma_scoring_mode",
    "minimum_han",
    "aka_dora_count",
    "build_rule_options",
    "round_label",
    "seat_wind_label",
    "is_closed_hand",
    "current_dora_indicators",
    "current_ura_indicators",
    "reveal_next_dora_indicator",
    "flush_pending_kan_dora",
    "apply_kan_dora_timing",
    "state_hash",
    "round_up_to_100",
    "copy_public_tiles",
    "clear_ippatsu",
    "invalidate_pending_double_riichi",
    "settle_pending_double_riichi",
    "is_furiten",
]
