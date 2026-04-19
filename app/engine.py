from __future__ import annotations

import hashlib
import json
import random
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mahjong.constants import CHUN, EAST, HAKU, HATSU, NORTH, SOUTH, WEST
from mahjong.agari import Agari
from mahjong.hand_calculating.divider import HandDivider
from mahjong.hand_calculating.fu import FuCalculator
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules
from mahjong.hand_calculating.scores import ScoresCalculator
from mahjong.meld import Meld
from mahjong.shanten import Shanten
from mahjong.tile import TilesConverter

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
NOTEN_PAYMENTS = {"4P": 3000, "3P": 2000}
SANMA_SCORING_MODES = {"TSUMO_LOSS", "NORTH_BISECTION"}
RULE_PROFILES = {"RANKED", "FRIEND", "KOYAKU"}
ACTION_PRIORITY = {"ron": 3, "open_kan": 2, "pon": 2, "chi": 1}
OPEN_MELD_TYPES = {"chi", "pon", "open_kan", "added_kan"}
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


@dataclass(slots=True)
class ActionChoice:
    action_id: str
    type: str
    seat: int
    label: str
    tile_id: int | None = None
    consumed_ids: list[int] = field(default_factory=list)
    meld_index: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.action_id,
            "type": self.type,
            "seat": self.seat,
            "label": self.label,
            "tile_id": self.tile_id,
            "consumed_ids": list(self.consumed_ids),
            "meld_index": self.meld_index,
            "meta": deepcopy(self.meta),
        }


calculator = HandCalculator()
shanten_calculator = Shanten()
agari_calculator = Agari()


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def stable_seed(*parts: Any) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


def tile_type(tile_id: int) -> int:
    return tile_id // 4


def is_red(tile_id: int) -> bool:
    return tile_id in {16, 52, 88}


def tile_sort_key(tile_id: int) -> tuple[int, int]:
    return tile_type(tile_id), 0 if is_red(tile_id) else 1, tile_id


def sort_tiles(tiles: list[int]) -> list[int]:
    return sorted(tiles, key=tile_sort_key)


def tile_label(tile_id: int) -> str:
    t = tile_type(tile_id)
    if t >= 27:
        return HONOR_LABELS[t]
    suit_index = t // 9
    rank = t % 9 + 1
    suit = "mps"[suit_index]
    if is_red(tile_id):
        return f"0{suit}"
    return f"{rank}{suit}"


