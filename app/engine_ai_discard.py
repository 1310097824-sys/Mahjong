"""AI 弃牌评估与 AlphaJong 风格前瞻。

这是当前 AI 的主战场：每个候选弃牌都会被拆成速度 EV、打点 EV、防守 EV、顺位 EV、
安全牌储备、放铳损失和浅层前瞻等分项，再合成最终分数。L3 会启用更强的多巡模拟；
晚巡会自动压缩搜索以降低卡顿。
"""

from __future__ import annotations

import random
from typing import Any

from app import rust_core
from app.engine_actions import can_double_riichi
from app.engine_common import ai_level_policy, ai_roll
from app.engine_constants import (
    ALPHA_ACTION_SEARCH_DEPTH,
    ALPHA_ACTION_SEARCH_WEIGHT,
    ALPHA_RIICHI_SEARCH_WEIGHT,
    ALPHA_SEARCH_DEPTH,
    ALPHA_SEARCH_DISCARD_BEAM,
    ALPHA_SEARCH_DISCOUNT,
    ALPHA_SEARCH_DRAW_BEAM,
    ALPHA_SEARCH_WEIGHT,
)
from app.engine_risk import *
from app.engine_rules import current_dora_indicators, is_closed_hand
from app.engine_shape import tenpai_wait_tile_types
from app.engine_tiles import (
    calculate_shanten_for_tiles,
    dora_from_indicator,
    is_honor,
    is_red,
    legal_tile_types_for_mode,
    representative_tile_id,
    sort_tiles,
    tile_label,
    tile_type,
    to_34_array,
)

