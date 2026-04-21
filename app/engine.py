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


def ai_level_policy(level: int) -> dict[str, Any]:
    return AI_LEVEL_POLICIES.get(level, AI_LEVEL_POLICIES[2])


def ai_roll(game: dict[str, Any], seat: int, salt: str) -> float:
    seed = stable_seed(game.get("seed", ""), game.get("round_cursor", 0), len(game.get("action_log", [])), seat, salt)
    return seed / float(0xFFFFFFFFFFFFFFFF)


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


def is_tile_type_legal_in_mode(tile_index: int, mode: str) -> bool:
    return mode != "3P" or tile_index not in SANMA_REMOVED_MANZU_TYPES


def legal_tile_types_for_mode(mode: str) -> list[int]:
    return [tile_index for tile_index in range(34) if is_tile_type_legal_in_mode(tile_index, mode)]


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
        for tile_index in SANMA_REMOVED_MANZU_TYPES:
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


def tenpai_wait_tile_types(concealed_tiles: list[int], *, mode: str = "4P") -> set[int]:
    try:
        if shanten_calculator.calculate_shanten(to_34_array(concealed_tiles)) != 0:
            return set()
    except ValueError:
        return set()

    grouped = counts_by_type(concealed_tiles)
    waits: set[int] = set()
    for tile_index in legal_tile_types_for_mode(mode):
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
        if tenpai_wait_tile_types(round_state["hands"][seat], mode=game["mode"]):
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
    return tenpai_wait_tile_types(concealed_tiles, mode=game["mode"])


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


def unique_tile_type_candidates(tiles: list[int]) -> list[int]:
    candidates: list[int] = []
    seen_types: set[tuple[int, bool]] = set()
    for tile_id in sort_tiles(tiles):
        key = (tile_type(tile_id), is_red(tile_id))
        if key in seen_types:
            continue
        seen_types.add(key)
        candidates.append(tile_id)
    return candidates


