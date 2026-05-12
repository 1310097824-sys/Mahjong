"""麻将牌表示、排序和基础转换工具。

系统内部以 0-135 的牌 ID 表示实体牌，以 0-33 的 tile type 表示牌种。
这个模块负责二者转换、三麻合法牌种、赤宝牌、宝牌翻译、向听数入口和牌山生成。
能走 Rust 的纯计算会优先走 Rust，保持性能；失败时仍有 Python 兜底。
"""

from __future__ import annotations

import random
from typing import Any

from mahjong.shanten import Shanten
from mahjong.tile import TilesConverter

from app import rust_core
from app.engine_constants import (
    ACTIVE_AKA_DORA_IDS_BY_MODE_COUNT,
    AKA_DORA_COUNTS_BY_MODE,
    DEFAULT_AKA_DORA_COUNTS,
    HONOR_LABELS,
    SANMA_REMOVED_MANZU_TYPES,
)

shanten_calculator = Shanten()

def tile_type(tile_id: int) -> int:
    rust_value = rust_core.tile_type(tile_id)
    if rust_value is not None:
        return rust_value
    return tile_id // 4

def default_aka_dora_count(mode: str) -> int:
    rust_value = rust_core.default_aka_dora_count(mode)
    if rust_value is not None:
        return rust_value
    return DEFAULT_AKA_DORA_COUNTS.get(mode, 3)

def normalize_aka_dora_count(mode: str, profile: str, value: Any) -> int:
    rust_value = rust_core.normalize_aka_dora_count(mode, profile, value)
    if rust_value is not None:
        return rust_value
    default = default_aka_dora_count(mode)
    if profile == "RANKED":
        return default
    try:
        count = int(value)
    except (TypeError, ValueError):
        return default
    return count if count in AKA_DORA_COUNTS_BY_MODE.get(mode, {default}) else default

def active_aka_dora_ids(game: dict[str, Any]) -> frozenset[int]:
    mode = game.get("mode", "4P")
    default = default_aka_dora_count(mode)
    try:
        count = int(game.get("aka_dora_count", default))
    except (TypeError, ValueError):
        count = default
    rust_ids = rust_core.active_aka_dora_ids(mode, count)
    if rust_ids is not None:
        return rust_ids
    active_ids = ACTIVE_AKA_DORA_IDS_BY_MODE_COUNT.get(mode, {}).get(
        count,
        ACTIVE_AKA_DORA_IDS_BY_MODE_COUNT.get(mode, {}).get(default, frozenset()),
    )
    return active_ids

def is_red(tile_id: int, game: dict[str, Any] | None = None) -> bool:
    if game is None:
        rust_value = rust_core.is_red_tile("4P", default_aka_dora_count("4P"), tile_id)
        if rust_value is not None:
            return rust_value
        return tile_id in {16, 52, 88}
    mode = game.get("mode", "4P")
    default = default_aka_dora_count(mode)
    try:
        count = int(game.get("aka_dora_count", default))
    except (TypeError, ValueError):
        count = default
    rust_value = rust_core.is_red_tile(mode, count, tile_id)
    if rust_value is not None:
        return rust_value
    return tile_id in active_aka_dora_ids(game)

def tile_sort_key(tile_id: int, game: dict[str, Any] | None = None) -> tuple[int, int]:
    return tile_type(tile_id), 0 if is_red(tile_id, game) else 1, tile_id

def sort_tiles(tiles: list[int], game: dict[str, Any] | None = None) -> list[int]:
    return sorted(tiles, key=lambda tile_id: tile_sort_key(tile_id, game))

def tile_label(tile_id: int, game: dict[str, Any] | None = None) -> str:
    t = tile_type(tile_id)
    if t >= 27:
        return HONOR_LABELS[t]
    suit_index = t // 9
    rank = t % 9 + 1
    suit = "mps"[suit_index]
    if is_red(tile_id, game):
        return f"0{suit}"
    return f"{rank}{suit}"

