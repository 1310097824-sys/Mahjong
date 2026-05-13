"""Rust 计算核心的 Python 桥接层。

规则主流程仍在 Python 中保持可读和可调试，性能敏感的纯计算函数逐步迁移到
 `rust_core` 动态库。这个模块负责加载 DLL、声明 ctypes 函数签名、把 Python
数据转换为 C ABI 数组，并在 Rust 不可用时返回 `None` 让 Python 兜底逻辑继续
工作。所有上层代码都应通过本模块调用 Rust，而不要直接操作 ctypes。
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
CRATE_DIR = ROOT_DIR / "rust_core"


def _library_names() -> list[str]:
    if sys.platform.startswith("win"):
        return ["mahjong_core.dll"]
    if sys.platform == "darwin":
        return ["libmahjong_core.dylib"]
    return ["libmahjong_core.so"]


def _candidate_paths() -> list[Path]:
    candidates: list[Path] = []
    for profile in ("release", "debug"):
        for name in _library_names():
            candidates.append(CRATE_DIR / "target" / profile / name)
    env_path = os.environ.get("MAHJONG_RUST_CORE_DLL")
    if env_path:
        candidates.insert(0, Path(env_path))
    return candidates


def _load_library() -> ctypes.CDLL | None:
    for path in _candidate_paths():
        if path.exists():
            try:
                return ctypes.CDLL(str(path))
            except OSError:
                continue
    return None


_LIB = _load_library()
_HAS_TILE_TYPE = False
_HAS_TILE_HELPERS = False
_HAS_LEGAL_TILE_TYPE = False
_HAS_DORA_FROM_INDICATOR = False
_HAS_SCORING_INDICATOR_TILE_ID = False
_HAS_RULE_SEAT_MATH = False
_HAS_ROUND_END_RULES = False
_HAS_RANKED_SETTLEMENT = False
_HAS_ACTION_RULES = False
_HAS_ROUND_STATE_RULES = False
_HAS_TERMINAL_HONOR_TYPES = False
_HAS_SCORING_PAYMENTS = False
_HAS_SCORING_LIABILITY = False
_HAS_LOCAL_YAKU = False
_HAS_VISIBLE_COUNTS = False
_HAS_TILE_VALUE_BONUS = False
_HAS_COMPLETE_HAND_SHAPE = False
_HAS_TENPAI_WAITS = False
_HAS_EFFECTIVE_FROM_COUNTS = False
_HAS_DRAW_FROM_COUNTS = False
_HAS_HAND_ROUTE_PROFILE = False
_HAS_DISCARD_METRICS = False
_HAS_TILE_DANGER = False
_HAS_AGGREGATE_SAFETY = False
_HAS_SAFE_RESERVE = False
_HAS_SAFE_RESERVE_BATCH = False
_HAS_ROUTE_PROFILES_AFTER_DISCARDS = False
_HAS_STRUCTURED_DISCARD_EV = False
_HAS_PUSH_FOLD_PROFILE = False
_HAS_DEFENSE_OVERRIDE_PROFILE = False
_HAS_DEAL_IN_LOSS_PROFILE = False
_HAS_DEFENSIVE_DISCARD_PROFILE = False
_HAS_GLOBAL_REWARD_PROFILE = False
_HAS_ALPHA_TERMINAL_EV = False


def _configure_library() -> None:
    global _HAS_TILE_TYPE, _HAS_TILE_HELPERS, _HAS_LEGAL_TILE_TYPE, _HAS_DORA_FROM_INDICATOR, _HAS_SCORING_INDICATOR_TILE_ID, _HAS_RULE_SEAT_MATH, _HAS_ROUND_END_RULES, _HAS_RANKED_SETTLEMENT, _HAS_ACTION_RULES, _HAS_ROUND_STATE_RULES, _HAS_TERMINAL_HONOR_TYPES, _HAS_SCORING_PAYMENTS, _HAS_SCORING_LIABILITY, _HAS_LOCAL_YAKU, _HAS_VISIBLE_COUNTS, _HAS_TILE_VALUE_BONUS, _HAS_COMPLETE_HAND_SHAPE, _HAS_TENPAI_WAITS, _HAS_EFFECTIVE_FROM_COUNTS, _HAS_DRAW_FROM_COUNTS, _HAS_HAND_ROUTE_PROFILE, _HAS_DISCARD_METRICS, _HAS_TILE_DANGER, _HAS_AGGREGATE_SAFETY, _HAS_SAFE_RESERVE, _HAS_SAFE_RESERVE_BATCH, _HAS_ROUTE_PROFILES_AFTER_DISCARDS, _HAS_STRUCTURED_DISCARD_EV, _HAS_PUSH_FOLD_PROFILE, _HAS_DEFENSE_OVERRIDE_PROFILE, _HAS_DEAL_IN_LOSS_PROFILE, _HAS_DEFENSIVE_DISCARD_PROFILE, _HAS_GLOBAL_REWARD_PROFILE, _HAS_ALPHA_TERMINAL_EV
    if _LIB is None:
        return
    _LIB.mahjong_core_version.argtypes = []
    _LIB.mahjong_core_version.restype = ctypes.c_uint32

    try:
        _LIB.mahjong_core_tile_type.argtypes = [ctypes.c_int32]
        _LIB.mahjong_core_tile_type.restype = ctypes.c_int32
        _HAS_TILE_TYPE = True
    except AttributeError:
        _HAS_TILE_TYPE = False

    try:
        _LIB.mahjong_core_default_aka_dora_count.argtypes = [ctypes.c_uint8]
        _LIB.mahjong_core_default_aka_dora_count.restype = ctypes.c_int32
        _LIB.mahjong_core_normalize_aka_dora_count.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_int32,
        ]
        _LIB.mahjong_core_normalize_aka_dora_count.restype = ctypes.c_int32
        _LIB.mahjong_core_active_aka_dora_ids.argtypes = [
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_active_aka_dora_ids.restype = ctypes.c_int32
        _LIB.mahjong_core_is_red_tile.argtypes = [ctypes.c_uint8, ctypes.c_int32, ctypes.c_int32]
        _LIB.mahjong_core_is_red_tile.restype = ctypes.c_int32
        _LIB.mahjong_core_tile_flags.argtypes = [ctypes.c_int32]
        _LIB.mahjong_core_tile_flags.restype = ctypes.c_int32
        _LIB.mahjong_core_legal_tile_types.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_legal_tile_types.restype = ctypes.c_int32
        _LIB.mahjong_core_representative_tile_id.argtypes = [
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_representative_tile_id.restype = ctypes.c_int32
        _HAS_TILE_HELPERS = True
    except AttributeError:
        _HAS_TILE_HELPERS = False

    try:
        _LIB.mahjong_core_is_legal_tile_type.argtypes = [ctypes.c_uint8, ctypes.c_int32]
        _LIB.mahjong_core_is_legal_tile_type.restype = ctypes.c_int32
        _HAS_LEGAL_TILE_TYPE = True
    except AttributeError:
        _HAS_LEGAL_TILE_TYPE = False

    try:
        _LIB.mahjong_core_dora_from_indicator.argtypes = [ctypes.c_uint8, ctypes.c_int32]
        _LIB.mahjong_core_dora_from_indicator.restype = ctypes.c_int32
        _HAS_DORA_FROM_INDICATOR = True
    except AttributeError:
        _HAS_DORA_FROM_INDICATOR = False

    try:
        _LIB.mahjong_core_scoring_indicator_tile_id.argtypes = [ctypes.c_uint8, ctypes.c_int32]
        _LIB.mahjong_core_scoring_indicator_tile_id.restype = ctypes.c_int32
        _HAS_SCORING_INDICATOR_TILE_ID = True
    except AttributeError:
        _HAS_SCORING_INDICATOR_TILE_ID = False

    try:
        _LIB.mahjong_core_player_count.argtypes = [ctypes.c_uint8]
        _LIB.mahjong_core_player_count.restype = ctypes.c_int32
        _LIB.mahjong_core_next_seat.argtypes = [ctypes.c_int32, ctypes.c_int32]
        _LIB.mahjong_core_next_seat.restype = ctypes.c_int32
        _LIB.mahjong_core_seat_distance.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
        _LIB.mahjong_core_seat_distance.restype = ctypes.c_int32
        _LIB.mahjong_core_seat_wind_code.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
        _LIB.mahjong_core_seat_wind_code.restype = ctypes.c_int32
        _LIB.mahjong_core_round_target_count.argtypes = [ctypes.c_uint8, ctypes.c_uint8]
        _LIB.mahjong_core_round_target_count.restype = ctypes.c_int32
        _LIB.mahjong_core_max_round_count.argtypes = [ctypes.c_uint8, ctypes.c_uint8]
        _LIB.mahjong_core_max_round_count.restype = ctypes.c_int32
        _HAS_RULE_SEAT_MATH = True
    except AttributeError:
        _HAS_RULE_SEAT_MATH = False

    try:
        _LIB.mahjong_core_is_win_like_round_result.argtypes = [ctypes.c_uint8, ctypes.c_uint8]
        _LIB.mahjong_core_is_win_like_round_result.restype = ctypes.c_int32
        _LIB.mahjong_core_goal_score_reached.argtypes = [
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_int32,
        ]
        _LIB.mahjong_core_goal_score_reached.restype = ctypes.c_int32
        _LIB.mahjong_core_should_auto_stop_all_last_dealer.argtypes = [
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_int32,
        ]
        _LIB.mahjong_core_should_auto_stop_all_last_dealer.restype = ctypes.c_int32
        _HAS_ROUND_END_RULES = True
    except AttributeError:
        _HAS_ROUND_END_RULES = False

    try:
        _LIB.mahjong_core_ranked_settlement_scores.argtypes = [
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_ranked_settlement_scores.restype = ctypes.c_int32
        _HAS_RANKED_SETTLEMENT = True
    except AttributeError:
        _HAS_RANKED_SETTLEMENT = False

    try:
        _LIB.mahjong_core_kuikae_forbidden_tile_types.argtypes = [
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_kuikae_forbidden_tile_types.restype = ctypes.c_int32
        _LIB.mahjong_core_chi_candidate_pairs.argtypes = [
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_chi_candidate_pairs.restype = ctypes.c_int32
        _HAS_ACTION_RULES = True
    except AttributeError:
        _HAS_ACTION_RULES = False

    try:
        # 这一组函数开始迁移“局内状态规则”：它们还不接收完整 round_state，
        # 而是由 Python 先把字典结构压平成 tile type、计数和布尔数组。这样 Rust
        # 侧可以保持纯函数，Python 侧也保留现有状态结构和兜底实现。
        _LIB.mahjong_core_is_furiten.argtypes = [
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_uint8,
            ctypes.c_uint8,
        ]
        _LIB.mahjong_core_is_furiten.restype = ctypes.c_int32
        _LIB.mahjong_core_can_double_riichi.argtypes = [ctypes.c_uint8, ctypes.c_uint8]
        _LIB.mahjong_core_can_double_riichi.restype = ctypes.c_int32
        _LIB.mahjong_core_pending_abortive_draw_kind.argtypes = [
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_uint8,
        ]
        _LIB.mahjong_core_pending_abortive_draw_kind.restype = ctypes.c_int32
        _LIB.mahjong_core_should_abort_for_four_kans.argtypes = [
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_should_abort_for_four_kans.restype = ctypes.c_int32
        _LIB.mahjong_core_is_tenhou_state.argtypes = [
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_is_tenhou_state.restype = ctypes.c_int32
        _LIB.mahjong_core_is_chiihou_state.argtypes = [
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_int32,
        ]
        _LIB.mahjong_core_is_chiihou_state.restype = ctypes.c_int32
        _LIB.mahjong_core_is_haitei_state.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
        ]
        _LIB.mahjong_core_is_haitei_state.restype = ctypes.c_int32
        _LIB.mahjong_core_is_houtei_state.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
        ]
        _LIB.mahjong_core_is_houtei_state.restype = ctypes.c_int32
        _LIB.mahjong_core_is_chankan_state.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
        ]
        _LIB.mahjong_core_is_chankan_state.restype = ctypes.c_int32
        _LIB.mahjong_core_is_renhou_state.argtypes = [
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_size_t,
            ctypes.c_uint8,
            ctypes.c_int32,
        ]
        _LIB.mahjong_core_is_renhou_state.restype = ctypes.c_int32
        _LIB.mahjong_core_can_abortive_draw_nine_terminals.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_can_abortive_draw_nine_terminals.restype = ctypes.c_int32
        _HAS_ROUND_STATE_RULES = True
    except AttributeError:
        _HAS_ROUND_STATE_RULES = False

    try:
        _LIB.mahjong_core_unique_terminal_honor_types.argtypes = [
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_unique_terminal_honor_types.restype = ctypes.c_int32
        _HAS_TERMINAL_HONOR_TYPES = True
    except AttributeError:
        _HAS_TERMINAL_HONOR_TYPES = False

    try:
        _LIB.mahjong_core_round_up_to_100.argtypes = [ctypes.c_double]
        _LIB.mahjong_core_round_up_to_100.restype = ctypes.c_int32
        _LIB.mahjong_core_score_result_total.argtypes = [
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
        ]
        _LIB.mahjong_core_score_result_total.restype = ctypes.c_int32
        _LIB.mahjong_core_full_honba_value.argtypes = [ctypes.c_uint8, ctypes.c_int32]
        _LIB.mahjong_core_full_honba_value.restype = ctypes.c_int32
        _LIB.mahjong_core_minimum_han_satisfied.argtypes = [
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.c_int32,
        ]
        _LIB.mahjong_core_minimum_han_satisfied.restype = ctypes.c_int32
        _LIB.mahjong_core_tsumo_payment_map.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_tsumo_payment_map.restype = ctypes.c_int32
        _LIB.mahjong_core_is_nagashi_mangan_candidate.argtypes = [
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_is_nagashi_mangan_candidate.restype = ctypes.c_int32
        _HAS_SCORING_PAYMENTS = True
    except AttributeError:
        _HAS_SCORING_PAYMENTS = False

    try:
        _LIB.mahjong_core_liability_key_for_call.argtypes = [
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_liability_key_for_call.restype = ctypes.c_int32
        _LIB.mahjong_core_liability_context_profile.argtypes = [
            ctypes.c_size_t,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_liability_context_profile.restype = ctypes.c_int32
        _HAS_SCORING_LIABILITY = True
    except AttributeError:
        _HAS_SCORING_LIABILITY = False

    try:
        _LIB.mahjong_core_local_mangan_yaku_code.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_int32,
        ]
        _LIB.mahjong_core_local_mangan_yaku_code.restype = ctypes.c_int32
        _LIB.mahjong_core_local_yakuman_yaku_code.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
        ]
        _LIB.mahjong_core_local_yakuman_yaku_code.restype = ctypes.c_int32
        _LIB.mahjong_core_local_han_yaku_mask.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
        ]
        _LIB.mahjong_core_local_han_yaku_mask.restype = ctypes.c_int32
        _LIB.mahjong_core_local_pattern_yaku_mask.argtypes = [
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_local_pattern_yaku_mask.restype = ctypes.c_int32
        _HAS_LOCAL_YAKU = True
    except AttributeError:
        _HAS_LOCAL_YAKU = False

    try:
        _LIB.mahjong_core_is_complete_hand_shape.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_int32,
        ]
        _LIB.mahjong_core_is_complete_hand_shape.restype = ctypes.c_int32
        _HAS_COMPLETE_HAND_SHAPE = True
    except AttributeError:
        _HAS_COMPLETE_HAND_SHAPE = False

    try:
        _LIB.mahjong_core_tenpai_waits_from_counts.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_tenpai_waits_from_counts.restype = ctypes.c_int32
        _HAS_TENPAI_WAITS = True
    except AttributeError:
        _HAS_TENPAI_WAITS = False

    _LIB.mahjong_core_counts_from_tiles.argtypes = [
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
    ]
    _LIB.mahjong_core_counts_from_tiles.restype = ctypes.c_int32

    try:
        _LIB.mahjong_core_visible_counts_from_tiles.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_visible_counts_from_tiles.restype = ctypes.c_int32
        _HAS_VISIBLE_COUNTS = True
    except AttributeError:
        _HAS_VISIBLE_COUNTS = False

    try:
        _LIB.mahjong_core_tile_value_bonus.argtypes = [
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_tile_value_bonus.restype = ctypes.c_double
        _HAS_TILE_VALUE_BONUS = True
    except AttributeError:
        _HAS_TILE_VALUE_BONUS = False

    _LIB.mahjong_core_shanten_34.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
    _LIB.mahjong_core_shanten_34.restype = ctypes.c_int32

    _LIB.mahjong_core_effective_tiles_after_discard.argtypes = [
        ctypes.c_uint8,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_size_t,
    ]
    _LIB.mahjong_core_effective_tiles_after_discard.restype = ctypes.c_int32

    try:
        _LIB.mahjong_core_effective_tiles_from_counts.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_effective_tiles_from_counts.restype = ctypes.c_int32
        _HAS_EFFECTIVE_FROM_COUNTS = True
    except AttributeError:
        _HAS_EFFECTIVE_FROM_COUNTS = False

    try:
        _LIB.mahjong_core_draw_tiles_from_counts.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_draw_tiles_from_counts.restype = ctypes.c_int32
        _HAS_DRAW_FROM_COUNTS = True
    except AttributeError:
        _HAS_DRAW_FROM_COUNTS = False

    try:
        _LIB.mahjong_core_hand_route_profile.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        _LIB.mahjong_core_hand_route_profile.restype = ctypes.c_int32
        _HAS_HAND_ROUTE_PROFILE = True
    except AttributeError:
        _HAS_HAND_ROUTE_PROFILE = False

    try:
        _LIB.mahjong_core_hand_route_profiles_after_discards.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_hand_route_profiles_after_discards.restype = ctypes.c_int32
        _HAS_ROUTE_PROFILES_AFTER_DISCARDS = True
    except AttributeError:
        _HAS_ROUTE_PROFILES_AFTER_DISCARDS = False

    try:
        _LIB.mahjong_core_discard_metrics_from_counts.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_discard_metrics_from_counts.restype = ctypes.c_int32
        _HAS_DISCARD_METRICS = True
    except AttributeError:
        _HAS_DISCARD_METRICS = False

    try:
        _LIB.mahjong_core_structured_discard_ev.argtypes = [
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_structured_discard_ev.restype = ctypes.c_int32
        _HAS_STRUCTURED_DISCARD_EV = True
    except AttributeError:
        _HAS_STRUCTURED_DISCARD_EV = False

    try:
        _LIB.mahjong_core_push_fold_profile.argtypes = [
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_push_fold_profile.restype = ctypes.c_int32
        _HAS_PUSH_FOLD_PROFILE = True
    except AttributeError:
        _HAS_PUSH_FOLD_PROFILE = False

    try:
        _LIB.mahjong_core_defense_override_profile.argtypes = [
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_defense_override_profile.restype = ctypes.c_int32
        _HAS_DEFENSE_OVERRIDE_PROFILE = True
    except AttributeError:
        _HAS_DEFENSE_OVERRIDE_PROFILE = False

    try:
        _LIB.mahjong_core_deal_in_loss_profile.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_deal_in_loss_profile.restype = ctypes.c_int32
        _HAS_DEAL_IN_LOSS_PROFILE = True
    except AttributeError:
        _HAS_DEAL_IN_LOSS_PROFILE = False

    try:
        _LIB.mahjong_core_defensive_discard_profile.argtypes = [
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_defensive_discard_profile.restype = ctypes.c_int32
        _HAS_DEFENSIVE_DISCARD_PROFILE = True
    except AttributeError:
        _HAS_DEFENSIVE_DISCARD_PROFILE = False

    try:
        _LIB.mahjong_core_global_reward_delta_profile.argtypes = [
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_global_reward_delta_profile.restype = ctypes.c_int32
        _HAS_GLOBAL_REWARD_PROFILE = True
    except AttributeError:
        _HAS_GLOBAL_REWARD_PROFILE = False

    try:
        _LIB.mahjong_core_alpha_terminal_projection_ev.argtypes = [
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_double),
        ]
        _LIB.mahjong_core_alpha_terminal_projection_ev.restype = ctypes.c_int32
        _HAS_ALPHA_TERMINAL_EV = True
    except AttributeError:
        _HAS_ALPHA_TERMINAL_EV = False

    try:
        _LIB.mahjong_core_tile_danger_for_opponent.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_double,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_tile_danger_for_opponent.restype = ctypes.c_int32
        _HAS_TILE_DANGER = True
    except AttributeError:
        _HAS_TILE_DANGER = False

    try:
        _LIB.mahjong_core_aggregate_safety_scores.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_aggregate_safety_scores.restype = ctypes.c_int32
        _HAS_AGGREGATE_SAFETY = True
    except AttributeError:
        _HAS_AGGREGATE_SAFETY = False

    try:
        _LIB.mahjong_core_safe_tile_reserve_profile.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_uint8),
        ]
        _LIB.mahjong_core_safe_tile_reserve_profile.restype = ctypes.c_int32
        _HAS_SAFE_RESERVE = True
    except AttributeError:
        _HAS_SAFE_RESERVE = False

    try:
        _LIB.mahjong_core_safe_tile_reserve_profiles_after_discards.argtypes = [
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        _LIB.mahjong_core_safe_tile_reserve_profiles_after_discards.restype = ctypes.c_int32
        _HAS_SAFE_RESERVE_BATCH = True
    except AttributeError:
        _HAS_SAFE_RESERVE_BATCH = False


_configure_library()


def is_available() -> bool:
    return _LIB is not None


def version() -> int | None:
    if _LIB is None:
        return None
    return int(_LIB.mahjong_core_version())


def _mode_code(mode: str) -> int:
    return 3 if mode == "3P" else 4


def _known_mode_code(mode: str) -> int | None:
    if mode == "3P":
        return 3
    if mode == "4P":
        return 4
    return None


def _east_only(round_length: str) -> int | None:
    if round_length == "EAST":
        return 1
    if round_length == "SOUTH":
        return 0
    return None


def tile_type(tile_id: int) -> int | None:
    if _LIB is None or not _HAS_TILE_TYPE:
        return None
    result = int(_LIB.mahjong_core_tile_type(int(tile_id)))
    return None if result == -999 else result


def default_aka_dora_count(mode: str) -> int | None:
    mode_code = _known_mode_code(mode)
    if _LIB is None or not _HAS_TILE_HELPERS or mode_code is None:
        return None
    result = int(_LIB.mahjong_core_default_aka_dora_count(mode_code))
    return None if result == -999 else result


def normalize_aka_dora_count(mode: str, profile: str, value: object) -> int | None:
    mode_code = _known_mode_code(mode)
    if _LIB is None or not _HAS_TILE_HELPERS or mode_code is None:
        return None
    try:
        int_value = int(value)  # type: ignore[arg-type]
        has_value = 1
    except (TypeError, ValueError):
        int_value = 0
        has_value = 0
    result = int(
        _LIB.mahjong_core_normalize_aka_dora_count(
            mode_code,
            1 if profile == "RANKED" else 0,
            has_value,
            int_value,
        )
    )
    return None if result == -999 else result


def active_aka_dora_ids(mode: str, count: int) -> frozenset[int] | None:
    mode_code = _known_mode_code(mode)
    if _LIB is None or not _HAS_TILE_HELPERS or mode_code is None:
        return None
    out_ids = (ctypes.c_int32 * 4)()
    result = int(_LIB.mahjong_core_active_aka_dora_ids(mode_code, int(count), out_ids, 4))
    if result == -999:
        return None
    return frozenset(int(out_ids[index]) for index in range(result))


def is_red_tile(mode: str, count: int, tile_id: int) -> bool | None:
    mode_code = _known_mode_code(mode)
    if _LIB is None or not _HAS_TILE_HELPERS or mode_code is None:
        return None
    result = int(_LIB.mahjong_core_is_red_tile(mode_code, int(count), int(tile_id)))
    return None if result == -999 else bool(result)


def tile_flags(tile_index: int) -> int | None:
    if _LIB is None or not _HAS_TILE_HELPERS:
        return None
    result = int(_LIB.mahjong_core_tile_flags(int(tile_index)))
    return None if result == -999 else result


def is_legal_tile_type(mode: str, tile_index: int) -> bool | None:
    if _LIB is None or not _HAS_LEGAL_TILE_TYPE:
        return None
    result = int(_LIB.mahjong_core_is_legal_tile_type(_mode_code(mode), int(tile_index)))
    return result != 0


def legal_tile_types(mode: str) -> list[int] | None:
    mode_code = _known_mode_code(mode)
    if _LIB is None or not _HAS_TILE_HELPERS or mode_code is None:
        return None
    out_types = (ctypes.c_int32 * 34)()
    result = int(_LIB.mahjong_core_legal_tile_types(mode_code, out_types, 34))
    if result == -999:
        return None
    return [int(out_types[index]) for index in range(result)]


def representative_tile_id(tile_index: int, hand_tiles: list[int] | None = None) -> int | None:
    if _LIB is None or not _HAS_TILE_HELPERS:
        return None
    blocked_tiles = hand_tiles or []
    blocked_array = _int32_array(blocked_tiles)
    result = int(
        _LIB.mahjong_core_representative_tile_id(
            int(tile_index),
            blocked_array,
            len(blocked_tiles),
        )
    )
    return None if result == -999 else result


def dora_from_indicator(indicator_tile_id: int, *, mode: str = "4P") -> int | None:
    if _LIB is None or not _HAS_DORA_FROM_INDICATOR:
        return None
    result = int(_LIB.mahjong_core_dora_from_indicator(_mode_code(mode), int(indicator_tile_id)))
    return None if result == -999 else result


def scoring_indicator_tile_id(indicator_tile_id: int, *, mode: str) -> int | None:
    if _LIB is None or not _HAS_SCORING_INDICATOR_TILE_ID:
        return None
    result = int(_LIB.mahjong_core_scoring_indicator_tile_id(_mode_code(mode), int(indicator_tile_id)))
    return None if result == -999 else result


def player_count(mode: str) -> int | None:
    mode_code = _known_mode_code(mode)
    if _LIB is None or not _HAS_RULE_SEAT_MATH or mode_code is None:
        return None
    result = int(_LIB.mahjong_core_player_count(mode_code))
    return None if result == -999 else result


def next_seat(seat: int, count: int) -> int | None:
    if _LIB is None or not _HAS_RULE_SEAT_MATH:
        return None
    result = int(_LIB.mahjong_core_next_seat(int(seat), int(count)))
    return None if result == -999 else result


def seat_distance(origin: int, target: int, count: int) -> int | None:
    if _LIB is None or not _HAS_RULE_SEAT_MATH:
        return None
    result = int(_LIB.mahjong_core_seat_distance(int(origin), int(target), int(count)))
    return None if result == -999 else result


def seat_wind_code(player_count: int, dealer_seat: int, seat: int) -> int | None:
    if _LIB is None or not _HAS_RULE_SEAT_MATH:
        return None
    # Rust 返回的是稳定编码而不是字符串：0=东、1=南、2=西、3=北。
    # Python 业务层继续把编码映射成既有的 "E/S/W/N"，这样 API 输出和日志格式都不变。
    result = int(_LIB.mahjong_core_seat_wind_code(int(player_count), int(dealer_seat), int(seat)))
    return None if result == -999 else result


def round_target_count(mode: str, round_length: str) -> int | None:
    mode_code = _known_mode_code(mode)
    east_only = _east_only(round_length)
    if _LIB is None or not _HAS_RULE_SEAT_MATH or mode_code is None or east_only is None:
        return None
    result = int(_LIB.mahjong_core_round_target_count(mode_code, east_only))
    return None if result == -999 else result


def max_round_count(mode: str, round_length: str) -> int | None:
    mode_code = _known_mode_code(mode)
    east_only = _east_only(round_length)
    if _LIB is None or not _HAS_RULE_SEAT_MATH or mode_code is None or east_only is None:
        return None
    result = int(_LIB.mahjong_core_max_round_count(mode_code, east_only))
    return None if result == -999 else result


def _round_result_kind_code(kind: str) -> int:
    return {"RON": 1, "TSUMO": 2, "DRAW": 3, "ABORTIVE_DRAW": 4}.get(kind, 0)


def _round_result_subtype_code(subtype: str) -> int:
    return {"NAGASHI_MANGAN": 1}.get(subtype, 0)


def is_win_like_round_result(kind: str, subtype: str) -> bool | None:
    if _LIB is None or not _HAS_ROUND_END_RULES:
        return None
    result = int(
        _LIB.mahjong_core_is_win_like_round_result(
            _round_result_kind_code(kind),
            _round_result_subtype_code(subtype),
        )
    )
    return None if result == -999 else bool(result)


def goal_score_reached(player_points: list[int], target_score: int) -> bool | None:
    if _LIB is None or not _HAS_ROUND_END_RULES:
        return None
    points_array = _int32_array(player_points)
    result = int(_LIB.mahjong_core_goal_score_reached(points_array, len(player_points), int(target_score)))
    return None if result == -999 else bool(result)


def should_auto_stop_all_last_dealer(
    dealer_continues: bool,
    round_cursor: int,
    base_rounds: int,
    round_result_kind: str,
    dealer_seat: int,
    player_points: list[int],
    target_score: int,
) -> bool | None:
    if _LIB is None or not _HAS_ROUND_END_RULES:
        return None
    # player_points 按 seat 顺序传给 Rust；Rust 用同分低 seat 优先找头名。
    # 这和 Python 的 top_player_entry 排序规则保持一致。
    points_array = _int32_array(player_points)
    result = int(
        _LIB.mahjong_core_should_auto_stop_all_last_dealer(
            1 if dealer_continues else 0,
            int(round_cursor),
            int(base_rounds),
            _round_result_kind_code(round_result_kind),
            int(dealer_seat),
            points_array,
            len(player_points),
            int(target_score),
        )
    )
    return None if result == -999 else bool(result)


def round_up_to_100(value: float) -> int | None:
    if _LIB is None or not _HAS_SCORING_PAYMENTS:
        return None
    result = int(_LIB.mahjong_core_round_up_to_100(float(value)))
    return None if result == -999 else result


def score_result_total(cost: dict[str, int]) -> int | None:
    if _LIB is None or not _HAS_SCORING_PAYMENTS:
        return None
    total = cost.get("total")
    total_value = int(total) if isinstance(total, int) else -1
    result = int(
        _LIB.mahjong_core_score_result_total(
            total_value,
            int(cost.get("main", 0)),
            int(cost.get("main_bonus", 0)),
            int(cost.get("additional", 0)),
            int(cost.get("additional_bonus", 0)),
        )
    )
    return None if result == -999 else result


def full_honba_value(mode: str, honba: int) -> int | None:
    if _LIB is None or not _HAS_SCORING_PAYMENTS:
        return None
    result = int(_LIB.mahjong_core_full_honba_value(_mode_code(mode), int(honba)))
    return None if result == -999 else result


def minimum_han_satisfied(han: int, yakuman_total_han: int, has_local_yaku: bool, minimum_han: int) -> bool | None:
    if _LIB is None or not _HAS_SCORING_PAYMENTS:
        return None
    result = int(
        _LIB.mahjong_core_minimum_han_satisfied(
            int(han),
            int(yakuman_total_han),
            1 if has_local_yaku else 0,
            int(minimum_han),
        )
    )
    return None if result == -999 else bool(result)


def tsumo_payment_map(
    mode: str,
    sanma_scoring_mode: str,
    player_count: int,
    winner: int,
    dealer: int,
    cost: dict[str, int],
) -> dict[int, int] | None:
    mode_code = _known_mode_code(mode)
    if _LIB is None or not _HAS_SCORING_PAYMENTS or mode_code is None:
        return None
    if player_count not in {3, 4}:
        return None
    out_payments = (ctypes.c_int32 * player_count)()
    result = int(
        _LIB.mahjong_core_tsumo_payment_map(
            mode_code,
            1 if sanma_scoring_mode == "NORTH_BISECTION" else 0,
            int(player_count),
            int(winner),
            int(dealer),
            int(cost.get("main", 0)),
            int(cost.get("main_bonus", 0)),
            int(cost.get("additional", 0)),
            int(cost.get("additional_bonus", 0)),
            out_payments,
            player_count,
        )
    )
    if result == -999:
        return None
    return {seat: int(out_payments[seat]) for seat in range(result) if seat != winner}


def is_nagashi_mangan_candidate(tile_ids: list[int], called_flags: list[bool]) -> bool | None:
    if _LIB is None or not _HAS_SCORING_PAYMENTS:
        return None
    # tile_ids 和 called_flags 来自同一条弃牌河，靠下标一一对应；Rust 返回 -999
    # 时代表桥接输入不完整或 DLL 版本不匹配，上层会继续走 Python 原逻辑。
    tile_array = _int32_array(tile_ids)
    called_array = (ctypes.c_uint8 * len(called_flags))(*(1 if flag else 0 for flag in called_flags))
    result = int(
        _LIB.mahjong_core_is_nagashi_mangan_candidate(
            tile_array,
            len(tile_ids),
            called_array,
            len(called_flags),
        )
    )
    return None if result == -999 else bool(result)


def liability_key_for_call(
    action_type: str,
    called_tile_type: int,
    same_seat: bool,
    existing_keys: set[str],
    triplet_tile_types: list[int],
) -> str | None:
    if _LIB is None or not _HAS_SCORING_LIABILITY:
        return None
    # Python 保留 round_state/liability 字典的所有权；这里只把动作、被鸣牌牌种、已有 key
    # 和刻子/杠子牌种列表压平成 C ABI 参数。Rust 返回 0 表示“本次不新增责任役”，
    # 1/2 再映射回系统里长期使用的字符串 key。
    action_code = {"pon": 1, "open_kan": 2}.get(action_type, 0)
    triplet_array = _int32_array(triplet_tile_types)
    result = int(
        _LIB.mahjong_core_liability_key_for_call(
            action_code,
            int(called_tile_type),
            1 if same_seat else 0,
            1 if "DAISANGEN" in existing_keys else 0,
            1 if "DAISUUSHI" in existing_keys else 0,
            triplet_array,
            len(triplet_tile_types),
        )
    )
    if result == -999:
        return None
    return {0: "", 1: "DAISANGEN", 2: "DAISUUSHI"}.get(result)


def liability_context_profile(
    player_count: int,
    yakuman_total_han: int,
    daisangen_eval_han: int,
    daisangen_liable_seat: int,
    daisangen_liability_han: int,
    daisuushi_eval_han: int,
    daisuushi_liable_seat: int,
    daisuushi_liability_han: int,
) -> tuple[int, int, int, int] | None:
    if _LIB is None or not _HAS_SCORING_LIABILITY:
        return None
    # 输出四元组含义与 Rust/FFI 保持一致：
    # (liable_seat, liable_han, remainder_han, key_mask)。key_mask 为 0 时表示没有包牌上下文，
    # 这和 None 不同；None 只表示 Rust 路径不可用或输入被 Rust 拒绝。
    out_profile = (ctypes.c_int32 * 4)()
    result = int(
        _LIB.mahjong_core_liability_context_profile(
            int(player_count),
            int(yakuman_total_han),
            int(daisangen_eval_han),
            int(daisangen_liable_seat),
            int(daisangen_liability_han),
            int(daisuushi_eval_han),
            int(daisuushi_liable_seat),
            int(daisuushi_liability_han),
            out_profile,
            4,
        )
    )
    if result == -999:
        return None
    return tuple(int(out_profile[index]) for index in range(4))


def local_mangan_yaku_name(
    koyaku_enabled: bool,
    is_tsumo: bool,
    is_haitei: bool,
    is_houtei: bool,
    win_tile_type: int,
) -> str | None:
    if _LIB is None or not _HAS_LOCAL_YAKU:
        return None
    # Rust 返回 code，Python 负责名字映射；空字符串表示“Rust 正常判断为无本地满贯役”，
    # None 只表示 Rust 路径不可用或输入非法，调用方会继续执行 Python 兜底逻辑。
    result = int(
        _LIB.mahjong_core_local_mangan_yaku_code(
            1 if koyaku_enabled else 0,
            1 if is_tsumo else 0,
            1 if is_haitei else 0,
            1 if is_houtei else 0,
            int(win_tile_type),
        )
    )
    if result == -999:
        return None
    return {0: "", 1: "Iipin moyue", 2: "Chuupin raoyui"}.get(result)


def local_yakuman_entries(
    koyaku_enabled: bool,
    double_riichi: bool,
    closed_hand: bool,
    is_haitei: bool,
    is_houtei: bool,
) -> list[tuple[str, int]] | None:
    if _LIB is None or not _HAS_LOCAL_YAKU:
        return None
    result = int(
        _LIB.mahjong_core_local_yakuman_yaku_code(
            1 if koyaku_enabled else 0,
            1 if double_riichi else 0,
            1 if closed_hand else 0,
            1 if is_haitei else 0,
            1 if is_houtei else 0,
        )
    )
    if result == -999:
        return None
    if result == 1:
        return [("Ishi no ue ni mo sannen", 13)]
    return []


def local_han_yaku_entries(
    koyaku_enabled: bool,
    is_tsumo: bool,
    has_last_discard: bool,
    discard_is_self: bool,
    discard_from_replacement_source: bool,
    discard_riichi: bool,
    discard_follows_kan: bool,
) -> list[tuple[str, int]] | None:
    if _LIB is None or not _HAS_LOCAL_YAKU:
        return None
    # mask 的低两位分别代表 Tsubame gaeshi 和 Kanburi。名字/番数仍由 Python 组装，
    # 这样未来改展示文本时不需要触碰 Rust ABI。
    result = int(
        _LIB.mahjong_core_local_han_yaku_mask(
            1 if koyaku_enabled else 0,
            1 if is_tsumo else 0,
            1 if has_last_discard else 0,
            1 if discard_is_self else 0,
            1 if discard_from_replacement_source else 0,
            1 if discard_riichi else 0,
            1 if discard_follows_kan else 0,
        )
    )
    if result == -999:
        return None
    entries: list[tuple[str, int]] = []
    if result & 0b01:
        entries.append(("Tsubame gaeshi", 1))
    if result & 0b10:
        entries.append(("Kanburi", 1))
    return entries


def local_pattern_entries_for_hand(hand: list[list[int]], is_open_hand: bool) -> list[tuple[str, int]] | None:
    if _LIB is None or not _HAS_LOCAL_YAKU:
        return None
    # HandDivider 的 hand 是嵌套列表，C ABI 不适合直接传嵌套结构。这里压平成：
    # flat_tiles = 所有 group 的牌种串联，group_lens = 每个 group 的长度。Rust 只返回 mask，
    # Python 保留“开门降番”和最终名字/番数。
    flat_tiles = [int(tile_type) for group in hand for tile_type in group]
    group_lens = [len(group) for group in hand]
    flat_array = _int32_array(flat_tiles)
    len_array = (ctypes.c_size_t * len(group_lens))(*group_lens)
    result = int(
        _LIB.mahjong_core_local_pattern_yaku_mask(
            flat_array,
            len(flat_tiles),
            len_array,
            len(group_lens),
        )
    )
    if result == -999:
        return None
    entries: list[tuple[str, int]] = []
    if result & 0b01:
        entries.append(("Isshoku sanjun", 2 if is_open_hand else 3))
    if result & 0b10:
        entries.append(("Sanrenkou", 2))
    return entries


def ranked_settlement_scores(mode: str, start_points: int, placement_points: list[int]) -> list[dict[str, int]] | None:
    mode_code = _known_mode_code(mode)
    if _LIB is None or not _HAS_RANKED_SETTLEMENT or mode_code is None:
        return None
    points_array = _int32_array(placement_points)
    out_point = (ctypes.c_int32 * len(placement_points))()
    out_uma = (ctypes.c_int32 * len(placement_points))()
    out_rank = (ctypes.c_int32 * len(placement_points))()
    result = int(
        _LIB.mahjong_core_ranked_settlement_scores(
            mode_code,
            int(start_points),
            points_array,
            len(placement_points),
            out_point,
            out_uma,
            out_rank,
            len(placement_points),
        )
    )
    if result == -999:
        return None
    return [
        {
            "point_score": int(out_point[index]),
            "uma": int(out_uma[index]),
            "rank_score": int(out_rank[index]),
        }
        for index in range(result)
    ]


def kuikae_forbidden_tile_types(action_type: str, discard_tile_id: int, consumed_ids: list[int]) -> list[int] | None:
    if _LIB is None or not _HAS_ACTION_RULES:
        return None
    action_code = {"chi": 1, "pon": 2}.get(action_type, 0)
    consumed_array = _int32_array(consumed_ids)
    out_types = (ctypes.c_int32 * 2)()
    result = int(
        _LIB.mahjong_core_kuikae_forbidden_tile_types(
            action_code,
            int(discard_tile_id),
            consumed_array,
            len(consumed_ids),
            out_types,
            2,
        )
    )
    if result == -999:
        return None
    return [int(out_types[index]) for index in range(result)]


def chi_candidates(hand_tiles: list[int], discard_tile_id: int) -> list[list[int]] | None:
    if _LIB is None or not _HAS_ACTION_RULES:
        return None
    hand_array = _int32_array(hand_tiles)
    out_tile_ids = (ctypes.c_int32 * 6)()
    result = int(
        _LIB.mahjong_core_chi_candidate_pairs(
            hand_array,
            len(hand_tiles),
            int(discard_tile_id),
            out_tile_ids,
            6,
        )
    )
    if result == -999:
        return None
    return [
        [int(out_tile_ids[index * 2]), int(out_tile_ids[index * 2 + 1])]
        for index in range(result)
    ]


def is_furiten(win_tile_type: int, discard_tile_types: list[int], temporary: bool, riichi: bool) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    # 这里刻意传 tile type 而不是 tile id：振听只关心“是否弃过这种牌”，
    # 不关心是哪一张实体牌。temporary/riichi 是另外两种振听来源，直接作为布尔位传入。
    discard_array = _int32_array(discard_tile_types)
    result = int(
        _LIB.mahjong_core_is_furiten(
            int(win_tile_type),
            discard_array,
            len(discard_tile_types),
            1 if temporary else 0,
            1 if riichi else 0,
        )
    )
    return None if result == -999 else bool(result)


def can_double_riichi(has_discards: bool, has_calls: bool) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    result = int(_LIB.mahjong_core_can_double_riichi(1 if has_discards else 0, 1 if has_calls else 0))
    return None if result == -999 else bool(result)


def pending_abortive_draw_kind(
    player_count: int,
    first_discard_tiles: list[int],
    discard_counts: list[int],
    riichi_flags: list[bool],
    has_calls: bool,
) -> str | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    # Rust 侧返回小整数，Python 侧再映射成既有的业务字符串，避免 FFI 暴露字符串
    # 生命周期。0 是正常的“无待流局”，None 才表示 Rust 路径不可用或输入非法。
    first_array = _int32_array(first_discard_tiles)
    count_array = _int32_array(discard_counts)
    riichi_array = (ctypes.c_uint8 * len(riichi_flags))(*(1 if flag else 0 for flag in riichi_flags))
    result = int(
        _LIB.mahjong_core_pending_abortive_draw_kind(
            int(player_count),
            first_array,
            len(first_discard_tiles),
            count_array,
            len(discard_counts),
            riichi_array,
            len(riichi_flags),
            1 if has_calls else 0,
        )
    )
    if result == -999:
        return None
    return {0: "", 1: "SUUFON_RENDA", 2: "SUUCHA_RIICHI"}.get(result)


def should_abort_for_four_kans(kan_count: int, kan_owner_flags: list[bool]) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    # Python 已经把 meld 字典压成每个座位一个 owner flag，Rust 只负责“四杠且多人拥有”
    # 这个纯规则判断，不在 FFI 边界解析复杂对象。
    owner_array = (ctypes.c_uint8 * len(kan_owner_flags))(*(1 if flag else 0 for flag in kan_owner_flags))
    result = int(_LIB.mahjong_core_should_abort_for_four_kans(int(kan_count), owner_array, len(kan_owner_flags)))
    return None if result == -999 else bool(result)


def is_tenhou_state(
    player_count: int,
    seat: int,
    dealer: int,
    is_tsumo: bool,
    has_calls: bool,
    discard_counts: list[int],
) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    # 天和需要看“全场是否还没人弃牌”，因此这里传每家弃牌数量，而不是只传 last_discard。
    # Rust 侧验证长度至少覆盖 player_count，失败时返回 -999 并触发 Python 兜底。
    count_array = _int32_array(discard_counts)
    result = int(
        _LIB.mahjong_core_is_tenhou_state(
            int(player_count),
            int(seat),
            int(dealer),
            1 if is_tsumo else 0,
            1 if has_calls else 0,
            count_array,
            len(discard_counts),
        )
    )
    return None if result == -999 else bool(result)


def is_chiihou_state(
    player_count: int,
    seat: int,
    dealer: int,
    is_tsumo: bool,
    has_calls: bool,
    seat_discard_count: int,
) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    # 地和只关心当前子家的首次摸牌是否被鸣牌打断；其他玩家的弃牌数量不进入旧逻辑，
    # 所以只把当前座位自己的弃牌数传给 Rust，保持行为完全一致。
    result = int(
        _LIB.mahjong_core_is_chiihou_state(
            int(player_count),
            int(seat),
            int(dealer),
            1 if is_tsumo else 0,
            1 if has_calls else 0,
            int(seat_discard_count),
        )
    )
    return None if result == -999 else bool(result)


def is_haitei_state(
    is_tsumo: bool,
    has_current_draw: bool,
    current_draw_from_wall: bool,
    turn_is_seat: bool,
    live_wall_empty: bool,
) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    result = int(
        _LIB.mahjong_core_is_haitei_state(
            1 if is_tsumo else 0,
            1 if has_current_draw else 0,
            1 if current_draw_from_wall else 0,
            1 if turn_is_seat else 0,
            1 if live_wall_empty else 0,
        )
    )
    return None if result == -999 else bool(result)


def is_houtei_state(
    is_tsumo: bool,
    has_last_discard: bool,
    discard_from_replacement_source: bool,
    discarder_last_draw_from_wall: bool,
    live_wall_empty: bool,
) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    # 杠后弃牌和拔北后的弃牌都不是正常河底，所以 Python 先把 source in {"kan", "kita"}
    # 压成 discard_from_replacement_source，Rust 只判断这个已归一化的规则位。
    result = int(
        _LIB.mahjong_core_is_houtei_state(
            1 if is_tsumo else 0,
            1 if has_last_discard else 0,
            1 if discard_from_replacement_source else 0,
            1 if discarder_last_draw_from_wall else 0,
            1 if live_wall_empty else 0,
        )
    )
    return None if result == -999 else bool(result)


def is_chankan_state(
    is_tsumo: bool,
    has_last_discard: bool,
    discard_source_is_kan: bool,
    kan_type_is_closed: bool,
) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    result = int(
        _LIB.mahjong_core_is_chankan_state(
            1 if is_tsumo else 0,
            1 if has_last_discard else 0,
            1 if discard_source_is_kan else 0,
            1 if kan_type_is_closed else 0,
        )
    )
    return None if result == -999 else bool(result)


def is_renhou_state(
    player_count: int,
    seat: int,
    dealer: int,
    is_tsumo: bool,
    koyaku_enabled: bool,
    has_calls: bool,
    seat_has_last_draw_source: bool,
    has_last_discard: bool,
    last_discard_seat: int,
    last_discard_from_replacement_source: bool,
    seat_discard_count: int,
) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    # 人和的判断拆成一组标量，避免把 Python 的 last_discard 字典结构暴露给 Rust。
    # last_discard_seat 只有 has_last_discard 为 True 时才有规则意义；Rust 会做座位边界校验。
    result = int(
        _LIB.mahjong_core_is_renhou_state(
            int(player_count),
            int(seat),
            int(dealer),
            1 if is_tsumo else 0,
            1 if koyaku_enabled else 0,
            1 if has_calls else 0,
            1 if seat_has_last_draw_source else 0,
            1 if has_last_discard else 0,
            int(last_discard_seat),
            1 if last_discard_from_replacement_source else 0,
            int(seat_discard_count),
        )
    )
    return None if result == -999 else bool(result)


def can_abortive_draw_nine_terminals(
    phase_is_discard: bool,
    turn_is_seat: bool,
    has_current_draw: bool,
    seat_has_discards: bool,
    has_calls: bool,
    unique_terminal_honor_count: int,
) -> bool | None:
    if _LIB is None or not _HAS_ROUND_STATE_RULES:
        return None
    # 九种九牌入口判定只需要若干状态位加“幺九牌去重数量”。实际去重仍在 Python
    # 调用 unique_terminal_honor_types 完成，Rust 这里不接收整副手牌。
    result = int(
        _LIB.mahjong_core_can_abortive_draw_nine_terminals(
            1 if phase_is_discard else 0,
            1 if turn_is_seat else 0,
            1 if has_current_draw else 0,
            1 if seat_has_discards else 0,
            1 if has_calls else 0,
            int(unique_terminal_honor_count),
        )
    )
    return None if result == -999 else bool(result)


def unique_terminal_honor_types(tiles: list[int]) -> set[int] | None:
    if _LIB is None or not _HAS_TERMINAL_HONOR_TYPES:
        return None
    tile_array = _int32_array(tiles)
    out_types = (ctypes.c_int32 * 13)()
    result = int(
        _LIB.mahjong_core_unique_terminal_honor_types(
            tile_array,
            len(tiles),
            out_types,
            13,
        )
    )
    if result == -999:
        return None
    return {int(out_types[index]) for index in range(result)}


def is_complete_hand_shape(mode: str, concealed_counts: list[int], meld_count: int) -> bool | None:
    if _LIB is None or not _HAS_COMPLETE_HAND_SHAPE:
        return None
    try:
        count_array = _u8_34_array(concealed_counts)
    except ValueError:
        return None
    result = int(
        _LIB.mahjong_core_is_complete_hand_shape(
            _mode_code(mode),
            count_array,
            34,
            int(meld_count),
        )
    )
    return None if result == -999 else bool(result)


def tenpai_waits_from_counts(
    mode: str,
    concealed_counts: list[int],
    owned_counts: list[int],
    meld_count: int,
) -> set[int] | None:
    if _LIB is None or not _HAS_TENPAI_WAITS:
        return None
    try:
        concealed_array = _u8_34_array(concealed_counts)
        owned_array = _u8_34_array(owned_counts)
    except ValueError:
        return None
    out_mask = (ctypes.c_uint8 * 34)()
    result = int(
        _LIB.mahjong_core_tenpai_waits_from_counts(
            _mode_code(mode),
            concealed_array,
            34,
            owned_array,
            34,
            int(meld_count),
            out_mask,
            34,
        )
    )
    if result == -999:
        return None
    return {index for index in range(34) if int(out_mask[index]) != 0}


def _int32_array(values: Iterable[int]) -> ctypes.Array:
    items = [int(value) for value in values]
    return (ctypes.c_int32 * len(items))(*items)


def _u8_34_array(values: Iterable[int]) -> ctypes.Array:
    items = [int(value) for value in values]
    if len(items) != 34:
        raise ValueError("expected 34 tile counts")
    return (ctypes.c_uint8 * 34)(*items)


def _u8_mask_array(values: Iterable[int], expected_len: int) -> ctypes.Array:
    items = [1 if int(value) else 0 for value in values]
    if len(items) != expected_len:
        raise ValueError(f"expected {expected_len} mask values")
    return (ctypes.c_uint8 * expected_len)(*items)


def _u8_array(values: Iterable[int], expected_len: int) -> ctypes.Array:
    items = [max(0, min(255, int(value))) for value in values]
    if len(items) != expected_len:
        raise ValueError(f"expected {expected_len} values")
    return (ctypes.c_uint8 * expected_len)(*items)


def _double_array(values: Iterable[float]) -> ctypes.Array:
    items = [float(value) for value in values]
    return (ctypes.c_double * len(items))(*items)


def _used_counts_array(values: dict[int, int] | list[int] | None) -> ctypes.Array:
    if values is None:
        return (ctypes.c_uint8 * 34)()
    if isinstance(values, dict):
        items = [0] * 34
        for key, value in values.items():
            tile_index = int(key)
            if 0 <= tile_index < 34:
                items[tile_index] = max(0, min(4, int(value)))
        return (ctypes.c_uint8 * 34)(*items)
    return _u8_34_array(values)


def to_34_array(tiles: list[int]) -> list[int] | None:
    if _LIB is None:
        return None
    tile_array = _int32_array(tiles)
    out_counts = (ctypes.c_uint8 * 34)()
    result = _LIB.mahjong_core_counts_from_tiles(tile_array, len(tiles), out_counts, 34)
    if result != 0:
        return None
    return [int(out_counts[index]) for index in range(34)]


def visible_counts_from_tiles(mode: str, tiles: list[int]) -> list[int] | None:
    if _LIB is None or not _HAS_VISIBLE_COUNTS:
        return None
    tile_array = _int32_array(tiles)
    out_counts = (ctypes.c_uint8 * 34)()
    result = _LIB.mahjong_core_visible_counts_from_tiles(
        _mode_code(mode),
        tile_array,
        len(tiles),
        out_counts,
        34,
    )
    if result != 0:
        return None
    return [int(out_counts[index]) for index in range(34)]


def tile_value_bonus(
    discard_tile_id: int,
    *,
    is_red_tile: bool,
    own_wind_type: int,
    round_wind_type: int,
    dora_types: Iterable[int],
) -> float | None:
    if _LIB is None or not _HAS_TILE_VALUE_BONUS:
        return None
    dora_mask = [0] * 34
    for tile_index in dora_types:
        index = int(tile_index)
        if 0 <= index < 34:
            dora_mask[index] = 1
    dora_array = _u8_34_array(dora_mask)
    result = float(
        _LIB.mahjong_core_tile_value_bonus(
            int(discard_tile_id),
            1 if is_red_tile else 0,
            int(own_wind_type),
            int(round_wind_type),
            dora_array,
            34,
        )
    )
    return None if result == -999.0 else result


def shanten_from_counts(counts: list[int]) -> int | None:
    if _LIB is None:
        return None
    try:
        count_array = _u8_34_array(counts)
    except ValueError:
        return None
    result = int(_LIB.mahjong_core_shanten_34(count_array, 34))
    return None if result == -999 else result


def shanten_of_tiles(tiles: list[int]) -> int | None:
    counts = to_34_array(tiles)
    if counts is None:
        return None
    return shanten_from_counts(counts)


def effective_tiles_after_discard(
    mode: str,
    source_tiles: list[int],
    discard_tile_id: int,
    visible_counts: list[int],
    base_shanten: int | None = None,
) -> tuple[int, list[dict[str, int]]] | None:
    if _LIB is None:
        return None
    mode_value = 3 if mode == "3P" else 4
    tile_array = _int32_array(source_tiles)
    try:
        visible_array = _u8_34_array(visible_counts)
    except ValueError:
        return None
    out_remaining = (ctypes.c_int32 * 34)()
    out_next_shanten = (ctypes.c_int32 * 34)()
    result = int(
        _LIB.mahjong_core_effective_tiles_after_discard(
            mode_value,
            tile_array,
            len(source_tiles),
            int(discard_tile_id),
            visible_array,
            34,
            int(base_shanten) if base_shanten is not None else 99,
            out_remaining,
            out_next_shanten,
            34,
        )
    )
    if result == -999:
        return None
    good_tiles = [
        {"type": tile_index, "remaining": int(out_remaining[tile_index]), "next_shanten": int(out_next_shanten[tile_index])}
        for tile_index in range(34)
        if int(out_remaining[tile_index]) > 0
    ]
    return result, good_tiles


def effective_tiles_from_counts(
    mode: str,
    counts: list[int],
    visible_counts: list[int],
    used_counts: dict[int, int] | list[int] | None = None,
    base_shanten: int | None = None,
) -> tuple[int, list[dict[str, int]]] | None:
    if _LIB is None or not _HAS_EFFECTIVE_FROM_COUNTS:
        return None
    mode_value = 3 if mode == "3P" else 4
    try:
        counts_array = _u8_34_array(counts)
        visible_array = _u8_34_array(visible_counts)
        used_array = _used_counts_array(used_counts)
    except ValueError:
        return None
    out_remaining = (ctypes.c_int32 * 34)()
    out_next_shanten = (ctypes.c_int32 * 34)()
    result = int(
        _LIB.mahjong_core_effective_tiles_from_counts(
            mode_value,
            counts_array,
            34,
            visible_array,
            34,
            used_array,
            34,
            int(base_shanten) if base_shanten is not None else 99,
            out_remaining,
            out_next_shanten,
            34,
        )
    )
    if result == -999:
        return None
    good_tiles = [
        {"type": tile_index, "remaining": int(out_remaining[tile_index]), "next_shanten": int(out_next_shanten[tile_index])}
        for tile_index in range(34)
        if int(out_remaining[tile_index]) > 0
    ]
    return result, good_tiles


def draw_tiles_from_counts(
    mode: str,
    counts: list[int],
    visible_counts: list[int],
    used_counts: dict[int, int] | list[int] | None = None,
) -> tuple[int, list[dict[str, int]]] | None:
    if _LIB is None or not _HAS_DRAW_FROM_COUNTS:
        return None
    mode_value = 3 if mode == "3P" else 4
    try:
        counts_array = _u8_34_array(counts)
        visible_array = _u8_34_array(visible_counts)
        used_array = _used_counts_array(used_counts)
    except ValueError:
        return None
    out_remaining = (ctypes.c_int32 * 34)()
    out_next_shanten = (ctypes.c_int32 * 34)()
    result = int(
        _LIB.mahjong_core_draw_tiles_from_counts(
            mode_value,
            counts_array,
            34,
            visible_array,
            34,
            used_array,
            34,
            out_remaining,
            out_next_shanten,
            34,
        )
    )
    if result == -999:
        return None
    draw_tiles = [
        {"type": tile_index, "remaining": int(out_remaining[tile_index]), "next_shanten": int(out_next_shanten[tile_index])}
        for tile_index in range(34)
        if int(out_remaining[tile_index]) > 0
    ]
    return result, draw_tiles


def hand_route_profile(
    concealed_counts: list[int],
    all_counts: list[int],
    value_honor_types: set[int] | list[int],
    *,
    triplet_meld_count: int,
    value_honor_triplet_meld_count: int,
    closed: bool,
    has_melds: bool,
    shanten_value: int,
) -> tuple[float, int] | None:
    if _LIB is None or not _HAS_HAND_ROUTE_PROFILE:
        return None
    value_honor_mask = [0] * 34
    for tile_index in value_honor_types:
        if 0 <= int(tile_index) < 34:
            value_honor_mask[int(tile_index)] = 1
    try:
        concealed_array = _u8_34_array(concealed_counts)
        all_array = _u8_34_array(all_counts)
        value_honor_array = _u8_34_array(value_honor_mask)
    except ValueError:
        return None
    route_mask = ctypes.c_uint32(0)
    result = int(
        _LIB.mahjong_core_hand_route_profile(
            concealed_array,
            34,
            all_array,
            34,
            value_honor_array,
            34,
            int(triplet_meld_count),
            int(value_honor_triplet_meld_count),
            1 if closed else 0,
            1 if has_melds else 0,
            int(shanten_value),
            ctypes.byref(route_mask),
        )
    )
    if result == -999:
        return None
    return result / 1000.0, int(route_mask.value)


def hand_route_profiles_after_discards(
    mode: str,
    source_concealed_counts: list[int],
    meld_counts: list[int],
    value_honor_types: set[int] | list[int],
    shanten_by_discard: list[int],
    *,
    triplet_meld_count: int,
    value_honor_triplet_meld_count: int,
    closed: bool,
    has_melds: bool,
) -> dict[int, tuple[float, int]] | None:
    if _LIB is None or not _HAS_ROUTE_PROFILES_AFTER_DISCARDS:
        return None
    value_honor_mask = [0] * 34
    for tile_index in value_honor_types:
        index = int(tile_index)
        if 0 <= index < 34:
            value_honor_mask[index] = 1
    try:
        source_array = _u8_34_array(source_concealed_counts)
        meld_array = _u8_34_array(meld_counts)
        value_honor_array = _u8_34_array(value_honor_mask)
    except ValueError:
        return None
    if len(shanten_by_discard) != 34:
        return None
    shanten_array = _int32_array(shanten_by_discard)
    out_bonus_milli = (ctypes.c_int32 * 34)()
    out_route_mask = (ctypes.c_uint32 * 34)()
    result = int(
        _LIB.mahjong_core_hand_route_profiles_after_discards(
            3 if mode == "3P" else 4,
            source_array,
            34,
            meld_array,
            34,
            value_honor_array,
            34,
            shanten_array,
            34,
            int(triplet_meld_count),
            int(value_honor_triplet_meld_count),
            1 if closed else 0,
            1 if has_melds else 0,
            out_bonus_milli,
            out_route_mask,
            34,
        )
    )
    if result == -999:
        return None
    profiles: dict[int, tuple[float, int]] = {}
    for tile_index in range(34):
        route_mask = int(out_route_mask[tile_index])
        bonus_milli = int(out_bonus_milli[tile_index])
        if int(shanten_by_discard[tile_index]) != 99:
            profiles[tile_index] = (bonus_milli / 1000.0, route_mask)
    return profiles


def discard_metrics_from_counts(
    mode: str,
    source_counts: list[int],
    base_visible_counts: list[int],
) -> dict[int, dict[str, int | list[dict[str, int]]]] | None:
    if _LIB is None or not _HAS_DISCARD_METRICS:
        return None
    mode_value = 3 if mode == "3P" else 4
    try:
        source_array = _u8_34_array(source_counts)
        visible_array = _u8_34_array(base_visible_counts)
    except ValueError:
        return None
    out_shanten = (ctypes.c_int32 * 34)()
    out_ukeire = (ctypes.c_int32 * 34)()
    out_remaining_matrix = (ctypes.c_int32 * (34 * 34))()
    result = int(
        _LIB.mahjong_core_discard_metrics_from_counts(
            mode_value,
            source_array,
            34,
            visible_array,
            34,
            out_shanten,
            out_ukeire,
            out_remaining_matrix,
            34,
            34 * 34,
        )
    )
    if result == -999:
        return None

    metrics: dict[int, dict[str, int | list[dict[str, int]]]] = {}
    for discard_type in range(34):
        shanten_value = int(out_shanten[discard_type])
        if shanten_value == 99:
            continue
        good_tiles = [
            {"type": tile_index, "remaining": int(out_remaining_matrix[discard_type * 34 + tile_index])}
            for tile_index in range(34)
            if int(out_remaining_matrix[discard_type * 34 + tile_index]) > 0
        ]
        metrics[discard_type] = {
            "shanten": shanten_value,
            "ukeire": int(out_ukeire[discard_type]),
            "good_tiles": good_tiles,
        }
    return metrics


def structured_discard_ev(
    *,
    shanten_value: int,
    ukeire: int,
    risk: float,
    value_penalty: float,
    route_bonus: float,
    route_count: int,
    level: int,
    progress: float,
    max_loss: int,
    max_threat: float,
    max_push_pressure: float,
    own_points: int,
    top_points: int,
    bottom_points: int,
    is_dealer: bool,
    is_closed: bool,
    live_tile_count: int,
    strategy_scale: float,
    attack_bias: float,
    defense_bias: float,
    value_bias: float,
    placement: int,
    placement_count: int,
    gap_to_above: int,
    is_all_last: bool,
    level_one_noise: float = 0.0,
) -> dict[str, float] | None:
    if _LIB is None or not _HAS_STRUCTURED_DISCARD_EV:
        return None
    out_values = (ctypes.c_double * 5)()
    result = int(
        _LIB.mahjong_core_structured_discard_ev(
            int(shanten_value),
            int(ukeire),
            float(risk),
            float(value_penalty),
            float(route_bonus),
            int(route_count),
            int(level),
            float(progress),
            int(max_loss),
            float(max_threat),
            float(max_push_pressure),
            int(own_points),
            int(top_points),
            int(bottom_points),
            1 if is_dealer else 0,
            1 if is_closed else 0,
            int(live_tile_count),
            float(strategy_scale),
            float(attack_bias),
            float(defense_bias),
            float(value_bias),
            int(placement),
            int(placement_count),
            int(gap_to_above),
            1 if is_all_last else 0,
            float(level_one_noise),
            out_values,
            5,
        )
    )
    if result == -999:
        return None
    return {
        "speed_ev": float(out_values[0]),
        "value_ev": float(out_values[1]),
        "defense_ev": float(out_values[2]),
        "table_ev": float(out_values[3]),
        "final_ev": float(out_values[4]),
    }


def push_fold_profile(
    *,
    shanten_value: int,
    risk: float,
    safety_score: float,
    hand_value_ev: float,
    estimated_han: float,
    wait_quality: float,
    progress: float,
    max_threat: float,
    max_push_pressure: float,
    max_loss: int,
    riichi_count: int,
    critical_count: int,
    high_count: int,
    defense_scale: float,
    strategy_scale: float,
    attack_bias: float,
    defense_bias: float,
    value_bias: float,
    is_dealer: bool,
    placement: int,
    placement_count: int,
    is_all_last: bool,
) -> dict[str, float | int] | None:
    if _LIB is None or not _HAS_PUSH_FOLD_PROFILE:
        return None
    out_values = (ctypes.c_double * 3)()
    out_codes = (ctypes.c_uint8 * 2)()
    result = int(
        _LIB.mahjong_core_push_fold_profile(
            int(shanten_value),
            float(risk),
            float(safety_score),
            float(hand_value_ev),
            float(estimated_han),
            float(wait_quality),
            float(progress),
            float(max_threat),
            float(max_push_pressure),
            int(max_loss),
            int(riichi_count),
            int(critical_count),
            int(high_count),
            float(defense_scale),
            float(strategy_scale),
            float(attack_bias),
            float(defense_bias),
            float(value_bias),
            1 if is_dealer else 0,
            int(placement),
            int(placement_count),
            1 if is_all_last else 0,
            out_values,
            out_codes,
            3,
            2,
        )
    )
    if result == -999:
        return None
    return {
        "push_fold_ev": float(out_values[0]),
        "pressure_score": float(out_values[1]),
        "commitment_score": float(out_values[2]),
        "mode_code": int(out_codes[0]),
        "label_code": int(out_codes[1]),
    }


def defense_override_profile(
    *,
    shanten_value: int,
    risk: float,
    safety_score: float,
    hand_value_ev: float,
    estimated_han: float,
    wait_quality: float,
    level: int,
    progress: float,
    max_threat: float,
    max_push_pressure: float,
    max_loss: int,
    riichi_count: int,
    critical_count: int,
    high_count: int,
    open_monster_count: int,
    attack_bias: float,
    defense_bias: float,
    value_bias: float,
    placement: int,
    placement_count: int,
    is_all_last: bool,
) -> dict[str, float | int] | None:
    if _LIB is None or not _HAS_DEFENSE_OVERRIDE_PROFILE:
        return None
    out_values = (ctypes.c_double * 2)()
    out_codes = (ctypes.c_uint8 * 2)()
    result = int(
        _LIB.mahjong_core_defense_override_profile(
            int(shanten_value),
            float(risk),
            float(safety_score),
            float(hand_value_ev),
            float(estimated_han),
            float(wait_quality),
            int(level),
            float(progress),
            float(max_threat),
            float(max_push_pressure),
            int(max_loss),
            int(riichi_count),
            int(critical_count),
            int(high_count),
            int(open_monster_count),
            float(attack_bias),
            float(defense_bias),
            float(value_bias),
            int(placement),
            int(placement_count),
            1 if is_all_last else 0,
            out_values,
            out_codes,
            2,
            2,
        )
    )
    if result == -999:
        return None
    return {
        "defense_override_ev": float(out_values[0]),
        "fold_need": float(out_values[1]),
        "mode_code": int(out_codes[0]),
        "label_code": int(out_codes[1]),
    }


def deal_in_loss_profile(
    *,
    dangers: list[float],
    safeties: list[float],
    push_pressures: list[float],
    estimated_losses: list[int],
    threat_level_codes: list[int],
    threat_type_codes: list[int],
    progress: float,
) -> dict[str, float | int] | None:
    if _LIB is None or not _HAS_DEAL_IN_LOSS_PROFILE:
        return None
    item_len = len(dangers)
    if not (
        len(safeties)
        == len(push_pressures)
        == len(estimated_losses)
        == len(threat_level_codes)
        == len(threat_type_codes)
        == item_len
    ):
        return None
    if item_len == 0:
        return {
            "deal_in_loss_ev": 0.0,
            "deal_in_rate": 0.0,
            "deal_in_points": 0,
            "top_index": -1,
        }
    danger_array = _double_array(dangers)
    safety_array = _double_array(safeties)
    push_array = _double_array(push_pressures)
    loss_array = _int32_array(estimated_losses)
    level_array = _u8_array(threat_level_codes, item_len)
    type_array = _u8_array(threat_type_codes, item_len)
    out_values = (ctypes.c_double * 3)()
    out_top_index = ctypes.c_int32(-1)
    result = int(
        _LIB.mahjong_core_deal_in_loss_profile(
            danger_array,
            safety_array,
            push_array,
            loss_array,
            level_array,
            type_array,
            item_len,
            float(progress),
            out_values,
            ctypes.byref(out_top_index),
            3,
        )
    )
    if result == -999:
        return None
    return {
        "deal_in_loss_ev": float(out_values[0]),
        "deal_in_rate": float(out_values[1]),
        "deal_in_points": int(round(float(out_values[2]))),
        "top_index": int(out_top_index.value),
    }


def defensive_discard_profile(
    *,
    safety_score: float,
    shanten_value: int,
    level_scale: float,
    progress: float,
    max_threat: float,
    max_push_pressure: float,
    max_loss: int,
    high_threat_count: int,
) -> dict[str, float | bool] | None:
    if _LIB is None or not _HAS_DEFENSIVE_DISCARD_PROFILE:
        return None
    out_values = (ctypes.c_double * 2)()
    out_mode = ctypes.c_uint8(0)
    result = int(
        _LIB.mahjong_core_defensive_discard_profile(
            float(safety_score),
            int(shanten_value),
            float(level_scale),
            float(progress),
            float(max_threat),
            float(max_push_pressure),
            int(max_loss),
            int(high_threat_count),
            out_values,
            ctypes.byref(out_mode),
            2,
        )
    )
    if result == -999:
        return None
    return {
        "safety_score": float(out_values[0]),
        "safety_ev": float(out_values[1]),
        "defense_mode": bool(out_mode.value),
    }


def global_reward_delta_profile(
    *,
    points: list[int],
    seat: int,
    shanten_value: int,
    ukeire: int,
    wait_quality: float,
    estimated_value: int,
    estimated_han: float,
    deal_in_rate: float,
    deal_in_points: int,
    level: int,
    progress: float,
    riichi_sticks: int,
    honba: int,
    placement: int,
    placement_count: int,
    is_all_last: bool,
) -> dict[str, float | int] | None:
    if _LIB is None or not _HAS_GLOBAL_REWARD_PROFILE:
        return None
    if not points or len(points) > 4 or seat < 0 or seat >= len(points):
        return None
    points_array = _int32_array(points)
    out_values = (ctypes.c_double * 1)()
    out_rank_deltas = (ctypes.c_int32 * 2)()
    result = int(
        _LIB.mahjong_core_global_reward_delta_profile(
            points_array,
            len(points),
            int(seat),
            int(shanten_value),
            int(ukeire),
            float(wait_quality),
            int(estimated_value),
            float(estimated_han),
            float(deal_in_rate),
            int(deal_in_points),
            int(level),
            float(progress),
            int(riichi_sticks),
            int(honba),
            int(placement),
            int(placement_count),
            1 if is_all_last else 0,
            out_values,
            out_rank_deltas,
            1,
            2,
        )
    )
    if result == -999:
        return None
    return {
        "global_reward_ev": float(out_values[0]),
        "win_rank_delta": int(out_rank_deltas[0]),
        "loss_rank_delta": int(out_rank_deltas[1]),
    }


def alpha_terminal_projection_ev(
    *,
    shanten_value: int,
    ukeire: int,
    route_bonus: float,
    hand_value_ev: float,
    attack_bias: float,
    defense_bias: float,
    value_bias: float,
    max_threat: float,
    max_push_pressure: float,
    max_loss: int,
    wait_quality: float,
    level: int,
) -> float | None:
    if _LIB is None or not _HAS_ALPHA_TERMINAL_EV:
        return None
    out_value = ctypes.c_double(0.0)
    result = int(
        _LIB.mahjong_core_alpha_terminal_projection_ev(
            int(shanten_value),
            int(ukeire),
            float(route_bonus),
            float(hand_value_ev),
            float(attack_bias),
            float(defense_bias),
            float(value_bias),
            float(max_threat),
            float(max_push_pressure),
            int(max_loss),
            float(wait_quality),
            int(level),
            ctypes.byref(out_value),
        )
    )
    if result == -999:
        return None
    return float(out_value.value)


def tile_danger_for_opponent(
    visible_counts: list[int],
    opponent_discard_types: set[int] | list[int],
    value_honor_types: set[int] | list[int],
    dora_types: set[int] | list[int],
    red_tile_ids: set[int] | frozenset[int] | list[int],
    *,
    threat: float,
    estimated_loss: int,
    progress: float,
    threat_type: int,
    threat_level: int,
    flush_suit: int | None,
    flush_with_honors: bool,
    toitoi: bool,
    tanyao_route: bool,
    yakuhai_route: bool,
    riichi: bool,
    open_meld_count: int,
) -> list[float] | None:
    if _LIB is None or not _HAS_TILE_DANGER:
        return None

    opponent_discard_mask = [0] * 34
    for tile_index in opponent_discard_types:
        index = int(tile_index)
        if 0 <= index < 34:
            opponent_discard_mask[index] = 1

    value_honor_mask = [0] * 34
    for tile_index in value_honor_types:
        index = int(tile_index)
        if 0 <= index < 34:
            value_honor_mask[index] = 1

    dora_mask = [0] * 34
    for tile_index in dora_types:
        index = int(tile_index)
        if 0 <= index < 34:
            dora_mask[index] = 1

    red_tile_mask = [0] * 136
    for tile_id in red_tile_ids:
        index = int(tile_id)
        if 0 <= index < 136:
            red_tile_mask[index] = 1

    try:
        visible_array = _u8_34_array(visible_counts)
        opponent_discard_array = _u8_34_array(opponent_discard_mask)
        value_honor_array = _u8_34_array(value_honor_mask)
        dora_array = _u8_34_array(dora_mask)
        red_tile_array = _u8_mask_array(red_tile_mask, 136)
    except ValueError:
        return None

    out_danger = (ctypes.c_double * 136)()
    result = int(
        _LIB.mahjong_core_tile_danger_for_opponent(
            visible_array,
            34,
            opponent_discard_array,
            34,
            value_honor_array,
            34,
            dora_array,
            34,
            red_tile_array,
            136,
            float(threat),
            int(estimated_loss),
            float(progress),
            int(threat_type),
            int(threat_level),
            -1 if flush_suit is None else int(flush_suit),
            1 if flush_with_honors else 0,
            1 if toitoi else 0,
            1 if tanyao_route else 0,
            1 if yakuhai_route else 0,
            1 if riichi else 0,
            int(open_meld_count),
            out_danger,
            136,
        )
    )
    if result == -999:
        return None
    return [float(out_danger[index]) for index in range(136)]


def aggregate_safety_scores(
    visible_counts: list[int],
    opponent_discard_types: list[set[int] | list[int]],
    value_honor_types: list[set[int] | list[int]],
    weights: list[float],
    tanyao_routes: list[bool],
) -> list[float] | None:
    if _LIB is None or not _HAS_AGGREGATE_SAFETY:
        return None
    opponent_count = len(opponent_discard_types)
    if (
        opponent_count == 0
        or len(value_honor_types) != opponent_count
        or len(weights) != opponent_count
        or len(tanyao_routes) != opponent_count
    ):
        return None

    discard_rows: list[int] = []
    value_rows: list[int] = []
    for discard_types, honor_types in zip(opponent_discard_types, value_honor_types):
        discard_mask = [0] * 34
        for tile_index in discard_types:
            index = int(tile_index)
            if 0 <= index < 34:
                discard_mask[index] = 1
        value_mask = [0] * 34
        for tile_index in honor_types:
            index = int(tile_index)
            if 0 <= index < 34:
                value_mask[index] = 1
        discard_rows.extend(discard_mask)
        value_rows.extend(value_mask)

    try:
        visible_array = _u8_34_array(visible_counts)
        discard_array = _u8_mask_array(discard_rows, opponent_count * 34)
        value_array = _u8_mask_array(value_rows, opponent_count * 34)
        weight_array = _double_array(weights)
        tanyao_array = _u8_mask_array([1 if value else 0 for value in tanyao_routes], opponent_count)
    except ValueError:
        return None

    out_scores = (ctypes.c_double * 34)()
    result = int(
        _LIB.mahjong_core_aggregate_safety_scores(
            visible_array,
            34,
            discard_array,
            opponent_count * 34,
            value_array,
            opponent_count * 34,
            weight_array,
            opponent_count,
            tanyao_array,
            opponent_count,
            opponent_count,
            out_scores,
            34,
        )
    )
    if result == -999:
        return None
    return [float(out_scores[index]) for index in range(34)]


def safe_tile_reserve_profile(
    mode: str,
    remaining_tiles: list[int],
    discarded_tile_id: int,
    shanten_value: int,
    progress: float,
    max_pressure: float,
    aggregate_scores: list[float],
) -> tuple[float, float, int] | None:
    if _LIB is None or not _HAS_SAFE_RESERVE:
        return None
    if len(aggregate_scores) != 34:
        return None
    mode_value = 3 if mode == "3P" else 4
    tile_array = _int32_array(remaining_tiles)
    score_array = _double_array(aggregate_scores)
    out_ev = ctypes.c_double(0.0)
    out_score = ctypes.c_double(0.0)
    out_label_code = ctypes.c_uint8(0)
    result = int(
        _LIB.mahjong_core_safe_tile_reserve_profile(
            mode_value,
            tile_array,
            len(remaining_tiles),
            int(discarded_tile_id),
            int(shanten_value),
            float(progress),
            float(max_pressure),
            score_array,
            34,
            ctypes.byref(out_ev),
            ctypes.byref(out_score),
            ctypes.byref(out_label_code),
        )
    )
    if result == -999:
        return None
    return float(out_ev.value), float(out_score.value), int(out_label_code.value)


def safe_tile_reserve_profiles_after_discards(
    mode: str,
    source_tiles: list[int],
    shanten_by_discard: list[int],
    progress: float,
    max_pressure: float,
    aggregate_scores: list[float],
) -> dict[int, tuple[float, float, int]] | None:
    if _LIB is None or not _HAS_SAFE_RESERVE_BATCH:
        return None
    if len(shanten_by_discard) != 34 or len(aggregate_scores) != 34:
        return None
    tile_array = _int32_array(source_tiles)
    shanten_array = _int32_array(shanten_by_discard)
    score_array = _double_array(aggregate_scores)
    out_ev = (ctypes.c_double * 34)()
    out_score = (ctypes.c_double * 34)()
    out_label = (ctypes.c_uint8 * 34)()
    result = int(
        _LIB.mahjong_core_safe_tile_reserve_profiles_after_discards(
            3 if mode == "3P" else 4,
            tile_array,
            len(source_tiles),
            shanten_array,
            34,
            float(progress),
            float(max_pressure),
            score_array,
            34,
            out_ev,
            out_score,
            out_label,
            34,
        )
    )
    if result == -999:
        return None
    profiles: dict[int, tuple[float, float, int]] = {}
    for tile_index in range(34):
        if int(out_label[tile_index]) != 0:
            profiles[tile_index] = (
                float(out_ev[tile_index]),
                float(out_score[tile_index]),
                int(out_label[tile_index]),
            )
    return profiles
