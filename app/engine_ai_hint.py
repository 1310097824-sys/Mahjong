"""行动提示面板的数据来源。

行动提示不是独立写一套“建议系统”，而是复用 AI 实际决策评估：弃牌、吃碰杠、
立直、自摸、荣和、拔北、九种九牌都会转换成可展示的推荐项。这样玩家看到的提示
和 AI 自己的判断保持一致，后续强化 AI 时提示也会自然变强。
"""

from __future__ import annotations

from typing import Any

from app.engine_actions import build_reaction_actions, build_turn_actions
from app.engine_ai_call import open_call_profile, riichi_decision_profile
from app.engine_ai_discard import (
    discard_profile,
    discard_metrics_for_hand,
    route_profiles_for_discards,
    safe_reserve_profiles_for_discards,
    shanten_of_tiles,
    sorted_discard_profiles,
)
from app.engine_common import ActionChoice, ai_level_policy
from app.engine_risk import *
from app.engine_rules import current_dora_indicators
from app.engine_tiles import calculate_shanten_for_tiles, dora_from_indicator, tile_label, tile_type

def hint_shanten_value(game: dict[str, Any], seat: int) -> int | None:
    try:
        return calculate_shanten_for_tiles(game["round_state"]["hands"][seat])
    except ValueError:
        return None

def turn_special_action_profile(game: dict[str, Any], seat: int, action: ActionChoice, level: int) -> dict[str, Any]:
    round_state = game["round_state"]
    current_shanten = shanten_of_tiles(round_state["hands"][seat])
    strategy = placement_strategy_context(game, seat)
    progress = round_progress_ratio(round_state)
    pressure = opponent_models(game, seat)
    max_threat = max((model["threat"] for model in pressure), default=0.0)
    max_push_pressure = max((model.get("push_pressure", model["threat"]) for model in pressure), default=0.0)
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
        defense_ev = 18.0 + max_threat * 4.0 + max_push_pressure * 4.5
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
        defense_ev = -(max_threat * (1.5 + progress * 2.5) + max_push_pressure * (1.4 + progress * 2.4))
        table_ev = 3.0 + strategy["value_bias"] * 6.0
        final_ev = round(speed_ev + value_ev + defense_ev + table_ev, 3)
        threshold = 8.0 + max(max_threat, max_push_pressure * 0.72) * 2.5
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
        effective_threat = max(max_threat, max_push_pressure * 0.74)
        defense_ev = -(6.0 + effective_threat * (8.0 + progress * 10.0) + min(8.0, max_loss / 3900))
        if action.type == "added_kan":
            defense_ev -= 3.5 + effective_threat * 3.0
        if current_shanten <= 1:
            defense_ev *= 0.72
        table_ev = (strategy["value_bias"] * 7.0 + strategy["attack_bias"] * 4.0 - strategy["defense_bias"] * 9.0)
        final_ev = round(speed_ev + value_ev + defense_ev + table_ev, 3)
        threshold = 12.0 if action.type == "closed_kan" else 16.0
        threshold += effective_threat * 4.0 + progress * 4.0 + strategy["defense_bias"] * 6.0
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
    max_push_pressure = max((model.get("push_pressure", model["threat"]) for model in pressure), default=0.0)
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
    defense_ev = 6.0 + max_threat * (4.0 + progress * 4.0) + max_push_pressure * (4.0 + progress * 5.0)
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
        source_tiles = game["round_state"]["hands"][seat]
        precomputed_metrics = discard_metrics_for_hand(game, seat, source_tiles)
        precomputed_routes = route_profiles_for_discards(game, seat, source_tiles, precomputed_metrics)
        precomputed_safe_reserves = safe_reserve_profiles_for_discards(
            game, seat, source_tiles, risk_context, precomputed_metrics
        )
        discard_item = discard_profile(
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

def serialize_special_action_hint(game: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    action: ActionChoice = profile["action"]
    best_discard = profile.get("best_discard")
    best_discard_tile = best_discard.get("tile_label") if isinstance(best_discard, dict) else None
    return {
        "id": action.action_id,
        "type": action.type,
        "label": action.label,
        "tile": tile_label(action.tile_id, game) if action.tile_id is not None else None,
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
        "alpha_action_ev": profile.get("alpha_action_ev"),
        "alpha_action_search_ev": profile.get("alpha_action_search_ev"),
        "alpha_action_label": profile.get("alpha_action_label", ""),
        "alpha_action_depth": profile.get("alpha_action_depth"),
        "global_reward_ev": profile.get("global_reward_ev"),
        "global_reward_label": profile.get("global_reward_label", ""),
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
        serialize_special_action_hint(game, profile)
        for profile in sorted(
            profiles,
            key=lambda item: (
                not bool(item.get("recommended", False)),
                -float(item.get("final_ev", 0.0)),
                item["action"].label,
            ),
        )
    ]

def build_hint_block(game: dict[str, Any], *, deep_search: bool = False) -> dict[str, Any] | None:
    round_state = game["round_state"]
    seat = game["human_seat"]
    level = 3
    is_human_turn = round_state["phase"] == "DISCARD" and round_state["turn_seat"] == seat
    is_human_reaction = round_state["phase"] == "REACTION" and bool(build_reaction_actions(game, seat))
    if not is_human_turn and not is_human_reaction:
        return None

    shanten_value = hint_shanten_value(game, seat)
    # 实时行动提示必须轻量：深度前瞻会在每次 public_state 刷新时触发，
    # 容易把一次出牌拖到数秒。深度搜索留给 AI 决策/后续按需分析。
    profiles = sorted_discard_profiles(game, seat, level, deep_search=deep_search)[:3] if is_human_turn else []
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
                "alpha_search_ev": item.get("alpha_search_ev", 0.0),
                "alpha_search_depth": item.get("alpha_search_depth", 0),
                "alpha_search_label": item.get("alpha_search_label", ""),
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
                "deal_in_loss_ev": item.get("deal_in_loss_ev", 0.0),
                "deal_in_rate": item.get("deal_in_rate", 0.0),
                "deal_in_points": item.get("deal_in_points", 0),
                "deal_in_label": item.get("deal_in_label", ""),
                "safe_reserve_ev": item.get("safe_reserve_ev", 0.0),
                "safe_reserve_score": item.get("safe_reserve_score", 0.0),
                "safe_reserve_label": item.get("safe_reserve_label", ""),
                "global_reward_ev": item.get("global_reward_ev", 0.0),
                "global_reward_label": item.get("global_reward_label", ""),
                "win_rank_delta": item.get("win_rank_delta", 0),
                "loss_rank_delta": item.get("loss_rank_delta", 0),
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

__all__ = [
    "hint_shanten_value",
    "turn_special_action_profile",
    "pass_action_profile_for_hint",
    "special_action_profile_for_hint",
    "serialize_special_action_hint",
    "special_action_hints",
    "build_hint_block",
]
