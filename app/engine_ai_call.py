"""AI 鸣牌、杠牌和立直相关评估。

吃、碰、明杠、暗杠、加杠、拔北、立直不再是简单 if/else，而是尽量接入同一套 EV
思路：比较鸣后向听、役种可行性、后续最佳弃牌、防守压力、打点提升和局况目标，
避免 AI 盲目碰牌导致无役或低价值路线。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.engine_ai_discard import (
    alpha_open_call_projection_profile,
    alpha_riichi_projection_profile,
    discard_profile,
    shanten_of_tiles,
)
from app.engine_actions import can_double_riichi
from app.engine_common import ActionChoice, ai_level_policy
from app.engine_constants import TRIPLET_MELD_TYPES
from app.engine_risk import *
from app.engine_rules import current_dora_indicators, seat_wind_label
from app.engine_scoring import (
    active_aka_dora_han,
    calculate_limit_hand_cost,
    estimate_hand_value_for_layout,
    score_result_total,
    scoring_tiles_from_layout,
    serialize_yaku_names,
    winning_tile_types_for_layout,
)
from app.engine_shape import tenpai_wait_tile_types
from app.engine_tiles import (
    counts_by_type,
    dora_from_indicator,
    is_honor,
    is_red,
    is_simple,
    pop_specific_tiles,
    sort_tiles,
    tile_type,
    tile_type_label,
    to_34_array,
)

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

    call_dora = sum(1 for tile_id in visible_call_tiles if is_red(tile_id, game) or tile_type(tile_id) in dora_types)
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
    round_state = game["round_state"]
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
        aka_han = active_aka_dora_han(
            game,
            scoring_tiles_from_layout(concealed_after_call, melds, win_tile_id, is_tsumo=False),
        )
        confirmed_yaku.extend(name.split(" ", 1)[0] for name in yaku_names)
        estimated_han = int(result.han or 0) + aka_han
        best_han = max(best_han, estimated_han)
        if aka_han:
            cost = calculate_limit_hand_cost(game, seat, han=estimated_han, is_tsumo=False, honba=round_state["honba"])
        else:
            cost = dict(result.cost)
        best_points = max(best_points, score_result_total(cost))
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
    candidates = unique_tile_type_candidates(concealed_after_call, game)
    if not candidates:
        return None
    risk_context = build_tile_risk_context(game, seat, hand_tiles=concealed_after_call)
    precomputed_metrics = discard_metrics_for_hand(game, seat, concealed_after_call)
    precomputed_routes = route_profiles_for_discards(game, seat, concealed_after_call, precomputed_metrics)
    precomputed_safe_reserves = safe_reserve_profiles_for_discards(
        game, seat, concealed_after_call, risk_context, precomputed_metrics
    )
    profiles = [
        discard_profile(
            game,
            seat,
            tile_id,
            level,
            hand_tiles=concealed_after_call,
            include_lookahead=False,
            risk_context=risk_context,
            precomputed_discard_metrics=precomputed_metrics,
            precomputed_route_profiles=precomputed_routes,
            precomputed_safe_reserves=precomputed_safe_reserves,
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
    max_push_pressure = max((model.get("push_pressure", model["threat"]) for model in pressure), default=0.0)
    max_loss = max((model["estimated_loss"] for model in pressure), default=0)
    effective_threat = max(max_threat, max_push_pressure * 0.72)
    call_commitment = open_call_commitment_profile(
        game,
        seat,
        action,
        current_shanten=current_shanten,
        next_shanten=next_shanten,
        shanten_gain=shanten_gain,
        yaku_profile=yaku_profile,
        best_discard=best_discard,
        max_threat=effective_threat,
        max_loss=max_loss,
        progress=progress,
        strategy=strategy,
        level=level,
    )
    alpha_action = alpha_open_call_projection_profile(game, seat, new_concealed, best_discard, level, yaku_profile)
    global_reward_ev = 0.0
    global_reward_label = ""
    if isinstance(best_discard, dict):
        global_reward_ev = round(float(best_discard.get("global_reward_ev", 0.0)) * (0.42 + strategy_scale * 0.18), 3)
        global_reward_label = str(best_discard.get("global_reward_label", ""))
    defense_ev = -(effective_threat * (8.0 + progress * 12.0))
    defense_ev -= min(12.0, max_loss / 2600) * (0.25 + progress * 0.55)
    if action.type == "open_kan":
        defense_ev -= 8.0 + effective_threat * 8.0
    if next_shanten <= 1:
        defense_ev *= 0.72
    defense_ev -= strategy["defense_bias"] * (5.5 + effective_threat * 7.0) * strategy_scale

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
        speed_ev
        + value_ev
        + defense_ev
        + table_ev
        + post_discard_ev
        + call_commitment["call_commitment_ev"]
        + alpha_action["alpha_action_ev"]
        + global_reward_ev,
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
        "alpha_action_ev": alpha_action["alpha_action_ev"],
        "alpha_action_search_ev": alpha_action["alpha_action_search_ev"],
        "alpha_action_label": alpha_action["alpha_action_label"],
        "alpha_action_depth": alpha_action["alpha_action_depth"],
        "global_reward_ev": global_reward_ev,
        "global_reward_label": global_reward_label,
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
    max_push_pressure = max((model.get("push_pressure", model["threat"]) for model in pressure), default=0.0)
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
    defense_ev -= max_threat * (3.5 + progress * 6.5)
    defense_ev -= max_push_pressure * (2.5 + progress * 5.5)
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

    remaining_after_riichi = list(round_state["hands"][seat])
    discard_tile_id = action.tile_id if action.tile_id is not None else discard_profile_item.get("tile_id")
    if discard_tile_id in remaining_after_riichi:
        remaining_after_riichi.remove(discard_tile_id)
    alpha_action = alpha_riichi_projection_profile(game, seat, remaining_after_riichi, discard_profile_item, level)
    global_reward_ev = round(
        float(discard_profile_item.get("global_reward_ev", 0.0)) * (0.48 + strategy_scale * 0.16),
        3,
    )
    global_reward_label = str(discard_profile_item.get("global_reward_label", ""))

    final_ev = round(
        speed_ev + value_ev + defense_ev + table_ev + deposit_ev + alpha_action["alpha_action_ev"] + global_reward_ev,
        3,
    )
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
        "alpha_action_ev": alpha_action["alpha_action_ev"],
        "alpha_action_search_ev": alpha_action["alpha_action_search_ev"],
        "alpha_action_label": alpha_action["alpha_action_label"],
        "alpha_action_depth": alpha_action["alpha_action_depth"],
        "global_reward_ev": global_reward_ev,
        "global_reward_label": global_reward_label,
        "final_ev": final_ev,
        "threshold": round(threshold, 3),
        "should_riichi": final_ev >= threshold,
        "strategy_label": strategy["label"],
    }

__all__ = [
    "call_route_profile",
    "prospective_open_call_melds",
    "confirm_open_call_tenpai_yaku",
    "open_call_yaku_viability_profile",
    "best_post_call_discard_profile",
    "open_call_commitment_profile",
    "open_call_threshold",
    "open_call_profile",
    "should_call_open",
    "riichi_decision_profile",
]
