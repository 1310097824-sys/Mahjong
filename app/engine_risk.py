"""对手建模、安全度和危险度评估。

AI 的防守判断集中在这里：根据对手立直、副露、染手迹象、役牌路线、弃牌河、宝牌
和巡目推测威胁等级，再给每张候选牌计算危险度/安全度。Rust core 已承接部分
批量危险度与安全度计算，Python 层保留解释性标签和规则兜底。
"""

from __future__ import annotations

from typing import Any

from app import rust_core
from app.engine_common import ai_level_policy
from app.engine_constants import (
    DRAGON_TYPES,
    OPEN_MELD_TYPES,
    RUST_DEFENSE_OVERRIDE_LABELS,
    RUST_DEFENSE_OVERRIDE_MODES,
    RUST_PUSH_FOLD_LABELS,
    RUST_PUSH_FOLD_MODES,
    RUST_ROUTE_LABELS,
    RUST_SAFE_RESERVE_LABELS,
    RUST_THREAT_LEVEL_CODES,
    RUST_THREAT_TYPE_CODES,
    SANMA_REMOVED_MANZU_TYPES,
    TRIPLET_MELD_TYPES,
)
from app.engine_rules import current_dora_indicators, ensure_game_defaults, is_closed_hand, seat_wind_label
from app.engine_shape import tenpai_wait_tile_types
from app.engine_tiles import (
    active_aka_dora_ids,
    calculate_shanten_for_tiles,
    calculate_shanten_from_counts,
    dora_from_indicator,
    is_honor,
    is_red,
    is_simple,
    is_terminal,
    is_tile_type_legal_in_mode,
    legal_tile_types_for_mode,
    sort_tiles,
    tile_label,
    tile_type,
    tile_type_label,
    to_34_array,
)


def unique_tile_type_candidates(tiles: list[int], game: dict[str, Any] | None = None) -> list[int]:
    candidates: list[int] = []
    seen_types: set[tuple[int, bool]] = set()
    for tile_id in sort_tiles(tiles, game):
        key = (tile_type(tile_id), is_red(tile_id, game))
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
            base_shanten = calculate_shanten_from_counts(counts)
        except ValueError:
            base_shanten = 8
    rust_result = rust_core.effective_tiles_after_discard(
        game["mode"],
        source_tiles,
        discard_tile_id,
        visible_counts,
        base_shanten,
    )
    if rust_result is not None:
        rust_ukeire, rust_good_tiles = rust_result
        return rust_ukeire, [
            {
                "type": int(item["type"]),
                "label": tile_type_label(int(item["type"])),
                "remaining": int(item["remaining"]),
            }
            for item in rust_good_tiles
        ]
    for tile_index in legal_tile_types_for_mode(game["mode"]):
        if counts[tile_index] >= 4 or visible_counts[tile_index] >= 4:
            continue
        test_tiles = tiles + [tile_index * 4]
        try:
            next_shanten = calculate_shanten_for_tiles(test_tiles)
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
        wait_types = tenpai_wait_tile_types(
            tiles_after_discard,
            mode=game["mode"],
            melds_data=game["round_state"]["melds"][seat],
        ) or good_types
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
        "threat_type": "unknown",
        "threat_level": "low",
        "threat_reasons": [],
        "push_pressure": 0.0,
        "flush_suit": None,
        "flush_with_honors": False,
        "toitoi": False,
        "tanyao": False,
        "yakuhai": False,
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

def threat_level_from_score(threat: float, estimated_loss: int, progress: float) -> str:
    pressure = threat + min(0.9, estimated_loss / 18000) + progress * 0.22
    if pressure >= 1.65:
        return "critical"
    if pressure >= 1.28:
        return "high"
    if pressure >= 0.88:
        return "medium"
    return "low"

