"""牌型结构与等待判断。

这里关注“牌能不能组成合法形”和“听哪些牌”，不直接处理分数结算。标准形、
七对子、国士无双、三麻去万子后的有效牌过滤等形状判断集中在这里，供和牌判断、
AI 进张评估和规则审计复用。
"""

from __future__ import annotations

from typing import Any

from app import rust_core
from app.engine_tiles import (
    is_honor,
    is_terminal,
    legal_tile_types_for_mode,
    representative_tile_id,
    tile_type,
)


def layout_meld_count(melds_data: list[dict[str, Any]]) -> int:
    return sum(1 for meld in melds_data if meld.get("type") != "kita")


def tile_type_counts_34(tiles: list[int]) -> list[int]:
    counts = [0] * 34
    for tile_id in tiles:
        counts[tile_type(tile_id)] += 1
    return counts


def can_form_standard_sets(counts: list[int], needed_sets: int) -> bool:
    memo: dict[tuple[tuple[int, ...], int], bool] = {}

    def search(state: tuple[int, ...], remaining_sets: int) -> bool:
        key = (state, remaining_sets)
        if key in memo:
            return memo[key]
        if remaining_sets == 0:
            memo[key] = all(count == 0 for count in state)
            return memo[key]

        first = next((index for index, count in enumerate(state) if count > 0), None)
        if first is None:
            memo[key] = remaining_sets == 0
            return memo[key]

        if state[first] >= 3:
            next_counts = list(state)
            next_counts[first] -= 3
            if search(tuple(next_counts), remaining_sets - 1):
                memo[key] = True
                return True

        if first < 27 and first % 9 <= 6 and state[first + 1] > 0 and state[first + 2] > 0:
            next_counts = list(state)
            next_counts[first] -= 1
            next_counts[first + 1] -= 1
            next_counts[first + 2] -= 1
            if search(tuple(next_counts), remaining_sets - 1):
                memo[key] = True
                return True

        memo[key] = False
        return False

    return search(tuple(counts), needed_sets)


def is_standard_complete_with_melds(concealed_tiles: list[int], melds_data: list[dict[str, Any]]) -> bool:
    meld_count = layout_meld_count(melds_data)
    needed_sets = 4 - meld_count
    if needed_sets < 0:
        return False
    if len(concealed_tiles) != needed_sets * 3 + 2:
        return False

    counts = tile_type_counts_34(concealed_tiles)
    for pair_index, count in enumerate(counts):
        if count < 2:
            continue
        counts[pair_index] -= 2
        if can_form_standard_sets(counts, needed_sets):
            counts[pair_index] += 2
            return True
        counts[pair_index] += 2
    return False


def is_chiitoitsu_complete(concealed_tiles: list[int], melds_data: list[dict[str, Any]]) -> bool:
    if layout_meld_count(melds_data) != 0 or len(concealed_tiles) != 14:
        return False
    counts = tile_type_counts_34(concealed_tiles)
    return sum(1 for count in counts if count == 2) == 7


def is_kokushi_complete(concealed_tiles: list[int], melds_data: list[dict[str, Any]], *, mode: str) -> bool:
    if layout_meld_count(melds_data) != 0 or len(concealed_tiles) != 14:
        return False
    required = {0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33}
    counts = tile_type_counts_34(concealed_tiles)
    return all(counts[index] > 0 for index in required) and any(counts[index] >= 2 for index in required)


def is_complete_hand_shape(
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]] | None = None,
    *,
    mode: str = "4P",
) -> bool:
    melds = melds_data or []
    rust_result = rust_core.is_complete_hand_shape(mode, tile_type_counts_34(concealed_tiles), layout_meld_count(melds))
    if rust_result is not None:
        return rust_result
    return (
        is_standard_complete_with_melds(concealed_tiles, melds)
        or is_chiitoitsu_complete(concealed_tiles, melds)
        or is_kokushi_complete(concealed_tiles, melds, mode=mode)
    )


def tenpai_wait_tile_types(
    concealed_tiles: list[int],
    *,
    mode: str = "4P",
    melds_data: list[dict[str, Any]] | None = None,
) -> set[int]:
    melds = melds_data or []
    owned_counts = tile_type_counts_34(concealed_tiles)
    for meld in melds:
        if meld.get("type") == "kita":
            continue
        for tile_id in meld.get("tiles", []):
            owned_counts[tile_type(tile_id)] += 1

    concealed_counts = tile_type_counts_34(concealed_tiles)
    rust_waits = rust_core.tenpai_waits_from_counts(mode, concealed_counts, owned_counts, layout_meld_count(melds))
    if rust_waits is not None:
        return rust_waits

    waits: set[int] = set()
    for tile_index in legal_tile_types_for_mode(mode):
        if owned_counts[tile_index] >= 4:
            continue
        if is_complete_hand_shape(concealed_tiles + [representative_tile_id(tile_index, concealed_tiles)], melds, mode=mode):
            waits.add(tile_index)
    return waits


def calculate_tenpai_seats(game: dict[str, Any]) -> list[int]:
    round_state = game["round_state"]
    tenpai: list[int] = []
    for seat in range(round_state["player_count"]):
        if tenpai_wait_tile_types(round_state["hands"][seat], mode=game["mode"], melds_data=round_state["melds"][seat]):
            tenpai.append(seat)
    return tenpai


def unique_terminal_honor_types(tiles: list[int]) -> set[int]:
    rust_types = rust_core.unique_terminal_honor_types(tiles)
    if rust_types is not None:
        return rust_types
    return {
        tile_type(tile_id)
        for tile_id in tiles
        if is_honor(tile_type(tile_id)) or is_terminal(tile_type(tile_id))
    }


__all__ = [
    "layout_meld_count",
    "tile_type_counts_34",
    "can_form_standard_sets",
    "is_standard_complete_with_melds",
    "is_chiitoitsu_complete",
    "is_kokushi_complete",
    "is_complete_hand_shape",
    "tenpai_wait_tile_types",
    "calculate_tenpai_seats",
    "unique_terminal_honor_types",
]