def tile_type_label(tile_index: int) -> str:
    if tile_index >= 27:
        return HONOR_LABELS[tile_index]
    suit = "mps"[tile_index // 9]
    rank = tile_index % 9 + 1
    return f"{rank}{suit}"

def representative_tile_id(tile_index: int, hand_tiles: list[int] | None = None) -> int:
    rust_value = rust_core.representative_tile_id(tile_index, hand_tiles)
    if rust_value is not None:
        return rust_value
    blocked = set(hand_tiles or [])
    candidate_ids = list(range(tile_index * 4, tile_index * 4 + 4))
    if tile_index in {4, 13, 22}:
        candidate_ids = candidate_ids[1:] + candidate_ids[:1]
    for tile_id in candidate_ids:
        if tile_id not in blocked:
            return tile_id
    return candidate_ids[0]

def is_honor(tile_index: int) -> bool:
    rust_flags = rust_core.tile_flags(tile_index)
    if rust_flags is not None:
        return bool(rust_flags & 0b001)
    return tile_index >= 27

def is_terminal(tile_index: int) -> bool:
    rust_flags = rust_core.tile_flags(tile_index)
    if rust_flags is not None:
        return bool(rust_flags & 0b010)
    return tile_index < 27 and tile_index % 9 in {0, 8}

def is_simple(tile_index: int) -> bool:
    rust_flags = rust_core.tile_flags(tile_index)
    if rust_flags is not None:
        return bool(rust_flags & 0b100)
    return tile_index < 27 and tile_index % 9 not in {0, 8}

def is_tile_type_legal_in_mode(tile_index: int, mode: str) -> bool:
    if 0 <= tile_index < 34:
        rust_value = rust_core.is_legal_tile_type(mode, tile_index)
        if rust_value is not None:
            return rust_value
    return mode != "3P" or tile_index not in SANMA_REMOVED_MANZU_TYPES

def legal_tile_types_for_mode(mode: str) -> list[int]:
    rust_types = rust_core.legal_tile_types(mode)
    if rust_types is not None:
        return rust_types
    return [tile_index for tile_index in range(34) if is_tile_type_legal_in_mode(tile_index, mode)]

def dora_from_indicator(indicator_tile_id: int, *, mode: str = "4P") -> int:
    rust_value = rust_core.dora_from_indicator(indicator_tile_id, mode=mode)
    if rust_value is not None:
        return rust_value
    indicator = tile_type(indicator_tile_id)
    if indicator < 27:
        if mode == "3P" and indicator == 0:
            return 8
        suit_base = (indicator // 9) * 9
        rank = indicator % 9
        return suit_base + ((rank + 1) % 9)
    if indicator <= 30:
        winds = [27, 28, 29, 30]
        return winds[(winds.index(indicator) + 1) % len(winds)]
    dragons = [31, 32, 33]
    return dragons[(dragons.index(indicator) + 1) % len(dragons)]

def scoring_indicator_tile_id(indicator_tile_id: int, *, mode: str) -> int:
    rust_value = rust_core.scoring_indicator_tile_id(indicator_tile_id, mode=mode)
    if rust_value is not None:
        return rust_value
    if mode != "3P":
        return indicator_tile_id
    if tile_type(indicator_tile_id) != 0:
        return indicator_tile_id
    # 三麻移除 2-8 万后，1 万指示牌应指向 9 万。
    # mahjong 库按四麻顺序计算，因此传入虚拟 8 万指示牌来得到 9 万宝牌。
    return 7 * 4 + (indicator_tile_id % 4)

def build_wall(mode: str, rng: random.Random) -> list[int]:
    tiles = list(range(136))
    if mode == "3P":
        removed = set()
        for tile_index in SANMA_REMOVED_MANZU_TYPES:
            removed.update(range(tile_index * 4, tile_index * 4 + 4))
        tiles = [tile for tile in tiles if tile not in removed]
    rng.shuffle(tiles)
    return tiles

def to_34_array(tiles: list[int]) -> list[int]:
    rust_counts = rust_core.to_34_array(tiles)
    if rust_counts is not None:
        return rust_counts
    return TilesConverter.to_34_array(tiles)

def calculate_shanten_from_counts(counts: list[int]) -> int:
    rust_value = rust_core.shanten_from_counts(counts)
    if rust_value is not None:
        return rust_value
    return shanten_calculator.calculate_shanten(counts)

def calculate_shanten_for_tiles(tiles: list[int]) -> int:
    rust_value = rust_core.shanten_of_tiles(tiles)
    if rust_value is not None:
        return rust_value
    return shanten_calculator.calculate_shanten(TilesConverter.to_34_array(tiles))

def counts_by_type(tiles: list[int]) -> dict[int, list[int]]:
    grouped: dict[int, list[int]] = {}
    for tile in sort_tiles(tiles):
        grouped.setdefault(tile_type(tile), []).append(tile)
    return grouped

def pop_specific_tiles(hand: list[int], tile_ids: list[int]) -> None:
    for tile_id in tile_ids:
        hand.remove(tile_id)

__all__ = [
    "tile_type",
    "default_aka_dora_count",
    "normalize_aka_dora_count",
    "active_aka_dora_ids",
    "is_red",
    "tile_sort_key",
    "sort_tiles",
    "tile_label",
    "tile_type_label",
    "representative_tile_id",
    "is_honor",
    "is_terminal",
    "is_simple",
    "is_tile_type_legal_in_mode",
    "legal_tile_types_for_mode",
    "dora_from_indicator",
    "scoring_indicator_tile_id",
    "build_wall",
    "to_34_array",
    "calculate_shanten_from_counts",
    "calculate_shanten_for_tiles",
    "counts_by_type",
    "pop_specific_tiles",
]