def opponent_models_from_risk_context(risk_context: dict[str, Any]) -> list[dict[str, Any]]:
    cached = risk_context.get("opponent_models")
    if cached is not None:
        return cached
    models: list[dict[str, Any]] = []
    for item in risk_context.get("opponents", []):
        profile = item["profile"]
        threat = float(profile.get("threat", 0.0))
        models.append(
            {
                "seat": item["seat"],
                "threat": threat,
                "threat_type": profile.get("threat_type", "unknown"),
                "threat_level": profile.get("threat_level", "low"),
                "threat_reasons": profile.get("threat_reasons", []),
                "push_pressure": profile.get("push_pressure", threat),
                "labels": profile.get("labels", []),
                "routes": profile.get("routes", []),
                "speed_class": profile.get("speed_class", "未知"),
                "open_meld_count": profile.get("open_meld_count", 0),
                "revealed_dora": profile.get("revealed_dora", 0),
                "estimated_loss": item["estimated_loss"],
            }
        )
    risk_context["opponent_models"] = models
    return models

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
    risk_context: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
) -> dict[str, float]:
    round_state = game["round_state"]
    progress = round_progress_ratio(round_state)
    opponent_pressure = (
        opponent_models_from_risk_context(risk_context)
        if risk_context is not None
        else opponent_models(game, seat)
    )
    max_loss = max((model["estimated_loss"] for model in opponent_pressure), default=0)
    max_threat = max((model["threat"] for model in opponent_pressure), default=0.0)
    max_push_pressure = max((model.get("push_pressure", model["threat"]) for model in opponent_pressure), default=0.0)
    strategy = strategy if strategy is not None else placement_strategy_context(game, seat)
    policy = ai_level_policy(level)
    all_points = [int(player["points"]) for player in game["players"]]
    own_points = int(game["players"][seat]["points"])
    level_one_noise = random.random() if level == 1 else 0.0
    rust_ev = rust_core.structured_discard_ev(
        shanten_value=shanten_value,
        ukeire=ukeire,
        risk=risk,
        value_penalty=value_penalty,
        route_bonus=route_bonus,
        route_count=len(routes),
        level=level,
        progress=progress,
        max_loss=max_loss,
        max_threat=max_threat,
        max_push_pressure=max_push_pressure,
        own_points=own_points,
        top_points=max(all_points),
        bottom_points=min(all_points),
        is_dealer=seat == round_state["dealer_seat"],
        is_closed=is_closed_hand(round_state, seat),
        live_tile_count=len(round_state["live_wall"]),
        strategy_scale=policy["strategy_scale"],
        attack_bias=strategy["attack_bias"],
        defense_bias=strategy["defense_bias"],
        value_bias=strategy["value_bias"],
        placement=strategy["placement"],
        placement_count=strategy["placement_count"],
        gap_to_above=strategy["gap_to_above"],
        is_all_last=strategy["is_all_last"],
        level_one_noise=level_one_noise,
    )
    if rust_ev is not None:
        return rust_ev

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
    danger_scale = (
        1.0
        + (progress * 0.55)
        + (max_threat * 0.18)
        + (max_push_pressure * 0.12)
        + min(0.45, max_loss / 32000)
    )
    defense_ev = -(risk * 15.5 * caution * danger_scale)

    table_ev = table_pressure_ev(game, seat, shanten_value, risk, level, strategy=strategy)
    final_ev = speed_ev + value_ev + defense_ev + table_ev
    if level == 1:
        final_ev += level_one_noise

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
        precomputed_metrics = discard_metrics_for_hand(game, seat, simulated_hand)
        precomputed_routes = route_profiles_for_discards(game, seat, simulated_hand, precomputed_metrics)
        precomputed_safe_reserves = (
            safe_reserve_profiles_for_discards(game, seat, simulated_hand, risk_context, precomputed_metrics)
            if risk_context is not None
            else None
        )
        next_profiles = [
            discard_profile(
                game,
                seat,
                tile_id,
                level,
                hand_tiles=simulated_hand,
                include_lookahead=False,
                risk_context=risk_context,
                precomputed_discard_metrics=precomputed_metrics,
                precomputed_route_profiles=precomputed_routes,
                precomputed_safe_reserves=precomputed_safe_reserves,
            )
            for tile_id in unique_tile_type_candidates(simulated_hand, game)
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

def alpha_used_count_key(used_counts: dict[int, int]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((tile_index, amount) for tile_index, amount in used_counts.items() if amount > 0))

def alpha_hand_count_key(hand_tiles: list[int]) -> tuple[int, ...]:
    return tuple(to_34_array(hand_tiles))

def alpha_remaining_count(tile_index: int, visible_counts: list[int], used_counts: dict[int, int]) -> int:
    return max(0, 4 - visible_counts[tile_index] - used_counts.get(tile_index, 0))

def alpha_effective_ukeire_from_state(
    game: dict[str, Any],
    hand_tiles: list[int],
    visible_counts: list[int],
    used_counts: dict[int, int],
    base_shanten: int,
) -> tuple[int, list[int]]:
    rust_result = rust_core.effective_tiles_from_counts(
        game["mode"],
        to_34_array(hand_tiles),
        visible_counts,
        used_counts,
        base_shanten,
    )
    if rust_result is not None:
        ukeire, good_tiles = rust_result
        return ukeire, [int(item["type"]) for item in good_tiles]

    ukeire = 0
    waits: list[int] = []
    for tile_index in legal_tile_types_for_mode(game["mode"]):
        remaining = alpha_remaining_count(tile_index, visible_counts, used_counts)
        if remaining <= 0:
            continue
        draw_id = representative_tile_id(tile_index, hand_tiles)
        try:
            next_shanten = calculate_shanten_for_tiles(hand_tiles + [draw_id])
        except ValueError:
            continue
        if next_shanten < base_shanten or (base_shanten == 0 and next_shanten == -1):
            ukeire += remaining
            waits.append(tile_index)
    return ukeire, waits

def alpha_terminal_projection_ev(
    game: dict[str, Any],
    seat: int,
    hand_tiles: list[int],
    level: int,
    visible_counts: list[int],
    used_counts: dict[int, int],
    *,
    risk_context: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
) -> float:
    shanten_value = shanten_of_tiles(hand_tiles)
    if shanten_value <= -1:
        return 260.0

    ukeire, wait_types = alpha_effective_ukeire_from_state(game, hand_tiles, visible_counts, used_counts, shanten_value)
    route_bonus, routes = hand_route_profile(game, seat, hand_tiles, shanten_value=shanten_value)
    wait_quality = 0.0
    if wait_types:
        wait_quality = min(1.0, (len(wait_types) / 5.0) + min(0.35, ukeire / 32.0))
    value_profile = hand_value_profile(game, seat, hand_tiles, shanten_value=shanten_value, routes=routes, wait_quality=wait_quality)
    strategy = strategy if strategy is not None else placement_strategy_context(game, seat)
    pressure = opponent_models_from_risk_context(risk_context) if risk_context is not None else opponent_models(game, seat)
    max_threat = max((model["threat"] for model in pressure), default=0.0)
    max_push_pressure = max((model.get("push_pressure", model["threat"]) for model in pressure), default=0.0)
    max_loss = max((model["estimated_loss"] for model in pressure), default=0)

    rust_ev = rust_core.alpha_terminal_projection_ev(
        shanten_value=shanten_value,
        ukeire=ukeire,
        route_bonus=route_bonus,
        hand_value_ev=float(value_profile["hand_value_ev"]),
        attack_bias=float(strategy["attack_bias"]),
        defense_bias=float(strategy["defense_bias"]),
        value_bias=float(strategy["value_bias"]),
        max_threat=max_threat,
        max_push_pressure=max_push_pressure,
        max_loss=max_loss,
        wait_quality=wait_quality,
        level=level,
    )
    if rust_ev is not None:
        return rust_ev

    ev = (-106.0 * shanten_value) + (ukeire * (2.0 + level * 0.24))
    ev += route_bonus * 0.72
    ev += value_profile["hand_value_ev"] * 0.72
    ev += strategy["attack_bias"] * 9.0 + strategy["value_bias"] * 7.0
    ev -= strategy["defense_bias"] * (5.0 + max_push_pressure * 7.0 + max_threat * 3.0) * (
        1.0 if shanten_value >= 2 else 0.42
    )
    if shanten_value >= 2:
        ev -= max_threat * 6.0 + max_push_pressure * 5.0 + min(10.0, max_loss / 2400)
    elif shanten_value <= 0:
        ev += wait_quality * 18.0
    return round(max(-380.0, min(300.0, ev)), 3)

def alpha_draw_candidates(
    game: dict[str, Any],
    seat: int,
    hand_tiles: list[int],
    visible_counts: list[int],
    used_counts: dict[int, int],
    *,
    max_candidates: int,
) -> list[dict[str, Any]]:
    base_shanten = shanten_of_tiles(hand_tiles)
    dora_types = {dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(game["round_state"])}
    candidates: list[dict[str, Any]] = []
    counts = to_34_array(hand_tiles)
    rust_draw_result = rust_core.draw_tiles_from_counts(game["mode"], counts, visible_counts, used_counts)
    if rust_draw_result is not None:
        _total_remaining, draw_infos = rust_draw_result
        draw_iterable = [
            (
                int(item["type"]),
                int(item["remaining"]),
                int(item["next_shanten"]),
            )
            for item in draw_infos
        ]
    else:
        draw_iterable = []
        for tile_index in legal_tile_types_for_mode(game["mode"]):
            remaining = alpha_remaining_count(tile_index, visible_counts, used_counts)
            if remaining <= 0 or counts[tile_index] >= 4:
                continue
            draw_id = representative_tile_id(tile_index, hand_tiles)
            try:
                next_shanten = calculate_shanten_for_tiles(hand_tiles + [draw_id])
            except ValueError:
                continue
            draw_iterable.append((tile_index, remaining, next_shanten))

    for tile_index, remaining, next_shanten in draw_iterable:
        draw_id = representative_tile_id(tile_index, hand_tiles)
        shanten_gain = base_shanten - next_shanten
        score = float(remaining)
        if next_shanten <= -1:
            score += 220.0
        elif shanten_gain > 0:
            score += 56.0 * shanten_gain
        elif base_shanten <= 1:
            score += 7.0
        if tile_index in dora_types:
            score += 12.0
        if is_honor(tile_index):
            score += 3.0 if counts[tile_index] >= 1 else -2.5
        else:
            rank = tile_index % 9
            if rank in {2, 3, 4, 5, 6}:
                score += 2.0
            if any(0 <= tile_index + offset < 27 and (tile_index + offset) // 9 == tile_index // 9 and counts[tile_index + offset] for offset in {-2, -1, 1, 2}):
                score += 4.0
        candidates.append(
            {
                "type": tile_index,
                "tile_id": draw_id,
                "remaining": remaining,
                "next_shanten": next_shanten,
                "score": round(score, 3),
            }
        )

    return sorted(candidates, key=lambda item: (-float(item["score"]), -int(item["remaining"]), int(item["type"])))[:max_candidates]

def alpha_search_config(
    game: dict[str, Any],
    seat: int,
    risk_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    round_state = game["round_state"]
    progress = round_progress_ratio(round_state)
    live_tiles = len(round_state.get("live_wall", []))
    if risk_context is not None:
        opponent_pressure = opponent_models_from_risk_context(risk_context)
    else:
        opponent_pressure = opponent_models(game, seat)
    max_push_pressure = max(
        (float(model.get("push_pressure", model.get("threat", 0.0))) for model in opponent_pressure),
        default=0.0,
    )

    if live_tiles <= 18 or progress >= 0.82 or max_push_pressure >= 1.85:
        return {
            "depth": 0,
            "draw_beam": 0,
            "discard_beam": 0,
            "weight": 0.10,
            "label": "晚巡快速评估",
        }
    if live_tiles <= 30 or progress >= 0.66 or max_push_pressure >= 1.35:
        return {
            "depth": 1,
            "draw_beam": 2,
            "discard_beam": 1,
            "weight": 0.14,
            "label": "晚巡压缩模拟",
        }
    return {
        "depth": ALPHA_SEARCH_DEPTH,
        "draw_beam": ALPHA_SEARCH_DRAW_BEAM,
        "discard_beam": ALPHA_SEARCH_DISCARD_BEAM,
        "weight": ALPHA_SEARCH_WEIGHT,
        "label": "多巡模拟",
    }

def alpha_branch_search_ev(
    game: dict[str, Any],
    seat: int,
    hand_tiles: list[int],
    level: int,
    *,
    depth: int,
    visible_counts: list[int],
    used_counts: dict[int, int],
    cache: dict[tuple[Any, ...], float],
    draw_beam: int = ALPHA_SEARCH_DRAW_BEAM,
    discard_beam: int = ALPHA_SEARCH_DISCARD_BEAM,
    risk_context: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
) -> float:
    cache_key = (depth, alpha_hand_count_key(hand_tiles), alpha_used_count_key(used_counts))
    if cache_key in cache:
        return cache[cache_key]

    if depth <= 0:
        value = alpha_terminal_projection_ev(
            game,
            seat,
            hand_tiles,
            level,
            visible_counts,
            used_counts,
            risk_context=risk_context,
            strategy=strategy,
        )
        cache[cache_key] = value
        return value

    draw_candidates = alpha_draw_candidates(
        game,
        seat,
        hand_tiles,
        visible_counts,
        used_counts,
        max_candidates=draw_beam,
    )
    if not draw_candidates:
        value = alpha_terminal_projection_ev(
            game,
            seat,
            hand_tiles,
            level,
            visible_counts,
            used_counts,
            risk_context=risk_context,
            strategy=strategy,
        )
        cache[cache_key] = value
        return value

    weighted_total = 0.0
    total_weight = 0
    for draw in draw_candidates:
        draw_type = int(draw["type"])
        remaining = int(draw["remaining"])
        drawn_tile_id = representative_tile_id(draw_type, hand_tiles)
        simulated_hand = sort_tiles(hand_tiles + [drawn_tile_id])
        next_used_counts = dict(used_counts)
        next_used_counts[draw_type] = next_used_counts.get(draw_type, 0) + 1

        if shanten_of_tiles(simulated_hand) <= -1:
            branch_ev = alpha_terminal_projection_ev(
                game,
                seat,
                simulated_hand,
                level,
                visible_counts,
                next_used_counts,
                risk_context=risk_context,
                strategy=strategy,
            )
        else:
            branch_risk_context = build_tile_risk_context(game, seat, hand_tiles=simulated_hand)
            precomputed_metrics = discard_metrics_for_hand(game, seat, simulated_hand)
            precomputed_routes = route_profiles_for_discards(game, seat, simulated_hand, precomputed_metrics)
            precomputed_safe_reserves = safe_reserve_profiles_for_discards(
                game, seat, simulated_hand, branch_risk_context, precomputed_metrics
            )
            profiles = [
                discard_profile(
                    game,
                    seat,
                    tile_id,
                    level,
                    hand_tiles=simulated_hand,
                    include_lookahead=False,
                    risk_context=branch_risk_context,
                    precomputed_discard_metrics=precomputed_metrics,
                    precomputed_route_profiles=precomputed_routes,
                    precomputed_safe_reserves=precomputed_safe_reserves,
                )
                for tile_id in unique_tile_type_candidates(simulated_hand, game)
            ]
            best_branch = -9999.0
            for profile in sorted(profiles, key=lambda item: (-item["score"], item["tile_label"]))[:discard_beam]:
                next_hand = list(simulated_hand)
                try:
                    next_hand.remove(profile["tile_id"])
                except ValueError:
                    continue
                future_ev = alpha_branch_search_ev(
                    game,
                    seat,
                    next_hand,
                    level,
                    depth=depth - 1,
                    visible_counts=visible_counts,
                    used_counts=next_used_counts,
                    cache=cache,
                    draw_beam=draw_beam,
                    discard_beam=discard_beam,
                    risk_context=risk_context,
                    strategy=strategy,
                )
                profile_ev = float(profile["final_ev"])
                branch_ev = profile_ev + ((future_ev - profile_ev) * ALPHA_SEARCH_DISCOUNT)
                best_branch = max(best_branch, branch_ev)
            branch_ev = (
                best_branch
                if best_branch > -9999.0
                else alpha_terminal_projection_ev(
                    game,
                    seat,
                    hand_tiles,
                    level,
                    visible_counts,
                    next_used_counts,
                    risk_context=risk_context,
                    strategy=strategy,
                )
            )

        weighted_total += branch_ev * remaining
        total_weight += remaining

    if total_weight <= 0:
        value = alpha_terminal_projection_ev(
            game,
            seat,
            hand_tiles,
            level,
            visible_counts,
            used_counts,
            risk_context=risk_context,
            strategy=strategy,
        )
    else:
        value = round(weighted_total / total_weight, 3)
    cache[cache_key] = value
    return value

def alpha_style_lookahead_profile(
    game: dict[str, Any],
    seat: int,
    tiles_after_discard: list[int],
    good_tiles: list[dict[str, Any]],
    *,
    level: int,
    base_final_ev: float,
    risk_context: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if level < 3 or not good_tiles:
        return {
            "lookahead_ev": 0.0,
            "alpha_search_ev": 0.0,
            "alpha_search_depth": 0,
            "alpha_search_label": "",
        }

    visible_counts = visible_tile_type_counts(game, seat, hand_tiles=tiles_after_discard)
    search_config = alpha_search_config(game, seat, risk_context)
    if int(search_config["depth"]) >= ALPHA_SEARCH_DEPTH:
        fast_ev = lookahead_after_discard_ev(
            game,
            seat,
            tiles_after_discard,
            good_tiles,
            level=level,
            base_final_ev=base_final_ev,
            risk_context=risk_context,
        )
    else:
        fast_ev = 0.0
    search_ev = alpha_branch_search_ev(
        game,
        seat,
        tiles_after_discard,
        level,
        depth=search_config["depth"],
        visible_counts=visible_counts,
        used_counts={},
        cache={},
        draw_beam=search_config["draw_beam"],
        discard_beam=search_config["discard_beam"],
        risk_context=risk_context,
        strategy=strategy,
    )
    alpha_adjust = round((search_ev - base_final_ev) * float(search_config["weight"]), 3)
    combined = round(max(-54.0, min(58.0, alpha_adjust + fast_ev * 0.35)), 3)
    label_base = str(search_config["label"])
    label = label_base if combined >= 0 else f"{label_base}偏弱"
    return {
        "lookahead_ev": combined,
        "alpha_search_ev": round(search_ev, 3),
        "alpha_search_depth": search_config["depth"],
        "alpha_search_label": label,
    }

def alpha_projection_for_hand(
    game: dict[str, Any],
    seat: int,
    hand_tiles: list[int],
    level: int,
    *,
    depth: int = ALPHA_ACTION_SEARCH_DEPTH,
) -> float:
    if level < 3:
        return 0.0
    visible_counts = visible_tile_type_counts(game, seat, hand_tiles=hand_tiles)
    search_config = alpha_search_config(game, seat)
    effective_depth = min(depth, int(search_config["depth"]))
    return alpha_branch_search_ev(
        game,
        seat,
        hand_tiles,
        level,
        depth=effective_depth,
        visible_counts=visible_counts,
        used_counts={},
        cache={},
        draw_beam=search_config["draw_beam"],
        discard_beam=search_config["discard_beam"],
    )

def alpha_open_call_projection_profile(
    game: dict[str, Any],
    seat: int,
    concealed_after_call: list[int],
    best_discard: dict[str, Any] | None,
    level: int,
    yaku_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if level < 3:
        return {
            "alpha_action_ev": 0.0,
            "alpha_action_search_ev": 0.0,
            "alpha_action_label": "",
            "alpha_action_depth": 0,
        }

    projected_hand = list(concealed_after_call)
    base_ev = alpha_terminal_projection_ev(game, seat, projected_hand, level, visible_tile_type_counts(game, seat, hand_tiles=projected_hand), {})
    if isinstance(best_discard, dict) and best_discard.get("tile_id") in projected_hand:
        projected_hand.remove(best_discard["tile_id"])
        base_ev = float(best_discard.get("final_ev", base_ev))

    search_ev = alpha_projection_for_hand(game, seat, projected_hand, level, depth=ALPHA_ACTION_SEARCH_DEPTH)
    action_ev = round((search_ev - base_ev) * ALPHA_ACTION_SEARCH_WEIGHT, 3)
    label = "\u9e23\u540e\u8def\u7ebf\u597d" if action_ev >= 0 else "\u9e23\u540e\u8def\u7ebf\u5dee"
    if yaku_profile is not None and not bool(yaku_profile.get("has_yaku_path", False)):
        action_ev = min(action_ev, -12.0)
        label = "\u6a21\u62df\u8def\u7ebf\u65e0\u5f79"
    elif yaku_profile is not None and not bool(yaku_profile.get("guaranteed_yaku", False)):
        confidence = float(yaku_profile.get("yaku_confidence") or 0.0)
        if confidence < 0.62:
            action_ev -= 5.0
            label = "\u6a21\u62df\u5f79\u8def\u504f\u5f31" if action_ev < 0 else "\u9e23\u540e\u8def\u7ebf\u5c1a\u53ef"
    return {
        "alpha_action_ev": round(max(-34.0, min(36.0, action_ev)), 3),
        "alpha_action_search_ev": round(search_ev, 3),
        "alpha_action_label": label,
        "alpha_action_depth": ALPHA_ACTION_SEARCH_DEPTH,
    }

def alpha_riichi_projection_profile(
    game: dict[str, Any],
    seat: int,
    remaining_after_riichi: list[int],
    discard_profile_item: dict[str, Any],
    level: int,
) -> dict[str, Any]:
    if level < 3:
        return {
            "alpha_action_ev": 0.0,
            "alpha_action_search_ev": 0.0,
            "alpha_action_label": "",
            "alpha_action_depth": 0,
        }

    round_state = game["round_state"]
    wait_types = tenpai_wait_tile_types(
        remaining_after_riichi,
        mode=game["mode"],
        melds_data=game["round_state"]["melds"][seat],
    )
    visible_counts = visible_tile_type_counts(game, seat, hand_tiles=remaining_after_riichi)
    remaining_waits = sum(max(0, 4 - visible_counts[tile_index]) for tile_index in wait_types)
    live_tiles = max(1, len(round_state["live_wall"]))
    wait_quality = float(discard_profile_item.get("wait_quality", 0.0))
    risk = float(discard_profile_item.get("risk", 0.0))
    estimated_han = float(discard_profile_item.get("estimated_han", 0.0))
    estimated_value = int(discard_profile_item.get("estimated_value", 0) or 0)
    strategy = placement_strategy_context(game, seat)
    pressure = opponent_models(game, seat)
    max_threat = max((model["threat"] for model in pressure), default=0.0)
    max_push_pressure = max((model.get("push_pressure", model["threat"]) for model in pressure), default=0.0)
    max_loss = max((model["estimated_loss"] for model in pressure), default=0)
    progress = round_progress_ratio(round_state)

    wait_density = remaining_waits / live_tiles
    search_ev = (
        remaining_waits * 9.0
        + wait_density * 180.0
        + wait_quality * 24.0
        + estimated_han * 7.0
        + min(26.0, estimated_value / 900)
        + strategy["riichi_bias"] * 14.0
        + strategy["attack_bias"] * 8.0
        - strategy["defense_bias"] * 12.0
        - risk * (8.0 + progress * 9.0)
        - max_threat * (4.0 + progress * 5.0)
        - max_push_pressure * (3.0 + progress * 5.0)
        - min(10.0, max_loss / 3900) * progress
    )
    if remaining_waits <= 2:
        search_ev -= 18.0
    if remaining_waits >= 6 and estimated_han <= 2:
        search_ev += 8.0
    if strategy["is_all_last"] and strategy["placement"] == 1:
        search_ev -= 16.0 + max_threat * 4.0
    if can_double_riichi(round_state, seat):
        search_ev += 10.0

    base_ev = float(discard_profile_item.get("final_ev", 0.0))
    action_ev = round((search_ev - base_ev) * ALPHA_RIICHI_SEARCH_WEIGHT, 3)
    label = "\u7acb\u76f4\u8def\u7ebf\u597d" if action_ev >= 0 else "\u7acb\u76f4\u9501\u624b\u504f\u5f31"
    return {
        "alpha_action_ev": round(max(-38.0, min(42.0, action_ev)), 3),
        "alpha_action_search_ev": round(max(-140.0, min(180.0, search_ev)), 3),
        "alpha_action_label": label,
        "alpha_action_depth": 1,
    }

def discard_profile(
    game: dict[str, Any],
    seat: int,
    discard_tile_id: int,
    level: int,
    *,
    hand_tiles: list[int] | None = None,
    include_lookahead: bool = True,
    risk_context: dict[str, Any] | None = None,
    precomputed_discard_metrics: dict[int, dict[str, Any]] | None = None,
    precomputed_route_profiles: dict[int, dict[str, Any]] | None = None,
    precomputed_safe_reserves: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    round_state = game["round_state"]
    policy = ai_level_policy(level)
    source_tiles = list(round_state["hands"][seat] if hand_tiles is None else hand_tiles)
    tiles = list(source_tiles)
    if discard_tile_id not in tiles:
        return {
            "tile_id": discard_tile_id,
            "tile_label": tile_label(discard_tile_id, game),
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
            "alpha_search_ev": 0.0,
            "alpha_search_depth": 0,
            "alpha_search_label": "",
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
            "deal_in_loss_ev": 0.0,
            "deal_in_rate": 0.0,
            "deal_in_points": 0,
            "deal_in_label": "",
            "safe_reserve_ev": 0.0,
            "safe_reserve_score": 0.0,
            "safe_reserve_label": "",
            "global_reward_ev": 0.0,
            "global_reward_label": "",
            "win_rank_delta": 0,
            "loss_rank_delta": 0,
            "defense_override_ev": 0.0,
            "defense_override_mode": "",
            "defense_override_label": "",
            "fold_need": 0.0,
            "forced_defense": False,
            "final_ev": -1998.0,
            "score": -1998.0,
        }
    tiles.remove(discard_tile_id)
    discard_type = tile_type(discard_tile_id)
    precomputed_metric = (
        precomputed_discard_metrics.get(discard_type)
        if precomputed_discard_metrics is not None
        else None
    )
    if precomputed_metric is not None:
        shanten_value = int(precomputed_metric["shanten"])
        ukeire = int(precomputed_metric["ukeire"])
        good_tile_infos = list(precomputed_metric["good_tiles"])
    else:
        try:
            shanten_value = calculate_shanten_for_tiles(tiles)
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
    deal_in_profile = discard_deal_in_loss_profile(game, seat, discard_tile_id, risk_context=risk_context)
    defense_profile = defensive_discard_profile(game, seat, discard_tile_id, shanten_value, level, risk_context)
    safe_reserve = (
        precomputed_safe_reserves.get(discard_type)
        if precomputed_safe_reserves is not None
        else None
    )
    if safe_reserve is None:
        safe_reserve = safe_tile_reserve_profile(game, seat, tiles, discard_tile_id, shanten_value, risk_context)
    strategy = placement_strategy_context(game, seat)
    shape_profile = shape_quality_profile(game, seat, tiles, shanten_value, ukeire, good_tile_infos, level)
    bonus = tile_value_bonus(game, seat, discard_tile_id)
    precomputed_route = (
        precomputed_route_profiles.get(discard_type)
        if precomputed_route_profiles is not None
        else None
    )
    if precomputed_route is not None:
        route_bonus = float(precomputed_route["route_bonus"])
        routes = list(precomputed_route["routes"])
    else:
        route_bonus, routes = hand_route_profile(game, seat, tiles, shanten_value=shanten_value)
    value_profile = hand_value_profile(
        game,
        seat,
        tiles,
        shanten_value=shanten_value,
        routes=routes,
        wait_quality=shape_profile["wait_quality"],
    )
    global_reward = global_reward_delta_profile(
        game,
        seat,
        shanten_value=shanten_value,
        ukeire=ukeire,
        wait_quality=shape_profile["wait_quality"],
        estimated_value=value_profile["estimated_value"],
        estimated_han=value_profile["estimated_han"],
        deal_in_rate=deal_in_profile["deal_in_rate"],
        deal_in_points=deal_in_profile["deal_in_points"],
        strategy=strategy,
        level=level,
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
        risk_context=risk_context,
        strategy=strategy,
    )
    lookahead_profile = (
        alpha_style_lookahead_profile(
            game,
            seat,
            tiles,
            good_tile_infos,
            level=level,
            base_final_ev=ev["final_ev"],
            risk_context=risk_context,
            strategy=strategy,
        )
        if include_lookahead and shanten_value <= 3
        else {
            "lookahead_ev": 0.0,
            "alpha_search_ev": 0.0,
            "alpha_search_depth": 0,
            "alpha_search_label": "",
        }
    )
    lookahead_ev = float(lookahead_profile["lookahead_ev"])
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
    deal_in_loss_ev = round(deal_in_profile["deal_in_loss_ev"] * (0.52 + policy["defense_scale"] * 0.48), 3)
    safe_reserve_ev = round(safe_reserve["safe_reserve_ev"] * (0.56 + policy["defense_scale"] * 0.44), 3)
    global_reward_ev = round(global_reward["global_reward_ev"] * (0.48 + policy["strategy_scale"] * 0.52), 3)
    final_ev = round(
        ev["final_ev"]
        + lookahead_ev
        + safety_ev
        + shape_profile["shape_ev"]
        + hand_value_ev
        + push_fold_ev
        + deal_in_loss_ev
        + safe_reserve_ev
        + global_reward_ev
        + defense_override_ev,
        3,
    )
    return {
        "tile_id": discard_tile_id,
        "tile_label": tile_label(discard_tile_id, game),
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
        "alpha_search_ev": lookahead_profile["alpha_search_ev"],
        "alpha_search_depth": lookahead_profile["alpha_search_depth"],
        "alpha_search_label": lookahead_profile["alpha_search_label"],
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
        "deal_in_loss_ev": deal_in_loss_ev,
        "deal_in_rate": deal_in_profile["deal_in_rate"],
        "deal_in_points": deal_in_profile["deal_in_points"],
        "deal_in_label": deal_in_profile["deal_in_label"],
        "safe_reserve_ev": safe_reserve_ev,
        "safe_reserve_score": safe_reserve["safe_reserve_score"],
        "safe_reserve_label": safe_reserve["safe_reserve_label"],
        "global_reward_ev": global_reward_ev,
        "global_reward_label": global_reward["global_reward_label"],
        "win_rank_delta": global_reward["win_rank_delta"],
        "loss_rank_delta": global_reward["loss_rank_delta"],
        "defense_override_ev": defense_override_ev,
        "defense_override_mode": defense_override["defense_override_mode"],
        "defense_override_label": defense_override["defense_override_label"],
        "fold_need": defense_override.get("fold_need", 0.0),
        "forced_defense": False,
        "final_ev": final_ev,
        "score": final_ev,
    }

def sorted_discard_profiles(
    game: dict[str, Any],
    seat: int,
    level: int,
    *,
    deep_search: bool = True,
) -> list[dict[str, Any]]:
    source_tiles = game["round_state"]["hands"][seat]
    candidates = unique_tile_type_candidates(source_tiles, game)
    risk_context = build_tile_risk_context(game, seat)
    precomputed_metrics = discard_metrics_for_hand(game, seat, source_tiles)
    precomputed_routes = route_profiles_for_discards(game, seat, source_tiles, precomputed_metrics)
    precomputed_safe_reserves = safe_reserve_profiles_for_discards(
        game, seat, source_tiles, risk_context, precomputed_metrics
    )
    if level >= 3 and deep_search:
        base_profiles = [
            discard_profile(
                game,
                seat,
                tile_id,
                level,
                include_lookahead=False,
                risk_context=risk_context,
                precomputed_discard_metrics=precomputed_metrics,
                precomputed_route_profiles=precomputed_routes,
                precomputed_safe_reserves=precomputed_safe_reserves,
            )
            for tile_id in candidates
        ]
        lookahead_tile_ids = {
            profile["tile_id"]
            for profile in sorted(base_profiles, key=lambda item: (-item["score"], item["tile_label"]))[:3]
            if profile["shanten"] <= 3
        }
        profiles = [
            discard_profile(
                game,
                seat,
                profile["tile_id"],
                level,
                risk_context=risk_context,
                precomputed_discard_metrics=precomputed_metrics,
                precomputed_route_profiles=precomputed_routes,
                precomputed_safe_reserves=precomputed_safe_reserves,
            )
            if profile["tile_id"] in lookahead_tile_ids
            else profile
            for profile in base_profiles
        ]
    else:
        profiles = [
            discard_profile(
                game,
                seat,
                tile_id,
                level,
                include_lookahead=deep_search,
                risk_context=risk_context,
                precomputed_discard_metrics=precomputed_metrics,
                precomputed_route_profiles=precomputed_routes,
                precomputed_safe_reserves=precomputed_safe_reserves,
            )
            for tile_id in candidates
        ]
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
    attack_deal_in_rate = float(attack_pick.get("deal_in_rate", 0.0))
    attack_deal_in_points = int(attack_pick.get("deal_in_points", 0))

    should_fold = False
    if attack_shanten >= 2 and max_pressure >= (1.05 if level >= 3 else 1.28):
        should_fold = True
    elif attack_shanten == 1 and max_pressure >= 1.28 and attack_commitment < 0.95:
        should_fold = True
    elif attack_shanten <= 0 and max_pressure >= 1.55 and (attack_han < 3 or attack_wait_quality < 0.48):
        should_fold = True
    elif attack_deal_in_points >= 1300 and attack_shanten >= 2:
        should_fold = True
    elif attack_deal_in_points >= 1900 and attack_shanten == 1 and attack_han < 3:
        should_fold = True
    elif attack_deal_in_rate >= 0.16 and attack_han < 4 and attack_commitment < 1.1:
        should_fold = True

    if not should_fold:
        return None

    safe_pool = [
        profile
        for profile in profiles
        if (
            float(profile.get("safety_score", 0.0)) >= 0.78
            and int(profile.get("deal_in_points", 99999)) <= 1400
        )
        or (
            float(profile.get("risk", 99.0)) <= 0.45
            and float(profile.get("safety_score", 0.0)) >= 0.56
            and int(profile.get("deal_in_points", 99999)) <= 900
        )
    ]
    if not safe_pool:
        return None

    selected = max(
        safe_pool,
        key=lambda item: (
            float(item.get("safety_score", 0.0)),
            -float(item.get("risk", 99.0)),
            -int(item.get("deal_in_points", 99999)),
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
        return calculate_shanten_for_tiles(tiles)
    except ValueError:
        return 8

__all__ = [
    "opponent_models_from_risk_context",
    "structured_discard_ev",
    "lookahead_after_discard_ev",
    "alpha_used_count_key",
    "alpha_hand_count_key",
    "alpha_remaining_count",
    "alpha_effective_ukeire_from_state",
    "alpha_terminal_projection_ev",
    "alpha_draw_candidates",
    "alpha_search_config",
    "alpha_branch_search_ev",
    "alpha_style_lookahead_profile",
    "alpha_projection_for_hand",
    "alpha_open_call_projection_profile",
    "alpha_riichi_projection_profile",
    "discard_profile",
    "sorted_discard_profiles",
    "forced_defense_profile_choice",
    "choose_profile_with_ai_policy",
    "shanten_of_tiles",
]
