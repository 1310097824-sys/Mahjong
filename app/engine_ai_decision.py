"""AI 实际行动选择器。

这里把候选动作排序并选出 AI 要执行的动作。流程优先处理强制规则（例如立直后摸切、
可自摸直接和牌），再评估九种九牌、拔北/杠、立直、弃牌和反应动作。它是 AI 评估
模块和动作执行模块之间的桥。
"""

from __future__ import annotations

from typing import Any

from app.engine_actions import build_reaction_actions, build_turn_actions, forced_riichi_tsumogiri_action
from app.engine_ai_call import open_call_profile, riichi_decision_profile
from app.engine_ai_discard import (
    choose_profile_with_ai_policy,
    discard_metrics_for_hand,
    discard_profile,
    route_profiles_for_discards,
    safe_reserve_profiles_for_discards,
    sorted_discard_profiles,
)
from app.engine_ai_hint import turn_special_action_profile
from app.engine_common import ActionChoice, ai_level_policy
from app.engine_constants import ACTION_PRIORITY
from app.engine_risk import build_tile_risk_context
from app.engine_rules import seat_distance
from app.engine_tiles import calculate_shanten_for_tiles, is_red, tile_type

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
            shanten_value = calculate_shanten_for_tiles(game["round_state"]["hands"][seat])
        except ValueError:
            shanten_value = 8
        if (level == 1 and shanten_value >= 4) or (level >= 2 and shanten_value >= 5):
            return abortive_draw_action, "起手幺九牌过多，选择九种九牌流局。"
    if game["mode"] == "3P":
        kita_profiles = [
            turn_special_action_profile(game, seat, action, level)
            for action in actions
            if action.type == "kita"
        ]
        if kita_profiles:
            best_kita_profile = max(kita_profiles, key=lambda item: item["final_ev"])
            if best_kita_profile["recommended"]:
                return (
                    best_kita_profile["action"],
                    f"拔北EV {best_kita_profile['final_ev']} 达标 | 局况 {best_kita_profile['strategy_label']} | 选择拔北。",
                )
    kan_profiles = [
        turn_special_action_profile(game, seat, action, level)
        for action in actions
        if action.type in {"closed_kan", "added_kan"}
    ]
    if kan_profiles:
        best_kan_profile = max(kan_profiles, key=lambda item: item["final_ev"])
        if best_kan_profile["recommended"]:
            return (
                best_kan_profile["action"],
                f"杠牌EV {best_kan_profile['final_ev']} 达标 | 阈值 {best_kan_profile['threshold']} | 局况 {best_kan_profile['strategy_label']} | 选择{best_kan_profile['action'].label}。",
            )
    if False and game["mode"] == "3P":
        for action in actions:
            if action.type == "kita":
                return action, "北牌可转为拔北宝牌。"
    if False and policy["closed_kan"]:
        for action in actions:
            if action.type == "closed_kan":
                return action, "局面安全，选择暗杠增加打点。"
    riichi_actions = [action for action in actions if action.type == "riichi"]
    if riichi_actions:
        risk_context = build_tile_risk_context(game, seat)
        source_tiles = game["round_state"]["hands"][seat]
        precomputed_metrics = discard_metrics_for_hand(game, seat, source_tiles)
        precomputed_routes = route_profiles_for_discards(game, seat, source_tiles, precomputed_metrics)
        precomputed_safe_reserves = safe_reserve_profiles_for_discards(
            game, seat, source_tiles, risk_context, precomputed_metrics
        )
        profiles = {
            action.tile_id: discard_profile(
                game,
                seat,
                action.tile_id or 0,
                level,
                include_lookahead=False,
                risk_context=risk_context,
                precomputed_discard_metrics=precomputed_metrics,
                precomputed_route_profiles=precomputed_routes,
                precomputed_safe_reserves=precomputed_safe_reserves,
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
    profiles = sorted_discard_profiles(game, seat, level, deep_search=False)
    profile_lookup = {(tile_type(profile["tile_id"]), is_red(profile["tile_id"], game)): profile for profile in profiles}
    action_profiles = [
        profile_lookup[(tile_type(action.tile_id or 0), is_red(action.tile_id or 0, game))]
        for action in discard_actions
    ]
    chosen_profile = choose_profile_with_ai_policy(game, seat, action_profiles, level)
    chosen_key = (tile_type(chosen_profile["tile_id"]), is_red(chosen_profile["tile_id"], game))
    chosen_discard = next(
        action
        for action in discard_actions
        if (tile_type(action.tile_id or 0), is_red(action.tile_id or 0, game)) == chosen_key
    )
    profile = profile_lookup[(tile_type(chosen_discard.tile_id or 0), is_red(chosen_discard.tile_id or 0, game))]
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

__all__ = [
    "choose_ai_turn_action",
    "choose_ai_reaction",
]
