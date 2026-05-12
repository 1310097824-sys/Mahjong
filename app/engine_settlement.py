"""流局、和牌和整场结算。

这里处理所有分数落地：自摸/荣和支付、供托、本场、责任支付、荒牌听牌罚符、
途中流局、连庄判断、终局排名和 UMA。结算完成后会写入 round_result/result_summary，
供前端结算面板、历史对局和玩家统计使用。
"""

from __future__ import annotations

import math
import sys
from typing import Any

from app import rust_core
from app.engine_actions import build_reaction_actions as _build_reaction_actions
from app.engine_common import now_iso
from app.engine_constants import ABORTIVE_DRAW_HEADLINES, HEAD_BUMP_ENABLED, MODE_POINTS, NOTEN_PAYMENTS, RANKED_UMA_UNITS
from app.engine_round import goal_score_reached, should_auto_stop_all_last_dealer
from app.engine_rules import ensure_game_defaults, ensure_round_state_defaults, seat_distance
from app.engine_scoring import (
    append_payment_detail,
    apply_tsumo_payments,
    calculate_limit_hand_cost,
    evaluate_hand as _evaluate_hand,
    full_honba_value,
    liability_context,
    nagashi_mangan_winners,
    tsumo_payment_map,
)
from app.engine_shape import calculate_tenpai_seats as _calculate_tenpai_seats
from app.engine_state import build_public_state


def _public_engine_function(name: str, fallback: Any) -> Any:
    module = sys.modules.get("app.engine")
    candidate = getattr(module, name, None) if module is not None else None
    if callable(candidate) and candidate is not fallback:
        return candidate
    return fallback


def _missing_engine_hook(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("app.engine hook is not available yet")


def record_action(*args: Any, **kwargs: Any) -> None:
    return _public_engine_function("record_action", _missing_engine_hook)(*args, **kwargs)


def evaluate_hand(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
    return _public_engine_function("evaluate_hand", _evaluate_hand)(*args, **kwargs)


def calculate_tenpai_seats(*args: Any, **kwargs: Any) -> list[int]:
    return _public_engine_function("calculate_tenpai_seats", _calculate_tenpai_seats)(*args, **kwargs)


def build_reaction_actions(*args: Any, **kwargs: Any) -> Any:
    return _public_engine_function("build_reaction_actions", _build_reaction_actions)(*args, **kwargs)

def settle_abortive_draw(game: dict[str, Any], kind: str, headline: str | None = None) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    game["honba"] += 1
    game["riichi_sticks"] = round_state["riichi_sticks"]
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = None
    round_state["pending_kita"] = None
    round_state["pending_dora_reveals"] = 0
    round_state["round_result"] = {
        "kind": "ABORTIVE_DRAW",
        "subtype": kind,
        "headline": headline or ABORTIVE_DRAW_HEADLINES.get(kind, "途中流局"),
        "score_changes": [0] * round_state["player_count"],
    }
    round_state["phase"] = "ROUND_END"
    record_action(game, -1, "DRAW_END", details=round_state["round_result"]["headline"])
    _public_engine_function("finalize_round", finalize_round)(game, dealer_continues=True)

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
    _public_engine_function("finalize_round", finalize_round)(game, dealer_continues=dealer_continues)

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
    _public_engine_function("finalize_round", finalize_round)(game, dealer_continues=seat == dealer)

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
    for detail in winner_details:
        detail["amount"] += score_changes[detail["seat"]]

    tenpai = calculate_tenpai_seats(game)
    dealer_continues = round_state["dealer_seat"] in tenpai
    game["honba"] += 1
    game["riichi_sticks"] = round_state["riichi_sticks"]
    round_state["pending_abortive_draw"] = None
    round_state["pending_kan"] = None
    round_state["pending_kita"] = None
    round_state["pending_dora_reveals"] = 0
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
    _public_engine_function("finalize_round", finalize_round)(game, dealer_continues=dealer_continues)

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
    game["riichi_sticks"] = round_state["riichi_sticks"]
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
    _public_engine_function("finalize_round", finalize_round)(game, dealer_continues=dealer_continues)

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
        if goal_score_reached(game):
            finish_game(game)
        return

    if not dealer_continues and goal_score_reached(game):
        finish_game(game)

def attach_ranked_settlement_scores(game: dict[str, Any], placements: list[dict[str, Any]]) -> dict[str, Any]:
    mode = game.get("mode", "4P")
    start_points = MODE_POINTS.get(mode, 25000)
    uma_units = RANKED_UMA_UNITS.get(mode, [])
    rank_bonus = 0.0
    rust_scores = rust_core.ranked_settlement_scores(
        mode,
        start_points,
        [int(entry["points"]) for entry in placements],
    )
    if rust_scores is not None and len(rust_scores) == len(placements):
        for entry, score in zip(placements, rust_scores):
            point_score = round(int(score["point_score"]) / 10, 1)
            uma = round(int(score["uma"]) / 10, 1)
            raw_rank_score = round(point_score + uma + rank_bonus, 1)
            entry["point_score"] = point_score
            entry["uma"] = uma
            entry["oka"] = 0.0
            entry["rank_bonus"] = rank_bonus
            entry["rank_score_raw"] = raw_rank_score
            entry["rank_score"] = int(score["rank_score"])
    else:
        for entry in placements:
            placement_index = max(0, int(entry["placement"]) - 1)
            point_score = round((int(entry["points"]) - start_points) / 1000, 1)
            uma = uma_units[placement_index] if placement_index < len(uma_units) else 0.0
            oka = 0.0
            raw_rank_score = round(point_score + uma + rank_bonus, 1)
            entry["point_score"] = point_score
            entry["uma"] = uma
            entry["oka"] = oka
            entry["rank_bonus"] = rank_bonus
            entry["rank_score_raw"] = raw_rank_score
            entry["rank_score"] = math.ceil(raw_rank_score)
    return {
        "profile": "MAHJONG_SOUL_RANKED",
        "start_score": start_points,
        "oka": 0.0,
        "uma": uma_units,
        "rank_bonus": rank_bonus,
        "rounding": "ceil",
        "unit": "1000点=1.0",
    }

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
    ranked_settlement = attach_ranked_settlement_scores(game, placements)
    game["status"] = "FINISHED"
    game["result_summary"] = {
        "placements": placements,
        "finished_at": now_iso(),
        "leftover_riichi_bonus": leftover_riichi * 1000,
        "ranked_settlement": ranked_settlement,
    }
    game["public_state"] = build_public_state(game)

__all__ = [
    "settle_abortive_draw",
    "build_ron_winners",
    "settle_ron",
    "settle_tsumo",
    "settle_nagashi_mangan",
    "settle_exhaustive_draw",
    "finalize_round",
    "attach_ranked_settlement_scores",
    "finish_game",
]
