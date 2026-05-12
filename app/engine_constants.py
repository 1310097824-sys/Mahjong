"""麻将规则和 AI 参数常量。

这个文件集中维护不随牌局动态改变的配置：三麻/四麻起点、规则档位、赤宝牌、
AI 难度权重、动作优先级、流局文案等。规则模块只读取这些常量，避免魔法数字
散落在引擎各处。
"""

from __future__ import annotations

from mahjong.constants import CHUN, EAST, HAKU, HATSU, NORTH, SOUTH, WEST

from app.config import settings

HONOR_LABELS = {
    27: "E",
    28: "S",
    29: "W",
    30: "N",
    31: "Wh",
    32: "G",
    33: "R",
}

WIND_CONSTANTS = {"E": EAST, "S": SOUTH, "W": WEST, "N": NORTH}

MODE_POINTS = {"4P": settings.default_4p_points, "3P": settings.default_3p_points}

TARGET_POINTS = {"4P": 30000, "3P": 40000}

RANKED_UMA_UNITS = {"4P": [15.0, 5.0, -5.0, -15.0], "3P": [15.0, 0.0, -15.0]}

NOTEN_PAYMENTS = {"4P": 3000, "3P": 2000}

SANMA_SCORING_MODES = {"TSUMO_LOSS", "NORTH_BISECTION"}

MINIMUM_HAN_OPTIONS = {1, 2, 4}

RULE_PROFILES = {"RANKED", "FRIEND", "KOYAKU"}

AKA_DORA_COUNTS_BY_MODE = {"4P": {0, 3, 4}, "3P": {0, 2}}

DEFAULT_AKA_DORA_COUNTS = {"4P": 3, "3P": 2}

AKA_DORA_IDS_BY_MODE_COUNT = {
    "4P": {
        0: set(),
        3: {16, 52, 88},
        4: {16, 52, 53, 88},
    },
    "3P": {
        0: set(),
        2: {52, 88},
    },
}

ACTIVE_AKA_DORA_IDS_BY_MODE_COUNT = {
    mode: {count: frozenset(tile_ids) for count, tile_ids in count_map.items()}
    for mode, count_map in AKA_DORA_IDS_BY_MODE_COUNT.items()
}

ACTION_PRIORITY = {"ron": 3, "open_kan": 2, "pon": 2, "chi": 1}

OPEN_MELD_TYPES = {"chi", "pon", "open_kan", "added_kan"}

SANMA_REMOVED_MANZU_TYPES = set(range(1, 8))

AI_LEVEL_POLICIES = {
    1: {
        "risk_scale": 0.48,
        "defense_scale": 0.32,
        "strategy_scale": 0.25,
        "mistake_rate": 0.28,
        "mistake_pool": 3,
        "call_threshold_shift": 10.0,
        "riichi_threshold_shift": 8.0,
        "open_kan": False,
        "closed_kan": False,
    },
    2: {
        "risk_scale": 0.82,
        "defense_scale": 0.72,
        "strategy_scale": 0.65,
        "mistake_rate": 0.08,
        "mistake_pool": 2,
        "call_threshold_shift": 3.0,
        "riichi_threshold_shift": 2.0,
        "open_kan": False,
        "closed_kan": False,
    },
    3: {
        "risk_scale": 1.0,
        "defense_scale": 1.0,
        "strategy_scale": 1.0,
        "mistake_rate": 0.0,
        "mistake_pool": 1,
        "call_threshold_shift": 0.0,
        "riichi_threshold_shift": 0.0,
        "open_kan": True,
        "closed_kan": True,
    },
}

ALPHA_SEARCH_DEPTH = 2

ALPHA_SEARCH_DRAW_BEAM = 3

ALPHA_SEARCH_DISCARD_BEAM = 2

ALPHA_SEARCH_DISCOUNT = 0.24

ALPHA_SEARCH_WEIGHT = 0.22

ALPHA_ACTION_SEARCH_DEPTH = 1

ALPHA_ACTION_SEARCH_WEIGHT = 0.18

ALPHA_RIICHI_SEARCH_WEIGHT = 0.2