def tile_type_label(tile_index: int) -> str:
    if tile_index >= 27:
        return HONOR_LABELS[tile_index]
    suit = "mps"[tile_index // 9]
    rank = tile_index % 9 + 1
    return f"{rank}{suit}"


def is_honor(tile_index: int) -> bool:
    return tile_index >= 27


def is_terminal(tile_index: int) -> bool:
    return tile_index < 27 and tile_index % 9 in {0, 8}


def is_simple(tile_index: int) -> bool:
    return tile_index < 27 and tile_index % 9 not in {0, 8}


def dora_from_indicator(indicator_tile_id: int, *, mode: str = "4P") -> int:
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
    if mode != "3P":
        return indicator_tile_id
    if tile_type(indicator_tile_id) != 0:
        return indicator_tile_id
    return 28 + (indicator_tile_id % 4)


def scoring_dora_indicators(game: dict[str, Any], round_state: dict[str, Any], *, ura: bool = False) -> list[int]:
    indicators = current_ura_indicators(round_state) if ura else current_dora_indicators(round_state)
    return [scoring_indicator_tile_id(tile_id, mode=game["mode"]) for tile_id in indicators]


def build_wall(mode: str, rng: random.Random) -> list[int]:
    tiles = list(range(136))
    if mode == "3P":
        removed = set()
        for tile_index in range(1, 8):
            removed.update(range(tile_index * 4, tile_index * 4 + 4))
        tiles = [tile for tile in tiles if tile not in removed]
    rng.shuffle(tiles)
    return tiles


def to_34_array(tiles: list[int]) -> list[int]:
    return TilesConverter.to_34_array(tiles)


def counts_by_type(tiles: list[int]) -> dict[int, list[int]]:
    grouped: dict[int, list[int]] = {}
    for tile in sort_tiles(tiles):
        grouped.setdefault(tile_type(tile), []).append(tile)
    return grouped


def pop_specific_tiles(hand: list[int], tile_ids: list[int]) -> None:
    for tile_id in tile_ids:
        hand.remove(tile_id)


def player_count(mode: str) -> int:
    return 4 if mode == "4P" else 3


def next_seat(seat: int, count: int) -> int:
    return (seat + 1) % count


def seat_distance(origin: int, target: int, count: int) -> int:
    return (target - origin) % count


def round_target_count(mode: str, round_length: str) -> int:
    base = player_count(mode)
    return base if round_length == "EAST" else base * 2


def max_round_count(mode: str, round_length: str) -> int:
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


def build_rule_options(game: dict[str, Any]) -> OptionalRules:
    enable_koyaku = bool(game.get("koyaku_enabled", False))
    return OptionalRules(
        has_open_tanyao=True,
        has_aka_dora=True,
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
    return int(((int(value) + (0 if float(value).is_integer() else 1)) + 99) // 100 * 100)


def copy_public_tiles(tiles: list[int], reveal: bool) -> list[dict[str, Any]]:
    if not reveal:
        return [{"label": "##"} for _ in tiles]
    return [{"id": tile, "label": tile_label(tile), "red": is_red(tile)} for tile in sort_tiles(tiles)]


def clear_ippatsu(round_state: dict[str, Any]) -> None:
    round_state["ippatsu"] = [False] * round_state["player_count"]


def invalidate_pending_double_riichi(round_state: dict[str, Any]) -> None:
    pending = round_state.get("double_riichi_pending")
    if not isinstance(pending, list) or len(pending) != round_state["player_count"]:
        round_state["double_riichi_pending"] = [False] * round_state["player_count"]
        return
    for seat, active in enumerate(pending):
        if active:
            round_state["double_riichi"][seat] = False
            pending[seat] = False


def settle_pending_double_riichi(round_state: dict[str, Any], seat: int) -> None:
    pending = round_state.get("double_riichi_pending")
    if not isinstance(pending, list) or len(pending) != round_state["player_count"]:
        round_state["double_riichi_pending"] = [False] * round_state["player_count"]
        return
    pending[seat] = False


def is_furiten(round_state: dict[str, Any], seat: int, win_tile_type: int) -> bool:
    own_discards = {tile_type(item["tile"]) for item in round_state["discards"][seat]}
    return (
        win_tile_type in own_discards
        or round_state["temporary_furiten"][seat]
        or round_state["riichi_furiten"][seat]
    )


def is_kita_north_exception(round_state: dict[str, Any], discard: dict[str, Any] | None) -> bool:
    if discard is None:
        return False
    return discard.get("source") == "kita" and tile_type(discard["tile"]) == 30


def has_shape_win_on_last_discard(game: dict[str, Any], seat: int) -> bool:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    discard = round_state["last_discard"]
    if discard is None or discard["seat"] == seat:
        return False
    if discard.get("source") == "kan":
        return False
    if is_head_bump_blocked(game, seat):
        return False
    tiles = list(round_state["hands"][seat]) + [discard["tile"]]
    try:
        return agari_calculator.is_agari(to_34_array(tiles))
    except ValueError:
        return False


def apply_forced_furiten_for_current_discard(game: dict[str, Any], *, exclude_seat: int | None = None) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    discard = round_state["last_discard"]
    if discard is None:
        return
    if is_kita_north_exception(round_state, discard):
        return
    for seat in range(round_state["player_count"]):
        if seat == discard["seat"] or seat == exclude_seat:
            continue
        if any(action.type == "ron" for action in build_reaction_actions(game, seat)):
            continue
        if not has_shape_win_on_last_discard(game, seat):
            continue
        if round_state["riichi"][seat]:
            round_state["riichi_furiten"][seat] = True
        else:
            round_state["temporary_furiten"][seat] = True


def can_ron_on_last_discard(game: dict[str, Any], seat: int, *, ignore_passed: bool = False) -> tuple[bool, dict[str, Any] | None]:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    if not ignore_passed and round_state["reaction_passed"][seat]:
        return False, None
    discard = round_state["last_discard"]
    if discard is None or discard["seat"] == seat:
        return False, None
    discard_tile = discard["tile"]
    discard_type = tile_type(discard_tile)
    ron_result = evaluate_hand(game, seat, discard_tile, is_tsumo=False, kyoutaku_override=0)
    furiten_exempt = is_kita_north_exception(round_state, discard)
    if ron_result is None or (not furiten_exempt and is_furiten(round_state, seat, discard_type)):
        return False, ron_result
    if discard.get("source") == "kan" and discard.get("kan_type") == "closed_kan":
        return is_kokushi_result(ron_result), ron_result
    return True, ron_result


def is_head_bump_blocked(game: dict[str, Any], seat: int) -> bool:
    if not HEAD_BUMP_ENABLED:
        return False
    round_state = game["round_state"]
    discard = round_state["last_discard"]
    if discard is None:
        return False
    count = round_state["player_count"]
    for step in range(1, count):
        other = (discard["seat"] + step) % count
        if other == seat:
            return False
        can_ron, _ = can_ron_on_last_discard(game, other)
        if can_ron:
            return True
    return False


def extract_special_yakuman_han(yaku_items: list[Any]) -> tuple[dict[str, int], int]:
    yakuman_keys: dict[str, int] = {}
    total_han = 0
    for yaku in yaku_items:
        if not getattr(yaku, "is_yakuman", False):
            continue
        han_value = max(getattr(yaku, "han_closed", 0) or 0, getattr(yaku, "han_open", 0) or 0)
        total_han += han_value
        type_name = type(yaku).__name__.lower()
        key = None
        if "kokushi" in type_name:
            key = "KOKUSHI"
        elif "daisangen" in type_name:
            key = "DAISANGEN"
        elif "daisuushii" in type_name:
            key = "DAISUUSHI"
        elif "suukantsu" in type_name:
            key = "SUUKANTSU"
        if key is not None:
            yakuman_keys[key] = max(yakuman_keys.get(key, 0), han_value)
    return yakuman_keys, total_han


def tenpai_wait_tile_types(concealed_tiles: list[int]) -> set[int]:
    try:
        if shanten_calculator.calculate_shanten(to_34_array(concealed_tiles)) != 0:
            return set()
    except ValueError:
        return set()

    grouped = counts_by_type(concealed_tiles)
    waits: set[int] = set()
    for tile_index in range(34):
        if len(grouped.get(tile_index, [])) >= 4:
            continue
        try:
            if shanten_calculator.calculate_shanten(to_34_array(concealed_tiles + [tile_index * 4])) == -1:
                waits.add(tile_index)
        except ValueError:
            continue
    return waits


def calculate_tenpai_seats(game: dict[str, Any]) -> list[int]:
    round_state = game["round_state"]
    tenpai: list[int] = []
    for seat in range(round_state["player_count"]):
        if tenpai_wait_tile_types(round_state["hands"][seat]):
            tenpai.append(seat)
    return tenpai


def calculate_limit_hand_cost(
    game: dict[str, Any],
    seat: int,
    *,
    han: int,
    is_tsumo: bool,
    honba: int = 0,
) -> dict[str, Any]:
    round_state = game["round_state"]
    config = HandConfig(
        is_tsumo=is_tsumo,
        player_wind=WIND_CONSTANTS[seat_wind_label(round_state, seat)],
        round_wind=WIND_CONSTANTS[round_state["prevalent_wind"]],
        kyoutaku_number=0,
        tsumi_number=honba,
        options=OptionalRules(has_open_tanyao=True, has_aka_dora=True),
    )
    return dict(ScoresCalculator.calculate_scores(han=han, fu=30, config=config, is_yakuman=han >= 13))


def score_result_total(cost: dict[str, Any]) -> int:
    total = cost.get("total")
    if isinstance(total, int):
        return total
    return (
        int(cost.get("main", 0))
        + int(cost.get("main_bonus", 0))
        + int(cost.get("additional", 0)) * 2
        + int(cost.get("additional_bonus", 0)) * 2
    )


def local_mangan_yaku_name(game: dict[str, Any], seat: int, win_tile_id: int, *, is_tsumo: bool) -> str | None:
    if not bool(game.get("koyaku_enabled", False)):
        return None
    round_state = game["round_state"]
    win_tile_type = tile_type(win_tile_id)
    if is_tsumo and is_haitei_state(round_state, seat, is_tsumo=True) and win_tile_type == 9:
        return "Iipin moyue"
    if not is_tsumo and is_houtei_state(round_state, is_tsumo=False) and win_tile_type == 17:
        return "Chuupin raoyui"
    return None


def local_yakuman_entries(
    game: dict[str, Any],
    seat: int,
    win_tile_id: int,
    *,
    is_tsumo: bool,
) -> list[tuple[str, int]]:
    if not bool(game.get("koyaku_enabled", False)):
        return []

    round_state = game["round_state"]
    if not round_state["double_riichi"][seat] or not is_closed_hand(round_state, seat):
        return []

    if is_haitei_state(round_state, seat, is_tsumo=is_tsumo) or is_houtei_state(round_state, is_tsumo=is_tsumo):
        return [("Ishi no ue ni mo sannen", 13)]
    return []


def discard_follows_kan(game: dict[str, Any], discarder: int) -> bool:
    actions = game.get("action_log", [])
    if len(actions) < 3:
        return False
    last_action = actions[-1]
    draw_action = actions[-2]
    kan_action = actions[-3]
    return (
        last_action.get("type") == "DISCARD"
        and draw_action.get("type") == "DRAW"
        and kan_action.get("type") == "KAN"
        and last_action.get("seat") == discarder
        and draw_action.get("seat") == discarder
        and kan_action.get("seat") == discarder
    )


def local_han_yaku_entries(
    game: dict[str, Any],
    seat: int,
    win_tile_id: int,
    *,
    is_tsumo: bool,
) -> list[tuple[str, int]]:
    if not bool(game.get("koyaku_enabled", False)) or is_tsumo:
        return []

    round_state = game["round_state"]
    discard = round_state.get("last_discard")
    if discard is None or discard.get("seat") == seat or discard.get("source") in {"kan", "kita"}:
        return []

    entries: list[tuple[str, int]] = []
    if discard.get("riichi"):
        entries.append(("Tsubame gaeshi", 1))
    if discard_follows_kan(game, discard["seat"]):
        entries.append(("Kanburi", 1))
    return entries


def hand_has_sanrenkou(hand: list[list[int]]) -> bool:
    triplet_heads = sorted(
        {
            group[0]
            for group in hand
            if len(group) >= 3 and group[0] == group[1] == group[2] and group[0] < 27
        }
    )
    return any(
        triplet_heads[index : index + 3] == [triplet_heads[index], triplet_heads[index] + 1, triplet_heads[index] + 2]
        for index in range(max(0, len(triplet_heads) - 2))
    )


def hand_has_isshoku_sanjun(hand: list[list[int]]) -> bool:
    sequence_counts: dict[tuple[int, int, int], int] = {}
    for group in hand:
        if len(group) != 3:
            continue
        if group[0] >= 27:
            continue
        if group[0] + 1 == group[1] and group[1] + 1 == group[2]:
            key = (group[0], group[1], group[2])
            sequence_counts[key] = sequence_counts.get(key, 0) + 1
            if sequence_counts[key] >= 3:
                return True
    return False


def local_pattern_entries_for_hand(hand: list[list[int]], *, is_open_hand: bool) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    if hand_has_isshoku_sanjun(hand):
        entries.append(("Isshoku sanjun", 2 if is_open_hand else 3))
    if hand_has_sanrenkou(hand):
        entries.append(("Sanrenkou", 2))
    return entries


def choose_local_pattern_entries(
    candidates: list[list[tuple[str, int]]],
    *,
    reference_yaku_names: list[str] | None = None,
) -> list[tuple[str, int]]:
    if not candidates:
        return []

    if reference_yaku_names:
        triplet_signals = (
            "Toitoi ",
            "San Ankou ",
            "Sanshoku Doukou ",
            "Sankantsu ",
            "Suukantsu ",
            "Daisangen ",
            "Shousangen ",
            "Shousuushii ",
            "Daisuushii ",
        )
        sequence_signals = (
            "Iipeikou ",
            "Ryanpeikou ",
            "Pinfu ",
            "Sanshoku Doujun ",
            "Ittsu ",
        )
        has_triplet_signal = any(name.startswith(triplet_signals) for name in reference_yaku_names)
        has_sequence_signal = any(name.startswith(sequence_signals) for name in reference_yaku_names)

        if has_triplet_signal and not has_sequence_signal:
            triplet_candidates = [candidate for candidate in candidates if any(name == "Sanrenkou" for name, _ in candidate)]
            if triplet_candidates:
                candidates = triplet_candidates
        elif has_sequence_signal and not has_triplet_signal:
            sequence_candidates = [candidate for candidate in candidates if any(name == "Isshoku sanjun" for name, _ in candidate)]
            if sequence_candidates:
                candidates = sequence_candidates

    return max(candidates, key=lambda candidate: (sum(han for _, han in candidate), len(candidate)))


def local_pattern_yaku_entries(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
    reference_yaku_names: list[str] | None = None,
) -> list[tuple[str, int]]:
    if not bool(game.get("koyaku_enabled", False)):
        return []

    open_melds = [meld for meld in melds_data if meld["type"] != "kita"]
    meld_objects = build_meld_objects_from_data(melds_data, seat)
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    for meld in open_melds:
        all_tiles.extend(meld["tiles"])

    categories = {
        "man": False,
        "pin": False,
        "sou": False,
        "wind": False,
        "dragon": False,
    }
    for tile_id in all_tiles:
        t = tile_type(tile_id)
        if t < 9:
            categories["man"] = True
        elif t < 18:
            categories["pin"] = True
        elif t < 27:
            categories["sou"] = True
        elif t < 31:
            categories["wind"] = True
        else:
            categories["dragon"] = True

    entries: list[tuple[str, int]] = []
    hand_options = HandDivider.divide_hand(to_34_array(all_tiles), meld_objects)
    is_open_hand = any(meld["type"] in OPEN_MELD_TYPES for meld in melds_data)
    entries.extend(
        choose_local_pattern_entries(
            [local_pattern_entries_for_hand(hand, is_open_hand=is_open_hand) for hand in hand_options],
            reference_yaku_names=reference_yaku_names,
        )
    )
    if (
        len(open_melds) == 4
        and all(meld["opened"] for meld in open_melds)
        and (
            (is_tsumo and len(concealed_tiles) == 2 and tile_type(concealed_tiles[0]) == tile_type(concealed_tiles[1]))
            or (not is_tsumo and len(concealed_tiles) == 1 and tile_type(concealed_tiles[0]) == tile_type(win_tile_id))
        )
    ):
        entries.append(("Shiiaru raotai", 1))
    if all(categories.values()):
        entries.append(("Uumensai", 2))
    return entries


def combined_local_han_entries(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
    reference_yaku_names: list[str] | None = None,
) -> list[tuple[str, int]]:
    entries = local_han_yaku_entries(game, seat, win_tile_id, is_tsumo=is_tsumo)
    entries.extend(
        local_pattern_yaku_entries(
            game,
            seat,
            concealed_tiles,
            melds_data,
            win_tile_id,
            is_tsumo=is_tsumo,
            reference_yaku_names=reference_yaku_names,
        )
    )
    return entries


def apply_local_yakuman_entries(
    yaku_names: list[str],
    yakuman_keys: dict[str, int],
    yakuman_total_han: int,
    local_yakuman_entries: list[tuple[str, int]],
) -> tuple[list[str], dict[str, int], int]:
    if not local_yakuman_entries:
        return yaku_names, yakuman_keys, yakuman_total_han

    names = [name for name, _ in local_yakuman_entries]
    updated_names = list(names) if yakuman_total_han == 0 else yaku_names + names
    updated_keys = dict(yakuman_keys)
    for name, han in local_yakuman_entries:
        updated_keys[f"LOCAL:{name}"] = han
        yakuman_total_han += han
    return updated_names, updated_keys, yakuman_total_han


def apply_local_yaku_replacements(
    base_han: int,
    yaku_names: list[str],
    local_han_entries: list[tuple[str, int]],
) -> tuple[int, list[str]]:
    updated_han = base_han
    updated_yaku_names = list(yaku_names)

    if any(name == "Isshoku sanjun" for name, _ in local_han_entries):
        for index, item in enumerate(updated_yaku_names):
            if item.startswith("Iipeikou "):
                updated_han -= 1
                del updated_yaku_names[index]
                break

    return updated_han, updated_yaku_names


def is_agari_layout(concealed_tiles: list[int], melds_data: list[dict[str, Any]], win_tile_id: int, *, is_tsumo: bool) -> bool:
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    for meld in melds_data:
        if meld["type"] != "kita":
            all_tiles.extend(meld["tiles"])
    try:
        return agari_calculator.is_agari(to_34_array(all_tiles))
    except ValueError:
        return False


def apply_local_mangan_floor(
    game: dict[str, Any],
    seat: int,
    *,
    is_tsumo: bool,
    local_yaku_name: str | None,
    score_result: dict[str, Any],
    yaku_names: list[str],
) -> dict[str, Any]:
    if not local_yaku_name:
        return score_result
    if local_yaku_name not in yaku_names:
        yaku_names.append(local_yaku_name)
    mangan_cost = calculate_limit_hand_cost(game, seat, han=5, is_tsumo=is_tsumo, honba=0)
    if score_result_total(score_result) < score_result_total(mangan_cost):
        return mangan_cost
    return score_result


def local_bonus_tile_names(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
) -> tuple[int, list[str]]:
    round_state = game["round_state"]
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    for meld in melds_data:
        if meld["type"] != "kita":
            all_tiles.extend(meld["tiles"])

    bonus_han = 0
    names: list[str] = []

    dora_types = [dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(round_state)]
    dora_han = sum(1 for tile_id in all_tiles if tile_type(tile_id) in dora_types)
    if dora_han:
        bonus_han += dora_han
        names.append(f"Dora {dora_han} han")

    aka_han = sum(1 for tile_id in all_tiles if is_red(tile_id))
    if aka_han:
        bonus_han += aka_han
        names.append(f"Aka Dora {aka_han} han")

    if round_state["riichi"][seat]:
        ura_types = [dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_ura_indicators(round_state)]
        ura_han = sum(1 for tile_id in all_tiles if tile_type(tile_id) in ura_types)
        if ura_han:
            bonus_han += ura_han
            names.append(f"Ura Dora {ura_han} han")

    nuki_han = round_state["nuki_count"][seat] if game["mode"] == "3P" else 0
    if nuki_han:
        bonus_han += nuki_han
        names.append(f"Nuki Dora {nuki_han} han")

    return bonus_han, names


def evaluate_local_only_hand(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
    local_han_entries: list[tuple[str, int]],
    local_yaku_name: str | None = None,
) -> dict[str, Any] | None:
    if not local_han_entries and not local_yaku_name:
        return None
    if not is_agari_layout(concealed_tiles, melds_data, win_tile_id, is_tsumo=is_tsumo):
        return None

    meld_objects = build_meld_objects_from_data(melds_data, seat)
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    for meld in melds_data:
        if meld["type"] != "kita":
            all_tiles.extend(meld["tiles"])

    hand_options = HandDivider.divide_hand(to_34_array(all_tiles), meld_objects)
    opened_melds = [meld.tiles_34 for meld in meld_objects if meld.opened]
    config = build_hand_config(game, seat, is_tsumo=is_tsumo, kyoutaku_override=kyoutaku_override)
    valued_tiles = [HAKU, HATSU, CHUN, config.player_wind, config.round_wind]
    bonus_han, bonus_names = local_bonus_tile_names(
        game,
        seat,
        concealed_tiles,
        melds_data,
        win_tile_id,
        is_tsumo=is_tsumo,
    )
    local_han_total = sum(han for _, han in local_han_entries)
    total_han = local_han_total + bonus_han
    if total_han <= 0 and not local_yaku_name:
        return None

    base_yaku_names = [f"{name} {han} han" for name, han in local_han_entries] + bonus_names
    score_han = max(total_han, 1 if local_yaku_name else 0)
    display_han = max(total_han, 5 if local_yaku_name else 0)
    best_result: dict[str, Any] | None = None
    best_rank: tuple[int, int, int] | None = None
    for hand in hand_options:
        for win_group in HandCalculator._find_win_groups(win_tile_id, hand, opened_melds):
            fu_details, fu = FuCalculator.calculate_fu(hand, win_tile_id, win_group, config, valued_tiles, meld_objects)
            cost = dict(ScoresCalculator.calculate_scores(han=score_han, fu=fu, config=config, is_yakuman=False))
            yaku_names = list(base_yaku_names)
            cost = apply_local_mangan_floor(
                game,
                seat,
                is_tsumo=is_tsumo,
                local_yaku_name=local_yaku_name,
                score_result=cost,
                yaku_names=yaku_names,
            )
            rank = (score_result_total(cost), display_han, fu)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_result = {
                    "han": display_han,
                    "fu": fu,
                    "cost": cost,
                    "yaku": yaku_names,
                    "fu_details": [dict(item) for item in fu_details],
                    "is_tsumo": is_tsumo,
                    "win_tile_label": tile_label(win_tile_id),
                    "yakuman_keys": {},
                    "yakuman_total_han": 0,
                }
    return best_result


def full_honba_value(game: dict[str, Any], *, is_tsumo: bool) -> int:
    round_state = game["round_state"]
    if is_tsumo and game["mode"] == "3P":
        return round_state["honba"] * 200
    return round_state["honba"] * 300


def append_payment_detail(
    game: dict[str, Any],
    payments: list[dict[str, Any]],
    *,
    from_seat: int | None,
    amount: int,
    kind: str,
) -> None:
    if amount <= 0:
        return
    from_name = "供托" if from_seat is None else game["players"][from_seat]["name"]
    payments.append(
        {
            "from_seat": from_seat,
            "from_name": from_name,
            "amount": amount,
            "kind": kind,
        }
    )


def tsumo_payment_kind(round_state: dict[str, Any], payer_seat: int) -> str:
    return "tsumo_dealer" if payer_seat == round_state["dealer_seat"] else "tsumo_child"


def tsumo_payment_map(game: dict[str, Any], seat: int, cost: dict[str, Any]) -> dict[int, int]:
    round_state = game["round_state"]
    dealer = round_state["dealer_seat"]
    losers = [loser for loser in range(round_state["player_count"]) if loser != seat]
    if game["mode"] == "3P" and sanma_scoring_mode(game) == "NORTH_BISECTION":
        if seat == dealer:
            per_loser = cost["main"] + cost.get("main_bonus", 0)
            bisection = round_up_to_100(per_loser / 2)
            return {loser: per_loser + bisection for loser in losers}

        dealer_payment = cost["main"] + cost.get("main_bonus", 0)
        child_payment = cost["additional"] + cost.get("additional_bonus", 0)
        bisection = round_up_to_100(child_payment / 2)
        return {
            loser: (dealer_payment if loser == dealer else child_payment) + bisection
            for loser in losers
        }
    if seat == dealer:
        per_loser = cost["main"] + cost.get("main_bonus", 0)
        return {loser: per_loser for loser in losers}

    dealer_payment = cost["main"] + cost.get("main_bonus", 0)
    child_payment = cost["additional"] + cost.get("additional_bonus", 0)
    return {
        loser: (dealer_payment if loser == dealer else child_payment)
        for loser in losers
    }


def apply_tsumo_payments(
    game: dict[str, Any],
    seat: int,
    cost: dict[str, Any],
    score_changes: list[int],
    payments: list[dict[str, Any]] | None = None,
    *,
    kind: str = "tsumo",
) -> None:
    round_state = game["round_state"]
    for loser, payment in tsumo_payment_map(game, seat, cost).items():
        score_changes[loser] -= payment
        score_changes[seat] += payment
        if payments is not None:
            append_payment_detail(
                game,
                payments,
                from_seat=loser,
                amount=payment,
                kind=tsumo_payment_kind(round_state, loser) if kind == "tsumo" else kind,
            )


def nagashi_mangan_winners(round_state: dict[str, Any]) -> list[int]:
    winners: list[int] = []
    for seat, discards in enumerate(round_state["discards"]):
        if not discards:
            continue
        if any(item.get("called", False) for item in discards):
            continue
        if any(not (is_terminal(tile_type(item["tile"])) or is_honor(tile_type(item["tile"]))) for item in discards):
            continue
        winners.append(seat)
    return winners


def triplet_family_types(melds: list[dict[str, Any]], family_types: set[int]) -> set[int]:
    return {
        tile_type(meld["tiles"][0])
        for meld in melds
        if meld["type"] in TRIPLET_MELD_TYPES and meld["tiles"] and tile_type(meld["tiles"][0]) in family_types
    }


def register_liability_for_call(round_state: dict[str, Any], seat: int, action_type: str, tile_id: int, discarder: int) -> None:
    if action_type not in {"pon", "open_kan"} or seat == discarder:
        return
    liability = round_state["liability_payments"][seat]
    melds = round_state["melds"][seat]
    tile_index = tile_type(tile_id)
    if tile_index in DRAGON_TYPES and "DAISANGEN" not in liability:
        if len(triplet_family_types(melds, DRAGON_TYPES)) == 3:
            liability["DAISANGEN"] = {"liable_seat": discarder, "han": 13}
    if tile_index in WIND_TILE_TYPES and "DAISUUSHI" not in liability:
        if len(triplet_family_types(melds, WIND_TILE_TYPES)) == 4:
            liability["DAISUUSHI"] = {"liable_seat": discarder, "han": 26}


def liability_context(game: dict[str, Any], winner_seat: int, evaluation: dict[str, Any] | None) -> dict[str, Any] | None:
    if evaluation is None or evaluation.get("yakuman_total_han", 0) < 13:
        return None
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    liability_map = round_state["liability_payments"][winner_seat]
    matched_keys = [
        key for key in ("DAISANGEN", "DAISUUSHI") if key in evaluation.get("yakuman_keys", {}) and key in liability_map
    ]
    if not matched_keys:
        return None
    liable_seats = {liability_map[key]["liable_seat"] for key in matched_keys}
    if len(liable_seats) != 1:
        return None
    liable_han = sum(min(liability_map[key]["han"], evaluation["yakuman_keys"][key]) for key in matched_keys)
    if liable_han <= 0:
        return None
    total_yakuman_han = evaluation.get("yakuman_total_han", 0)
    return {
        "liable_seat": next(iter(liable_seats)),
        "liable_han": min(liable_han, total_yakuman_han),
        "remainder_han": max(0, total_yakuman_han - liable_han),
        "keys": matched_keys,
    }


def serialize_yaku_names(yaku_items: list[Any]) -> list[str]:
    result: list[str] = []
    for yaku in yaku_items:
        name = getattr(yaku, "name", str(yaku))
        han_open = getattr(yaku, "han_open", None)
        han_closed = getattr(yaku, "han_closed", None)
        han_value = han_closed if han_closed is not None else han_open
        if han_value is None:
            result.append(name)
        else:
            result.append(f"{name} {han_value} han")
    return result


def build_meld_objects_from_data(melds_data: list[dict[str, Any]], seat: int) -> list[Meld]:
    meld_objects: list[Meld] = []
    for meld in melds_data:
        if meld["type"] == "kita":
            continue
        meld_type = {
            "chi": Meld.CHI,
            "pon": Meld.PON,
            "open_kan": Meld.KAN,
            "closed_kan": Meld.KAN,
            "added_kan": Meld.SHOUMINKAN,
        }[meld["type"]]
        meld_objects.append(
            Meld(
                meld_type=meld_type,
                tiles=tuple(meld["tiles"]),
                opened=meld["opened"],
                called_tile=meld.get("called_tile"),
                who=seat,
                from_who=meld.get("from_seat"),
            )
        )
    return meld_objects


def build_meld_objects(round_state: dict[str, Any], seat: int) -> list[Meld]:
    return build_meld_objects_from_data(round_state["melds"][seat], seat)


def build_hand_config(
    game: dict[str, Any],
    seat: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
    riichi_override: bool | None = None,
    ippatsu_override: bool | None = None,
    rinshan_override: bool | None = None,
    chankan_override: bool | None = None,
    haitei_override: bool | None = None,
    houtei_override: bool | None = None,
    daburu_override: bool | None = None,
    tenhou_override: bool | None = None,
    chiihou_override: bool | None = None,
) -> HandConfig:
    round_state = game["round_state"]
    return HandConfig(
        is_tsumo=is_tsumo,
        is_riichi=round_state["riichi"][seat] if riichi_override is None else riichi_override,
        is_ippatsu=round_state["ippatsu"][seat] if ippatsu_override is None else ippatsu_override,
        is_rinshan=(round_state["last_draw_source"][seat] == "rinshan") if rinshan_override is None else rinshan_override,
        is_chankan=is_chankan_state(round_state, is_tsumo=is_tsumo) if chankan_override is None else chankan_override,
        is_haitei=is_haitei_state(round_state, seat, is_tsumo=is_tsumo) if haitei_override is None else haitei_override,
        is_houtei=is_houtei_state(round_state, is_tsumo=is_tsumo) if houtei_override is None else houtei_override,
        is_daburu_riichi=round_state["double_riichi"][seat] if daburu_override is None else daburu_override,
        is_tenhou=is_tenhou_state(round_state, seat, is_tsumo=is_tsumo) if tenhou_override is None else tenhou_override,
        is_renhou=is_renhou_state(game, seat, is_tsumo=is_tsumo),
        is_chiihou=is_chiihou_state(round_state, seat, is_tsumo=is_tsumo) if chiihou_override is None else chiihou_override,
        player_wind=WIND_CONSTANTS[seat_wind_label(round_state, seat)],
        round_wind=WIND_CONSTANTS[round_state["prevalent_wind"]],
        kyoutaku_number=round_state["riichi_sticks"] if kyoutaku_override is None else kyoutaku_override,
        tsumi_number=round_state["honba"],
        options=build_rule_options(game),
    )


def estimate_hand_value_for_layout(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
    riichi_override: bool | None = None,
    ippatsu_override: bool | None = None,
    rinshan_override: bool | None = None,
    chankan_override: bool | None = None,
    haitei_override: bool | None = None,
    houtei_override: bool | None = None,
    daburu_override: bool | None = None,
    tenhou_override: bool | None = None,
    chiihou_override: bool | None = None,
) -> Any:
    round_state = game["round_state"]
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    for meld in melds_data:
        if meld["type"] != "kita":
            all_tiles.extend(meld["tiles"])
    config = build_hand_config(
        game,
        seat,
        is_tsumo=is_tsumo,
        kyoutaku_override=kyoutaku_override,
        riichi_override=riichi_override,
        ippatsu_override=ippatsu_override,
        rinshan_override=rinshan_override,
        chankan_override=chankan_override,
        haitei_override=haitei_override,
        houtei_override=houtei_override,
        daburu_override=daburu_override,
        tenhou_override=tenhou_override,
        chiihou_override=chiihou_override,
    )
    return calculator.estimate_hand_value(
        all_tiles,
        win_tile_id,
        melds=build_meld_objects_from_data(melds_data, seat),
        dora_indicators=scoring_dora_indicators(game, round_state),
        ura_dora_indicators=scoring_dora_indicators(game, round_state, ura=True)
        if (round_state["riichi"][seat] if riichi_override is None else riichi_override)
        else None,
        config=config,
    )


def tile_type_count_in_layout(concealed_tiles: list[int], melds_data: list[dict[str, Any]], tile_index: int) -> int:
    total = sum(1 for tile in concealed_tiles if tile_type(tile) == tile_index)
    for meld in melds_data:
        if meld["type"] == "kita":
            continue
        total += sum(1 for tile in meld["tiles"] if tile_type(tile) == tile_index)
    return total


def winning_tile_types_for_layout(
    game: dict[str, Any], seat: int, concealed_tiles: list[int], melds_data: list[dict[str, Any]]
) -> set[int]:
    return tenpai_wait_tile_types(concealed_tiles)


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


def unique_terminal_honor_types(tiles: list[int]) -> set[int]:
    return {
        tile_type(tile_id)
        for tile_id in tiles
        if is_honor(tile_type(tile_id)) or is_terminal(tile_type(tile_id))
    }


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


def should_abort_for_triple_ron(game: dict[str, Any], winners: list[int]) -> bool:
    return False


def settle_abortive_draw(game: dict[str, Any], kind: str, headline: str | None = None) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    game["honba"] += 1
    game["riichi_sticks"] = 0
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = None
    round_state["pending_kita"] = None
    round_state["pending_dora_reveals"] = 0
    round_state["riichi_sticks"] = 0
    round_state["round_result"] = {
        "kind": "ABORTIVE_DRAW",
        "subtype": kind,
        "headline": headline or ABORTIVE_DRAW_HEADLINES.get(kind, "途中流局"),
        "score_changes": [0] * round_state["player_count"],
    }
    round_state["phase"] = "ROUND_END"
    record_action(game, -1, "DRAW_END", details=round_state["round_result"]["headline"])
    finalize_round(game, dealer_continues=True)


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
    if should_abort_for_four_kans(round_state):
        settle_abortive_draw(game, "SUUKAIKAN")
        return True
    draw_from_rinshan(game, seat, "宀笂鎽哥墝")
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


def kuikae_forbidden_tile_types(action_type: str, discard_tile_id: int, consumed_ids: list[int]) -> list[int]:
    called_type = tile_type(discard_tile_id)
    if action_type == "pon":
        return [called_type]
    if action_type != "chi":
        return []

    meld_types = sorted(tile_type(tile_id) for tile_id in consumed_ids + [discard_tile_id])
    forbidden = {called_type}
    suit_base = (called_type // 9) * 9
    if called_type == meld_types[0] and meld_types[2] < suit_base + 8:
        forbidden.add(meld_types[2] + 1)
    elif called_type == meld_types[2] and meld_types[0] > suit_base:
        forbidden.add(meld_types[0] - 1)
    return sorted(forbidden)


def legal_post_call_discards(game: dict[str, Any], seat: int, action_type: str, discard_tile_id: int, consumed_ids: list[int]) -> list[int]:
    round_state = game["round_state"]
    candidate_hand = list(round_state["hands"][seat])
    pop_specific_tiles(candidate_hand, consumed_ids)
    forbidden_types = set(kuikae_forbidden_tile_types(action_type, discard_tile_id, consumed_ids))
    return [tile_id for tile_id in sort_tiles(candidate_hand) if tile_type(tile_id) not in forbidden_types]


def can_declare_riichi_closed_kan(game: dict[str, Any], seat: int, consumed_ids: list[int]) -> bool:
    round_state = game["round_state"]
    drawn = round_state["current_draw"]
    if drawn is None or drawn not in consumed_ids:
        return False

    before_tiles = list(round_state["hands"][seat])
    before_tiles.remove(drawn)
    before_waits = winning_tile_types_for_layout(game, seat, before_tiles, round_state["melds"][seat])
    if not before_waits:
        return False

    after_tiles = list(round_state["hands"][seat])
    pop_specific_tiles(after_tiles, consumed_ids)
    after_melds = deepcopy(round_state["melds"][seat])
    after_melds.append(
        {
            "type": "closed_kan",
            "tiles": sort_tiles(consumed_ids),
            "opened": False,
            "called_tile": None,
            "from_seat": seat,
        }
    )
    after_waits = winning_tile_types_for_layout(game, seat, after_tiles, after_melds)
    return before_waits == after_waits


def evaluate_hand(
    game: dict[str, Any],
    seat: int,
    win_tile_id: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
) -> dict[str, Any] | None:
    round_state = game["round_state"]
    local_yaku_name = local_mangan_yaku_name(game, seat, win_tile_id, is_tsumo=is_tsumo)
    local_yakuman = local_yakuman_entries(game, seat, win_tile_id, is_tsumo=is_tsumo)
    if is_tsumo and is_tenhou_state(round_state, seat, is_tsumo=True):
        best: dict[str, Any] | None = None
        for candidate_tile_id in sort_tiles(round_state["hands"][seat]):
            candidate_result = estimate_hand_value_for_layout(
                game,
                seat,
                round_state["hands"][seat],
                round_state["melds"][seat],
                candidate_tile_id,
                is_tsumo=True,
                kyoutaku_override=kyoutaku_override,
                tenhou_override=True,
            )
            if candidate_result.error:
                continue
            serialized = serialize_evaluation_result(
                game,
                seat,
                candidate_result,
                candidate_tile_id,
                is_tsumo=True,
                kyoutaku_override=kyoutaku_override,
                tenhou_override=True,
            )
            if best is None or evaluation_result_rank(serialized) > evaluation_result_rank(best):
                best = serialized
        return best
    config = build_hand_config(game, seat, is_tsumo=is_tsumo, kyoutaku_override=kyoutaku_override)
    result = estimate_hand_value_for_layout(
        game,
        seat,
        round_state["hands"][seat],
        round_state["melds"][seat],
        win_tile_id,
        is_tsumo=is_tsumo,
        kyoutaku_override=kyoutaku_override,
    )
    if result.error:
        local_han_entries = combined_local_han_entries(
            game,
            seat,
            round_state["hands"][seat],
            round_state["melds"][seat],
            win_tile_id,
            is_tsumo=is_tsumo,
        )
        if (
            local_yaku_name
            and not local_han_entries
            and is_agari_layout(round_state["hands"][seat], round_state["melds"][seat], win_tile_id, is_tsumo=is_tsumo)
        ):
            return {
                "han": 5,
                "fu": 30,
                "cost": calculate_limit_hand_cost(game, seat, han=5, is_tsumo=is_tsumo, honba=0),
                "yaku": [local_yaku_name],
                "fu_details": [],
                "is_tsumo": is_tsumo,
                "win_tile_label": tile_label(win_tile_id),
                "yakuman_keys": {},
                "yakuman_total_han": 0,
            }
        local_only_result = evaluate_local_only_hand(
            game,
            seat,
            round_state["hands"][seat],
            round_state["melds"][seat],
            win_tile_id,
            is_tsumo=is_tsumo,
            kyoutaku_override=kyoutaku_override,
            local_han_entries=local_han_entries,
            local_yaku_name=local_yaku_name,
        )
        if local_only_result is not None:
            return local_only_result
        return None
    yakuman_keys, yakuman_total_han = extract_special_yakuman_han(result.yaku)
    yaku_names = serialize_yaku_names(result.yaku)
    local_han_entries = combined_local_han_entries(
        game,
        seat,
        round_state["hands"][seat],
        round_state["melds"][seat],
        win_tile_id,
        is_tsumo=is_tsumo,
        reference_yaku_names=yaku_names,
    )
    yaku_names, yakuman_keys, yakuman_total_han = apply_local_yakuman_entries(
        yaku_names,
        yakuman_keys,
        yakuman_total_han,
        local_yakuman,
    )
    is_yakuman_hand = yakuman_total_han > 0
    base_han = result.han
    if not is_yakuman_hand:
        base_han, yaku_names = apply_local_yaku_replacements(base_han, yaku_names, local_han_entries)
    local_han_total = 0 if is_yakuman_hand else sum(han for _, han in local_han_entries)
    han = yakuman_total_han if is_yakuman_hand else base_han + local_han_total
    if not is_yakuman_hand:
        yaku_names.extend(f"{name} {han_value} han" for name, han_value in local_han_entries)
    nuki = round_state["nuki_count"][seat] if game["mode"] == "3P" and not is_yakuman_hand else 0
    if nuki:
        han += nuki
        yaku_names.append(f"拔北宝牌 {nuki} 番")
    score_result = ScoresCalculator.calculate_scores(
        han=han,
        fu=result.fu,
        config=config,
        is_yakuman=is_yakuman_hand,
    )
    score_result = apply_local_mangan_floor(
        game,
        seat,
        is_tsumo=is_tsumo,
        local_yaku_name=None if is_yakuman_hand else local_yaku_name,
        score_result=dict(score_result),
        yaku_names=yaku_names,
    )
    return {
        "han": han,
        "fu": result.fu,
        "cost": dict(score_result),
        "yaku": yaku_names,
        "fu_details": [dict(item) for item in result.fu_details],
        "is_tsumo": is_tsumo,
        "win_tile_label": tile_label(win_tile_id),
        "yakuman_keys": yakuman_keys,
        "yakuman_total_han": yakuman_total_han,
    }


def serialize_evaluation_result(
    game: dict[str, Any],
    seat: int,
    result: Any,
    win_tile_id: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
    tenhou_override: bool | None = None,
) -> dict[str, Any]:
    round_state = game["round_state"]
    local_yaku_name = local_mangan_yaku_name(game, seat, win_tile_id, is_tsumo=is_tsumo)
    local_yakuman = local_yakuman_entries(game, seat, win_tile_id, is_tsumo=is_tsumo)
    config = build_hand_config(
        game,
        seat,
        is_tsumo=is_tsumo,
        kyoutaku_override=kyoutaku_override,
        tenhou_override=tenhou_override,
    )
    yakuman_keys, yakuman_total_han = extract_special_yakuman_han(result.yaku)
    yaku_names = serialize_yaku_names(result.yaku)
    local_han_entries = combined_local_han_entries(
        game,
        seat,
        round_state["hands"][seat],
        round_state["melds"][seat],
        win_tile_id,
        is_tsumo=is_tsumo,
        reference_yaku_names=yaku_names,
    )
    yaku_names, yakuman_keys, yakuman_total_han = apply_local_yakuman_entries(
        yaku_names,
        yakuman_keys,
        yakuman_total_han,
        local_yakuman,
    )
    is_yakuman_hand = yakuman_total_han > 0
    base_han = result.han
    if not is_yakuman_hand:
        base_han, yaku_names = apply_local_yaku_replacements(base_han, yaku_names, local_han_entries)
    local_han_total = 0 if is_yakuman_hand else sum(han_value for _, han_value in local_han_entries)
    han = yakuman_total_han if is_yakuman_hand else base_han + local_han_total
    if not is_yakuman_hand:
        yaku_names.extend(f"{name} {han_value} han" for name, han_value in local_han_entries)
    nuki = round_state["nuki_count"][seat] if game["mode"] == "3P" and not is_yakuman_hand else 0
    if nuki:
        han += nuki
        yaku_names.append(f"拔北宝牌 {nuki} 番")
    score_result = ScoresCalculator.calculate_scores(
        han=han,
        fu=result.fu,
        config=config,
        is_yakuman=is_yakuman_hand,
    )
    score_result = apply_local_mangan_floor(
        game,
        seat,
        is_tsumo=is_tsumo,
        local_yaku_name=None if is_yakuman_hand else local_yaku_name,
        score_result=dict(score_result),
        yaku_names=yaku_names,
    )
    return {
        "han": han,
        "fu": result.fu,
        "cost": dict(score_result),
        "yaku": yaku_names,
        "fu_details": [dict(item) for item in result.fu_details],
        "is_tsumo": is_tsumo,
        "win_tile_label": tile_label(win_tile_id),
        "yakuman_keys": yakuman_keys,
        "yakuman_total_han": yakuman_total_han,
    }


def evaluation_result_rank(item: dict[str, Any]) -> tuple[int, int, int, int]:
    cost = item["cost"]
    total = cost.get("total")
    if total is None:
        total = (
            cost.get("main", 0)
            + cost.get("main_bonus", 0)
            + cost.get("additional", 0) * 2
            + cost.get("additional_bonus", 0) * 2
        )
    return (
        item["yakuman_total_han"],
        int(total),
        item["han"],
        item["fu"],
    )


def wait_count_after_discard(game: dict[str, Any], seat: int, discard_tile_id: int) -> tuple[int, list[str]]:
    round_state = game["round_state"]
    tiles = list(round_state["hands"][seat])
    tiles.remove(discard_tile_id)
    counts = to_34_array(tiles)
    visible_counts = visible_tile_type_counts(game, seat, hand_tiles=tiles)
    ukeire = 0
    good_tiles: list[str] = []
    try:
        base_shanten = shanten_calculator.calculate_shanten(counts)
    except ValueError:
        base_shanten = 8
    for tile_index in range(34):
        if counts[tile_index] >= 4 or visible_counts[tile_index] >= 4:
            continue
        test_tiles = tiles + [tile_index * 4]
        try:
            next_shanten = shanten_calculator.calculate_shanten(to_34_array(test_tiles))
        except ValueError:
            continue
        if next_shanten < base_shanten or (base_shanten == 0 and next_shanten == -1):
            remaining = max(0, 4 - visible_counts[tile_index])
            ukeire += remaining
            good_tiles.append(tile_type_label(tile_index))
    return ukeire, good_tiles


def tile_suit_index(tile_index: int) -> int | None:
    if tile_index >= 27:
        return None
    return tile_index // 9


def infer_open_hand_profile(game: dict[str, Any], seat: int, opponent: int) -> dict[str, Any]:
    round_state = game["round_state"]
    if opponent == seat:
        return {"threat": 0.0, "flush_suit": None, "flush_with_honors": False, "toitoi": False, "value_honor_types": set(), "labels": []}
    if round_state["riichi"][opponent]:
        return {
            "threat": round(1.0 + min(round_state["nuki_count"][opponent], 2) * 0.08, 3),
            "flush_suit": None,
            "flush_with_honors": False,
            "toitoi": False,
            "value_honor_types": set(),
            "labels": ["立直"],
        }

    melds = round_state["melds"][opponent]
    open_melds = [meld for meld in melds if meld["type"] in OPEN_MELD_TYPES]
    nuki_count = round_state["nuki_count"][opponent]
    if not open_melds and nuki_count <= 0:
        return {"threat": 0.0, "flush_suit": None, "flush_with_honors": False, "toitoi": False, "value_honor_types": set(), "labels": []}

    threat = 0.12 + (len(open_melds) * 0.16) + (min(nuki_count, 4) * 0.12)
    triplet_types = {tile_type(meld["tiles"][0]) for meld in open_melds if meld["type"] in TRIPLET_MELD_TYPES}
    seat_wind_type = round_state["wind_type_map"][seat_wind_label(round_state, opponent)]
    prevalent_wind_type = round_state["wind_type_map"][round_state["prevalent_wind"]]
    value_honor_types = set(DRAGON_TYPES)
    value_honor_types.add(seat_wind_type)
    value_honor_types.add(prevalent_wind_type)
    labels: list[str] = []
    if triplet_types & DRAGON_TYPES:
        threat += 0.24
        labels.append("役牌")
    if seat_wind_type in triplet_types:
        threat += 0.16
        if "役牌" not in labels:
            labels.append("役牌")
    if prevalent_wind_type in triplet_types:
        threat += 0.12
        if "役牌" not in labels:
            labels.append("役牌")

    dora_types = {dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(round_state)}
    revealed_dora = sum(
        1
        for meld in melds
        for tile_id in meld["tiles"]
        if is_red(tile_id) or tile_type(tile_id) in dora_types
    )
    threat += min(revealed_dora, 3) * 0.05

    meld_tile_types = [tile_type(tile_id) for meld in open_melds for tile_id in meld["tiles"]]
    suit_counts = [sum(1 for ttype in meld_tile_types if tile_suit_index(ttype) == suit) for suit in range(3)]
    honor_count = sum(1 for ttype in meld_tile_types if is_honor(ttype))
    dominant_suit = max(range(3), key=lambda suit: suit_counts[suit]) if any(suit_counts) else None
    flush_suit = None
    flush_with_honors = False
    if dominant_suit is not None:
        dominant_count = suit_counts[dominant_suit]
        off_suit_count = sum(suit_counts) - dominant_count
        if dominant_count >= 5 and dominant_count >= off_suit_count + 2:
            flush_suit = dominant_suit
            flush_with_honors = honor_count > 0
            threat += 0.12 if flush_with_honors else 0.18
            labels.append("混一色" if flush_with_honors else "清一色")

    toitoi = len(triplet_types) >= 2 or sum(1 for meld in open_melds if meld["type"] in TRIPLET_MELD_TYPES) >= 2
    if toitoi:
        threat += 0.1
        labels.append("对对和")

    return {
        "threat": round(min(threat, 0.95), 3),
        "flush_suit": flush_suit,
        "flush_with_honors": flush_with_honors,
        "toitoi": toitoi,
        "value_honor_types": value_honor_types,
        "labels": labels[:3],
    }


def tile_risk_score(game: dict[str, Any], seat: int, discard_tile_id: int) -> float:
    round_state = game["round_state"]
    ttype = tile_type(discard_tile_id)
    base = 0.0
    threatening = [
        (idx, infer_open_hand_profile(game, seat, idx))
        for idx in range(round_state["player_count"])
        if idx != seat
    ]
    threatening = [(idx, profile) for idx, profile in threatening if profile["threat"] > 0]
    if not threatening:
        return 0.0
    for opponent, profile in threatening:
        threat = profile["threat"]
        opponent_discards = {tile_type(item["tile"]) for item in round_state["discards"][opponent]}
        if ttype in opponent_discards:
            continue
        tile_base = 0.0
        if is_honor(ttype):
            tile_base = 0.22 if sum(1 for item in round_state["discards"][opponent] if tile_type(item["tile"]) == ttype) > 0 else 0.7
        elif is_terminal(ttype):
            tile_base = 0.5
        else:
            tile_base = 1.0
        rank = ttype % 9
        if ttype < 27:
            left_suji = ttype - 3 if rank >= 3 else None
            right_suji = ttype + 3 if rank <= 5 else None
            if (left_suji is not None and left_suji in opponent_discards) or (
                right_suji is not None and right_suji in opponent_discards
            ):
                tile_base *= 0.7
        suit_index = tile_suit_index(ttype)
        if profile["flush_suit"] is not None:
            if suit_index == profile["flush_suit"]:
                tile_base *= 1.34 if not profile["flush_with_honors"] else 1.22
            elif suit_index is not None:
                tile_base *= 0.72
            elif is_honor(ttype):
                tile_base *= 1.18 if profile["flush_with_honors"] else 0.65
        if profile["toitoi"] and (is_terminal(ttype) or is_honor(ttype)):
            tile_base *= 1.12
        if ttype in profile["value_honor_types"]:
            tile_base *= 1.18
        base += tile_base * threat
    return round(base, 3)


def tile_value_bonus(game: dict[str, Any], seat: int, discard_tile_id: int) -> float:
    round_state = game["round_state"]
    bonus = 0.0
    if is_red(discard_tile_id):
        bonus += 1.0
    dora_types = {dora_from_indicator(tile, mode=game["mode"]) for tile in current_dora_indicators(round_state)}
    if tile_type(discard_tile_id) in dora_types:
        bonus += 0.75
    ttype = tile_type(discard_tile_id)
    wind = seat_wind_label(round_state, seat)
    if ttype == round_state["wind_type_map"][wind]:
        bonus += 0.35
    if ttype == round_state["wind_type_map"][round_state["prevalent_wind"]]:
        bonus += 0.35
    return bonus


def visible_tile_type_counts(game: dict[str, Any], seat: int, *, hand_tiles: list[int] | None = None) -> list[int]:
    round_state = game["round_state"]
    counts = [0] * 34
    concealed_tiles = round_state["hands"][seat] if hand_tiles is None else hand_tiles

    for tile_id in concealed_tiles:
        counts[tile_type(tile_id)] += 1

    for discards in round_state["discards"]:
        for item in discards:
            if item.get("called", False):
                continue
            counts[tile_type(item["tile"])] += 1

    for melds in round_state["melds"]:
        for meld in melds:
            for tile_id in meld["tiles"]:
                counts[tile_type(tile_id)] += 1

    for tile_id in current_dora_indicators(round_state):
        counts[tile_type(tile_id)] += 1

    return [min(4, value) for value in counts]


def hand_route_profile(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    *,
    shanten_value: int,
) -> tuple[float, list[str]]:
    round_state = game["round_state"]
    melds = [meld for meld in round_state["melds"][seat] if meld["type"] != "kita"]
    counts = to_34_array(concealed_tiles)
    all_tile_types = [tile_type(tile_id) for tile_id in concealed_tiles]
    for meld in melds:
        all_tile_types.extend(tile_type(tile_id) for tile_id in meld["tiles"])

    simple_count = sum(1 for ttype in all_tile_types if is_simple(ttype))
    terminal_count = sum(1 for ttype in all_tile_types if is_terminal(ttype))
    honor_count = sum(1 for ttype in all_tile_types if is_honor(ttype))
    suit_counts = [sum(1 for ttype in all_tile_types if tile_suit_index(ttype) == suit) for suit in range(3)]
    dominant_suit = max(range(3), key=lambda suit: suit_counts[suit]) if any(suit_counts) else 0
    pair_count = sum(1 for value in counts if value >= 2)
    triplet_count = sum(1 for value in counts if value >= 3) + sum(1 for meld in melds if meld["type"] in TRIPLET_MELD_TYPES)

    wind = seat_wind_label(round_state, seat)
    value_honor_types = {
        round_state["wind_type_map"][wind],
        round_state["wind_type_map"][round_state["prevalent_wind"]],
        31,
        32,
        33,
    }
    value_honor_sets = sum(1 for ttype in value_honor_types if counts[ttype] >= 2)
    value_honor_sets += sum(1 for meld in melds if meld["type"] in TRIPLET_MELD_TYPES and tile_type(meld["tiles"][0]) in value_honor_types)

    route_scale = 1.0 if shanten_value <= 2 else 0.8 if shanten_value <= 4 else 0.6
    bonus = 0.0
    routes: list[str] = []

    if honor_count == 0 and terminal_count <= 2 and simple_count >= max(8, len(all_tile_types) - 2):
        routes.append("断幺")
        bonus += 6.5

    if value_honor_sets:
        routes.append("役牌")
        bonus += 4.5 + (value_honor_sets * 1.8)

    dominant_count = suit_counts[dominant_suit]
    off_suit_count = sum(suit_counts) - dominant_count
    if dominant_count >= 9 and off_suit_count == 0 and honor_count == 0:
        routes.append("清一色")
        bonus += 14.0
    elif dominant_count >= 8 and off_suit_count <= 1 and honor_count >= 1:
        routes.append("混一色")
        bonus += 10.0

    if is_closed_hand(round_state, seat) and not melds and pair_count >= 4:
        routes.append("七对子")
        bonus += 3.5 + (pair_count * 1.6)

    if triplet_count >= 2 and pair_count >= 2:
        routes.append("对对和")
        bonus += 4.0 + (triplet_count * 1.8)

    unique_routes: list[str] = []
    for route in routes:
        if route not in unique_routes:
            unique_routes.append(route)

    return round(bonus * route_scale, 3), unique_routes[:3]


def discard_profile(game: dict[str, Any], seat: int, discard_tile_id: int, level: int) -> dict[str, Any]:
    round_state = game["round_state"]
    tiles = list(round_state["hands"][seat])
    tiles.remove(discard_tile_id)
    try:
        shanten_value = shanten_calculator.calculate_shanten(to_34_array(tiles))
    except ValueError:
        shanten_value = 8
    ukeire, waits = wait_count_after_discard(game, seat, discard_tile_id)
    risk = tile_risk_score(game, seat, discard_tile_id)
    bonus = tile_value_bonus(game, seat, discard_tile_id)
    route_bonus, routes = hand_route_profile(game, seat, tiles, shanten_value=shanten_value)
    if level == 1:
        score = (-100 * shanten_value) + (ukeire * 1.4) - (bonus * 2.0) + (route_bonus * 0.65) + random.random()
    elif level == 2:
        score = (-110 * shanten_value) + (ukeire * 2.5) - (risk * 16.0) - (bonus * 3.5) + (route_bonus * 0.9)
    else:
        point_gap = max(player["points"] for player in game["players"]) - game["players"][seat]["points"]
        aggression = 1.4 if point_gap > 8000 else 1.0
        score = (-115 * shanten_value) + (ukeire * 3.2 * aggression) - (risk * 18.0) - (bonus * 4.0) + route_bonus
    return {
        "tile_id": discard_tile_id,
        "tile_label": tile_label(discard_tile_id),
        "shanten": shanten_value,
        "ukeire": ukeire,
        "waits": waits[:6],
        "risk": risk,
        "value_penalty": bonus,
        "routes": routes,
        "route_bonus": route_bonus,
        "score": round(score, 3),
    }


def sorted_discard_profiles(game: dict[str, Any], seat: int, level: int) -> list[dict[str, Any]]:
    profiles = [discard_profile(game, seat, tile_id, level) for tile_id in sort_tiles(game["round_state"]["hands"][seat])]
    return sorted(profiles, key=lambda item: (-item["score"], item["tile_label"]))


def can_riichi_after_discard(game: dict[str, Any], seat: int, discard_tile_id: int) -> bool:
    round_state = game["round_state"]
    if round_state["riichi"][seat]:
        return False
    if not is_closed_hand(round_state, seat):
        return False
    if game["players"][seat]["points"] < 1000:
        return False
    if len(round_state["live_wall"]) < 4:
        return False
    remaining = list(round_state["hands"][seat])
    remaining.remove(discard_tile_id)
    return bool(tenpai_wait_tile_types(remaining))


def can_double_riichi(round_state: dict[str, Any], seat: int) -> bool:
    return seat_is_on_first_turn(round_state, seat) and round_is_uninterrupted(round_state)


def build_discard_actions(game: dict[str, Any], seat: int) -> list[ActionChoice]:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    if round_state["riichi"][seat]:
        drawn = round_state["current_draw"]
        if drawn is not None:
            return [ActionChoice(f"discard|{drawn}", "discard", seat, f"打出 {tile_label(drawn)}", tile_id=drawn)]
        return []
    forbidden_types = set(round_state["kuikae_forbidden_types"][seat])
    actions: list[ActionChoice] = []
    seen: set[int] = set()
    for tile_id in sort_tiles(round_state["hands"][seat]):
        if tile_id in seen:
            continue
        seen.add(tile_id)
        if tile_type(tile_id) in forbidden_types:
            continue
        actions.append(ActionChoice(f"discard|{tile_id}", "discard", seat, f"打出 {tile_label(tile_id)}", tile_id=tile_id))
        if can_riichi_after_discard(game, seat, tile_id):
            actions.append(ActionChoice(f"riichi|{tile_id}", "riichi", seat, f"立直并打出 {tile_label(tile_id)}", tile_id=tile_id))
    return actions


def build_closed_kan_actions(game: dict[str, Any], seat: int) -> list[ActionChoice]:
    round_state = game["round_state"]
    if round_state["kan_count"] >= 4 or not round_state["rinshan_tiles"] or round_state["current_draw"] is None:
        return []
    grouped = counts_by_type(round_state["hands"][seat])
    actions: list[ActionChoice] = []
    for tile_index, tiles in grouped.items():
        if len(tiles) == 4:
            if round_state["riichi"][seat] and not can_declare_riichi_closed_kan(game, seat, tiles):
                continue
            action_id = f"closed_kan|{tile_index}|{','.join(str(tile) for tile in tiles)}"
            actions.append(
                ActionChoice(
                    action_id,
                    "closed_kan",
                    seat,
                    f"暗杠 {tile_type_label(tile_index)}",
                    tile_id=tiles[0],
                    consumed_ids=list(tiles),
                )
            )
    if round_state["riichi"][seat]:
        return actions
    for idx, meld in enumerate(round_state["melds"][seat]):
        if meld["type"] != "pon":
            continue
        meld_tile_type = tile_type(meld["tiles"][0])
        extra_tiles = grouped.get(meld_tile_type, [])
        if extra_tiles:
            tile_id = extra_tiles[0]
            action_id = f"added_kan|{meld_tile_type}|{idx}|{tile_id}"
            actions.append(
                ActionChoice(
                    action_id,
                    "added_kan",
                    seat,
                    f"加杠 {tile_type_label(meld_tile_type)}",
                    tile_id=tile_id,
                    consumed_ids=[tile_id],
                    meld_index=idx,
                )
            )
    return actions


def build_turn_actions(game: dict[str, Any], seat: int) -> list[ActionChoice]:
    round_state = game["round_state"]
    actions: list[ActionChoice] = []
    if can_abortive_draw_nine_terminals(game, seat):
        actions.append(ActionChoice("abortive_draw|KYUUSHU_KYUUHAI", "abortive_draw", seat, "九种九牌流局"))
    drawn = round_state["current_draw"]
    if drawn is not None and evaluate_hand(game, seat, drawn, is_tsumo=True) is not None:
        actions.append(ActionChoice("tsumo", "tsumo", seat, "自摸"))
    if game["mode"] == "3P" and not round_state["kita_blocked"][seat]:
        for tile_id in sort_tiles(round_state["hands"][seat]):
            if tile_type(tile_id) == 30:
                if round_state["riichi"][seat]:
                    break
                actions.append(ActionChoice(f"kita|{tile_id}", "kita", seat, f"拔北 {tile_label(tile_id)}", tile_id=tile_id))
                break
    actions.extend(build_closed_kan_actions(game, seat))
    actions.extend(build_discard_actions(game, seat))
    return actions


def chi_candidates(hand_tiles: list[int], discard_tile: int) -> list[list[int]]:
    ttype = tile_type(discard_tile)
    if is_honor(ttype):
        return []
    suit = ttype // 9
    rank = ttype % 9
    grouped = counts_by_type(hand_tiles)
    candidates: list[list[int]] = []
    for delta_pair in [(-2, -1), (-1, 1), (1, 2)]:
        a = rank + delta_pair[0]
        b = rank + delta_pair[1]
        if not (0 <= a <= 8 and 0 <= b <= 8):
            continue
        ta = suit * 9 + a
        tb = suit * 9 + b
        if grouped.get(ta) and grouped.get(tb):
            candidates.append([grouped[ta][0], grouped[tb][0]])
    return candidates


def build_reaction_actions(game: dict[str, Any], seat: int) -> list[ActionChoice]:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    if round_state["reaction_passed"][seat]:
        return []
    discard = round_state["last_discard"]
    if discard is None or discard["seat"] == seat:
        return []
    discard_tile = discard["tile"]
    discard_type = tile_type(discard_tile)
    actions: list[ActionChoice] = []
    can_ron, ron_result = can_ron_on_last_discard(game, seat)
    if can_ron and not is_head_bump_blocked(game, seat):
        actions.append(ActionChoice("ron", "ron", seat, f"荣和 {tile_label(discard_tile)}", tile_id=discard_tile))
    if discard.get("source") in {"kan", "kita"}:
        return [action for action in actions if action.type == "ron"]
    if round_state["riichi"][seat]:
        return actions
    grouped = counts_by_type(round_state["hands"][seat])
    same_tiles = grouped.get(discard_type, [])
    if len(same_tiles) >= 2:
        consumed = same_tiles[:2]
        if legal_post_call_discards(game, seat, "pon", discard_tile, consumed):
            actions.append(
                ActionChoice(
                f"pon|{discard_tile}|{','.join(str(tile) for tile in consumed)}",
                "pon",
                seat,
                f"碰 {tile_type_label(discard_type)}",
                discard_tile,
                consumed,
                )
            )
    if len(same_tiles) >= 3 and round_state["kan_count"] < 4 and round_state["rinshan_tiles"]:
        consumed = same_tiles[:3]
        actions.append(
            ActionChoice(
                f"open_kan|{discard_tile}|{','.join(str(tile) for tile in consumed)}",
                "open_kan",
                seat,
                f"明杠 {tile_type_label(discard_type)}",
                discard_tile,
                consumed,
            )
        )
    if game["mode"] == "4P" and seat == next_seat(discard["seat"], round_state["player_count"]) and not is_honor(discard_type):
        for consumed in chi_candidates(round_state["hands"][seat], discard_tile):
            labels = " ".join(tile_label(tile) for tile in sort_tiles(consumed + [discard_tile]))
            if legal_post_call_discards(game, seat, "chi", discard_tile, consumed):
                actions.append(
                    ActionChoice(
                    f"chi|{discard_tile}|{','.join(str(tile) for tile in consumed)}",
                    "chi",
                    seat,
                    f"吃 {labels}",
                    discard_tile,
                    consumed,
                    )
                )
    return actions


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
        "hand": copy_public_tiles(round_state["hands"][seat], reveal),
        "melds": [
            {
                "type": meld["type"],
                "opened": meld["opened"],
                "tiles": [tile_label(tile) for tile in meld["tiles"]],
                "from_seat": meld.get("from_seat"),
            }
            for meld in round_state["melds"][seat]
        ],
        "discards": [
            {"tile": tile_label(item["tile"]), "riichi": item.get("riichi", False), "called": item.get("called", False)}
            for item in round_state["discards"][seat]
        ],
        "nuki_count": round_state["nuki_count"][seat],
        "last_reason": player.get("last_reason", ""),
    }


def build_hint_block(game: dict[str, Any]) -> dict[str, Any] | None:
    round_state = game["round_state"]
    seat = game["human_seat"]
    if round_state["phase"] != "DISCARD" or round_state["turn_seat"] != seat:
        return None
    try:
        shanten_value = shanten_calculator.calculate_shanten(to_34_array(round_state["hands"][seat]))
    except ValueError:
        shanten_value = None
    profiles = sorted_discard_profiles(game, seat, 3)[:3]
    return {
        "shanten": shanten_value,
        "top_discards": [
            {
                "tile": item["tile_label"],
                "ukeire": item["ukeire"],
                "risk": item["risk"],
                "score": item["score"],
                "waits": item["waits"],
                "routes": item["routes"],
            }
            for item in profiles
        ],
    }


def legal_actions_for_human(game: dict[str, Any]) -> list[ActionChoice]:
    if game["status"] == "FINISHED":
        return []
    round_state = game["round_state"]
    seat = game["human_seat"]
    if round_state["phase"] == "ROUND_END":
        return [ActionChoice("next_round", "next_round", seat, "下一局")]
    if round_state["phase"] == "DISCARD" and round_state["turn_seat"] == seat:
        return build_turn_actions(game, seat)
    if round_state["phase"] == "REACTION":
        actions = build_reaction_actions(game, seat)
        if actions:
            actions.append(ActionChoice("pass", "pass", seat, "过"))
        return actions
    return []


def build_public_state(game: dict[str, Any]) -> dict[str, Any]:
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
            prompt = f"请响应 {game['players'][discard['seat']]['name']} 打出的 {tile_label(discard['tile'])}。"
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
        "human_hand": copy_public_tiles(round_state["hands"][game["human_seat"]], True),
        "dora_indicators": [tile_label(tile) for tile in current_dora_indicators(round_state)],
        "last_discard": None
        if round_state["last_discard"] is None
        else {"seat": round_state["last_discard"]["seat"], "tile": tile_label(round_state["last_discard"]["tile"])},
        "legal_actions": [action.to_dict() for action in legal_actions_for_human(game)],
        "prompt": prompt,
        "log_tail": game["action_log"][-settings.replay_tail_limit :],
        "replay_steps": len(game["snapshots"]),
        "round_result": deepcopy(round_state["round_result"]),
        "hint": build_hint_block(game),
    }


def record_action(game: dict[str, Any], seat: int, action_type: str, *, tile_id: int | None = None, details: str = "") -> None:
    round_state = game["round_state"]
    entry = {
        "seq": len(game["action_log"]) + 1,
        "round": round_label(round_state["prevalent_wind"], round_state["hand_number"], round_state["honba"]),
        "seat": seat,
        "actor": "SYSTEM" if seat < 0 else game["players"][seat]["name"],
        "type": action_type,
        "tile": tile_label(tile_id) if tile_id is not None else "",
        "details": details,
        "timestamp": now_iso(),
        "state_hash": state_hash(round_state),
    }
    game["action_log"].append(entry)
    game["public_state"] = build_public_state(game)
    game["snapshots"].append({"seq": entry["seq"], "type": action_type, "round": entry["round"], "state": deepcopy(game["public_state"])})


def build_round(game: dict[str, Any]) -> dict[str, Any]:
    ensure_game_defaults(game)
    count = player_count(game["mode"])
    round_cursor = game["round_cursor"]
    prevalent = "E" if round_cursor < count else "S"
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


def should_call_open(game: dict[str, Any], seat: int, action: ActionChoice, level: int) -> bool:
    round_state = game["round_state"]
    if action.type == "ron":
        return True
    if action.type == "open_kan" and level < 3:
        return False
    current_concealed = list(round_state["hands"][seat])
    try:
        current_shanten = shanten_calculator.calculate_shanten(to_34_array(current_concealed))
    except ValueError:
        current_shanten = 8
    new_concealed = list(current_concealed)
    pop_specific_tiles(new_concealed, action.consumed_ids)
    try:
        next_shanten = shanten_calculator.calculate_shanten(to_34_array(new_concealed))
    except ValueError:
        next_shanten = 8
    called_type = tile_type(action.tile_id or 0)
    is_value_honor = called_type in {
        round_state["wind_type_map"][seat_wind_label(round_state, seat)],
        round_state["wind_type_map"][round_state["prevalent_wind"]],
        31,
        32,
        33,
    }
    tanyao_track = all(is_simple(tile_type(tile)) for tile in new_concealed + [action.tile_id or 0] if tile_type(tile) < 34)
    if level == 1:
        return False
    if level == 2:
        return next_shanten < current_shanten and (is_value_honor or tanyao_track)
    if is_value_honor and next_shanten <= current_shanten:
        return True
    if action.type == "chi":
        return next_shanten < current_shanten and tanyao_track
    return next_shanten <= current_shanten and (tanyao_track or current_shanten <= 1)


def choose_ai_turn_action(game: dict[str, Any], seat: int) -> tuple[ActionChoice, str]:
    level = game["players"][seat]["ai_level"]
    actions = build_turn_actions(game, seat)
    for action in actions:
        if action.type == "tsumo":
            return action, "检测到可和牌，选择自摸。"
    abortive_draw_action = next((action for action in actions if action.type == "abortive_draw"), None)
    if abortive_draw_action is not None:
        try:
            shanten_value = shanten_calculator.calculate_shanten(to_34_array(game["round_state"]["hands"][seat]))
        except ValueError:
            shanten_value = 8
        if (level == 1 and shanten_value >= 4) or (level >= 2 and shanten_value >= 5):
            return abortive_draw_action, "起手幺九牌过多，选择九种九牌流局。"
    if game["mode"] == "3P":
        for action in actions:
            if action.type == "kita":
                return action, "北牌可转为拔北宝牌。"
    if level >= 3:
        for action in actions:
            if action.type == "closed_kan":
                return action, "局面安全，选择暗杠增加打点。"
    riichi_actions = [action for action in actions if action.type == "riichi"]
    if riichi_actions:
        profiles = {action.tile_id: discard_profile(game, seat, action.tile_id or 0, level) for action in riichi_actions}
        best_riichi = max(riichi_actions, key=lambda item: profiles[item.tile_id]["score"])
        profile = profiles[best_riichi.tile_id]
        if level == 1 and profile["ukeire"] >= 3:
            return best_riichi, f"已听牌，进张 {profile['ukeire']}，选择立直。"
        if level == 2 and profile["ukeire"] >= 4 and profile["risk"] <= 1.2:
            return best_riichi, f"听牌质量不错，进张 {profile['ukeire']}，选择立直。"
        if level >= 3 and (profile["ukeire"] >= 4 or game["players"][seat]["points"] < max(p["points"] for p in game["players"])):
            return best_riichi, f"需要施压，进张 {profile['ukeire']}，选择立直。"
    discard_actions = [action for action in actions if action.type == "discard"]
    profiles = sorted_discard_profiles(game, seat, level)
    profile_lookup = {profile["tile_id"]: profile for profile in profiles}
    chosen_discard = max(discard_actions, key=lambda item: profile_lookup[item.tile_id]["score"])
    profile = profile_lookup[chosen_discard.tile_id]
    reason = f"L{level} 选择 {profile['tile_label']} | 向听 {profile['shanten']} | 进张 {profile['ukeire']} | 危险度 {profile['risk']}"
    return chosen_discard, reason


def choose_ai_reaction(game: dict[str, Any]) -> tuple[ActionChoice | None, str | None]:
    round_state = game["round_state"]
    count = round_state["player_count"]
    for seat in range(count):
        if seat == game["human_seat"]:
            continue
        reactions = build_reaction_actions(game, seat)
        if any(action.type == "ron" for action in reactions):
            return None, "ron"
    for seat in range(count):
        if seat == game["human_seat"]:
            continue
        level = game["players"][seat]["ai_level"]
        seat_choices = build_reaction_actions(game, seat)
        seat_choices = [choice for choice in seat_choices if choice.type != "ron"]
        seat_choices.sort(
            key=lambda item: (-ACTION_PRIORITY.get(item.type, 0), seat_distance(round_state["last_discard"]["seat"], seat, count))
        )
        for action in seat_choices:
            if should_call_open(game, seat, action, level):
                return action, f"L{level} 选择{action.label}来提升节奏。"
    return None, None


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
    round_state["last_discard"] = None
    round_state["pending_abortive_draw"] = None
    round_state["reaction_passed"] = [False] * round_state["player_count"]
    round_state["turn_seat"] = next_seat(round_state["turn_seat"], round_state["player_count"])
    draw_from_live_wall(game, round_state["turn_seat"])


def apply_discard(game: dict[str, Any], seat: int, tile_id: int, *, declare_riichi: bool = False) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    flush_pending_kan_dora(round_state)
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
    if action_type in {"open_kan", "closed_kan", "added_kan"}:
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
        if should_abort_for_four_kans(round_state):
            settle_abortive_draw(game, "SUUKAIKAN")
            return
        draw_from_rinshan(game, seat, "岭上摸牌")
    else:
        record_action(game, seat, action_type.upper(), tile_id=discard_tile_id, details={"chi": "吃牌", "pon": "碰牌"}[action_type])


def perform_kita(game: dict[str, Any], seat: int, tile_id: int) -> None:
    begin_kita_reaction(game, seat, tile_id)


def build_ron_winners(game: dict[str, Any], include_human: bool) -> list[int]:
    round_state = game["round_state"]
    winners = []
    for seat in range(round_state["player_count"]):
        if seat == round_state["last_discard"]["seat"]:
            continue
        if not include_human and seat == game["human_seat"]:
            continue
        if any(action.type == "ron" for action in build_reaction_actions(game, seat)):
            winners.append(seat)
    if HEAD_BUMP_ENABLED and winners:
        loser = round_state["last_discard"]["seat"]
        return [min(winners, key=lambda candidate: seat_distance(loser, candidate, round_state["player_count"]))]
    return winners


def settle_ron(game: dict[str, Any], winners: list[int]) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    loser = round_state["last_discard"]["seat"]
    discard_tile_id = round_state["last_discard"]["tile"]
    count = round_state["player_count"]
    ordered = sorted(winners, key=lambda seat: seat_distance(loser, seat, count))
    honba_recipient = ordered[0] if ordered else None
    riichi_discard_ron = bool(round_state["discards"][loser] and round_state["discards"][loser][-1].get("riichi", False))
    available_riichi_sticks = max(0, round_state["riichi_sticks"] - (1 if riichi_discard_ron else 0))
    score_changes = [0] * count
    winner_details = []
    for seat in ordered:
        evaluation = evaluate_hand(game, seat, discard_tile_id, is_tsumo=False, kyoutaku_override=0)
        if evaluation is None:
            continue
        liability = liability_context(game, seat, evaluation)
        liability_details = None
        payment_details: list[dict[str, Any]] = []
        honba_value = full_honba_value(game, is_tsumo=False) if seat == honba_recipient else 0
        if liability is not None:
            liable_seat = liability["liable_seat"]
            liability_cost = calculate_limit_hand_cost(game, seat, han=liability["liable_han"], is_tsumo=False, honba=0)
            liability_amount = liability_cost["main"]
            if liable_seat == loser:
                score_changes[loser] -= liability_amount + honba_value
                append_payment_detail(
                    game,
                    payment_details,
                    from_seat=loser,
                    amount=liability_amount + honba_value,
                    kind="liability_full",
                )
            else:
                share = liability_amount // 2
                score_changes[liable_seat] -= share + honba_value
                score_changes[loser] -= share
                append_payment_detail(
                    game,
                    payment_details,
                    from_seat=liable_seat,
                    amount=share + honba_value,
                    kind="liability_share",
                )
                append_payment_detail(game, payment_details, from_seat=loser, amount=share, kind="liability_share")
            score_changes[seat] += liability_amount + honba_value
            if liability["remainder_han"] >= 13:
                remainder_cost = calculate_limit_hand_cost(game, seat, han=liability["remainder_han"], is_tsumo=False, honba=0)
                score_changes[loser] -= remainder_cost["main"]
                score_changes[seat] += remainder_cost["main"]
                append_payment_detail(game, payment_details, from_seat=loser, amount=remainder_cost["main"], kind="discard_ron")
            liability_details = {
                "liable_seat": liable_seat,
                "liable_name": game["players"][liable_seat]["name"],
                "keys": liability["keys"],
                "mode": "split",
            }
        else:
            amount = evaluation["cost"]["main"] + honba_value
            score_changes[seat] += amount
            score_changes[loser] -= amount
            append_payment_detail(game, payment_details, from_seat=loser, amount=amount, kind="discard_ron")
        winner_details.append(
            {
                "seat": seat,
                "name": game["players"][seat]["name"],
                "han": evaluation["han"],
                "fu": evaluation["fu"],
                "yaku": evaluation["yaku"],
                "yaku_level": evaluation["cost"].get("yaku_level"),
                "fu_details": evaluation.get("fu_details", []),
                "is_tsumo": evaluation.get("is_tsumo", False),
                "win_tile_label": evaluation.get("win_tile_label"),
                "payments": payment_details,
                "amount": score_changes[seat],
                "liability": liability_details,
            }
        )
    if riichi_discard_ron:
        score_changes[loser] += 1000
    if ordered:
        score_changes[ordered[0]] += available_riichi_sticks * 1000
        if winner_details and available_riichi_sticks > 0:
            append_payment_detail(
                game,
                winner_details[0]["payments"],
                from_seat=None,
                amount=available_riichi_sticks * 1000,
                kind="riichi_bonus",
            )
    for seat, delta in enumerate(score_changes):
        game["players"][seat]["points"] += delta
    dealer = round_state["dealer_seat"]
    dealer_continues = dealer in ordered
    game["honba"] = game["honba"] + 1 if dealer_continues else 0
    game["riichi_sticks"] = 0
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = None
    round_state["pending_kita"] = None
    round_state["pending_dora_reveals"] = 0
    round_state["round_result"] = {
        "kind": "RON",
        "headline": f"{' / '.join(game['players'][seat]['name'] for seat in ordered)} 荣和！",
        "winners": winner_details,
        "loser": game["players"][loser]["name"],
        "score_changes": score_changes,
    }
    round_state["phase"] = "ROUND_END"
    round_state["riichi_sticks"] = 0
    record_action(game, -1, "RON", tile_id=discard_tile_id, details=round_state["round_result"]["headline"])
    finalize_round(game, dealer_continues=dealer_continues)


def settle_tsumo(game: dict[str, Any], seat: int) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    win_tile = round_state["current_draw"]
    evaluation = evaluate_hand(game, seat, win_tile, is_tsumo=True, kyoutaku_override=0)
    if evaluation is None:
        return
    count = round_state["player_count"]
    score_changes = [0] * count
    liability = liability_context(game, seat, evaluation)
    liability_details = None
    payment_details: list[dict[str, Any]] = []
    if liability is not None:
        liable_seat = liability["liable_seat"]
        liability_cost = calculate_limit_hand_cost(game, seat, han=liability["liable_han"], is_tsumo=True, honba=0)
        liability_amount = sum(tsumo_payment_map(game, seat, liability_cost).values()) + full_honba_value(game, is_tsumo=True)
        score_changes[liable_seat] -= liability_amount
        score_changes[seat] += liability_amount
        append_payment_detail(game, payment_details, from_seat=liable_seat, amount=liability_amount, kind="liability_full")
        if liability["remainder_han"] >= 13:
            remainder_cost = calculate_limit_hand_cost(game, seat, han=liability["remainder_han"], is_tsumo=True, honba=0)
            apply_tsumo_payments(game, seat, remainder_cost, score_changes, payment_details, kind="tsumo")
        liability_details = {
            "liable_seat": liable_seat,
            "liable_name": game["players"][liable_seat]["name"],
            "keys": liability["keys"],
            "mode": "full",
        }
    else:
        apply_tsumo_payments(game, seat, evaluation["cost"], score_changes, payment_details, kind="tsumo")
    score_changes[seat] += round_state["riichi_sticks"] * 1000
    append_payment_detail(
        game,
        payment_details,
        from_seat=None,
        amount=round_state["riichi_sticks"] * 1000,
        kind="riichi_bonus",
    )
    for idx, delta in enumerate(score_changes):
        game["players"][idx]["points"] += delta
    dealer = round_state["dealer_seat"]
    game["honba"] = game["honba"] + 1 if seat == dealer else 0
    game["riichi_sticks"] = 0
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = None
    round_state["pending_kita"] = None
    round_state["pending_dora_reveals"] = 0
    round_state["riichi_sticks"] = 0
    round_state["round_result"] = {
        "kind": "TSUMO",
        "headline": f"{game['players'][seat]['name']} 自摸！",
        "winners": [
            {
                "seat": seat,
                "name": game["players"][seat]["name"],
                "han": evaluation["han"],
                "fu": evaluation["fu"],
                "yaku": evaluation["yaku"],
                "yaku_level": evaluation["cost"].get("yaku_level"),
                "fu_details": evaluation.get("fu_details", []),
                "is_tsumo": evaluation.get("is_tsumo", False),
                "win_tile_label": evaluation.get("win_tile_label"),
                "payments": payment_details,
                "amount": score_changes[seat],
                "liability": liability_details,
            }
        ],
        "score_changes": score_changes,
    }
    round_state["phase"] = "ROUND_END"
    record_action(game, seat, "TSUMO", tile_id=win_tile, details=round_state["round_result"]["headline"])
    finalize_round(game, dealer_continues=seat == dealer)


def settle_nagashi_mangan(game: dict[str, Any], winners: list[int]) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    count = round_state["player_count"]
    score_changes = [0] * count
    ordered = sorted(winners, key=lambda seat: seat_distance(round_state["dealer_seat"], seat, count))
    winner_details = []
    for seat in ordered:
        payment_details: list[dict[str, Any]] = []
        cost = calculate_limit_hand_cost(game, seat, han=5, is_tsumo=True, honba=round_state["honba"])
        apply_tsumo_payments(game, seat, cost, score_changes, payment_details, kind="tsumo")
        winner_details.append(
            {
                "seat": seat,
                "name": game["players"][seat]["name"],
                "han": 5,
                "fu": 30,
                "yaku": ["Nagashi mangan 5 han"],
                "yaku_level": "mangan",
                "payments": payment_details,
                "amount": 0,
                "liability": None,
            }
        )
    for idx, delta in enumerate(score_changes):
        game["players"][idx]["points"] += delta
    if ordered:
        score_changes[ordered[0]] += round_state["riichi_sticks"] * 1000
        if winner_details:
            append_payment_detail(
                game,
                winner_details[0]["payments"],
                from_seat=None,
                amount=round_state["riichi_sticks"] * 1000,
                kind="riichi_bonus",
            )
            game["players"][ordered[0]]["points"] += round_state["riichi_sticks"] * 1000
    for detail in winner_details:
        detail["amount"] += score_changes[detail["seat"]]

    tenpai = calculate_tenpai_seats(game)
    dealer_continues = round_state["dealer_seat"] in tenpai
    game["honba"] += 1
    game["riichi_sticks"] = 0
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = None
    round_state["pending_kita"] = None
    round_state["pending_dora_reveals"] = 0
    round_state["riichi_sticks"] = 0
    round_state["round_result"] = {
        "kind": "DRAW",
        "subtype": "NAGASHI_MANGAN",
        "headline": f"{' / '.join(game['players'][seat]['name'] for seat in winners)} 流局满贯",
        "winners": winner_details,
        "tenpai": [game["players"][seat]["name"] for seat in tenpai],
        "score_changes": score_changes,
    }
    round_state["phase"] = "ROUND_END"
    record_action(game, -1, "DRAW_END", details=round_state["round_result"]["headline"])
    finalize_round(game, dealer_continues=dealer_continues)


def settle_exhaustive_draw(game: dict[str, Any]) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    count = round_state["player_count"]
    nagashi_winners = nagashi_mangan_winners(round_state)
    if nagashi_winners:
        settle_nagashi_mangan(game, nagashi_winners)
        return
    tenpai = calculate_tenpai_seats(game)
    score_changes = [0] * count
    total = NOTEN_PAYMENTS[game["mode"]]
    if tenpai and len(tenpai) != count:
        noten = [seat for seat in range(count) if seat not in tenpai]
        gain = total // len(tenpai)
        loss = total // len(noten)
        for seat in tenpai:
            score_changes[seat] += gain
        for seat in noten:
            score_changes[seat] -= loss
    for idx, delta in enumerate(score_changes):
        game["players"][idx]["points"] += delta
    dealer_continues = round_state["dealer_seat"] in tenpai
    game["honba"] += 1
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = None
    round_state["pending_kita"] = None
    round_state["pending_dora_reveals"] = 0
    round_state["round_result"] = {
        "kind": "DRAW",
        "headline": "荒牌流局。",
        "tenpai": [game["players"][seat]["name"] for seat in tenpai],
        "score_changes": score_changes,
    }
    round_state["phase"] = "ROUND_END"
    record_action(game, -1, "DRAW_END", details=round_state["round_result"]["headline"])
    finalize_round(game, dealer_continues=dealer_continues)


def finalize_round(game: dict[str, Any], *, dealer_continues: bool) -> None:
    ensure_game_defaults(game)
    current_cursor = game["round_cursor"]
    base_rounds = game["base_rounds"]
    max_rounds = game["max_rounds"]
    in_extra_round = current_cursor >= base_rounds

    if any(player["points"] < 0 for player in game["players"]):
        finish_game(game)
        return

    if should_auto_stop_all_last_dealer(game, dealer_continues=dealer_continues):
        finish_game(game)
        return

    if not dealer_continues:
        game["round_cursor"] += 1

    if game["round_cursor"] >= max_rounds:
        finish_game(game)
        return

    if current_cursor < base_rounds - 1:
        return

    if in_extra_round:
        if is_win_like_round_result(game) and goal_score_reached(game):
            finish_game(game)
        return

    if not dealer_continues and goal_score_reached(game):
        finish_game(game)


def finish_game(game: dict[str, Any]) -> None:
    ensure_game_defaults(game)
    leftover_riichi = game.get("riichi_sticks", 0)
    if leftover_riichi > 0:
        top_player = min(
            game["players"],
            key=lambda player: (-player["points"], player["seat"]),
        )
        top_player["points"] += leftover_riichi * 1000
        game["riichi_sticks"] = 0
        if game.get("round_state"):
            game["round_state"]["riichi_sticks"] = 0
    placements = sorted(
        [
            {"seat": player["seat"], "name": player["name"], "points": player["points"], "is_human": player["is_human"]}
            for player in game["players"]
        ],
        key=lambda item: (-item["points"], item["seat"]),
    )
    for placement, entry in enumerate(placements, start=1):
        entry["placement"] = placement
    game["status"] = "FINISHED"
    game["result_summary"] = {
        "placements": placements,
        "finished_at": now_iso(),
        "leftover_riichi_bonus": leftover_riichi * 1000,
    }
    game["public_state"] = build_public_state(game)


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
                forced_discards = [action for action in human_actions if action.type == "discard"]
                if round_state["riichi"][seat] and len(human_actions) == 1 and len(forced_discards) == 1:
                    execute_action(game, forced_discards[0].action_id, actor_seat=seat, advance=False)
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


def execute_action(
    game: dict[str, Any], action_id: str, *, actor_seat: int | None = None, advance: bool = True
) -> dict[str, Any]:
    ensure_game_defaults(game)
    seat = actor_seat if actor_seat is not None else game["human_seat"]
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
            if not is_kita_north_exception(round_state, round_state.get("last_discard")):
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