def classify_opponent_threat(
    game: dict[str, Any],
    seat: int,
    opponent: int,
    profile: dict[str, Any],
    estimated_loss: int | None = None,
) -> dict[str, Any]:
    round_state = game["round_state"]
    progress = round_progress_ratio(round_state)
    routes = set(profile.get("routes", [])) | set(profile.get("labels", []))
    open_meld_count = int(profile.get("open_meld_count", 0))
    revealed_dora = int(profile.get("revealed_dora", 0))
    threat = float(profile.get("threat", 0.0))
    if estimated_loss is None:
        estimated_loss = estimate_opponent_loss(game, seat, opponent, profile)

    threat_type = "quiet"
    reasons: list[str] = []
    if profile.get("riichi"):
        threat_type = "riichi"
        reasons.append("立直")
    elif profile.get("flush_suit") is not None:
        threat_type = "flush"
        reasons.append("染手")
    elif profile.get("toitoi"):
        threat_type = "toitoi"
        reasons.append("对对")
    elif any(label in routes for label in {"役牌", "连风牌"}):
        threat_type = "yakuhai"
        reasons.append("役牌")
    elif open_meld_count >= 2:
        threat_type = "fast_open"
        reasons.append("副露快攻")
    elif open_meld_count == 1 or round_state["nuki_count"][opponent]:
        threat_type = "open_probe"
        reasons.append("副露推进")

    if revealed_dora >= 2 or estimated_loss >= 8000:
        reasons.append("高打点")
    if opponent == round_state["dealer_seat"]:
        reasons.append("亲家")
    if progress >= 0.68:
        reasons.append("晚巡")

    level = threat_level_from_score(threat, estimated_loss, progress)
    push_pressure = threat + min(0.95, estimated_loss / 16000) + progress * 0.35
    if threat_type == "riichi":
        push_pressure += 0.24
    elif threat_type in {"flush", "toitoi"}:
        push_pressure += 0.18
    elif threat_type == "yakuhai":
        push_pressure += 0.1
    if opponent == round_state["dealer_seat"]:
        push_pressure += 0.12

    return {
        "threat_type": threat_type,
        "threat_level": level,
        "threat_reasons": unique_ordered_labels(reasons)[:4],
        "push_pressure": round(max(0.0, min(2.6, push_pressure)), 3),
    }

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
    yakuhai = bool(triplet_types & value_honor_types)
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

    active_red_ids = active_aka_dora_ids(game)
    revealed_dora = sum(
        1
        for meld in melds
        for tile_id in meld["tiles"]
        if tile_id in active_red_ids or tile_type(tile_id) in dora_types
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
        "yakuhai": yakuhai,
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
    opponent_discards = profile.get("_discard_types")
    if opponent_discards is None:
        opponent_discards = {tile_type(item["tile"]) for item in round_state["discards"][opponent]}
    if tile_index in opponent_discards:
        return 0.0

    routes = set(profile.get("routes", [])) | set(profile.get("labels", []))
    value_honor_types = set(profile.get("value_honor_types", set()))
    threat_type = str(profile.get("threat_type", "unknown"))
    threat_level = str(profile.get("threat_level", "low"))
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

    if threat_type == "riichi":
        tile_base *= 1.12
    elif threat_type == "flush" and suit_index == flush_suit:
        tile_base *= 1.08
    elif threat_type == "yakuhai" and (is_honor(tile_index) or tile_index in value_honor_types):
        tile_base *= 1.12
    elif threat_type == "fast_open" and not is_honor(tile_index):
        tile_base *= 1.06

    tile_base *= {
        "critical": 1.18,
        "high": 1.1,
        "medium": 1.03,
    }.get(threat_level, 1.0)

    if dora_types is None:
        dora_types = {dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(round_state)}
    if is_red(discard_tile_id, game) or tile_index in dora_types:
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
        estimated_loss = estimate_opponent_loss(game, seat, opponent, profile)
        profile.update(classify_opponent_threat(game, seat, opponent, profile, estimated_loss))
        profile["_discard_types"] = {tile_type(item["tile"]) for item in round_state["discards"][opponent]}
        opponents.append(
            {
                "seat": opponent,
                "profile": profile,
                "estimated_loss": estimated_loss,
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
        base += cached_tile_danger_against_opponent(game, seat, discard_tile_id, item, context)
    return round(base, 3)

def ensure_rust_danger_cache(game: dict[str, Any], seat: int, risk_context: dict[str, Any]) -> None:
    if risk_context.get("_rust_danger_attempted"):
        return
    risk_context["_rust_danger_attempted"] = True
    opponents = risk_context.get("opponents", [])
    if not opponents:
        return

    cache = risk_context.setdefault("danger_cache", {})
    progress = round_progress_ratio(game["round_state"])
    red_tile_ids = active_aka_dora_ids(game)
    for item in opponents:
        opponent = int(item["seat"])
        profile = item["profile"]
        danger_table = rust_core.tile_danger_for_opponent(
            risk_context["visible_counts"],
            profile.get("_discard_types", set()),
            profile.get("value_honor_types", set()),
            risk_context.get("dora_types", set()),
            red_tile_ids,
            threat=float(profile.get("threat", 0.0)),
            estimated_loss=int(item.get("estimated_loss", 0)),
            progress=progress,
            threat_type=RUST_THREAT_TYPE_CODES.get(str(profile.get("threat_type", "")), 0),
            threat_level=RUST_THREAT_LEVEL_CODES.get(str(profile.get("threat_level", "")), 0),
            flush_suit=profile.get("flush_suit"),
            flush_with_honors=bool(profile.get("flush_with_honors", False)),
            toitoi=bool(profile.get("toitoi", False)),
            tanyao_route=bool(profile.get("tanyao", False)),
            yakuhai_route=bool(profile.get("yakuhai", False)),
            riichi=bool(profile.get("riichi", False)),
            open_meld_count=int(profile.get("open_meld_count", 0)),
        )
        if danger_table is None:
            continue
        for tile_id, danger in enumerate(danger_table):
            cache[(opponent, tile_id)] = float(danger)

def cached_tile_danger_against_opponent(
    game: dict[str, Any],
    seat: int,
    discard_tile_id: int,
    opponent_item: dict[str, Any],
    risk_context: dict[str, Any],
) -> float:
    cache = risk_context.setdefault("danger_cache", {})
    key = (int(opponent_item["seat"]), int(discard_tile_id))
    if key in cache:
        return float(cache[key])
    ensure_rust_danger_cache(game, seat, risk_context)
    if key in cache:
        return float(cache[key])
    danger = tile_danger_against_opponent(
        game,
        seat,
        opponent_item["seat"],
        discard_tile_id,
        opponent_item["profile"],
        risk_context["visible_counts"],
        dora_types=risk_context["dora_types"],
        estimated_loss=opponent_item["estimated_loss"],
    )
    cache[key] = danger
    return danger

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
        danger = cached_tile_danger_against_opponent(game, seat, discard_tile_id, item, context)
        if danger <= 0:
            continue
        labels = profile.get("routes") or profile.get("labels") or [profile.get("speed_class", "推进")]
        sources.append(
            {
                "seat": opponent,
                "name": game["players"][opponent]["name"],
                "risk": round(danger, 3),
                "routes": unique_ordered_labels(list(profile.get("threat_reasons", [])) + list(labels))[:3],
                "estimated_loss": item["estimated_loss"],
                "threat_type": profile.get("threat_type", "unknown"),
                "threat_level": profile.get("threat_level", "low"),
            }
        )
    return sorted(sources, key=lambda item: (-item["risk"], -item["estimated_loss"]))[:3]

def discard_deal_in_loss_profile(
    game: dict[str, Any],
    seat: int,
    discard_tile_id: int,
    *,
    risk_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = risk_context if risk_context is not None else build_tile_risk_context(game, seat)
    opponents = context["opponents"]
    if not opponents:
        return {
            "deal_in_loss_ev": 0.0,
            "deal_in_rate": 0.0,
            "deal_in_points": 0,
            "deal_in_label": "无放铳压力",
        }

    visible_counts = context["visible_counts"]
    tile_index = tile_type(discard_tile_id)
    progress = round_progress_ratio(game["round_state"])
    total_expected_points = 0.0
    max_rate = 0.0
    dangers: list[float] = []
    safeties: list[float] = []
    safety_labels: list[str] = []
    push_pressures: list[float] = []
    estimated_losses: list[int] = []
    threat_level_codes: list[int] = []
    threat_type_codes: list[int] = []
    top_label = "低风险"

    for item in opponents:
        opponent = item["seat"]
        profile = item["profile"]
        danger = cached_tile_danger_against_opponent(game, seat, discard_tile_id, item, context)
        if danger <= 0:
            continue
        safety, safety_label = cached_tile_safety_against_opponent(
            game,
            opponent,
            tile_index,
            profile,
            visible_counts,
            context,
        )
        push_pressure = float(profile.get("push_pressure", profile.get("threat", 0.0)))
        threat_level = str(profile.get("threat_level", "low"))
        threat_type = str(profile.get("threat_type", "unknown"))
        dangers.append(danger)
        safeties.append(safety)
        safety_labels.append(safety_label)
        push_pressures.append(push_pressure)
        estimated_losses.append(int(item["estimated_loss"]))
        threat_level_codes.append(RUST_THREAT_LEVEL_CODES.get(threat_level, 0))
        threat_type_codes.append(RUST_THREAT_TYPE_CODES.get(threat_type, 0))
        level_rate = {
            "critical": 1.45,
            "high": 1.24,
            "medium": 1.08,
            "low": 0.9,
        }.get(threat_level, 1.0)
        type_rate = {
            "riichi": 1.18,
            "flush": 1.1,
            "toitoi": 1.08,
            "yakuhai": 1.06,
            "fast_open": 1.05,
        }.get(threat_type, 1.0)
        safety_discount = max(0.38, 1.08 - safety * 0.68)
        raw_rate = danger * 0.034 * level_rate * type_rate * safety_discount
        raw_rate *= 0.72 + progress * 0.62 + min(0.32, push_pressure * 0.1)
        deal_in_rate = max(0.0, min(0.42, raw_rate))
        expected_points = deal_in_rate * int(item["estimated_loss"])
        total_expected_points += expected_points
        if deal_in_rate > max_rate:
            max_rate = deal_in_rate
            top_label = safety_label

    rust_profile = rust_core.deal_in_loss_profile(
        dangers=dangers,
        safeties=safeties,
        push_pressures=push_pressures,
        estimated_losses=estimated_losses,
        threat_level_codes=threat_level_codes,
        threat_type_codes=threat_type_codes,
        progress=progress,
    )
    if rust_profile is not None:
        max_rate = float(rust_profile["deal_in_rate"])
        top_index = int(rust_profile["top_index"])
        if 0 <= top_index < len(safety_labels):
            top_label = safety_labels[top_index]
        if max_rate >= 0.18:
            label = f"楂樻斁閾抽闄╋細{top_label}"
        elif max_rate >= 0.09:
            label = f"涓斁閾抽闄╋細{top_label}"
        elif max_rate > 0:
            label = f"浣庢斁閾抽闄╋細{top_label}"
        else:
            label = "瀹夊叏鐗屽帇鍔涗綆"
        return {
            "deal_in_loss_ev": float(rust_profile["deal_in_loss_ev"]),
            "deal_in_rate": max_rate,
            "deal_in_points": int(rust_profile["deal_in_points"]),
            "deal_in_label": label,
        }

    loss_ev = -(total_expected_points / 118.0)
    if max_rate >= 0.18:
        label = f"高放铳风险：{top_label}"
    elif max_rate >= 0.09:
        label = f"中放铳风险：{top_label}"
    elif max_rate > 0:
        label = f"低放铳风险：{top_label}"
    else:
        label = "安全牌压力低"

    return {
        "deal_in_loss_ev": round(max(-120.0, min(0.0, loss_ev)), 3),
        "deal_in_rate": round(max_rate, 3),
        "deal_in_points": int(round(total_expected_points)),
        "deal_in_label": label,
    }

def tile_safety_against_opponent(
    game: dict[str, Any],
    opponent: int,
    tile_index: int,
    profile: dict[str, Any],
    visible_counts: list[int],
) -> tuple[float, str]:
    round_state = game["round_state"]
    opponent_discards = profile.get("_discard_types")
    if opponent_discards is None:
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

def cached_tile_safety_against_opponent(
    game: dict[str, Any],
    opponent: int,
    tile_index: int,
    profile: dict[str, Any],
    visible_counts: list[int],
    risk_context: dict[str, Any],
) -> tuple[float, str]:
    cache = risk_context.setdefault("safety_cache", {})
    key = (int(opponent), int(tile_index))
    if key in cache:
        return cache[key]
    result = tile_safety_against_opponent(game, opponent, tile_index, profile, visible_counts)
    cache[key] = result
    return result

def ensure_rust_aggregate_safety_cache(game: dict[str, Any], risk_context: dict[str, Any]) -> None:
    if risk_context.get("_rust_aggregate_safety_attempted"):
        return
    risk_context["_rust_aggregate_safety_attempted"] = True
    opponents = risk_context.get("opponents", [])
    if not opponents:
        return

    opponent_discard_types: list[set[int]] = []
    value_honor_types: list[set[int]] = []
    weights: list[float] = []
    tanyao_routes: list[bool] = []
    for item in opponents:
        profile = item["profile"]
        threat = float(profile.get("threat", 0.0))
        push_pressure = float(profile.get("push_pressure", threat))
        estimated_loss = int(item["estimated_loss"])
        weight = max(threat, push_pressure * 0.72) * (0.7 + min(0.9, estimated_loss / 22000))
        opponent_discard_types.append(set(profile.get("_discard_types", set())))
        value_honor_types.append(set(profile.get("value_honor_types", set())))
        weights.append(weight)
        tanyao_routes.append(bool(profile.get("tanyao", False)))

    scores = rust_core.aggregate_safety_scores(
        risk_context["visible_counts"],
        opponent_discard_types,
        value_honor_types,
        weights,
        tanyao_routes,
    )
    if scores is None:
        return

    safety_cache = risk_context.setdefault("aggregate_safety_cache", {})
    for tile_index, score in enumerate(scores):
        safety_cache[tile_index] = float(score)

def aggregate_tile_safety_score(
    game: dict[str, Any],
    seat: int,
    tile_index: int,
    risk_context: dict[str, Any],
) -> float:
    opponents = risk_context["opponents"]
    if not opponents:
        return 0.0
    safety_cache = risk_context.setdefault("aggregate_safety_cache", {})
    if tile_index in safety_cache:
        return float(safety_cache[tile_index])
    ensure_rust_aggregate_safety_cache(game, risk_context)
    if tile_index in safety_cache:
        return float(safety_cache[tile_index])

    visible_counts = risk_context["visible_counts"]
    weighted_safety = 0.0
    total_weight = 0.0
    for item in opponents:
        profile = item["profile"]
        threat = float(profile.get("threat", 0.0))
        push_pressure = float(profile.get("push_pressure", threat))
        estimated_loss = int(item["estimated_loss"])
        weight = max(threat, push_pressure * 0.72) * (0.7 + min(0.9, estimated_loss / 22000))
        safety, _ = cached_tile_safety_against_opponent(
            game,
            item["seat"],
            tile_index,
            profile,
            visible_counts,
            risk_context,
        )
        weighted_safety += safety * weight
        total_weight += weight
    score = weighted_safety / total_weight if total_weight else 0.0
    safety_cache[tile_index] = score
    return score

def safe_tile_reserve_profile(
    game: dict[str, Any],
    seat: int,
    remaining_tiles: list[int],
    discarded_tile_id: int,
    shanten_value: int,
    risk_context: dict[str, Any],
) -> dict[str, Any]:
    opponents = risk_context["opponents"]
    if not opponents:
        return {
            "safe_reserve_ev": 0.0,
            "safe_reserve_score": 0.0,
            "safe_reserve_label": "无明显威胁",
        }

    progress = round_progress_ratio(game["round_state"])
    max_pressure = max(
        float(item["profile"].get("push_pressure", item["profile"].get("threat", 0.0))) for item in opponents
    )
    if shanten_value <= 0 and max_pressure < 1.28:
        target_reserve = 0.58
    elif shanten_value <= 1:
        target_reserve = 0.9
    else:
        target_reserve = 1.2

    ensure_rust_aggregate_safety_cache(game, risk_context)
    aggregate_cache = risk_context.get("aggregate_safety_cache", {})
    if all(tile_index in aggregate_cache for tile_index in range(34)):
        rust_result = rust_core.safe_tile_reserve_profile(
            game["mode"],
            remaining_tiles,
            discarded_tile_id,
            shanten_value,
            progress,
            max_pressure,
            [float(aggregate_cache[tile_index]) for tile_index in range(34)],
        )
        if rust_result is not None:
            reserve_ev, reserve_score, label_code = rust_result
            return {
                "safe_reserve_ev": round(max(-42.0, min(18.0, reserve_ev)), 3),
                "safe_reserve_score": round(reserve_score, 3),
                "safe_reserve_label": RUST_SAFE_RESERVE_LABELS.get(label_code, "安全牌储备可接受"),
            }

    remaining_scores: list[float] = []
    for tile_id in remaining_tiles:
        tile_index = tile_type(tile_id)
        if not is_tile_type_legal_in_mode(tile_index, game["mode"]):
            continue
        remaining_scores.append(aggregate_tile_safety_score(game, seat, tile_index, risk_context))

    best_reserves = sorted(remaining_scores, reverse=True)[:2]
    reserve_score = sum(best_reserves)
    discarded_safety = aggregate_tile_safety_score(game, seat, tile_type(discarded_tile_id), risk_context)
    pressure_scale = 0.58 + min(1.0, max_pressure / 1.65) + progress * 0.24
    reserve_gap = max(0.0, target_reserve - reserve_score)
    reserve_ev = -reserve_gap * (12.0 + pressure_scale * 9.0)

    if discarded_safety >= 0.74 and reserve_score < target_reserve:
        reserve_ev -= (discarded_safety - max(best_reserves or [0.0])) * (9.0 + pressure_scale * 8.0)
    elif reserve_score >= target_reserve + 0.28:
        reserve_ev += min(8.0, (reserve_score - target_reserve) * (6.0 + pressure_scale * 3.0))

    if reserve_score >= target_reserve + 0.28:
        label = "保留了安全牌储备"
    elif discarded_safety >= 0.74 and reserve_score < target_reserve:
        label = "切掉安全牌后储备不足"
    elif reserve_score < target_reserve:
        label = "安全牌储备偏少"
    else:
        label = "安全牌储备可接受"

    return {
        "safe_reserve_ev": round(max(-42.0, min(18.0, reserve_ev)), 3),
        "safe_reserve_score": round(reserve_score, 3),
        "safe_reserve_label": label,
    }

def safe_reserve_profiles_for_discards(
    game: dict[str, Any],
    seat: int,
    source_tiles: list[int],
    risk_context: dict[str, Any],
    precomputed_discard_metrics: dict[int, dict[str, Any]] | None,
) -> dict[int, dict[str, Any]] | None:
    opponents = risk_context["opponents"]
    if not opponents or precomputed_discard_metrics is None:
        return None

    ensure_rust_aggregate_safety_cache(game, risk_context)
    aggregate_cache = risk_context.get("aggregate_safety_cache", {})
    if not all(tile_index in aggregate_cache for tile_index in range(34)):
        return None

    max_pressure = max(
        float(item["profile"].get("push_pressure", item["profile"].get("threat", 0.0))) for item in opponents
    )
    shanten_by_discard = [99] * 34
    for tile_index, metric in precomputed_discard_metrics.items():
        if 0 <= int(tile_index) < 34:
            shanten_by_discard[int(tile_index)] = int(metric["shanten"])

    rust_profiles = rust_core.safe_tile_reserve_profiles_after_discards(
        game["mode"],
        source_tiles,
        shanten_by_discard,
        round_progress_ratio(game["round_state"]),
        max_pressure,
        [float(aggregate_cache[tile_index]) for tile_index in range(34)],
    )
    if rust_profiles is None:
        return None

    return {
        tile_index: {
            "safe_reserve_ev": round(max(-42.0, min(18.0, reserve_ev)), 3),
            "safe_reserve_score": round(reserve_score, 3),
            "safe_reserve_label": RUST_SAFE_RESERVE_LABELS.get(label_code, "安全牌储备可接受"),
        }
        for tile_index, (reserve_ev, reserve_score, label_code) in rust_profiles.items()
    }

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
    max_push_pressure = 0.0
    max_loss = 0
    high_threat_count = 0

    for item in opponents:
        profile = item["profile"]
        estimated_loss = int(item["estimated_loss"])
        threat = float(profile["threat"])
        push_pressure = float(profile.get("push_pressure", threat))
        max_threat = max(max_threat, threat)
        max_push_pressure = max(max_push_pressure, push_pressure)
        max_loss = max(max_loss, estimated_loss)
        if profile.get("threat_level") in {"high", "critical"}:
            high_threat_count += 1
        weight = max(threat, push_pressure * 0.72) * (0.72 + min(0.85, estimated_loss / 24000))
        safety, label = cached_tile_safety_against_opponent(
            game,
            item["seat"],
            tile_index,
            profile,
            visible_counts,
            risk_context,
        )
        weighted_safety += safety * weight
        total_weight += weight
        label_weights[label] = label_weights.get(label, 0.0) + weight

    safety_score = weighted_safety / total_weight if total_weight else 0.0
    progress = round_progress_ratio(round_state)
    pressure = (
        max_threat
        + max_push_pressure * 0.22
        + min(0.72, max_loss / 24000)
        + progress * 0.38
        + high_threat_count * 0.08
    )
    offense_commitment = 0.58 if shanten_value <= 0 else 0.42 if shanten_value == 1 else 0.18 if shanten_value == 2 else -0.06
    level_scale = policy["defense_scale"]
    rust_profile = rust_core.defensive_discard_profile(
        safety_score=safety_score,
        shanten_value=shanten_value,
        level_scale=level_scale,
        progress=progress,
        max_threat=max_threat,
        max_push_pressure=max_push_pressure,
        max_loss=max_loss,
        high_threat_count=high_threat_count,
    )
    if rust_profile is not None:
        defense_mode = bool(rust_profile["defense_mode"])
        label = max(label_weights.items(), key=lambda item: item[1])[0] if label_weights else "\u666e\u901a"
        if defense_mode and safety_score >= 0.82:
            label = f"\u9632\u5b88\uff1a{label}"
        elif defense_mode and safety_score <= 0.2:
            label = "\u9ad8\u5371\u63a8\u8fdb"
        return {
            "safety_score": float(rust_profile["safety_score"]),
            "safety_label": label,
            "defense_mode": defense_mode,
            "safety_ev": float(rust_profile["safety_ev"]),
        }
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
    max_push_pressure = max(
        float(item["profile"].get("push_pressure", item["profile"]["threat"])) for item in opponents
    )
    max_loss = max(int(item["estimated_loss"]) for item in opponents)
    riichi_count = sum(1 for item in opponents if item["profile"].get("riichi"))
    critical_count = sum(1 for item in opponents if item["profile"].get("threat_level") == "critical")
    high_count = sum(1 for item in opponents if item["profile"].get("threat_level") == "high")
    rust_profile = rust_core.push_fold_profile(
        shanten_value=shanten_value,
        risk=risk,
        safety_score=safety_score,
        hand_value_ev=hand_value_ev,
        estimated_han=estimated_han,
        wait_quality=wait_quality,
        progress=progress,
        max_threat=max_threat,
        max_push_pressure=max_push_pressure,
        max_loss=max_loss,
        riichi_count=riichi_count,
        critical_count=critical_count,
        high_count=high_count,
        defense_scale=policy["defense_scale"],
        strategy_scale=policy["strategy_scale"],
        attack_bias=strategy["attack_bias"],
        defense_bias=strategy["defense_bias"],
        value_bias=strategy["value_bias"],
        is_dealer=strategy["is_dealer"],
        placement=strategy["placement"],
        placement_count=strategy["placement_count"],
        is_all_last=strategy["is_all_last"],
    )
    if rust_profile is not None:
        return {
            "push_fold_ev": float(rust_profile["push_fold_ev"]),
            "push_fold_label": RUST_PUSH_FOLD_LABELS.get(int(rust_profile["label_code"]), "边界半押"),
            "push_fold_mode": RUST_PUSH_FOLD_MODES.get(int(rust_profile["mode_code"]), "balanced"),
            "pressure_score": float(rust_profile["pressure_score"]),
            "commitment_score": float(rust_profile["commitment_score"]),
        }

    pressure = (
        max_threat * 0.82
        + max_push_pressure * 0.3
        + min(0.92, max_loss / 18000)
        + min(0.72, risk / 4.8)
        + progress * 0.42
        + riichi_count * 0.16
        + critical_count * 0.16
        + high_count * 0.08
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
    max_push_pressure = max(
        float(item["profile"].get("push_pressure", item["profile"]["threat"])) for item in opponents
    )
    max_loss = max(int(item["estimated_loss"]) for item in opponents)
    riichi_count = sum(1 for item in opponents if item["profile"].get("riichi"))
    critical_count = sum(1 for item in opponents if item["profile"].get("threat_level") == "critical")
    high_count = sum(1 for item in opponents if item["profile"].get("threat_level") == "high")
    open_monster_count = sum(
        1
        for item in opponents
        if item["profile"].get("open_meld_count", 0) >= 3 or int(item["estimated_loss"]) >= 8000
    )
    rust_profile = rust_core.defense_override_profile(
        shanten_value=shanten_value,
        risk=risk,
        safety_score=safety_score,
        hand_value_ev=hand_value_ev,
        estimated_han=estimated_han,
        wait_quality=wait_quality,
        level=level,
        progress=progress,
        max_threat=max_threat,
        max_push_pressure=max_push_pressure,
        max_loss=max_loss,
        riichi_count=riichi_count,
        critical_count=critical_count,
        high_count=high_count,
        open_monster_count=open_monster_count,
        attack_bias=strategy["attack_bias"],
        defense_bias=strategy["defense_bias"],
        value_bias=strategy["value_bias"],
        placement=strategy["placement"],
        placement_count=strategy["placement_count"],
        is_all_last=strategy["is_all_last"],
    )
    if rust_profile is not None:
        return {
            "defense_override_ev": float(rust_profile["defense_override_ev"]),
            "defense_override_mode": RUST_DEFENSE_OVERRIDE_MODES.get(int(rust_profile["mode_code"]), ""),
            "defense_override_label": RUST_DEFENSE_OVERRIDE_LABELS.get(int(rust_profile["label_code"]), ""),
            "fold_need": float(rust_profile["fold_need"]),
        }

    pressure = (
        max_threat
        + max_push_pressure * 0.28
        + min(0.95, max_loss / 17000)
        + min(0.72, risk / 4.2)
        + progress * 0.46
        + riichi_count * 0.24
        + critical_count * 0.2
        + high_count * 0.1
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
    ttype = tile_type(discard_tile_id)
    wind = seat_wind_label(round_state, seat)
    own_wind_type = round_state["wind_type_map"][wind]
    round_wind_type = round_state["wind_type_map"][round_state["prevalent_wind"]]
    dora_types = {dora_from_indicator(tile, mode=game["mode"]) for tile in current_dora_indicators(round_state)}
    rust_bonus = rust_core.tile_value_bonus(
        discard_tile_id,
        is_red_tile=is_red(discard_tile_id, game),
        own_wind_type=own_wind_type,
        round_wind_type=round_wind_type,
        dora_types=dora_types,
    )
    if rust_bonus is not None:
        return rust_bonus

    bonus = 0.0
    if is_red(discard_tile_id, game):
        bonus += 1.0
    if ttype in dora_types:
        bonus += 0.75
    if ttype == own_wind_type:
        bonus += 0.35
    if ttype == round_wind_type:
        bonus += 0.35
    return bonus

def visible_tile_type_counts(game: dict[str, Any], seat: int, *, hand_tiles: list[int] | None = None) -> list[int]:
    round_state = game["round_state"]
    visible_tiles = list(round_state["hands"][seat] if hand_tiles is None else hand_tiles)
    for discards in round_state["discards"]:
        for item in discards:
            if item.get("called", False):
                continue
            visible_tiles.append(item["tile"])
    for melds in round_state["melds"]:
        for meld in melds:
            visible_tiles.extend(meld["tiles"])
    visible_tiles.extend(current_dora_indicators(round_state))

    rust_counts = rust_core.visible_counts_from_tiles(game["mode"], visible_tiles)
    if rust_counts is not None:
        return rust_counts

    counts = [0] * 34

    for tile_id in visible_tiles:
        counts[tile_type(tile_id)] += 1

    if game["mode"] == "3P":
        for tile_index in SANMA_REMOVED_MANZU_TYPES:
            counts[tile_index] = 4

    return [min(4, value) for value in counts]

def discard_metrics_for_hand(game: dict[str, Any], seat: int, source_tiles: list[int]) -> dict[int, dict[str, Any]] | None:
    source_counts = to_34_array(source_tiles)
    base_visible_counts = visible_tile_type_counts(game, seat, hand_tiles=[])
    rust_metrics = rust_core.discard_metrics_from_counts(game["mode"], source_counts, base_visible_counts)
    if rust_metrics is None:
        return None
    return {
        tile_index: {
            "shanten": int(metric["shanten"]),
            "ukeire": int(metric["ukeire"]),
            "good_tiles": [
                {
                    "type": int(item["type"]),
                    "label": tile_type_label(int(item["type"])),
                    "remaining": int(item["remaining"]),
                }
                for item in metric["good_tiles"]
            ],
        }
        for tile_index, metric in rust_metrics.items()
    }

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

    wind = seat_wind_label(round_state, seat)
    value_honor_types = {
        round_state["wind_type_map"][wind],
        round_state["wind_type_map"][round_state["prevalent_wind"]],
        31,
        32,
        33,
    }
    closed = is_closed_hand(round_state, seat)
    triplet_meld_count = sum(1 for meld in melds if meld["type"] in TRIPLET_MELD_TYPES)
    value_honor_triplet_meld_count = sum(
        1
        for meld in melds
        if meld["type"] in TRIPLET_MELD_TYPES and tile_type(meld["tiles"][0]) in value_honor_types
    )
    all_counts = [0] * 34
    for tile_index in all_tile_types:
        all_counts[tile_index] += 1

    rust_profile = rust_core.hand_route_profile(
        counts,
        all_counts,
        value_honor_types,
        triplet_meld_count=triplet_meld_count,
        value_honor_triplet_meld_count=value_honor_triplet_meld_count,
        closed=closed,
        has_melds=bool(melds),
        shanten_value=shanten_value,
    )
    if rust_profile is not None:
        bonus, route_mask = rust_profile
        routes = [label for bit, label in RUST_ROUTE_LABELS if route_mask & bit]
        return round(bonus, 3), routes[:3]

    simple_count = sum(1 for ttype in all_tile_types if is_simple(ttype))
    terminal_count = sum(1 for ttype in all_tile_types if is_terminal(ttype))
    honor_count = sum(1 for ttype in all_tile_types if is_honor(ttype))
    suit_counts = [sum(1 for ttype in all_tile_types if tile_suit_index(ttype) == suit) for suit in range(3)]
    dominant_suit = max(range(3), key=lambda suit: suit_counts[suit]) if any(suit_counts) else 0
    pair_count = sum(1 for value in counts if value >= 2)
    triplet_count = sum(1 for value in counts if value >= 3) + triplet_meld_count

    value_honor_sets = sum(1 for ttype in value_honor_types if counts[ttype] >= 2)
    value_honor_sets += value_honor_triplet_meld_count

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

    if closed and not melds and pair_count >= 4:
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

def route_profiles_for_discards(
    game: dict[str, Any],
    seat: int,
    source_tiles: list[int],
    precomputed_discard_metrics: dict[int, dict[str, Any]] | None,
) -> dict[int, dict[str, Any]] | None:
    if precomputed_discard_metrics is None:
        return None

    round_state = game["round_state"]
    source_counts = to_34_array(source_tiles)
    melds = [meld for meld in round_state["melds"][seat] if meld["type"] != "kita"]
    meld_counts = [0] * 34
    for meld in melds:
        for tile_id in meld["tiles"]:
            meld_counts[tile_type(tile_id)] += 1

    wind = seat_wind_label(round_state, seat)
    value_honor_types = {
        round_state["wind_type_map"][wind],
        round_state["wind_type_map"][round_state["prevalent_wind"]],
        31,
        32,
        33,
    }
    shanten_by_discard = [99] * 34
    for tile_index, metric in precomputed_discard_metrics.items():
        if 0 <= int(tile_index) < 34:
            shanten_by_discard[int(tile_index)] = int(metric["shanten"])

    triplet_meld_count = sum(1 for meld in melds if meld["type"] in TRIPLET_MELD_TYPES)
    value_honor_triplet_meld_count = sum(
        1
        for meld in melds
        if meld["type"] in TRIPLET_MELD_TYPES and tile_type(meld["tiles"][0]) in value_honor_types
    )
    rust_profiles = rust_core.hand_route_profiles_after_discards(
        game["mode"],
        source_counts,
        meld_counts,
        value_honor_types,
        shanten_by_discard,
        triplet_meld_count=triplet_meld_count,
        value_honor_triplet_meld_count=value_honor_triplet_meld_count,
        closed=is_closed_hand(round_state, seat),
        has_melds=bool(melds),
    )
    if rust_profiles is None:
        return None

    return {
        tile_index: {
            "route_bonus": round(bonus, 3),
            "routes": [label for bit, label in RUST_ROUTE_LABELS if route_mask & bit][:3],
        }
        for tile_index, (bonus, route_mask) in rust_profiles.items()
    }

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
    active_red_ids = active_aka_dora_ids(game)
    dora_count = sum(1 for tile_id in all_tiles if tile_id in active_red_ids or tile_type(tile_id) in dora_types)
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
        profile.update(classify_opponent_threat(game, seat, opponent, profile, estimated_loss))

        models.append(
            {
                "seat": opponent,
                "threat": profile["threat"],
                "threat_type": profile.get("threat_type", "unknown"),
                "threat_level": profile.get("threat_level", "low"),
                "threat_reasons": profile.get("threat_reasons", []),
                "push_pressure": profile.get("push_pressure", profile["threat"]),
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

def table_pressure_ev(
    game: dict[str, Any],
    seat: int,
    shanten_value: int,
    risk: float,
    level: int = 3,
    *,
    strategy: dict[str, Any] | None = None,
) -> float:
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
    strategy = strategy if strategy is not None else placement_strategy_context(game, seat)
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

def placement_rank_for_points(points: list[int], seat: int) -> int:
    standings = sorted(range(len(points)), key=lambda item: (-points[item], item))
    return standings.index(seat) + 1

def placement_utility(rank: int, player_count_value: int) -> float:
    if player_count_value == 3:
        return {1: 42.0, 2: 4.0, 3: -46.0}.get(rank, -46.0)
    return {1: 48.0, 2: 14.0, 3: -16.0, 4: -54.0}.get(rank, -54.0)

def global_reward_delta_profile(
    game: dict[str, Any],
    seat: int,
    *,
    shanten_value: int,
    ukeire: int,
    wait_quality: float,
    estimated_value: int,
    estimated_han: float,
    deal_in_rate: float,
    deal_in_points: int,
    strategy: dict[str, Any],
    level: int,
) -> dict[str, Any]:
    points = [int(player["points"]) for player in game["players"]]
    rust_profile = rust_core.global_reward_delta_profile(
        points=points,
        seat=seat,
        shanten_value=shanten_value,
        ukeire=ukeire,
        wait_quality=wait_quality,
        estimated_value=estimated_value,
        estimated_han=estimated_han,
        deal_in_rate=deal_in_rate,
        deal_in_points=deal_in_points,
        level=level,
        progress=round_progress_ratio(game["round_state"]),
        riichi_sticks=int(game.get("riichi_sticks", 0)),
        honba=int(game.get("honba", 0)),
        placement=int(strategy["placement"]),
        placement_count=int(strategy["placement_count"]),
        is_all_last=bool(strategy["is_all_last"]),
    )
    if rust_profile is not None:
        global_ev = float(rust_profile["global_reward_ev"])
        win_rank_delta = int(rust_profile["win_rank_delta"])
        loss_rank_delta = int(rust_profile["loss_rank_delta"])
        if win_rank_delta > 0 and global_ev > 0:
            label = "\u987a\u4f4d\u6536\u76ca\uff1a\u8ffd\u5206\u6709\u6548"
        elif loss_rank_delta < 0 and deal_in_points > 0:
            label = "\u987a\u4f4d\u98ce\u9669\uff1a\u5931\u70b9\u4f1a\u4f24\u6392\u540d"
        elif strategy["placement"] == 1:
            label = "\u987a\u4f4d\u76ee\u6807\uff1a\u5b88\u4f4f\u9886\u5148"
        else:
            label = "\u987a\u4f4d\u76ee\u6807\uff1a\u6b63\u5e38\u63a8\u8fdb"
        return {
            "global_reward_ev": global_ev,
            "global_reward_label": label,
            "win_rank_delta": win_rank_delta,
            "loss_rank_delta": loss_rank_delta,
        }

    player_count_value = len(points)
    current_rank = placement_rank_for_points(points, seat)
    current_utility = placement_utility(current_rank, player_count_value)

    win_points = max(0, estimated_value + game.get("riichi_sticks", 0) * 1000 + game.get("honba", 0) * 300)
    win_points_state = list(points)
    win_points_state[seat] += win_points
    win_rank = placement_rank_for_points(win_points_state, seat)
    win_delta = placement_utility(win_rank, player_count_value) - current_utility

    loss_points_state = list(points)
    loss_points_state[seat] -= max(0, deal_in_points)
    loss_rank = placement_rank_for_points(loss_points_state, seat)
    loss_delta = placement_utility(loss_rank, player_count_value) - current_utility

    speed_proxy = max(0.0, 4.0 - max(0, shanten_value)) / 4.0
    win_probability_proxy = min(0.46, 0.03 + speed_proxy * 0.12 + min(0.16, ukeire / 120.0) + wait_quality * 0.08)
    if shanten_value <= 0:
        win_probability_proxy += 0.08
    if estimated_han >= 5:
        win_probability_proxy += 0.03
    win_probability_proxy = min(0.58, win_probability_proxy)

    progress = round_progress_ratio(game["round_state"])
    loss_probability_proxy = min(0.42, deal_in_rate * (0.85 + progress * 0.35))
    late_multiplier = 1.0
    if strategy["is_all_last"]:
        late_multiplier += 0.35
        if current_rank == 1:
            late_multiplier += 0.25
        elif current_rank == player_count_value:
            late_multiplier += 0.18

    utility_ev = (win_delta * win_probability_proxy + loss_delta * loss_probability_proxy) * late_multiplier
    point_ev = (win_points * win_probability_proxy - deal_in_points * loss_probability_proxy) / 1700.0
    if strategy["placement"] == 1 and strategy["is_all_last"]:
        point_ev *= 0.36
    elif strategy["placement"] == strategy["placement_count"]:
        point_ev *= 1.18

    global_ev = (utility_ev * (0.55 + level * 0.08)) + point_ev
    if win_delta > 0 and global_ev > 0:
        label = "顺位收益：追分有效"
    elif loss_delta < 0 and deal_in_points > 0:
        label = "顺位风险：失点会伤排名"
    elif strategy["placement"] == 1:
        label = "顺位目标：守住领先"
    else:
        label = "顺位目标：正常推进"

    return {
        "global_reward_ev": round(max(-48.0, min(52.0, global_ev)), 3),
        "global_reward_label": label,
        "win_rank_delta": current_rank - win_rank,
        "loss_rank_delta": current_rank - loss_rank,
    }

__all__ = [
    "unique_tile_type_candidates",
    "effective_tiles_after_discard",
    "wait_count_after_discard",
    "wait_shape_label",
    "shape_quality_profile",
    "tile_suit_index",
    "unique_ordered_labels",
    "empty_opponent_profile",
    "suji_safety_multiplier",
    "visible_wall_multiplier",
    "estimate_opponent_loss",
    "threat_level_from_score",
    "classify_opponent_threat",
    "infer_open_hand_profile",
    "tile_danger_against_opponent",
    "build_tile_risk_context",
    "tile_risk_score",
    "ensure_rust_danger_cache",
    "cached_tile_danger_against_opponent",
    "discard_risk_sources",
    "discard_deal_in_loss_profile",
    "tile_safety_against_opponent",
    "cached_tile_safety_against_opponent",
    "ensure_rust_aggregate_safety_cache",
    "aggregate_tile_safety_score",
    "safe_tile_reserve_profile",
    "safe_reserve_profiles_for_discards",
    "defensive_discard_profile",
    "push_fold_profile",
    "defense_override_profile",
    "tile_value_bonus",
    "visible_tile_type_counts",
    "discard_metrics_for_hand",
    "hand_route_profile",
    "route_profiles_for_discards",
    "rough_points_from_han",
    "hand_value_label",
    "hand_value_profile",
    "round_progress_ratio",
    "opponent_models",
    "placement_strategy_context",
    "table_pressure_ev",
    "placement_rank_for_points",
    "placement_utility",
    "global_reward_delta_profile",
]