ABORTIVE_DRAW_HEADLINES = {
    "KYUUSHU_KYUUHAI": "九种九牌流局",
    "SUUFON_RENDA": "四风连打",
    "SUUCHA_RIICHI": "四家立直",
    "SUUKAIKAN": "四杠散了",
    "SANCHAHOU": "三家和",
}

KAN_DETAIL_LABELS = {"open_kan": "明杠", "closed_kan": "暗杠", "added_kan": "加杠"}

HEAD_BUMP_ENABLED = False

DRAGON_TYPES = {31, 32, 33}

WIND_TILE_TYPES = {27, 28, 29, 30}

TRIPLET_MELD_TYPES = {"pon", "open_kan", "added_kan", "closed_kan"}

RUST_ROUTE_LABELS = [
    (1 << 0, "断幺"),
    (1 << 1, "役牌"),
    (1 << 2, "清一色"),
    (1 << 3, "混一色"),
    (1 << 4, "七对子"),
    (1 << 5, "对对和"),
]

RUST_THREAT_TYPE_CODES = {"riichi": 1, "flush": 2, "yakuhai": 3, "fast_open": 4, "toitoi": 5}

RUST_THREAT_LEVEL_CODES = {"medium": 1, "high": 2, "critical": 3}

RUST_SAFE_RESERVE_LABELS = {
    1: "保留了安全牌储备",
    2: "切掉安全牌后储备不足",
    3: "安全牌储备偏少",
    4: "安全牌储备可接受",
}

RUST_PUSH_FOLD_MODES = {1: "push", 2: "lean_push", 3: "balanced", 4: "fold"}

RUST_PUSH_FOLD_LABELS = {
    1: "胜负手全押",
    2: "优势推进",
    3: "边界半押",
    4: "优先撤退",
    5: "弃和守备",
}

RUST_DEFENSE_OVERRIDE_MODES = {0: "", 1: "soft_fold", 2: "hard_fold", 3: "push_guard"}

RUST_DEFENSE_OVERRIDE_LABELS = {
    0: "",
    1: "谨慎押退",
    2: "强制弃和",
    3: "一向听撤退",
    4: "听牌谨慎押",
}

__all__ = [
    "HONOR_LABELS",
    "WIND_CONSTANTS",
    "MODE_POINTS",
    "TARGET_POINTS",
    "RANKED_UMA_UNITS",
    "NOTEN_PAYMENTS",
    "SANMA_SCORING_MODES",
    "MINIMUM_HAN_OPTIONS",
    "RULE_PROFILES",
    "AKA_DORA_COUNTS_BY_MODE",
    "DEFAULT_AKA_DORA_COUNTS",
    "AKA_DORA_IDS_BY_MODE_COUNT",
    "ACTIVE_AKA_DORA_IDS_BY_MODE_COUNT",
    "ACTION_PRIORITY",
    "OPEN_MELD_TYPES",
    "SANMA_REMOVED_MANZU_TYPES",
    "AI_LEVEL_POLICIES",
    "ALPHA_SEARCH_DEPTH",
    "ALPHA_SEARCH_DRAW_BEAM",
    "ALPHA_SEARCH_DISCARD_BEAM",
    "ALPHA_SEARCH_DISCOUNT",
    "ALPHA_SEARCH_WEIGHT",
    "ALPHA_ACTION_SEARCH_DEPTH",
    "ALPHA_ACTION_SEARCH_WEIGHT",
    "ALPHA_RIICHI_SEARCH_WEIGHT",
    "ABORTIVE_DRAW_HEADLINES",
    "KAN_DETAIL_LABELS",
    "HEAD_BUMP_ENABLED",
    "DRAGON_TYPES",
    "WIND_TILE_TYPES",
    "TRIPLET_MELD_TYPES",
    "RUST_ROUTE_LABELS",
    "RUST_THREAT_TYPE_CODES",
    "RUST_THREAT_LEVEL_CODES",
    "RUST_SAFE_RESERVE_LABELS",
    "RUST_PUSH_FOLD_MODES",
    "RUST_PUSH_FOLD_LABELS",
    "RUST_DEFENSE_OVERRIDE_MODES",
    "RUST_DEFENSE_OVERRIDE_LABELS",
]