def effective_tiles_after_discard(
    game: dict[str, Any],
    seat: int,
    source_tiles: list[int],
    discard_tile_id: int,
    *,
    base_shanten: int | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    tiles = list(source_tiles)
    if discard_tile_id not in tiles:
        return 0, []
    tiles.remove(discard_tile_id)
    counts = to_34_array(tiles)
    visible_counts = visible_tile_type_counts(game, seat, hand_tiles=tiles)
    ukeire = 0
    good_tiles: list[dict[str, Any]] = []
    if base_shanten is None:
        try:
            base_shanten = shanten_calculator.calculate_shanten(counts)
        except ValueError:
            base_shanten = 8
    for tile_index in legal_tile_types_for_mode(game["mode"]):
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
            good_tiles.append(
                {
                    "type": tile_index,
                    "label": tile_type_label(tile_index),
                    "remaining": remaining,
                }
            )
    return ukeire, good_tiles


def wait_count_after_discard(game: dict[str, Any], seat: int, discard_tile_id: int) -> tuple[int, list[str]]:
    round_state = game["round_state"]
    ukeire, good_tiles = effective_tiles_after_discard(game, seat, round_state["hands"][seat], discard_tile_id)
    return ukeire, [item["label"] for item in good_tiles]


def wait_shape_label(wait_types: set[int]) -> str:
    if not wait_types:
        return "\u65e0\u8fdb\u5f20"
    suited_waits = sorted(wait for wait in wait_types if wait < 27)
    if len(wait_types) >= 3:
        return "\u591a\u9762\u542c\u724c"
    if len(wait_types) >= 2:
        for left in suited_waits:
            if left + 3 in suited_waits and left // 9 == (left + 3) // 9:
                return "\u4e24\u9762\u542c\u724c"
        return "\u597d\u578b\u542c\u724c"
    wait = next(iter(wait_types))
    if is_honor(wait):
        return "\u5b57\u724c\u5355\u9a91"
    if is_terminal(wait):
        return "\u8fb9\u5f20/\u5355\u9a91"
    return "\u574e\u5f20/\u5355\u9a91"


def shape_quality_profile(
    game: dict[str, Any],
    seat: int,
    tiles_after_discard: list[int],
    shanten_value: int,
    ukeire: int,
    good_tiles: list[dict[str, Any]],
    level: int,
) -> dict[str, Any]:
    policy = ai_level_policy(level)
    level_scale = 0.35 if level == 1 else 0.72 if level == 2 else 1.0
    level_scale = min(level_scale, float(policy["strategy_scale"]) + 0.15)
    dora_types = {dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(game["round_state"])}
    good_types = {int(item["type"]) for item in good_tiles}

    shape_ev = 0.0
    quality = 0.0
    label = "\u8fdb\u5f20\u4e00\u822c"
    if shanten_value == 0:
        wait_types = tenpai_wait_tile_types(tiles_after_discard, mode=game["mode"]) or good_types
        label = wait_shape_label(wait_types)
        wait_count = len(wait_types)
        suited_count = sum(1 for wait in wait_types if wait < 27)
        remaining_bonus = min(9.0, ukeire * 0.38)
        shape_ev += remaining_bonus
        quality += min(1.0, ukeire / 10)
        if wait_count >= 3:
            shape_ev += 16.0
            quality += 0.55
        elif wait_count >= 2:
            shape_ev += 10.0
            quality += 0.38
        else:
            shape_ev -= 8.0
            quality -= 0.28
        if suited_count == 0:
            shape_ev -= 3.5
        if wait_types and all(is_terminal(wait) or is_honor(wait) for wait in wait_types):
            shape_ev -= 3.0
        if wait_types & dora_types:
            shape_ev += 4.5
    elif shanten_value == 1:
        if ukeire >= 24:
            label = "\u5bbd\u4e00\u5411\u542c"
            shape_ev += 8.0
            quality += 0.48
        elif ukeire >= 14:
            label = "\u666e\u901a\u4e00\u5411\u542c"
            shape_ev += 3.5
            quality += 0.24
        else:
            label = "\u7a84\u4e00\u5411\u542c"
            shape_ev -= 5.5
            quality -= 0.22
        if good_types & dora_types:
            shape_ev += 2.5
    elif shanten_value == 2:
        if ukeire >= 28:
            label = "\u8fdb\u5f20\u5bbd"
            shape_ev += 4.0
            quality += 0.22
        elif ukeire <= 10:
            label = "\u8fdb\u5f20\u7a84"
            shape_ev -= 3.5
            quality -= 0.15
        else:
            label = "\u8fdb\u5f20\u666e\u901a"
            shape_ev += 1.0
    else:
        if ukeire >= 34:
            label = "\u65e9\u5de1\u5bbd\u624b"
            shape_ev += 2.5
        elif ukeire <= 12:
            label = "\u8fdb\u5f20\u504f\u7a84"
            shape_ev -= 2.0

    shape_ev = round(max(-18.0, min(28.0, shape_ev * level_scale)), 3)
    quality = round(max(0.0, min(1.0, 0.5 + quality)), 3)
    return {
        "shape_ev": shape_ev,
        "shape_label": label,
        "wait_quality": quality,
    }


def tile_suit_index(tile_index: int) -> int | None:
    if tile_index >= 27:
        return None
    return tile_index // 9


def unique_ordered_labels(labels: list[str]) -> list[str]:
    unique: list[str] = []
    for label in labels:
        if label not in unique:
            unique.append(label)
    return unique


def empty_opponent_profile() -> dict[str, Any]:
    return {
        "threat": 0.0,
        "flush_suit": None,
        "flush_with_honors": False,
        "toitoi": False,
        "tanyao": False,
        "riichi": False,
        "value_honor_types": set(),
        "revealed_dora": 0,
        "open_meld_count": 0,
        "speed_class": "未知",
        "routes": [],
        "labels": [],
    }


def suji_safety_multiplier(tile_index: int, opponent_discards: set[int]) -> float:
    if tile_index >= 27:
        return 1.0
    rank = tile_index % 9
    safe_suji = 0
    if rank >= 3 and tile_index - 3 in opponent_discards:
        safe_suji += 1
    if rank <= 5 and tile_index + 3 in opponent_discards:
        safe_suji += 1
    if safe_suji >= 2:
        return 0.55
    if safe_suji == 1:
        return 0.68 if rank in {3, 4, 5} else 0.74
    return 1.0


def visible_wall_multiplier(tile_index: int, visible_counts: list[int]) -> float:
    visible = visible_counts[tile_index]
    multiplier = 1.0
    if visible >= 3:
        multiplier *= 0.64
    elif visible == 2:
        multiplier *= 0.84

    if tile_index < 27:
        rank = tile_index % 9
        if rank >= 1 and visible_counts[tile_index - 1] >= 4:
            multiplier *= 0.86
        if rank <= 7 and visible_counts[tile_index + 1] >= 4:
            multiplier *= 0.86
    return multiplier


def estimate_opponent_loss(game: dict[str, Any], seat: int, opponent: int, profile: dict[str, Any]) -> int:
    round_state = game["round_state"]
    open_meld_count = int(profile.get("open_meld_count", 0))
    revealed_dora = int(profile.get("revealed_dora", 0))
    routes = set(profile.get("routes", [])) | set(profile.get("labels", []))

    if profile.get("riichi"):
        estimated_loss = 5200 + revealed_dora * 1500 + round_state["nuki_count"][opponent] * 1000
    else:
        estimated_loss = 1000 + open_meld_count * 1100 + revealed_dora * 1000 + round_state["nuki_count"][opponent] * 1200
        if "快攻" in routes and len(routes) <= 2:
            estimated_loss += 700
        if "断幺" in routes:
            estimated_loss += 900
        if "役牌" in routes:
            estimated_loss += 1900
        if "对对和" in routes:
            estimated_loss += 2400
        if "混一色" in routes:
            estimated_loss += 3600
        if "清一色" in routes:
            estimated_loss += 7600
    if opponent == round_state["dealer_seat"]:
        estimated_loss = int(estimated_loss * 1.35)
    return min(32000, max(1000, estimated_loss))


def infer_open_hand_profile(game: dict[str, Any], seat: int, opponent: int) -> dict[str, Any]:
    round_state = game["round_state"]
    if opponent == seat:
        return empty_opponent_profile()

    dora_types = {dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(round_state)}
    if round_state["riichi"][opponent]:
        profile = empty_opponent_profile()
        profile.update(
            {
                "threat": round(1.0 + min(round_state["nuki_count"][opponent], 2) * 0.08, 3),
                "riichi": True,
                "revealed_dora": round_state["nuki_count"][opponent],
                "speed_class": "门清听牌",
                "routes": ["立直", "门清"],
                "labels": ["立直"],
            }
        )
        return profile

    melds = round_state["melds"][opponent]
    open_melds = [meld for meld in melds if meld["type"] in OPEN_MELD_TYPES]
    nuki_count = round_state["nuki_count"][opponent]
    if not open_melds and nuki_count <= 0:
        return empty_opponent_profile()

    threat = 0.12 + (len(open_melds) * 0.16) + (min(nuki_count, 4) * 0.12)
    triplet_types = {tile_type(meld["tiles"][0]) for meld in open_melds if meld["type"] in TRIPLET_MELD_TYPES}
    seat_wind_type = round_state["wind_type_map"][seat_wind_label(round_state, opponent)]
    prevalent_wind_type = round_state["wind_type_map"][round_state["prevalent_wind"]]
    value_honor_types = set(DRAGON_TYPES)
    value_honor_types.add(seat_wind_type)
    value_honor_types.add(prevalent_wind_type)
    labels: list[str] = []
    routes: list[str] = []
    if triplet_types & DRAGON_TYPES:
        threat += 0.24
        labels.append("役牌")
        routes.append("役牌")
    if seat_wind_type in triplet_types:
        threat += 0.16
        labels.append("役牌")
        routes.append("役牌")
    if prevalent_wind_type in triplet_types:
        threat += 0.12
        labels.append("役牌")
        routes.append("役牌")

    revealed_dora = sum(
        1
        for meld in melds
        for tile_id in meld["tiles"]
        if is_red(tile_id) or tile_type(tile_id) in dora_types
    )
    threat += min(revealed_dora, 3) * 0.05

    meld_tile_types = [tile_type(tile_id) for meld in open_melds for tile_id in meld["tiles"]]
    tanyao = bool(meld_tile_types) and all(is_simple(ttype) for ttype in meld_tile_types)
    if tanyao:
        threat += 0.08
        labels.append("断幺")
        routes.append("断幺")

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
            route = "混一色" if flush_with_honors else "清一色"
            labels.append(route)
            routes.append(route)

    toitoi = len(triplet_types) >= 2 or sum(1 for meld in open_melds if meld["type"] in TRIPLET_MELD_TYPES) >= 2
    if toitoi:
        threat += 0.1
        labels.append("对对和")
        routes.append("对对和")

    if revealed_dora:
        routes.append("宝牌")
    if nuki_count:
        labels.append("拔北")
        routes.append("拔北")

    if open_melds and not routes:
        labels.append("快攻")
        routes.append("快攻")
        threat *= 0.78

    discard_count = len(round_state["discards"][opponent])
    speed_class = "快攻" if len(open_melds) >= 2 or (open_melds and discard_count <= 8) else "副露推进"
    if "混一色" in routes or "清一色" in routes:
        speed_class = "染手"
    elif toitoi:
        speed_class = "对对"

    return {
        "threat": round(min(threat, 0.95), 3),
        "flush_suit": flush_suit,
        "flush_with_honors": flush_with_honors,
        "toitoi": toitoi,
        "tanyao": tanyao,
        "riichi": False,
        "value_honor_types": value_honor_types,
        "revealed_dora": revealed_dora,
        "open_meld_count": len(open_melds),
        "speed_class": speed_class,
        "routes": unique_ordered_labels(routes)[:4],
        "labels": unique_ordered_labels(labels)[:4],
    }


def tile_danger_against_opponent(
    game: dict[str, Any],
    seat: int,
    opponent: int,
    discard_tile_id: int,
    profile: dict[str, Any],
    visible_counts: list[int],
    *,
    dora_types: set[int] | None = None,
    estimated_loss: int | None = None,
) -> float:
    round_state = game["round_state"]
    tile_index = tile_type(discard_tile_id)
    opponent_discards = {tile_type(item["tile"]) for item in round_state["discards"][opponent]}
    if tile_index in opponent_discards:
        return 0.0

    routes = set(profile.get("routes", [])) | set(profile.get("labels", []))
    value_honor_types = set(profile.get("value_honor_types", set()))
    if is_honor(tile_index):
        tile_base = 0.92 if tile_index in value_honor_types else 0.58
        if visible_counts[tile_index] >= 2:
            tile_base *= 0.62
    elif is_terminal(tile_index):
        tile_base = 0.58
    else:
        rank = tile_index % 9
        if rank in {1, 7}:
            tile_base = 0.82
        elif rank in {2, 6}:
            tile_base = 0.96
        else:
            tile_base = 1.08

    if "断幺" in routes:
        tile_base *= 0.55 if (is_terminal(tile_index) or is_honor(tile_index)) else 1.1

    suit_index = tile_suit_index(tile_index)
    flush_suit = profile.get("flush_suit")
    if flush_suit is not None:
        if suit_index == flush_suit:
            tile_base *= 1.48 if not profile.get("flush_with_honors") else 1.32
        elif suit_index is not None:
            tile_base *= 0.42
        elif is_honor(tile_index):
            tile_base *= 1.18 if profile.get("flush_with_honors") else 0.52

    if "役牌" in routes and tile_index in value_honor_types:
        tile_base *= 1.38 if visible_counts[tile_index] <= 1 else 0.78

    if profile.get("toitoi") and (is_terminal(tile_index) or is_honor(tile_index) or tile_index in value_honor_types):
        tile_base *= 1.22

    if dora_types is None:
        dora_types = {dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(round_state)}
    if is_red(discard_tile_id) or tile_index in dora_types:
        tile_base *= 1.34

    suji_multiplier = suji_safety_multiplier(tile_index, opponent_discards)
    if profile.get("toitoi"):
        suji_multiplier = 1.0 - ((1.0 - suji_multiplier) * 0.35)
    if flush_suit is not None and suit_index == flush_suit:
        suji_multiplier = 1.0 - ((1.0 - suji_multiplier) * 0.55)
    tile_base *= suji_multiplier
    tile_base *= visible_wall_multiplier(tile_index, visible_counts)

    progress = round_progress_ratio(round_state)
    if estimated_loss is None:
        estimated_loss = estimate_opponent_loss(game, seat, opponent, profile)
    loss_scale = 0.72 + min(0.68, estimated_loss / 24000)
    if profile.get("riichi"):
        tile_base *= 1.0 + progress * 0.28
    elif profile.get("open_meld_count", 0) >= 2:
        tile_base *= 1.0 + progress * 0.18

    return max(0.0, tile_base * float(profile["threat"]) * loss_scale)


def build_tile_risk_context(
    game: dict[str, Any],
    seat: int,
    *,
    hand_tiles: list[int] | None = None,
) -> dict[str, Any]:
    round_state = game["round_state"]
    opponents: list[dict[str, Any]] = []
    for opponent in range(round_state["player_count"]):
        if opponent == seat:
            continue
        profile = infer_open_hand_profile(game, seat, opponent)
        if profile["threat"] <= 0:
            continue
        opponents.append(
            {
                "seat": opponent,
                "profile": profile,
                "estimated_loss": estimate_opponent_loss(game, seat, opponent, profile),
            }
        )
    return {
        "visible_counts": visible_tile_type_counts(game, seat, hand_tiles=hand_tiles),
        "opponents": opponents,
        "dora_types": {dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(round_state)},
    }


def tile_risk_score(
    game: dict[str, Any],
    seat: int,
    discard_tile_id: int,
    *,
    risk_context: dict[str, Any] | None = None,
) -> float:
    context = risk_context if risk_context is not None else build_tile_risk_context(game, seat)
    visible_counts = context["visible_counts"]
    threatening = context["opponents"]
    if not threatening:
        return 0.0
    base = 0.0
    for item in threatening:
        base += tile_danger_against_opponent(
            game,
            seat,
            item["seat"],
            discard_tile_id,
            item["profile"],
            visible_counts,
            dora_types=context["dora_types"],
            estimated_loss=item["estimated_loss"],
        )
    return round(base, 3)


def discard_risk_sources(
    game: dict[str, Any],
    seat: int,
    discard_tile_id: int,
    *,
    risk_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    context = risk_context if risk_context is not None else build_tile_risk_context(game, seat)
    visible_counts = context["visible_counts"]
    sources: list[dict[str, Any]] = []
    for item in context["opponents"]:
        opponent = item["seat"]
        profile = item["profile"]
        danger = tile_danger_against_opponent(
            game,
            seat,
            opponent,
            discard_tile_id,
            profile,
            visible_counts,
            dora_types=context["dora_types"],
            estimated_loss=item["estimated_loss"],
        )
        if danger <= 0:
            continue
        labels = profile.get("routes") or profile.get("labels") or [profile.get("speed_class", "推进")]
        sources.append(
            {
                "seat": opponent,
                "name": game["players"][opponent]["name"],
                "risk": round(danger, 3),
                "routes": labels[:3],
                "estimated_loss": item["estimated_loss"],
            }
        )
    return sorted(sources, key=lambda item: (-item["risk"], -item["estimated_loss"]))[:3]


def tile_safety_against_opponent(
    game: dict[str, Any],
    opponent: int,
    tile_index: int,
    profile: dict[str, Any],
    visible_counts: list[int],
) -> tuple[float, str]:
    round_state = game["round_state"]
    opponent_discards = {tile_type(item["tile"]) for item in round_state["discards"][opponent]}
    routes = set(profile.get("routes", [])) | set(profile.get("labels", []))
    value_honor_types = set(profile.get("value_honor_types", set()))

    if tile_index in opponent_discards:
        return 1.0, "现物"
    if visible_counts[tile_index] >= 4:
        return 0.88, "壁"
    if is_honor(tile_index):
        if visible_counts[tile_index] >= 3:
            return 0.82, "字牌壁"
        if visible_counts[tile_index] >= 2 and tile_index not in value_honor_types:
            return 0.66, "熟字牌"
        if tile_index not in value_honor_types and "断幺" in routes:
            return 0.56, "断幺外"
        return 0.22, "字牌危险"

    suji_multiplier = suji_safety_multiplier(tile_index, opponent_discards)
    if suji_multiplier <= 0.56:
        return 0.68, "双筋"
    if suji_multiplier <= 0.74:
        return 0.52, "筋"
    if is_terminal(tile_index):
        return 0.38, "幺九"
    if tile_index < 27:
        rank = tile_index % 9
        if rank in {1, 7}:
            return 0.3, "外侧牌"
    return 0.12, "无筋"


def defensive_discard_profile(
    game: dict[str, Any],
    seat: int,
    discard_tile_id: int,
    shanten_value: int,
    level: int,
    risk_context: dict[str, Any],
) -> dict[str, Any]:
    policy = ai_level_policy(level)
    opponents = risk_context["opponents"]
    if not opponents:
        return {
            "safety_score": 0.0,
            "safety_label": "无威胁",
            "defense_mode": False,
            "safety_ev": 0.0,
        }

    round_state = game["round_state"]
    tile_index = tile_type(discard_tile_id)
    visible_counts = risk_context["visible_counts"]
    weighted_safety = 0.0
    total_weight = 0.0
    label_weights: dict[str, float] = {}
    max_threat = 0.0
    max_loss = 0

    for item in opponents:
        profile = item["profile"]
        estimated_loss = int(item["estimated_loss"])
        threat = float(profile["threat"])
        max_threat = max(max_threat, threat)
        max_loss = max(max_loss, estimated_loss)
        weight = threat * (0.72 + min(0.85, estimated_loss / 24000))
        safety, label = tile_safety_against_opponent(game, item["seat"], tile_index, profile, visible_counts)
        weighted_safety += safety * weight
        total_weight += weight
        label_weights[label] = label_weights.get(label, 0.0) + weight

    safety_score = weighted_safety / total_weight if total_weight else 0.0
    progress = round_progress_ratio(round_state)
    pressure = max_threat + min(0.72, max_loss / 24000) + progress * 0.38
    offense_commitment = 0.58 if shanten_value <= 0 else 0.42 if shanten_value == 1 else 0.18 if shanten_value == 2 else -0.06
    level_scale = policy["defense_scale"]
    defense_need = max(0.0, pressure - offense_commitment) * level_scale
    defense_mode = defense_need >= 0.72

    safety_ev = 0.0
    if defense_need > 0:
        safety_ev = (safety_score - 0.35) * 46.0 * defense_need
        if safety_score >= 0.82 and shanten_value >= 2:
            safety_ev += 14.0 * defense_need
        if defense_mode and shanten_value >= 3:
            safety_ev += (safety_score - 0.28) * 70.0 * defense_need
        if safety_score <= 0.18 and defense_mode:
            safety_ev -= 12.0 * defense_need

    label = max(label_weights.items(), key=lambda item: item[1])[0] if label_weights else "普通"
    if defense_mode and safety_score >= 0.82:
        label = f"防守：{label}"
    elif defense_mode and safety_score <= 0.2:
        label = "高危推进"

    return {
        "safety_score": round(safety_score, 3),
        "safety_label": label,
        "defense_mode": defense_mode,
        "safety_ev": round(max(-96.0, min(120.0, safety_ev)), 3),
    }


def push_fold_profile(
    game: dict[str, Any],
    seat: int,
    *,
    shanten_value: int,
    risk: float,
    safety_score: float,
    hand_value_ev: float,
    estimated_han: float,
    wait_quality: float,
    level: int,
    risk_context: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    policy = ai_level_policy(level)
    opponents = risk_context["opponents"]
    if not opponents:
        return {
            "push_fold_ev": 0.0,
            "push_fold_label": "\u65e0\u5a01\u80c1\u63a8\u8fdb",
            "push_fold_mode": "push",
            "pressure_score": 0.0,
            "commitment_score": 0.0,
        }

    round_state = game["round_state"]
    progress = round_progress_ratio(round_state)
    max_threat = max(float(item["profile"]["threat"]) for item in opponents)
    max_loss = max(int(item["estimated_loss"]) for item in opponents)
    riichi_count = sum(1 for item in opponents if item["profile"].get("riichi"))

    pressure = (
        max_threat * 0.82
        + min(0.92, max_loss / 18000)
        + min(0.72, risk / 4.8)
        + progress * 0.42
        + riichi_count * 0.16
    )
    pressure += strategy["defense_bias"] * 0.62
    pressure -= strategy["attack_bias"] * 0.28
    pressure *= 0.72 + policy["defense_scale"] * 0.38

    if shanten_value <= 0:
        commitment = 0.92
    elif shanten_value == 1:
        commitment = 0.58
    elif shanten_value == 2:
        commitment = 0.22
    else:
        commitment = -0.06
    commitment += min(0.68, hand_value_ev / 58.0)
    commitment += wait_quality * (0.26 if shanten_value <= 1 else 0.08)
    if estimated_han >= 5:
        commitment += 0.22
    elif estimated_han >= 3:
        commitment += 0.1
    if strategy["is_dealer"] and shanten_value <= 1:
        commitment += 0.12
    if strategy["placement"] == strategy["placement_count"] and shanten_value <= 2:
        commitment += 0.16
    if strategy["is_all_last"] and strategy["placement"] == 1:
        commitment -= 0.26
    commitment += strategy["attack_bias"] * 0.42
    commitment += strategy["value_bias"] * 0.28
    commitment -= strategy["defense_bias"] * 0.36
    commitment *= 0.74 + policy["strategy_scale"] * 0.32

    margin = commitment - pressure
    if margin >= 0.28:
        mode = "push"
        label = "\u80dc\u8d1f\u624b\u5168\u62bc"
        ev = min(32.0, margin * 18.0 + max(0.0, 0.46 - risk) * 9.0)
    elif margin >= 0.02:
        mode = "lean_push"
        label = "\u4f18\u52bf\u63a8\u8fdb"
        ev = margin * 14.0 + (safety_score - 0.32) * 8.0
    elif margin >= -0.34:
        mode = "balanced"
        label = "\u8fb9\u754c\u534a\u62bc"
        ev = (safety_score - 0.42) * 28.0 + margin * 18.0
    else:
        mode = "fold"
        label = "\u4f18\u5148\u64a4\u9000" if shanten_value <= 1 else "\u5f03\u548c\u5b88\u5907"
        ev = (safety_score - 0.36) * 82.0 + margin * 20.0
        if safety_score >= 0.82:
            ev += 15.0 + min(12.0, pressure * 5.0)
        if safety_score <= 0.18:
            ev -= 16.0 + min(18.0, pressure * 6.0)

    return {
        "push_fold_ev": round(max(-72.0, min(72.0, ev)), 3),
        "push_fold_label": label,
        "push_fold_mode": mode,
        "pressure_score": round(max(0.0, min(2.5, pressure)), 3),
        "commitment_score": round(max(-0.4, min(2.4, commitment)), 3),
    }


def defense_override_profile(
    game: dict[str, Any],
    seat: int,
    *,
    shanten_value: int,
    risk: float,
    safety_score: float,
    hand_value_ev: float,
    estimated_han: float,
    wait_quality: float,
    level: int,
    risk_context: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    opponents = risk_context["opponents"]
    if level <= 1 or not opponents:
        return {"defense_override_ev": 0.0, "defense_override_mode": "", "defense_override_label": ""}

    round_state = game["round_state"]
    progress = round_progress_ratio(round_state)
    max_threat = max(float(item["profile"]["threat"]) for item in opponents)
    max_loss = max(int(item["estimated_loss"]) for item in opponents)
    riichi_count = sum(1 for item in opponents if item["profile"].get("riichi"))
    open_monster_count = sum(
        1
        for item in opponents
        if item["profile"].get("open_meld_count", 0) >= 3 or int(item["estimated_loss"]) >= 8000
    )

    pressure = (
        max_threat
        + min(0.95, max_loss / 17000)
        + min(0.72, risk / 4.2)
        + progress * 0.46
        + riichi_count * 0.24
        + open_monster_count * 0.16
        + strategy["defense_bias"] * 0.72
    )
    commitment = 0.0
    if shanten_value <= 0:
        commitment += 1.08
    elif shanten_value == 1:
        commitment += 0.62
    elif shanten_value == 2:
        commitment += 0.22
    else:
        commitment -= 0.12
    commitment += min(0.74, hand_value_ev / 54.0)
    commitment += min(0.32, max(0.0, estimated_han - 2.0) * 0.09)
    commitment += wait_quality * (0.28 if shanten_value <= 1 else 0.08)
    commitment += strategy["attack_bias"] * 0.42 + strategy["value_bias"] * 0.26
    commitment -= strategy["defense_bias"] * 0.44
    if strategy["is_all_last"] and strategy["placement"] == 1:
        commitment -= 0.34
    if strategy["placement"] == strategy["placement_count"] and shanten_value <= 1:
        commitment += 0.22

    fold_need = pressure - commitment
    if fold_need < (0.5 if level >= 3 else 0.72):
        return {
            "defense_override_ev": 0.0,
            "defense_override_mode": "",
            "defense_override_label": "",
            "fold_need": round(fold_need, 3),
        }

    ev = 0.0
    mode = "soft_fold"
    label = "谨慎押退"
    if shanten_value >= 2:
        mode = "hard_fold"
        label = "强制弃和"
        ev += 18.0 + fold_need * 18.0
    elif shanten_value == 1 and estimated_han < 3 and wait_quality < 0.62:
        mode = "hard_fold"
        label = "一向听撤退"
        ev += 10.0 + fold_need * 14.0
    elif shanten_value <= 0 and estimated_han >= 4 and wait_quality >= 0.62:
        # Good tenpai hands may still push, but unsafe tiles are punished below.
        mode = "push_guard"
        label = "听牌谨慎押"
        ev += fold_need * 4.0
    else:
        ev += fold_need * 9.0

    if safety_score >= 0.92:
        ev += 32.0 + min(18.0, pressure * 6.0)
    elif safety_score >= 0.78:
        ev += 22.0 + min(12.0, pressure * 4.0)
    elif safety_score >= 0.58 and risk <= 0.55:
        ev += 10.0
    elif safety_score <= 0.2 or risk >= 1.45:
        ev -= 34.0 + min(24.0, pressure * 7.0)

    if riichi_count and shanten_value >= 1 and safety_score >= 0.78:
        ev += 12.0
    if max_loss >= 12000 and safety_score <= 0.35:
        ev -= 18.0
    if level == 2:
        ev *= 0.72

    return {
        "defense_override_ev": round(max(-82.0, min(104.0, ev)), 3),
        "defense_override_mode": mode,
        "defense_override_label": label,
        "fold_need": round(fold_need, 3),
    }


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

    if game["mode"] == "3P":
        for tile_index in SANMA_REMOVED_MANZU_TYPES:
            counts[tile_index] = 4

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


def rough_points_from_han(game: dict[str, Any], seat: int, estimated_han: float) -> int:
    dealer = seat == game["round_state"]["dealer_seat"]
    han = int(max(1, round(estimated_han)))
    if han >= 13:
        return 48000 if dealer else 32000
    if han >= 11:
        return 36000 if dealer else 24000
    if han >= 8:
        return 24000 if dealer else 16000
    if han >= 6:
        return 18000 if dealer else 12000
    if han >= 5:
        return 12000 if dealer else 8000
    if han == 4:
        return 11600 if dealer else 7700
    if han == 3:
        return 5800 if dealer else 3900
    if han == 2:
        return 2900 if dealer else 2000
    return 1500 if dealer else 1000


def hand_value_label(estimated_han: float, estimated_points: int) -> str:
    if estimated_han >= 13:
        return "\u5f79\u6ee1\u7ea7"
    if estimated_han >= 11:
        return "\u4e09\u500d\u6ee1\u7ea7"
    if estimated_han >= 8:
        return "\u500d\u6ee1\u7ea7"
    if estimated_han >= 6:
        return "\u8df3\u6ee1\u7ea7"
    if estimated_han >= 5 or estimated_points >= 7700:
        return "\u6ee1\u8d2f\u7ea7"
    if estimated_han >= 3:
        return "\u4e2d\u6253\u70b9"
    if estimated_han >= 2:
        return "\u4f4e\u4e2d\u6253\u70b9"
    return "\u4f4e\u6253\u70b9"


def hand_value_profile(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    *,
    shanten_value: int,
    routes: list[str],
    wait_quality: float,
) -> dict[str, Any]:
    round_state = game["round_state"]
    melds = [meld for meld in round_state["melds"][seat] if meld["type"] != "kita"]
    closed = is_closed_hand(round_state, seat)
    all_tiles = list(concealed_tiles)
    for meld in melds:
        all_tiles.extend(meld["tiles"])
    all_types = [tile_type(tile_id) for tile_id in all_tiles]
    dora_types = {dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(round_state)}
    dora_count = sum(1 for tile_id in all_tiles if is_red(tile_id) or tile_type(tile_id) in dora_types)
    if game["mode"] == "3P":
        dora_count += round_state["nuki_count"][seat]

    route_set = set(routes)
    estimated_han = float(dora_count)
    route_labels: list[str] = []
    if "\u65ad\u5e7a" in route_set:
        estimated_han += 1
        route_labels.append("\u65ad\u5e7a")
    if "\u5f79\u724c" in route_set:
        estimated_han += 1
        route_labels.append("\u5f79\u724c")
    if "\u4e03\u5bf9\u5b50" in route_set:
        estimated_han += 2
        route_labels.append("\u4e03\u5bf9")
    if "\u5bf9\u5bf9\u548c" in route_set:
        estimated_han += 2
        route_labels.append("\u5bf9\u5bf9")
    if "\u6df7\u4e00\u8272" in route_set:
        estimated_han += 3 if closed else 2
        route_labels.append("\u6df7\u4e00\u8272")
    if "\u6e05\u4e00\u8272" in route_set:
        estimated_han += 6 if closed else 5
        route_labels.append("\u6e05\u4e00\u8272")
    if closed and shanten_value == 0 and game["players"][seat]["points"] >= 1000 and len(round_state["live_wall"]) >= 4:
        estimated_han += 1.45 + max(0.0, wait_quality - 0.5) * 0.8
        route_labels.append("\u7acb\u76f4\u671f\u5f85")
    elif closed and shanten_value == 1:
        estimated_han += 0.45
    if not route_labels and dora_count:
        route_labels.append("\u5b9d\u724c")

    if estimated_han <= 0:
        estimated_han = 0.35 if shanten_value <= 1 else 0.15
    estimated_points = rough_points_from_han(game, seat, estimated_han)
    value_scale = 1.0 if shanten_value <= 1 else 0.72 if shanten_value == 2 else 0.42
    hand_value_ev = max(0.0, min(38.0, (estimated_points - 1200) / 360.0)) * value_scale
    if dora_count >= 2 and shanten_value <= 2:
        hand_value_ev += 3.5
    if estimated_han >= 5 and shanten_value <= 2:
        hand_value_ev += 5.0

    return {
        "estimated_han": round(estimated_han, 2),
        "estimated_value": estimated_points,
        "value_label": hand_value_label(estimated_han, estimated_points),
        "value_routes": unique_ordered_labels(route_labels)[:3],
        "dora_count": dora_count,
        "hand_value_ev": round(max(0.0, min(46.0, hand_value_ev)), 3),
    }


def round_progress_ratio(round_state: dict[str, Any]) -> float:
    initial_live_tiles = 69 if round_state["player_count"] == 4 else 50
    remaining = len(round_state.get("live_wall", []))
    return max(0.0, min(1.0, 1.0 - (remaining / initial_live_tiles)))


def opponent_models(game: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    round_state = game["round_state"]
    models: list[dict[str, Any]] = []
    for opponent in range(round_state["player_count"]):
        if opponent == seat:
            continue
        profile = infer_open_hand_profile(game, seat, opponent)
        if profile["threat"] <= 0:
            continue
        estimated_loss = estimate_opponent_loss(game, seat, opponent, profile)

        models.append(
            {
                "seat": opponent,
                "threat": profile["threat"],
                "labels": profile["labels"],
                "routes": profile.get("routes", []),
                "speed_class": profile.get("speed_class", "未知"),
                "open_meld_count": profile.get("open_meld_count", 0),
                "revealed_dora": profile.get("revealed_dora", 0),
                "estimated_loss": estimated_loss,
            }
        )
    return models


def placement_strategy_context(game: dict[str, Any], seat: int) -> dict[str, Any]:
    ensure_game_defaults(game)
    round_state = game["round_state"]
    players = game["players"]
    standings = sorted(players, key=lambda player: (-player["points"], player["seat"]))
    placement_by_seat = {player["seat"]: index + 1 for index, player in enumerate(standings)}
    placement = placement_by_seat[seat]
    own_points = players[seat]["points"]
    count = len(players)
    above_points = standings[placement - 2]["points"] if placement > 1 else own_points
    below_points = standings[placement]["points"] if placement < count else own_points
    top_points = standings[0]["points"]
    bottom_points = standings[-1]["points"]
    gap_to_above = max(0, above_points - own_points)
    lead_to_below = max(0, own_points - below_points)
    gap_to_top = max(0, top_points - own_points)
    lead_to_bottom = max(0, own_points - bottom_points)
    rounds_remaining = max(0, game["base_rounds"] - game["round_cursor"] - 1)
    is_all_last = game["round_cursor"] >= game["base_rounds"] - 1
    is_late = rounds_remaining <= max(1, count // 2)
    is_extra = game["round_cursor"] >= game["base_rounds"]
    is_dealer = seat == round_state["dealer_seat"]
    over_target = own_points >= game["target_score"]

    attack_bias = 0.0
    defense_bias = 0.0
    value_bias = 0.0
    riichi_bias = 0.0
    call_bias = 0.0
    labels: list[str] = []

    if placement == 1:
        labels.append("守位")
        defense_bias += 0.18 + min(0.32, lead_to_below / 24000)
        attack_bias -= 0.08
        riichi_bias -= 0.08
        if is_late:
            defense_bias += 0.18
            call_bias -= 0.08
    else:
        labels.append("追分")
        attack_bias += min(0.32, gap_to_above / 22000)
        value_bias += min(0.34, gap_to_top / 26000)
        riichi_bias += min(0.22, gap_to_above / 26000)

    if placement == count:
        labels.append("避ラス")
        attack_bias += 0.2
        value_bias += 0.18
        riichi_bias += 0.12
        defense_bias -= 0.08
    elif placement == 1 and lead_to_below >= 12000:
        labels.append("大幅领先")
        defense_bias += 0.18
        value_bias -= 0.08

    if is_all_last or is_extra:
        labels.append("末局")
        if placement == 1:
            defense_bias += 0.35
            attack_bias -= 0.12
            value_bias -= 0.1
            riichi_bias -= 0.16
            call_bias -= 0.08
        elif gap_to_above > 0:
            attack_bias += 0.28
            value_bias += min(0.42, gap_to_above / 18000)
            riichi_bias += min(0.26, gap_to_above / 22000)
            call_bias += 0.1

    if is_dealer:
        labels.append("亲家")
        if placement == 1 and is_all_last and over_target:
            defense_bias += 0.22
            riichi_bias -= 0.08
        else:
            attack_bias += 0.16
            call_bias += 0.08
            riichi_bias += 0.08

    if own_points < 12000:
        labels.append("低点数")
        attack_bias += 0.18
        value_bias += 0.18
        defense_bias -= 0.08

    labels = []
    if placement == 1:
        labels.append("\u5b88\u4f4d")
    else:
        labels.append("\u8ffd\u5206")
    if placement == count:
        labels.append("\u907f\u672b\u4f4d")
    elif placement == 1 and lead_to_below >= 12000:
        labels.append("\u5927\u5e45\u9886\u5148")
    if is_all_last or is_extra:
        labels.append("\u672b\u5c40")
    if is_dealer:
        labels.append("\u4eb2\u5bb6")
    if own_points < 12000:
        labels.append("\u4f4e\u70b9\u6570")

    label = " / ".join(unique_ordered_labels(labels)[:3])
    return {
        "placement": placement,
        "placement_count": count,
        "label": label,
        "attack_bias": round(max(-0.35, min(0.75, attack_bias)), 3),
        "defense_bias": round(max(-0.25, min(0.95, defense_bias)), 3),
        "value_bias": round(max(-0.2, min(0.75, value_bias)), 3),
        "riichi_bias": round(max(-0.25, min(0.65, riichi_bias)), 3),
        "call_bias": round(max(-0.2, min(0.55, call_bias)), 3),
        "gap_to_above": gap_to_above,
        "lead_to_below": lead_to_below,
        "gap_to_top": gap_to_top,
        "lead_to_bottom": lead_to_bottom,
        "rounds_remaining": rounds_remaining,
        "is_all_last": is_all_last,
        "is_extra": is_extra,
        "is_dealer": is_dealer,
    }


def table_pressure_ev(game: dict[str, Any], seat: int, shanten_value: int, risk: float, level: int = 3) -> float:
    round_state = game["round_state"]
    own_points = game["players"][seat]["points"]
    all_points = [player["points"] for player in game["players"]]
    top_points = max(all_points)
    bottom_points = min(all_points)
    progress = round_progress_ratio(round_state)

    ev = 0.0
    point_gap = top_points - own_points
    if point_gap > 8000:
        ev += min(20.0, point_gap / 1800) * (1.0 if shanten_value <= 2 else 0.35)
    if own_points == top_points and risk > 0:
        lead = own_points - bottom_points
        ev -= min(16.0, lead / 2500) * (0.7 + progress)
    if seat == round_state["dealer_seat"] and shanten_value <= 1:
        ev += 5.5
    if progress > 0.72:
        if shanten_value >= 2:
            ev -= 7.5 + (risk * 5.0)
        else:
            ev += 3.5
    strategy = placement_strategy_context(game, seat)
    strategy_scale = ai_level_policy(level)["strategy_scale"]
    if shanten_value <= 1:
        ev += strategy["attack_bias"] * 12.0 * strategy_scale
        ev += strategy["value_bias"] * 7.0 * strategy_scale
    else:
        ev += strategy["attack_bias"] * 5.0 * strategy_scale
        ev -= strategy["defense_bias"] * (5.0 + shanten_value * 1.6) * strategy_scale
    ev -= strategy["defense_bias"] * risk * (7.0 + progress * 6.0) * strategy_scale
    if strategy_scale >= 0.6 and strategy["is_all_last"] and strategy["placement"] == 1 and risk > 0:
        ev -= (8.0 + risk * 5.0) * strategy_scale
    if strategy_scale >= 0.6 and strategy["placement"] == strategy["placement_count"] and shanten_value <= 2:
        ev += min(10.0, strategy["gap_to_above"] / 2200) * strategy_scale
    return round(ev, 3)


def structured_discard_ev(
    game: dict[str, Any],
    seat: int,
    *,
    shanten_value: int,
    ukeire: int,
    risk: float,
    value_penalty: float,
    route_bonus: float,
    routes: list[str],
    level: int,
) -> dict[str, float]:
    round_state = game["round_state"]
    progress = round_progress_ratio(round_state)
    opponent_pressure = opponent_models(game, seat)
    max_loss = max((model["estimated_loss"] for model in opponent_pressure), default=0)
    max_threat = max((model["threat"] for model in opponent_pressure), default=0.0)

    speed_weight = 1.65 + (level * 0.62)
    shanten_weight = 104 + (level * 4)
    speed_ev = (-shanten_weight * shanten_value) + (ukeire * speed_weight)
    if shanten_value == 0:
        speed_ev += 18 + min(18, ukeire * 0.45)
    elif shanten_value == 1:
        speed_ev += 7

    value_scale = 0.7 if level == 1 else 0.92 if level == 2 else 1.08
    value_ev = (route_bonus * value_scale) - (value_penalty * (2.0 + level))
    if shanten_value == 0 and is_closed_hand(round_state, seat) and game["players"][seat]["points"] >= 1000 and len(round_state["live_wall"]) >= 4:
        value_ev += 8.5
    if routes and shanten_value <= 2:
        value_ev += min(6.0, len(routes) * 1.8)

    caution = 0.72 if level == 1 else 1.0 if level == 2 else 1.18
    if game["players"][seat]["points"] == max(player["points"] for player in game["players"]):
        caution += 0.22
    if max_loss >= 8000:
        caution += 0.16
    danger_scale = 1.0 + (progress * 0.55) + (max_threat * 0.18) + min(0.45, max_loss / 32000)
    defense_ev = -(risk * 15.5 * caution * danger_scale)

    table_ev = table_pressure_ev(game, seat, shanten_value, risk, level)
    final_ev = speed_ev + value_ev + defense_ev + table_ev
    if level == 1:
        final_ev += random.random()

    return {
        "speed_ev": round(speed_ev, 3),
        "value_ev": round(value_ev, 3),
        "defense_ev": round(defense_ev, 3),
        "table_ev": round(table_ev, 3),
        "final_ev": round(final_ev, 3),
    }


def lookahead_after_discard_ev(
    game: dict[str, Any],
    seat: int,
    tiles_after_discard: list[int],
    good_tiles: list[dict[str, Any]],
    *,
    level: int,
    base_final_ev: float,
    risk_context: dict[str, Any] | None = None,
) -> float:
    if level < 3 or not good_tiles:
        return 0.0

    weighted_total = 0.0
    total_weight = 0
    for item in sorted(good_tiles, key=lambda value: (-int(value["remaining"]), int(value["type"])))[:2]:
        remaining = int(item["remaining"])
        if remaining <= 0:
            continue
        simulated_hand = list(tiles_after_discard) + [int(item["type"]) * 4]
        next_profiles = [
            discard_profile(
                game,
                seat,
                tile_id,
                level,
                hand_tiles=simulated_hand,
                include_lookahead=False,
                risk_context=risk_context,
            )
            for tile_id in unique_tile_type_candidates(simulated_hand)
        ]
        if not next_profiles:
            continue
        best_next = max(next_profiles, key=lambda profile: profile["final_ev"])
        weighted_total += float(best_next["final_ev"]) * remaining
        total_weight += remaining

    if total_weight <= 0:
        return 0.0

    average_next_ev = weighted_total / total_weight
    lookahead_ev = (average_next_ev - base_final_ev) * 0.16
    return round(max(-28.0, min(28.0, lookahead_ev)), 3)


def discard_profile(
    game: dict[str, Any],
    seat: int,
    discard_tile_id: int,
    level: int,
    *,
    hand_tiles: list[int] | None = None,
    include_lookahead: bool = True,
    risk_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    round_state = game["round_state"]
    policy = ai_level_policy(level)
    source_tiles = list(round_state["hands"][seat] if hand_tiles is None else hand_tiles)
    tiles = list(source_tiles)
    if discard_tile_id not in tiles:
        return {
            "tile_id": discard_tile_id,
            "tile_label": tile_label(discard_tile_id),
            "shanten": 8,
            "ukeire": 0,
            "waits": [],
            "risk": 999.0,
            "raw_risk": 999.0,
            "value_penalty": 0.0,
            "routes": [],
            "route_bonus": 0.0,
            "speed_ev": -999.0,
            "value_ev": 0.0,
            "defense_ev": -999.0,
            "table_ev": 0.0,
            "lookahead_ev": 0.0,
            "safety_ev": 0.0,
            "safety_score": 0.0,
            "safety_label": "非法",
            "defense_mode": False,
            "strategy_label": "",
            "placement": 0,
            "shape_ev": 0.0,
            "shape_label": "非法",
            "wait_quality": 0.0,
            "hand_value_ev": 0.0,
            "estimated_han": 0.0,
            "estimated_value": 0,
            "value_label": "非法",
            "value_routes": [],
            "dora_count": 0,
            "push_fold_ev": 0.0,
            "push_fold_label": "\u975e\u6cd5",
            "push_fold_mode": "fold",
            "pressure_score": 0.0,
            "commitment_score": 0.0,
            "defense_override_ev": 0.0,
            "defense_override_mode": "",
            "defense_override_label": "",
            "fold_need": 0.0,
            "forced_defense": False,
            "final_ev": -1998.0,
            "score": -1998.0,
        }
    tiles.remove(discard_tile_id)
    try:
        shanten_value = shanten_calculator.calculate_shanten(to_34_array(tiles))
    except ValueError:
        shanten_value = 8
    ukeire, good_tile_infos = effective_tiles_after_discard(
        game,
        seat,
        source_tiles,
        discard_tile_id,
        base_shanten=shanten_value,
    )
    waits = [item["label"] for item in good_tile_infos]
    if risk_context is None:
        risk_context = build_tile_risk_context(game, seat, hand_tiles=source_tiles)
    raw_risk = tile_risk_score(game, seat, discard_tile_id, risk_context=risk_context)
    risk = round(raw_risk * policy["risk_scale"], 3)
    defense_profile = defensive_discard_profile(game, seat, discard_tile_id, shanten_value, level, risk_context)
    strategy = placement_strategy_context(game, seat)
    shape_profile = shape_quality_profile(game, seat, tiles, shanten_value, ukeire, good_tile_infos, level)
    bonus = tile_value_bonus(game, seat, discard_tile_id)
    route_bonus, routes = hand_route_profile(game, seat, tiles, shanten_value=shanten_value)
    value_profile = hand_value_profile(
        game,
        seat,
        tiles,
        shanten_value=shanten_value,
        routes=routes,
        wait_quality=shape_profile["wait_quality"],
    )
    ev = structured_discard_ev(
        game,
        seat,
        shanten_value=shanten_value,
        ukeire=ukeire,
        risk=risk,
        value_penalty=bonus,
        route_bonus=route_bonus,
        routes=routes,
        level=level,
    )
    lookahead_ev = (
        lookahead_after_discard_ev(
            game,
            seat,
            tiles,
            good_tile_infos,
            level=level,
            base_final_ev=ev["final_ev"],
            risk_context=risk_context,
        )
        if include_lookahead and shanten_value <= 3
        else 0.0
    )
    safety_ev = round(defense_profile["safety_ev"] * policy["defense_scale"], 3)
    hand_value_ev = round(value_profile["hand_value_ev"] * (0.45 + policy["strategy_scale"] * 0.55), 3)
    push_fold = push_fold_profile(
        game,
        seat,
        shanten_value=shanten_value,
        risk=risk,
        safety_score=defense_profile["safety_score"],
        hand_value_ev=hand_value_ev,
        estimated_han=value_profile["estimated_han"],
        wait_quality=shape_profile["wait_quality"],
        level=level,
        risk_context=risk_context,
        strategy=strategy,
    )
    defense_override = defense_override_profile(
        game,
        seat,
        shanten_value=shanten_value,
        risk=risk,
        safety_score=defense_profile["safety_score"],
        hand_value_ev=hand_value_ev,
        estimated_han=value_profile["estimated_han"],
        wait_quality=shape_profile["wait_quality"],
        level=level,
        risk_context=risk_context,
        strategy=strategy,
    )
    push_fold_ev = round(push_fold["push_fold_ev"] * (0.42 + policy["strategy_scale"] * 0.58), 3)
    defense_override_ev = round(
        defense_override["defense_override_ev"] * (0.52 + policy["defense_scale"] * 0.48),
        3,
    )
    final_ev = round(
        ev["final_ev"]
        + lookahead_ev
        + safety_ev
        + shape_profile["shape_ev"]
        + hand_value_ev
        + push_fold_ev
        + defense_override_ev,
        3,
    )
    return {
        "tile_id": discard_tile_id,
        "tile_label": tile_label(discard_tile_id),
        "shanten": shanten_value,
        "ukeire": ukeire,
        "waits": waits[:6],
        "risk": risk,
        "raw_risk": raw_risk,
        "value_penalty": bonus,
        "routes": routes,
        "route_bonus": route_bonus,
        "speed_ev": ev["speed_ev"],
        "value_ev": ev["value_ev"],
        "defense_ev": ev["defense_ev"],
        "table_ev": ev["table_ev"],
        "lookahead_ev": lookahead_ev,
        "safety_ev": safety_ev,
        "safety_score": defense_profile["safety_score"],
        "safety_label": defense_profile["safety_label"],
        "defense_mode": defense_profile["defense_mode"],
        "strategy_label": strategy["label"],
        "placement": strategy["placement"],
        "shape_ev": shape_profile["shape_ev"],
        "shape_label": shape_profile["shape_label"],
        "wait_quality": shape_profile["wait_quality"],
        "hand_value_ev": hand_value_ev,
        "estimated_han": value_profile["estimated_han"],
        "estimated_value": value_profile["estimated_value"],
        "value_label": value_profile["value_label"],
        "value_routes": value_profile["value_routes"],
        "dora_count": value_profile["dora_count"],
        "push_fold_ev": push_fold_ev,
        "push_fold_label": push_fold["push_fold_label"],
        "push_fold_mode": push_fold["push_fold_mode"],
        "pressure_score": push_fold["pressure_score"],
        "commitment_score": push_fold["commitment_score"],
        "defense_override_ev": defense_override_ev,
        "defense_override_mode": defense_override["defense_override_mode"],
        "defense_override_label": defense_override["defense_override_label"],
        "fold_need": defense_override.get("fold_need", 0.0),
        "forced_defense": False,
        "final_ev": final_ev,
        "score": final_ev,
    }


def sorted_discard_profiles(game: dict[str, Any], seat: int, level: int) -> list[dict[str, Any]]:
    candidates = unique_tile_type_candidates(game["round_state"]["hands"][seat])
    risk_context = build_tile_risk_context(game, seat)
    if level >= 3:
        base_profiles = [
            discard_profile(game, seat, tile_id, level, include_lookahead=False, risk_context=risk_context)
            for tile_id in candidates
        ]
        lookahead_tile_ids = {
            profile["tile_id"]
            for profile in sorted(base_profiles, key=lambda item: (-item["score"], item["tile_label"]))[:3]
            if profile["shanten"] <= 3
        }
        profiles = [
            discard_profile(game, seat, profile["tile_id"], level, risk_context=risk_context)
            if profile["tile_id"] in lookahead_tile_ids
            else profile
            for profile in base_profiles
        ]
    else:
        profiles = [discard_profile(game, seat, tile_id, level, risk_context=risk_context) for tile_id in candidates]
    return sorted(profiles, key=lambda item: (-item["score"], item["tile_label"]))


def forced_defense_profile_choice(
    game: dict[str, Any], seat: int, profiles: list[dict[str, Any]], level: int
) -> dict[str, Any] | None:
    if level <= 1 or not profiles:
        return None
    max_pressure = max(float(profile.get("pressure_score", 0.0)) for profile in profiles)
    if max_pressure < (1.05 if level >= 3 else 1.28):
        return None

    ordered = sorted(profiles, key=lambda item: (-item["score"], item["tile_label"]))
    attack_pick = ordered[0]
    attack_commitment = float(attack_pick.get("commitment_score", 0.0))
    attack_shanten = int(attack_pick.get("shanten", 8))
    attack_han = float(attack_pick.get("estimated_han", 0.0))
    attack_wait_quality = float(attack_pick.get("wait_quality", 0.0))

    should_fold = False
    if attack_shanten >= 2 and max_pressure >= (1.05 if level >= 3 else 1.28):
        should_fold = True
    elif attack_shanten == 1 and max_pressure >= 1.28 and attack_commitment < 0.95:
        should_fold = True
    elif attack_shanten <= 0 and max_pressure >= 1.55 and (attack_han < 3 or attack_wait_quality < 0.48):
        should_fold = True

    if not should_fold:
        return None

    safe_pool = [
        profile
        for profile in profiles
        if float(profile.get("safety_score", 0.0)) >= 0.78
        or (float(profile.get("risk", 99.0)) <= 0.45 and float(profile.get("safety_score", 0.0)) >= 0.56)
    ]
    if not safe_pool:
        return None

    selected = max(
        safe_pool,
        key=lambda item: (
            float(item.get("safety_score", 0.0)),
            -float(item.get("risk", 99.0)),
            float(item.get("defense_override_ev", 0.0)),
            float(item.get("score", -9999.0)),
        ),
    )
    if selected["tile_id"] == attack_pick["tile_id"]:
        return None
    selected["forced_defense"] = True
    selected["push_fold_label"] = "强制弃和" if attack_shanten >= 2 else "强制押退"
    selected["push_fold_mode"] = "fold"
    return selected


def choose_profile_with_ai_policy(game: dict[str, Any], seat: int, profiles: list[dict[str, Any]], level: int) -> dict[str, Any]:
    if not profiles:
        raise ValueError("No profiles to choose from")
    ordered = sorted(profiles, key=lambda item: (-item["score"], item["tile_label"]))
    defensive_choice = forced_defense_profile_choice(game, seat, profiles, level)
    if defensive_choice is not None:
        return defensive_choice
    policy = ai_level_policy(level)
    mistake_pool = max(1, min(int(policy["mistake_pool"]), len(ordered)))
    if mistake_pool > 1 and ai_roll(game, seat, "discard_mistake") < float(policy["mistake_rate"]):
        offset = int(ai_roll(game, seat, "discard_offset") * mistake_pool)
        return ordered[min(offset, mistake_pool - 1)]
    return ordered[0]


def shanten_of_tiles(tiles: list[int]) -> int:
    try:
        return shanten_calculator.calculate_shanten(to_34_array(tiles))
    except ValueError:
        return 8


def call_route_profile(game: dict[str, Any], seat: int, action: ActionChoice, concealed_after_call: list[int]) -> tuple[float, list[str]]:
    round_state = game["round_state"]
    called_tile = action.tile_id or 0
    called_type = tile_type(called_tile)
    visible_call_tiles = list(action.consumed_ids) + [called_tile]
    all_types = [tile_type(tile_id) for tile_id in concealed_after_call + visible_call_tiles]
    for meld in round_state["melds"][seat]:
        all_types.extend(tile_type(tile_id) for tile_id in meld["tiles"])

    counts = to_34_array(concealed_after_call)
    own_wind_type = round_state["wind_type_map"][seat_wind_label(round_state, seat)]
    round_wind_type = round_state["wind_type_map"][round_state["prevalent_wind"]]
    value_honor_types = {own_wind_type, round_wind_type, 31, 32, 33}
    dora_types = {dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(round_state)}

    routes: list[str] = []
    bonus = 0.0
    if action.type in {"pon", "open_kan"} and called_type in value_honor_types:
        routes.append("役牌")
        bonus += 19.0
    elif any(counts[ttype] >= 2 for ttype in value_honor_types):
        routes.append("役牌候补")
        bonus += 5.5

    if all_types and all(is_simple(ttype) for ttype in all_types):
        routes.append("断幺")
        bonus += 9.0

    suited_types = [ttype for ttype in all_types if ttype < 27]
    honor_count = sum(1 for ttype in all_types if is_honor(ttype))
    if suited_types:
        suit_counts = [sum(1 for ttype in suited_types if tile_suit_index(ttype) == suit) for suit in range(3)]
        dominant_suit = max(range(3), key=lambda suit: suit_counts[suit])
        off_suit_count = len(suited_types) - suit_counts[dominant_suit]
        if suit_counts[dominant_suit] >= 8 and off_suit_count == 0:
            if honor_count:
                routes.append("混一色")
                bonus += 13.0
            else:
                routes.append("清一色")
                bonus += 20.0

    triplet_like = sum(1 for meld in round_state["melds"][seat] if meld["type"] in TRIPLET_MELD_TYPES)
    triplet_like += 1 if action.type in {"pon", "open_kan"} else 0
    triplet_like += sum(1 for amount in counts if amount >= 3)
    pair_count = sum(1 for amount in counts if amount >= 2)
    if triplet_like >= 2 and pair_count >= 1:
        routes.append("对对和")
        bonus += 9.5

    call_dora = sum(1 for tile_id in visible_call_tiles if is_red(tile_id) or tile_type(tile_id) in dora_types)
    if call_dora:
        routes.append("宝牌")
        bonus += min(10.0, call_dora * 3.2)
    if action.type == "open_kan":
        bonus += 5.0

    unique_routes: list[str] = []
    for route in routes:
        if route not in unique_routes:
            unique_routes.append(route)
    return round(bonus, 3), unique_routes[:4]


def prospective_open_call_melds(game: dict[str, Any], seat: int, action: ActionChoice) -> list[dict[str, Any]]:
    round_state = game["round_state"]
    melds = deepcopy(round_state["melds"][seat])
    if action.type not in {"chi", "pon", "open_kan"} or action.tile_id is None:
        return melds
    discarder = round_state["last_discard"]["seat"] if round_state.get("last_discard") is not None else None
    melds.append(
        {
            "type": action.type,
            "tiles": sort_tiles(list(action.consumed_ids) + [action.tile_id]),
            "opened": True,
            "called_tile": action.tile_id,
            "from_seat": discarder,
        }
    )
    return melds


def confirm_open_call_tenpai_yaku(
    game: dict[str, Any],
    seat: int,
    action: ActionChoice,
    concealed_after_call: list[int],
) -> dict[str, Any]:
    melds = prospective_open_call_melds(game, seat, action)
    wait_types = winning_tile_types_for_layout(game, seat, concealed_after_call, melds)
    confirmed_yaku: list[str] = []
    best_han = 0
    best_points = 0
    confirmed_waits: list[str] = []
    for wait_type in sorted(wait_types):
        win_tile_id = wait_type * 4
        result = estimate_hand_value_for_layout(
            game,
            seat,
            concealed_after_call,
            melds,
            win_tile_id,
            is_tsumo=False,
            riichi_override=False,
            ippatsu_override=False,
        )
        if result.error:
            continue
        yaku_names = serialize_yaku_names(result.yaku)
        confirmed_yaku.extend(name.split(" ", 1)[0] for name in yaku_names)
        best_han = max(best_han, int(result.han or 0))
        best_points = max(best_points, score_result_total(dict(result.cost)))
        confirmed_waits.append(tile_type_label(wait_type))

    return {
        "is_tenpai": bool(wait_types),
        "confirmed": bool(confirmed_waits),
        "waits": confirmed_waits,
        "yaku": unique_ordered_labels(confirmed_yaku)[:4],
        "best_han": best_han,
        "best_points": best_points,
    }


def open_call_yaku_viability_profile(
    game: dict[str, Any],
    seat: int,
    action: ActionChoice,
    concealed_after_call: list[int],
    routes: list[str],
    next_shanten: int,
    level: int,
) -> dict[str, Any]:
    round_state = game["round_state"]
    called_tile = action.tile_id or 0
    called_type = tile_type(called_tile)
    visible_call_tiles = list(action.consumed_ids) + [called_tile]
    existing_melds = [meld for meld in round_state["melds"][seat] if meld["type"] != "kita"]
    all_types = [tile_type(tile_id) for tile_id in concealed_after_call + visible_call_tiles]
    for meld in existing_melds:
        all_types.extend(tile_type(tile_id) for tile_id in meld["tiles"])

    counts = to_34_array(concealed_after_call)
    own_wind_type = round_state["wind_type_map"][seat_wind_label(round_state, seat)]
    round_wind_type = round_state["wind_type_map"][round_state["prevalent_wind"]]
    value_honor_types = {own_wind_type, round_wind_type, 31, 32, 33}

    guaranteed_routes: list[str] = []
    candidate_routes: list[str] = []
    confidence = 0.0

    existing_value_meld = any(
        meld["type"] in TRIPLET_MELD_TYPES and tile_type(meld["tiles"][0]) in value_honor_types
        for meld in existing_melds
    )
    called_value_triplet = action.type in {"pon", "open_kan"} and called_type in value_honor_types
    if existing_value_meld or called_value_triplet:
        guaranteed_routes.append("役牌")
        confidence = max(confidence, 1.0)

    if all_types and all(is_simple(ttype) for ttype in all_types):
        candidate_routes.append("断幺")
        confidence = max(confidence, 0.86)

    suited_types = [ttype for ttype in all_types if ttype < 27]
    honor_count = sum(1 for ttype in all_types if is_honor(ttype))
    if suited_types:
        suit_counts = [sum(1 for ttype in suited_types if tile_suit_index(ttype) == suit) for suit in range(3)]
        dominant_suit = max(range(3), key=lambda suit: suit_counts[suit])
        off_suit_count = len(suited_types) - suit_counts[dominant_suit]
        if off_suit_count == 0:
            if honor_count:
                candidate_routes.append("混一色")
                confidence = max(confidence, 0.76)
            else:
                candidate_routes.append("清一色")
                confidence = max(confidence, 0.82)

    triplet_like = sum(1 for meld in existing_melds if meld["type"] in TRIPLET_MELD_TYPES)
    triplet_like += 1 if action.type in {"pon", "open_kan"} else 0
    triplet_like += sum(1 for amount in counts if amount >= 3)
    pair_count = sum(1 for amount in counts if amount >= 2)
    if action.type in {"pon", "open_kan"} and triplet_like >= 2 and pair_count >= 1:
        candidate_routes.append("对对和")
        confidence = max(confidence, 0.82 if triplet_like >= 3 else 0.66)

    value_honor_pairs = sum(1 for ttype in value_honor_types if counts[ttype] >= 2)
    if value_honor_pairs and "役牌" not in guaranteed_routes:
        candidate_routes.append("役牌候补")
        confidence = max(confidence, 0.58 if next_shanten <= 1 else 0.48)

    all_yaku_routes = unique_ordered_labels(guaranteed_routes + candidate_routes)
    has_yaku_path = bool(all_yaku_routes)
    guaranteed_yaku = bool(guaranteed_routes)
    weak_candidate_only = has_yaku_path and not guaranteed_yaku and confidence < 0.62
    route_set = set(routes)
    dora_only = bool(route_set) and route_set <= {"宝牌"}

    if next_shanten == 0:
        confirmation = confirm_open_call_tenpai_yaku(game, seat, action, concealed_after_call)
        if confirmation["confirmed"]:
            confirmed_routes = confirmation["yaku"] or all_yaku_routes or ["有役听牌"]
            label = f"有役听牌：{'/'.join(confirmed_routes)}"
            return {
                "has_yaku_path": True,
                "guaranteed_yaku": True,
                "yaku_confidence": 1.0,
                "yaku_ev": 14.0 + min(8.0, len(confirmation["waits"]) * 1.6),
                "threshold_adjust": -7.0,
                "routes": confirmed_routes,
                "yaku_label": label,
                "yaku_reason": f"鸣后听牌已通过计分器验证可和，等待 {', '.join(confirmation['waits'][:5])}。",
            }
        if confirmation["is_tenpai"]:
            penalty = 54.0 if level >= 3 else 42.0 if level == 2 else 32.0
            return {
                "has_yaku_path": False,
                "guaranteed_yaku": False,
                "yaku_confidence": 0.0,
                "yaku_ev": -penalty,
                "threshold_adjust": 38.0,
                "routes": [],
                "yaku_label": "听牌但无役",
                "yaku_reason": "鸣后虽然听牌，但用当前副露和所有待牌验证后没有可和役；宝牌不能替代役，建议跳过。",
            }

    if not has_yaku_path:
        penalty = 44.0 if level >= 3 else 36.0 if level == 2 else 28.0
        threshold_adjust = 30.0 if level >= 3 else 22.0 if level == 2 else 16.0
        label = "鸣后无稳定役"
        reason = "鸣牌会破坏门清，当前看不到断幺、役牌、染手、对对和等稳定役；宝牌本身不能作为和牌役。"
        if dora_only:
            reason += " 这类牌即使有宝牌，也容易变成副露无役。"
        return {
            "has_yaku_path": False,
            "guaranteed_yaku": False,
            "yaku_confidence": 0.0,
            "yaku_ev": -penalty,
            "threshold_adjust": threshold_adjust,
            "routes": [],
            "yaku_label": label,
            "yaku_reason": reason,
        }

    if weak_candidate_only:
        penalty = 13.0 if level >= 3 else 9.0
        label = f"役路偏弱：{'/'.join(all_yaku_routes)}"
        return {
            "has_yaku_path": True,
            "guaranteed_yaku": False,
            "yaku_confidence": round(confidence, 3),
            "yaku_ev": -penalty,
            "threshold_adjust": 11.0,
            "routes": all_yaku_routes,
            "yaku_label": label,
            "yaku_reason": "鸣后只有候补役路线，尚未形成稳定役；除非明显推进向听或局况必须追分，否则更倾向跳过。",
        }

    bonus = 11.0 if guaranteed_yaku else 5.5 + confidence * 5.0
    threshold_adjust = -5.0 if guaranteed_yaku else -1.5
    label = f"可和路线：{'/'.join(all_yaku_routes)}"
    return {
        "has_yaku_path": True,
        "guaranteed_yaku": guaranteed_yaku,
        "yaku_confidence": round(confidence, 3),
        "yaku_ev": round(bonus, 3),
        "threshold_adjust": threshold_adjust,
        "routes": all_yaku_routes,
        "yaku_label": label,
        "yaku_reason": "鸣后仍保留可和役路线，AI 会继续结合速度、打点和放铳风险决定是否执行。",
    }


def best_post_call_discard_profile(
    game: dict[str, Any],
    seat: int,
    concealed_after_call: list[int],
    level: int,
) -> dict[str, Any] | None:
    candidates = unique_tile_type_candidates(concealed_after_call)
    if not candidates:
        return None
    risk_context = build_tile_risk_context(game, seat, hand_tiles=concealed_after_call)
    profiles = [
        discard_profile(
            game,
            seat,
            tile_id,
            level,
            hand_tiles=concealed_after_call,
            include_lookahead=False,
            risk_context=risk_context,
        )
        for tile_id in candidates
    ]
    return max(profiles, key=lambda profile: profile["final_ev"])


def open_call_commitment_profile(
    game: dict[str, Any],
    seat: int,
    action: ActionChoice,
    *,
    current_shanten: int,
    next_shanten: int,
    shanten_gain: int,
    yaku_profile: dict[str, Any],
    best_discard: dict[str, Any] | None,
    max_threat: float,
    max_loss: int,
    progress: float,
    strategy: dict[str, Any],
    level: int,
) -> dict[str, Any]:
    if action.type not in {"chi", "pon", "open_kan"}:
        return {
            "call_commitment_ev": 0.0,
            "call_commitment_label": "",
            "call_commitment_blocker": False,
            "call_commitment_reason": "",
            "threshold_adjust": 0.0,
        }

    policy = ai_level_policy(level)
    has_yaku_path = bool(yaku_profile.get("has_yaku_path", False))
    guaranteed_yaku = bool(yaku_profile.get("guaranteed_yaku", False))
    yaku_confidence = float(yaku_profile.get("yaku_confidence") or 0.0)
    post_ukeire = float(best_discard.get("ukeire", 0.0)) if isinstance(best_discard, dict) else 0.0
    post_risk = float(best_discard.get("risk", 0.0)) if isinstance(best_discard, dict) else 0.0
    post_safety = float(best_discard.get("safety_score", 0.0)) if isinstance(best_discard, dict) else 0.0
    post_forced_defense = bool(best_discard.get("forced_defense", False)) if isinstance(best_discard, dict) else False
    strategy_scale = float(policy["strategy_scale"])

    ev = 0.0
    threshold_adjust = 0.0
    blocker = False
    reasons: list[str] = []

    if shanten_gain >= 2:
        ev += 18.0
        threshold_adjust -= 4.0
        reasons.append("\u8fde\u8df3\u5411\u542c")
    elif shanten_gain == 1:
        ev += 8.0 + max(0.0, 2.0 - next_shanten) * 3.0
        threshold_adjust -= 2.0
        reasons.append("\u6539\u5584\u5411\u542c")
    else:
        penalty = 13.0 if level >= 3 else 8.0
        ev -= penalty + progress * 6.0
        threshold_adjust += 6.0 if level >= 3 else 3.0
        reasons.append("\u4e0d\u6539\u5584\u5411\u542c")

    if guaranteed_yaku:
        ev += 8.0 + yaku_confidence * 5.0
        threshold_adjust -= 3.0
        reasons.append("\u5df2\u6709\u7a33\u5b9a\u5f79")
    elif has_yaku_path:
        ev += yaku_confidence * 7.0 - 2.5
        if yaku_confidence < 0.62:
            ev -= 7.0
            threshold_adjust += 5.0
            reasons.append("\u5f79\u8def\u4e0d\u7a33")
    else:
        ev -= 36.0 if level >= 3 else 24.0
        threshold_adjust += 26.0 if level >= 3 else 16.0
        blocker = True
        reasons.append("\u9e23\u540e\u65e0\u5f79")

    far_open = next_shanten >= 3 or (next_shanten >= 2 and shanten_gain <= 0)
    if far_open and not guaranteed_yaku:
        ev -= 16.0 + progress * 10.0
        threshold_adjust += 10.0
        reasons.append("\u8fdc\u624b\u526f\u9732")
        if level >= 3 and max_threat >= 0.85:
            blocker = True

    if post_ukeire:
        if next_shanten <= 1 and post_ukeire >= 10:
            ev += min(12.0, post_ukeire * 0.45)
            reasons.append("\u9e23\u540e\u8fdb\u5f20\u597d")
        elif post_ukeire <= 4 and next_shanten >= 1:
            ev -= 9.0
            threshold_adjust += 4.0
            reasons.append("\u9e23\u540e\u8fdb\u5f20\u5c11")

    if post_forced_defense:
        ev -= 16.0
        threshold_adjust += 8.0
        reasons.append("\u9e23\u540e\u8981\u64a4\u9000")
    elif post_risk >= 1.25 and post_safety < 0.45:
        ev -= 18.0 + min(12.0, max_threat * 5.0)
        threshold_adjust += 8.0
        reasons.append("\u9e23\u540e\u9996\u6253\u5371\u9669")
    elif post_safety >= 0.78 and max_threat >= 0.9:
        ev += 7.0
        reasons.append("\u6709\u5b89\u5168\u51fa\u53e3")

    if max_threat >= 1.1 and next_shanten >= 1:
        danger_tax = 8.0 + min(14.0, max_loss / 1800) * (0.35 + progress * 0.65)
        ev -= danger_tax
        threshold_adjust += 5.0
        reasons.append("\u573a\u4e0a\u538b\u529b\u9ad8")
    if action.type == "open_kan":
        kan_tax = 10.0 + max_threat * 8.0 + progress * 4.0
        ev -= kan_tax
        threshold_adjust += 7.0
        reasons.append("\u660e\u6760\u7ed9\u65b0\u5b9d\u724c")

    if strategy["call_bias"] > 0 and shanten_gain >= 1:
        ev += strategy["call_bias"] * 8.0 * strategy_scale
        threshold_adjust -= strategy["call_bias"] * 3.5 * strategy_scale
    if strategy["defense_bias"] > 0 and next_shanten >= 1:
        ev -= strategy["defense_bias"] * 10.0 * strategy_scale
        threshold_adjust += strategy["defense_bias"] * 5.0 * strategy_scale

    if level >= 3:
        if next_shanten >= 3 and shanten_gain <= 0:
            blocker = True
        if max_threat >= 1.25 and post_risk >= 1.15 and next_shanten > 0:
            blocker = True
        if has_yaku_path and not guaranteed_yaku and yaku_confidence < 0.5 and next_shanten >= 2:
            blocker = True

    if blocker:
        label = "\u4e0d\u5efa\u8bae\u9e23"
    elif ev >= 12.0:
        label = "\u53ef\u4ee5\u9e23\u724c"
    elif ev >= 0.0:
        label = "\u8fb9\u754c\u9e23\u724c"
    else:
        label = "\u503e\u5411\u8df3\u8fc7"

    return {
        "call_commitment_ev": round(max(-88.0, min(64.0, ev)), 3),
        "call_commitment_label": label,
        "call_commitment_blocker": blocker,
        "call_commitment_reason": "\u3001".join(unique_ordered_labels(reasons)[:4]),
        "threshold_adjust": round(threshold_adjust, 3),
    }


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
    return bool(tenpai_wait_tile_types(remaining, mode=game["mode"]))


def can_double_riichi(round_state: dict[str, Any], seat: int) -> bool:
    return seat_is_on_first_turn(round_state, seat) and round_is_uninterrupted(round_state)


def build_discard_actions(game: dict[str, Any], seat: int) -> list[ActionChoice]:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    if round_state["riichi"][seat]:
        drawn = round_state["current_draw"]
        if drawn is not None:
            return [
                ActionChoice(
                    f"discard|{drawn}",
                    "discard",
                    seat,
                    f"摸切 {tile_label(drawn)}",
                    tile_id=drawn,
                    meta={"forced_tsumogiri": True},
                )
            ]
        return []
    forbidden_types = set(round_state["kuikae_forbidden_types"][seat])
    actions: list[ActionChoice] = []
    seen: set[tuple[int, bool]] = set()
    riichi_seen_labels: set[str] = set()
    for tile_id in sort_tiles(round_state["hands"][seat]):
        key = (tile_type(tile_id), is_red(tile_id))
        if key in seen:
            continue
        seen.add(key)
        if tile_type(tile_id) in forbidden_types:
            continue
        actions.append(ActionChoice(f"discard|{tile_id}", "discard", seat, f"打出 {tile_label(tile_id)}", tile_id=tile_id))
        riichi_label_key = tile_label(tile_id)
        if riichi_label_key not in riichi_seen_labels and can_riichi_after_discard(game, seat, tile_id):
            riichi_seen_labels.add(riichi_label_key)
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


def forced_riichi_tsumogiri_action(game: dict[str, Any], seat: int, actions: list[ActionChoice] | None = None) -> ActionChoice | None:
    round_state = game["round_state"]
    if not round_state["riichi"][seat]:
        return None
    drawn = round_state.get("current_draw")
    if drawn is None:
        return None
    choices = actions if actions is not None else build_turn_actions(game, seat)
    discard_choices = [action for action in choices if action.type == "discard" and action.tile_id == drawn]
    if not discard_choices:
        return None
    if any(action.type in {"tsumo", "closed_kan"} for action in choices):
        return None
    return discard_choices[0]


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


def hint_shanten_value(game: dict[str, Any], seat: int) -> int | None:
    try:
        return shanten_calculator.calculate_shanten(to_34_array(game["round_state"]["hands"][seat]))
    except ValueError:
        return None


def turn_special_action_profile(game: dict[str, Any], seat: int, action: ActionChoice, level: int) -> dict[str, Any]:
    round_state = game["round_state"]
    current_shanten = shanten_of_tiles(round_state["hands"][seat])
    strategy = placement_strategy_context(game, seat)
    progress = round_progress_ratio(round_state)
    pressure = opponent_models(game, seat)
    max_threat = max((model["threat"] for model in pressure), default=0.0)
    max_loss = max((model["estimated_loss"] for model in pressure), default=0)

    if action.type == "tsumo":
        return {
            "action": action,
            "current_shanten": -1,
            "next_shanten": -1,
            "routes": ["自摸和牌"],
            "speed_ev": 999.0,
            "value_ev": 999.0,
            "defense_ev": 0.0,
            "table_ev": 0.0,
            "post_discard_ev": 0.0,
            "final_ev": 1998.0,
            "threshold": 0.0,
            "recommended": True,
            "best_discard": None,
            "strategy_label": strategy["label"],
            "reason": "已经满足自摸和牌条件，标准立直麻将下应直接和牌。",
        }

    if action.type == "abortive_draw":
        speed_ev = 18.0 if current_shanten >= 5 else 6.0
        value_ev = 0.0
        defense_ev = 18.0 + max_threat * 6.0
        table_ev = 3.0 if strategy["placement"] == 1 else 0.0
        final_ev = round(speed_ev + value_ev + defense_ev + table_ev, 3)
        threshold = 26.0 if current_shanten >= 5 else 36.0
        recommended = final_ev >= threshold
        return {
            "action": action,
            "current_shanten": current_shanten,
            "next_shanten": current_shanten,
            "routes": ["九种九牌", "保留点棒"],
            "speed_ev": round(speed_ev, 3),
            "value_ev": round(value_ev, 3),
            "defense_ev": round(defense_ev, 3),
            "table_ev": round(table_ev, 3),
            "post_discard_ev": 0.0,
            "final_ev": final_ev,
            "threshold": threshold,
            "recommended": recommended,
            "best_discard": None,
            "strategy_label": strategy["label"],
            "reason": "起手幺九牌过多时可以选择九种九牌流局；牌太散或场上压力高时更建议流局。",
        }

    if action.type == "kita":
        value_ev = 18.0
        speed_ev = 7.5
        defense_ev = -(max_threat * (2.0 + progress * 3.0))
        table_ev = 3.0 + strategy["value_bias"] * 6.0
        final_ev = round(speed_ev + value_ev + defense_ev + table_ev, 3)
        threshold = 8.0 + max_threat * 2.5
        return {
            "action": action,
            "current_shanten": current_shanten,
            "next_shanten": current_shanten,
            "routes": ["拔北宝牌", "岭上补牌"],
            "speed_ev": round(speed_ev, 3),
            "value_ev": round(value_ev, 3),
            "defense_ev": round(defense_ev, 3),
            "table_ev": round(table_ev, 3),
            "post_discard_ev": 0.0,
            "final_ev": final_ev,
            "threshold": round(threshold, 3),
            "recommended": final_ev >= threshold,
            "best_discard": None,
            "strategy_label": strategy["label"],
            "reason": "三麻拔北通常能增加宝牌价值并补摸一张，除非极端防守局面，一般倾向执行。",
        }

    if action.type in {"closed_kan", "added_kan"}:
        policy = ai_level_policy(level)
        dora_types = {dora_from_indicator(tile, mode=game["mode"]) for tile in current_dora_indicators(round_state)}
        tile_is_dora = action.tile_id is not None and tile_type(action.tile_id) in dora_types
        speed_ev = 9.0 if current_shanten <= 1 else 3.0
        value_ev = 12.0 + (5.0 if action.type == "closed_kan" else 2.0)
        if tile_is_dora:
            value_ev += 5.0
        if round_state["riichi"][seat]:
            value_ev += 2.5
        defense_ev = -(6.0 + max_threat * (8.0 + progress * 10.0) + min(8.0, max_loss / 3900))
        if action.type == "added_kan":
            defense_ev -= 3.5 + max_threat * 3.0
        if current_shanten <= 1:
            defense_ev *= 0.72
        table_ev = (strategy["value_bias"] * 7.0 + strategy["attack_bias"] * 4.0 - strategy["defense_bias"] * 9.0)
        final_ev = round(speed_ev + value_ev + defense_ev + table_ev, 3)
        threshold = 12.0 if action.type == "closed_kan" else 16.0
        threshold += max_threat * 4.0 + progress * 4.0 + strategy["defense_bias"] * 6.0
        recommended = bool(policy["closed_kan"]) and final_ev >= threshold
        kan_name = "暗杠" if action.type == "closed_kan" else "加杠"
        routes = [kan_name, "岭上补牌", "增加宝牌"]
        if action.type == "added_kan":
            routes.append("注意抢杠")
        return {
            "action": action,
            "current_shanten": current_shanten,
            "next_shanten": current_shanten,
            "routes": routes,
            "speed_ev": round(speed_ev, 3),
            "value_ev": round(value_ev, 3),
            "defense_ev": round(defense_ev, 3),
            "table_ev": round(table_ev, 3),
            "post_discard_ev": 0.0,
            "final_ev": final_ev,
            "threshold": round(threshold, 3),
            "recommended": recommended,
            "best_discard": None,
            "strategy_label": strategy["label"],
            "reason": f"{kan_name}会带来岭上补牌和新宝牌，但也会提升全场打点；对手威胁高时会更谨慎。",
        }

    return {
        "action": action,
        "current_shanten": current_shanten,
        "next_shanten": current_shanten,
        "routes": [],
        "speed_ev": 0.0,
        "value_ev": 0.0,
        "defense_ev": 0.0,
        "table_ev": 0.0,
        "post_discard_ev": 0.0,
        "final_ev": 0.0,
        "threshold": 0.0,
        "recommended": False,
        "best_discard": None,
        "strategy_label": strategy["label"],
        "reason": "该操作暂时没有更细的路线收益，默认谨慎处理。",
    }


def pass_action_profile_for_hint(game: dict[str, Any], seat: int, action: ActionChoice, level: int) -> dict[str, Any]:
    round_state = game["round_state"]
    current_shanten = shanten_of_tiles(round_state["hands"][seat])
    strategy = placement_strategy_context(game, seat)
    progress = round_progress_ratio(round_state)
    pressure = opponent_models(game, seat)
    max_threat = max((model["threat"] for model in pressure), default=0.0)
    reactions = build_reaction_actions(game, seat)

    if any(choice.type == "ron" for choice in reactions):
        return {
            "action": action,
            "current_shanten": current_shanten,
            "next_shanten": current_shanten,
            "routes": ["\u4e0d\u5efa\u8bae\u8df3\u8fc7\u548c\u724c"],
            "speed_ev": -999.0,
            "value_ev": -999.0,
            "defense_ev": 0.0,
            "table_ev": 0.0,
            "post_discard_ev": 0.0,
            "final_ev": -1998.0,
            "threshold": 0.0,
            "recommended": False,
            "best_discard": None,
            "strategy_label": strategy["label"],
            "reason": "\u5df2\u7ecf\u6ee1\u8db3\u8363\u548c\u6761\u4ef6\uff0c\u6807\u51c6\u7acb\u76f4\u9ebb\u5c06\u4e0d\u5e94\u8df3\u8fc7\u53ef\u548c\u724c\u3002",
        }

    call_profiles = [
        open_call_profile(game, seat, choice, level)
        for choice in reactions
        if choice.type in {"chi", "pon", "open_kan"}
    ]
    best_call = max(call_profiles, key=lambda profile: profile["final_ev"], default=None)
    recommended_call = next((profile for profile in call_profiles if profile["should_call"]), None)

    speed_ev = 4.0 if current_shanten <= 2 else 8.0
    value_ev = 4.0 if current_shanten <= 1 else 7.0
    defense_ev = 6.0 + max_threat * (5.0 + progress * 5.0)
    table_ev = strategy["defense_bias"] * 7.0 - strategy["call_bias"] * 4.0
    post_discard_ev = 0.0
    routes = ["\u4fdd\u6301\u95e8\u6e05", "\u8df3\u8fc7\u9e23\u724c"]
    reason_parts: list[str] = []

    if best_call is not None:
        gap = float(best_call["threshold"]) - float(best_call["final_ev"])
        if gap > 0:
            post_discard_ev += min(18.0, gap * 0.35)
            reason_parts.append("\u9e23\u724c\u672a\u8fbe\u9608\u503c")
        if best_call.get("has_yaku_path") is False:
            value_ev += 10.0
            reason_parts.append("\u9e23\u540e\u65e0\u5f79")
        if best_call.get("call_commitment_blocker"):
            defense_ev += 8.0
            reason_parts.append("\u526f\u9732\u627f\u8bfa\u5ea6\u4f4e")
        if best_call["should_call"]:
            push_gap = float(best_call["final_ev"]) - float(best_call["threshold"])
            speed_ev -= 12.0 + min(12.0, push_gap * 0.28)
            value_ev -= 6.0
            routes.append("\u6709\u66f4\u4f18\u9e23\u724c")
            reason_parts.append("\u6709\u53ef\u6267\u884c\u7684\u9e23\u724c")

    final_ev = round(speed_ev + value_ev + defense_ev + table_ev + post_discard_ev, 3)
    recommended = recommended_call is None
    threshold = 9.0 if recommended else 18.0
    reason = "\u3001".join(unique_ordered_labels(reason_parts)[:4])
    if not reason:
        reason = "\u6ca1\u6709\u770b\u5230\u8db3\u4ee5\u6253\u7834\u95e8\u6e05\u7684\u9e23\u724c\u6536\u76ca\uff0c\u4f18\u5148\u4fdd\u6301\u624b\u724c\u5f39\u6027\u3002"

    return {
        "action": action,
        "current_shanten": current_shanten,
        "next_shanten": current_shanten,
        "routes": routes,
        "speed_ev": round(speed_ev, 3),
        "value_ev": round(value_ev, 3),
        "defense_ev": round(defense_ev, 3),
        "table_ev": round(table_ev, 3),
        "post_discard_ev": round(post_discard_ev, 3),
        "final_ev": final_ev,
        "threshold": threshold,
        "recommended": recommended,
        "best_discard": None,
        "strategy_label": strategy["label"],
        "reason": reason,
    }


def special_action_profile_for_hint(game: dict[str, Any], seat: int, action: ActionChoice, level: int) -> dict[str, Any]:
    if action.type == "pass":
        return pass_action_profile_for_hint(game, seat, action, level)

    if action.type in {"chi", "pon", "open_kan", "ron"}:
        profile = open_call_profile(game, seat, action, level)
        profile["recommended"] = bool(profile.get("should_call"))
        if action.type == "ron":
            profile["reason"] = "已经满足荣和条件，标准立直麻将下应直接和牌。"
        else:
            yaku_note = profile.get("yaku_reason") or ""
            profile["reason"] = (
                "鸣牌会改变向听、打点、防守和鸣后第一打；这里优先检查鸣后是否仍有可和役，"
                "再按速度 EV、打点 EV、场况 EV 与风险阈值综合判断。"
                f" {yaku_note}"
            ).strip()
        return profile

    if action.type == "riichi":
        risk_context = build_tile_risk_context(game, seat)
        discard_item = discard_profile(
            game,
            seat,
            action.tile_id or 0,
            level,
            include_lookahead=False,
            risk_context=risk_context,
        )
        profile = riichi_decision_profile(game, seat, action, discard_item, level)
        profile["current_shanten"] = shanten_of_tiles(game["round_state"]["hands"][seat])
        profile["next_shanten"] = discard_item["shanten"]
        profile["routes"] = ["立直", *discard_item.get("routes", [])]
        profile["post_discard_ev"] = discard_item.get("lookahead_ev", 0.0)
        profile["recommended"] = bool(profile.get("should_riichi"))
        profile["best_discard"] = discard_item
        profile["reason"] = "立直会锁手并押出一千点，AI 会比较进张、预期打点、危险度和局况后再决定是否立直。"
        return profile

    return turn_special_action_profile(game, seat, action, level)


def serialize_special_action_hint(profile: dict[str, Any]) -> dict[str, Any]:
    action: ActionChoice = profile["action"]
    best_discard = profile.get("best_discard")
    best_discard_tile = best_discard.get("tile_label") if isinstance(best_discard, dict) else None
    return {
        "id": action.action_id,
        "type": action.type,
        "label": action.label,
        "tile": tile_label(action.tile_id) if action.tile_id is not None else None,
        "current_shanten": profile.get("current_shanten"),
        "next_shanten": profile.get("next_shanten"),
        "routes": profile.get("routes", []),
        "speed_ev": profile.get("speed_ev", 0.0),
        "value_ev": profile.get("value_ev", 0.0),
        "defense_ev": profile.get("defense_ev", 0.0),
        "table_ev": profile.get("table_ev", 0.0),
        "post_discard_ev": profile.get("post_discard_ev", 0.0),
        "call_commitment_ev": profile.get("call_commitment_ev"),
        "call_commitment_label": profile.get("call_commitment_label", ""),
        "call_commitment_reason": profile.get("call_commitment_reason", ""),
        "call_commitment_blocker": profile.get("call_commitment_blocker"),
        "final_ev": profile.get("final_ev", 0.0),
        "threshold": profile.get("threshold", 0.0),
        "recommended": bool(profile.get("recommended", False)),
        "best_discard_tile": best_discard_tile,
        "strategy_label": profile.get("strategy_label", ""),
        "reason": profile.get("reason", ""),
        "yaku_label": profile.get("yaku_label", ""),
        "yaku_confidence": profile.get("yaku_confidence"),
        "has_yaku_path": profile.get("has_yaku_path"),
        "guaranteed_yaku": profile.get("guaranteed_yaku"),
    }


def special_action_hints(game: dict[str, Any], seat: int, level: int) -> list[dict[str, Any]]:
    round_state = game["round_state"]
    if round_state["phase"] == "DISCARD" and round_state["turn_seat"] == seat:
        actions = [action for action in build_turn_actions(game, seat) if action.type != "discard"]
    elif round_state["phase"] == "REACTION":
        actions = build_reaction_actions(game, seat)
        if actions:
            actions.append(ActionChoice("pass|hint", "pass", seat, "\u8fc7"))
    else:
        return []

    profiles = [special_action_profile_for_hint(game, seat, action, level) for action in actions]
    return [
        serialize_special_action_hint(profile)
        for profile in sorted(
            profiles,
            key=lambda item: (
                not bool(item.get("recommended", False)),
                -float(item.get("final_ev", 0.0)),
                item["action"].label,
            ),
        )
    ]


def build_hint_block(game: dict[str, Any]) -> dict[str, Any] | None:
    round_state = game["round_state"]
    seat = game["human_seat"]
    level = 3
    is_human_turn = round_state["phase"] == "DISCARD" and round_state["turn_seat"] == seat
    is_human_reaction = round_state["phase"] == "REACTION" and bool(build_reaction_actions(game, seat))
    if not is_human_turn and not is_human_reaction:
        return None

    shanten_value = hint_shanten_value(game, seat)
    profiles = sorted_discard_profiles(game, seat, level)[:3] if is_human_turn else []
    risk_context = build_tile_risk_context(game, seat)
    return {
        "shanten": shanten_value,
        "special_actions": special_action_hints(game, seat, level),
        "top_discards": [
            {
                "tile": item["tile_label"],
                "ukeire": item["ukeire"],
                "risk": item["risk"],
                "score": item["score"],
                "waits": item["waits"],
                "routes": item["routes"],
                "speed_ev": item["speed_ev"],
                "value_ev": item["value_ev"],
                "defense_ev": item["defense_ev"],
                "table_ev": item["table_ev"],
                "lookahead_ev": item["lookahead_ev"],
                "safety_ev": item["safety_ev"],
                "safety_score": item["safety_score"],
                "safety_label": item["safety_label"],
                "defense_mode": item["defense_mode"],
                "strategy_label": item["strategy_label"],
                "placement": item["placement"],
                "shape_ev": item["shape_ev"],
                "shape_label": item["shape_label"],
                "wait_quality": item["wait_quality"],
                "hand_value_ev": item["hand_value_ev"],
                "estimated_han": item["estimated_han"],
                "estimated_value": item["estimated_value"],
                "value_label": item["value_label"],
                "value_routes": item["value_routes"],
                "dora_count": item["dora_count"],
                "push_fold_ev": item["push_fold_ev"],
                "push_fold_label": item["push_fold_label"],
                "push_fold_mode": item["push_fold_mode"],
                "pressure_score": item["pressure_score"],
                "commitment_score": item["commitment_score"],
                "defense_override_ev": item["defense_override_ev"],
                "defense_override_mode": item["defense_override_mode"],
                "defense_override_label": item["defense_override_label"],
                "fold_need": item["fold_need"],
                "forced_defense": item["forced_defense"],
                "final_ev": item["final_ev"],
                "risk_sources": discard_risk_sources(game, seat, item["tile_id"], risk_context=risk_context),
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


def open_call_threshold(level: int, action_type: str, next_shanten: int) -> float:
    policy = ai_level_policy(level)
    if level <= 1:
        base = 40.0 if next_shanten <= 1 else 52.0
        return base + policy["call_threshold_shift"]
    if level == 2:
        base = 18.0 if next_shanten <= 1 else 28.0
        return base + policy["call_threshold_shift"]
    if action_type == "open_kan":
        base = 18.0 if next_shanten <= 1 else 30.0
        return base + policy["call_threshold_shift"]
    base = 6.0 if next_shanten <= 1 else 13.0
    return base + policy["call_threshold_shift"]


def open_call_profile(game: dict[str, Any], seat: int, action: ActionChoice, level: int) -> dict[str, Any]:
    round_state = game["round_state"]
    policy = ai_level_policy(level)
    if action.type == "ron":
        return {
            "action": action,
            "current_shanten": -1,
            "next_shanten": -1,
            "routes": ["荣和"],
            "speed_ev": 999.0,
            "value_ev": 999.0,
            "defense_ev": 0.0,
            "table_ev": 0.0,
            "post_discard_ev": 0.0,
            "final_ev": 1998.0,
            "threshold": 0.0,
            "should_call": True,
            "best_discard": None,
        }
    current_concealed = list(round_state["hands"][seat])
    current_shanten = shanten_of_tiles(current_concealed)
    new_concealed = list(current_concealed)
    try:
        pop_specific_tiles(new_concealed, action.consumed_ids)
    except ValueError:
        return {
            "action": action,
            "current_shanten": current_shanten,
            "next_shanten": 8,
            "routes": [],
            "speed_ev": -999.0,
            "value_ev": 0.0,
            "defense_ev": -999.0,
            "table_ev": 0.0,
            "post_discard_ev": 0.0,
            "final_ev": -1998.0,
            "threshold": 999.0,
            "should_call": False,
            "best_discard": None,
        }

    next_shanten = shanten_of_tiles(new_concealed)
    progress = round_progress_ratio(round_state)
    strategy = placement_strategy_context(game, seat)
    strategy_scale = policy["strategy_scale"]
    shanten_gain = current_shanten - next_shanten

    speed_ev = shanten_gain * (38.0 + level * 5.0)
    speed_ev += (strategy["attack_bias"] * 10.0 + strategy["call_bias"] * 8.0) * strategy_scale
    if next_shanten == 0:
        speed_ev += 20.0
    elif next_shanten == 1:
        speed_ev += 9.0
    if shanten_gain < 0:
        speed_ev -= 34.0
    if action.type == "chi" and shanten_gain <= 0:
        speed_ev -= 11.0 + progress * 8.0
    if action.type in {"pon", "open_kan"} and shanten_gain == 0:
        speed_ev += 4.5
    if action.type == "open_kan" and shanten_gain <= 0:
        speed_ev -= 14.0

    route_bonus, routes = call_route_profile(game, seat, action, new_concealed)
    yaku_profile = open_call_yaku_viability_profile(game, seat, action, new_concealed, routes, next_shanten, level)
    routes = unique_ordered_labels(routes + yaku_profile["routes"])[:5]
    value_scale = 0.72 if level == 1 else 0.92 if level == 2 else 1.08
    value_ev = route_bonus * value_scale
    value_ev += yaku_profile["yaku_ev"]
    value_ev += (strategy["value_bias"] * 13.0 + strategy["call_bias"] * 7.0) * strategy_scale
    if not routes:
        value_ev -= 16.0 if level >= 3 else 11.0
    elif not yaku_profile["has_yaku_path"]:
        value_ev -= 8.0 if level >= 3 else 5.0
    elif not yaku_profile["guaranteed_yaku"] and next_shanten >= 2:
        value_ev -= 5.0
    if action.type == "open_kan":
        value_ev += 4.0 if level >= 3 else -10.0

    best_discard = best_post_call_discard_profile(game, seat, new_concealed, level)
    post_discard_ev = 0.0
    if best_discard is not None:
        post_discard_ev += min(24.0, float(best_discard["ukeire"]) * 0.32)
        post_discard_ev -= float(best_discard["risk"]) * (3.2 + progress)
        if best_discard["shanten"] <= next_shanten:
            post_discard_ev += 4.0

    pressure = opponent_models(game, seat)
    max_threat = max((model["threat"] for model in pressure), default=0.0)
    max_loss = max((model["estimated_loss"] for model in pressure), default=0)
    call_commitment = open_call_commitment_profile(
        game,
        seat,
        action,
        current_shanten=current_shanten,
        next_shanten=next_shanten,
        shanten_gain=shanten_gain,
        yaku_profile=yaku_profile,
        best_discard=best_discard,
        max_threat=max_threat,
        max_loss=max_loss,
        progress=progress,
        strategy=strategy,
        level=level,
    )
    defense_ev = -(max_threat * (8.0 + progress * 12.0))
    defense_ev -= min(12.0, max_loss / 2600) * (0.25 + progress * 0.55)
    if action.type == "open_kan":
        defense_ev -= 8.0 + max_threat * 8.0
    if next_shanten <= 1:
        defense_ev *= 0.72
    defense_ev -= strategy["defense_bias"] * (5.5 + max_threat * 7.0) * strategy_scale

    own_points = game["players"][seat]["points"]
    top_points = max(player["points"] for player in game["players"])
    table_ev = 0.0
    if top_points - own_points >= 8000 and shanten_gain >= 0:
        table_ev += min(12.0, (top_points - own_points) / 2600)
    if own_points == top_points and max_threat > 0:
        table_ev -= 5.0 + progress * 5.0
    if seat == round_state["dealer_seat"] and next_shanten <= 1:
        table_ev += 4.5
    table_ev += (strategy["attack_bias"] * 7.0 + strategy["call_bias"] * 9.0 - strategy["defense_bias"] * 8.0) * strategy_scale

    final_ev = round(
        speed_ev + value_ev + defense_ev + table_ev + post_discard_ev + call_commitment["call_commitment_ev"],
        3,
    )
    threshold = open_call_threshold(level, action.type, next_shanten)
    threshold += yaku_profile["threshold_adjust"]
    threshold += call_commitment["threshold_adjust"]
    threshold -= (strategy["call_bias"] * 9.0 + strategy["attack_bias"] * 4.5) * strategy_scale
    threshold += strategy["defense_bias"] * 9.0 * strategy_scale
    if strategy_scale >= 0.6 and strategy["is_all_last"] and strategy["placement"] == 1:
        threshold += 6.0 * strategy_scale
    should_call = final_ev >= threshold
    if not yaku_profile["has_yaku_path"]:
        should_call = False
    elif not yaku_profile["guaranteed_yaku"] and shanten_gain <= 0 and action.type in {"pon", "chi", "open_kan"}:
        should_call = False
    elif not yaku_profile["guaranteed_yaku"] and next_shanten >= 2 and action.type in {"pon", "open_kan"}:
        should_call = False
    if call_commitment["call_commitment_blocker"]:
        should_call = False
    if action.type == "open_kan" and not policy["open_kan"]:
        should_call = False

    return {
        "action": action,
        "current_shanten": current_shanten,
        "next_shanten": next_shanten,
        "routes": routes,
        "speed_ev": round(speed_ev, 3),
        "value_ev": round(value_ev, 3),
        "defense_ev": round(defense_ev, 3),
        "table_ev": round(table_ev, 3),
        "post_discard_ev": round(post_discard_ev, 3),
        "call_commitment_ev": call_commitment["call_commitment_ev"],
        "call_commitment_label": call_commitment["call_commitment_label"],
        "call_commitment_reason": call_commitment["call_commitment_reason"],
        "call_commitment_blocker": call_commitment["call_commitment_blocker"],
        "final_ev": final_ev,
        "threshold": round(threshold, 3),
        "should_call": should_call,
        "best_discard": best_discard,
        "strategy_label": strategy["label"],
        "yaku_label": yaku_profile["yaku_label"],
        "yaku_reason": yaku_profile["yaku_reason"],
        "yaku_confidence": yaku_profile["yaku_confidence"],
        "has_yaku_path": yaku_profile["has_yaku_path"],
        "guaranteed_yaku": yaku_profile["guaranteed_yaku"],
    }


def should_call_open(game: dict[str, Any], seat: int, action: ActionChoice, level: int) -> bool:
    return bool(open_call_profile(game, seat, action, level)["should_call"])


def riichi_decision_profile(
    game: dict[str, Any],
    seat: int,
    action: ActionChoice,
    discard_profile_item: dict[str, Any],
    level: int,
) -> dict[str, Any]:
    round_state = game["round_state"]
    policy = ai_level_policy(level)
    progress = round_progress_ratio(round_state)
    ukeire = float(discard_profile_item["ukeire"])
    risk = float(discard_profile_item["risk"])
    shape_ev = float(discard_profile_item.get("shape_ev", 0.0))
    wait_quality = float(discard_profile_item.get("wait_quality", 0.5))
    hand_value_ev = float(discard_profile_item.get("hand_value_ev", 0.0))
    estimated_han = float(discard_profile_item.get("estimated_han", 0.0))
    own_points = game["players"][seat]["points"]
    top_points = max(player["points"] for player in game["players"])
    pressure = opponent_models(game, seat)
    max_threat = max((model["threat"] for model in pressure), default=0.0)
    max_loss = max((model["estimated_loss"] for model in pressure), default=0)
    strategy = placement_strategy_context(game, seat)
    strategy_scale = policy["strategy_scale"]

    speed_ev = min(24.0, ukeire * (2.15 + level * 0.2))
    value_ev = 18.0 + min(18.0, ukeire * 1.25)
    value_ev += shape_ev * (0.46 + level * 0.08)
    value_ev += hand_value_ev * (0.35 + level * 0.08)
    value_ev += (strategy["value_bias"] * 14.0 + strategy["riichi_bias"] * 16.0) * strategy_scale
    if seat == round_state["dealer_seat"]:
        value_ev += 5.0
    if can_double_riichi(round_state, seat):
        value_ev += 7.5

    defense_ev = -(risk * (7.5 + progress * 11.0))
    defense_ev -= max_threat * (4.0 + progress * 8.0)
    defense_ev -= min(7.0, max_loss / 4200) * progress
    defense_ev -= strategy["defense_bias"] * (6.0 + risk * 5.0) * strategy_scale
    if ukeire <= 2:
        defense_ev -= 7.0
    if progress > 0.72 and risk >= 1.0:
        defense_ev -= 8.0

    table_ev = 0.0
    if top_points - own_points >= 8000:
        table_ev += min(12.0, (top_points - own_points) / 2400)
    if own_points == top_points and max_threat > 0:
        table_ev -= 4.0 + progress * 6.0
    table_ev += (strategy["attack_bias"] * 6.0 + strategy["riichi_bias"] * 8.0 - strategy["defense_bias"] * 7.0) * strategy_scale
    deposit_ev = -4.0 if own_points <= 2000 else -2.0
    if game["players"][seat]["points"] < 1000:
        deposit_ev = -999.0

    final_ev = round(speed_ev + value_ev + defense_ev + table_ev + deposit_ev, 3)
    threshold = 30.0 if level == 1 else 22.0 if level == 2 else 13.0
    threshold += policy["riichi_threshold_shift"]
    if top_points - own_points >= 8000:
        threshold -= 4.0
    if own_points == top_points and progress > 0.55:
        threshold += 5.0
    if wait_quality >= 0.78:
        threshold -= 2.5
    elif wait_quality <= 0.35:
        threshold += 4.5
    if estimated_han >= 5 and wait_quality <= 0.45 and strategy["placement"] == 1:
        threshold += 3.5
    elif estimated_han <= 2 and wait_quality >= 0.55:
        threshold -= 1.5
    threshold -= (strategy["riichi_bias"] * 9.0 + strategy["attack_bias"] * 4.0) * strategy_scale
    threshold += strategy["defense_bias"] * 10.0 * strategy_scale
    if strategy_scale >= 0.6 and strategy["is_all_last"] and strategy["placement"] == 1:
        threshold += 8.0 * strategy_scale

    return {
        "action": action,
        "discard_profile": discard_profile_item,
        "speed_ev": round(speed_ev, 3),
        "value_ev": round(value_ev, 3),
        "defense_ev": round(defense_ev, 3),
        "table_ev": round(table_ev + deposit_ev, 3),
        "final_ev": final_ev,
        "threshold": round(threshold, 3),
        "should_riichi": final_ev >= threshold,
        "strategy_label": strategy["label"],
    }


def choose_ai_turn_action(game: dict[str, Any], seat: int) -> tuple[ActionChoice, str]:
    level = game["players"][seat]["ai_level"]
    policy = ai_level_policy(level)
    actions = build_turn_actions(game, seat)
    forced_tsumogiri = forced_riichi_tsumogiri_action(game, seat, actions)
    if forced_tsumogiri is not None:
        return forced_tsumogiri, "立直后无自摸或合法暗杠，按标准规则自动摸切。"
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
    if policy["closed_kan"]:
        for action in actions:
            if action.type == "closed_kan":
                return action, "局面安全，选择暗杠增加打点。"
    riichi_actions = [action for action in actions if action.type == "riichi"]
    if riichi_actions:
        risk_context = build_tile_risk_context(game, seat)
        profiles = {
            action.tile_id: discard_profile(
                game,
                seat,
                action.tile_id or 0,
                level,
                include_lookahead=False,
                risk_context=risk_context,
            )
            for action in riichi_actions
        }
        riichi_profiles = [
            riichi_decision_profile(game, seat, action, profiles[action.tile_id], level)
            for action in riichi_actions
        ]
        best_riichi_profile = max(riichi_profiles, key=lambda item: item["final_ev"])
        if best_riichi_profile["should_riichi"]:
            profile = best_riichi_profile["discard_profile"]
            return (
                best_riichi_profile["action"],
                f"立直EV {best_riichi_profile['final_ev']} 达标，局况 {best_riichi_profile['strategy_label']}，进张 {profile['ukeire']}，选择立直。",
            )
    discard_actions = [action for action in actions if action.type == "discard"]
    profiles = sorted_discard_profiles(game, seat, level)
    profile_lookup = {(tile_type(profile["tile_id"]), is_red(profile["tile_id"])): profile for profile in profiles}
    action_profiles = [
        profile_lookup[(tile_type(action.tile_id or 0), is_red(action.tile_id or 0))]
        for action in discard_actions
    ]
    chosen_profile = choose_profile_with_ai_policy(game, seat, action_profiles, level)
    chosen_discard = next(
        action
        for action in discard_actions
        if (tile_type(action.tile_id or 0), is_red(action.tile_id or 0)) == (tile_type(chosen_profile["tile_id"]), is_red(chosen_profile["tile_id"]))
    )
    profile = profile_lookup[(tile_type(chosen_discard.tile_id or 0), is_red(chosen_discard.tile_id or 0))]
    route_text = "/".join(profile["routes"]) if profile["routes"] else "牌效"
    best_profile = max(action_profiles, key=lambda item: item["score"])
    defense_note = f" | {profile['push_fold_label']}" if profile.get("forced_defense") else ""
    mistake_note = " | 难度随机" if chosen_profile["tile_id"] != best_profile["tile_id"] and level <= 2 else ""
    mistake_note += defense_note
    reason = (
        f"L{level} 选择 {profile['tile_label']} | 向听 {profile['shanten']} | 进张 {profile['ukeire']} | "
        f"风险 {profile['risk']} | 安全 {profile['safety_label']} | 前瞻 {profile['lookahead_ev']} | "
        f"形状 {profile['shape_label']} | 打点 {profile['value_label']} | 押退 {profile['push_fold_label']} | EV {profile['final_ev']} | "
        f"局况 {profile['strategy_label']} | 路线 {route_text}{mistake_note}"
    )
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
    declared: list[dict[str, Any]] = []
    for seat in range(count):
        if seat == game["human_seat"]:
            continue
        level = game["players"][seat]["ai_level"]
        seat_choices = build_reaction_actions(game, seat)
        seat_choices = [choice for choice in seat_choices if choice.type != "ron"]
        seat_profiles = [
            open_call_profile(game, seat, action, level)
            for action in seat_choices
        ]
        seat_profiles = [profile for profile in seat_profiles if profile["should_call"]]
        if seat_profiles:
            best_profile = max(seat_profiles, key=lambda profile: profile["final_ev"])
            declared.append(best_profile)
    if declared:
        selected = min(
            declared,
            key=lambda profile: (
                -ACTION_PRIORITY.get(profile["action"].type, 0),
                seat_distance(round_state["last_discard"]["seat"], profile["action"].seat, count),
                -profile["final_ev"],
            ),
        )
        action = selected["action"]
        level = game["players"][action.seat]["ai_level"]
        route_text = "/".join(selected["routes"]) if selected["routes"] else "速度"
        return (
            action,
            f"L{level} 选择{action.label} | 向听 {selected['current_shanten']}→{selected['next_shanten']} | "
            f"鸣牌EV {selected['final_ev']} | 局况 {selected.get('strategy_label', '')} | 路线 {route_text}",
        )
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
                forced_tsumogiri = forced_riichi_tsumogiri_action(game, seat, human_actions)
                if forced_tsumogiri is not None:
                    execute_action(game, forced_tsumogiri.action_id, actor_seat=seat, advance=False)
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
