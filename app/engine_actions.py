"""合法动作生成与响应规则。

本模块负责告诉前端/AI“当前能做什么”：出牌、吃、碰、杠、立直、自摸、荣和、拔北、
九种九牌等都会在这里生成 `ActionChoice`。它同时处理振听、头跳、抢暗杠国士限制、
立直后暗杠限制和反应通过后的临时振听等规则细节。
"""

from __future__ import annotations

import sys
from copy import deepcopy
from typing import Any

from app import rust_core
from app.engine_common import ActionChoice
from app.engine_constants import HEAD_BUMP_ENABLED
from app.engine_round import can_abortive_draw_nine_terminals, is_kokushi_result, round_is_uninterrupted, seat_is_on_first_turn
from app.engine_rules import ensure_round_state_defaults, is_closed_hand, is_furiten, next_seat
from app.engine_scoring import evaluate_hand, winning_tile_types_for_layout
from app.engine_shape import is_complete_hand_shape, tenpai_wait_tile_types
from app.engine_tiles import counts_by_type, is_honor, is_red, pop_specific_tiles, sort_tiles, tile_label, tile_type, tile_type_label


def _public_engine_function(name: str, fallback: Any) -> Any:
    module = sys.modules.get("app.engine")
    candidate = getattr(module, name, None) if module is not None else None
    if callable(candidate) and candidate is not fallback:
        return candidate
    return fallback

def has_shape_win_on_last_discard(game: dict[str, Any], seat: int) -> bool:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    discard = round_state["last_discard"]
    if discard is None or discard["seat"] == seat:
        return False
    if discard.get("source") == "kan":
        return False
    if _public_engine_function("is_head_bump_blocked", is_head_bump_blocked)(game, seat):
        return False
    tiles = list(round_state["hands"][seat]) + [discard["tile"]]
    return is_complete_hand_shape(tiles, round_state["melds"][seat], mode=game.get("mode", "4P"))

def apply_forced_furiten_for_current_discard(game: dict[str, Any], *, exclude_seat: int | None = None) -> None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    discard = round_state["last_discard"]
    if discard is None:
        return
    if discard.get("source") == "kita":
        return
    for seat in range(round_state["player_count"]):
        if seat == discard["seat"] or seat == exclude_seat:
            continue
        reaction_builder = _public_engine_function("build_reaction_actions", build_reaction_actions)
        if any(action.type == "ron" for action in reaction_builder(game, seat)):
            continue
        shape_checker = _public_engine_function("has_shape_win_on_last_discard", has_shape_win_on_last_discard)
        if not shape_checker(game, seat):
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
    evaluator = _public_engine_function("evaluate_hand", evaluate_hand)
    ron_result = evaluator(game, seat, discard_tile, is_tsumo=False, kyoutaku_override=0)
    if ron_result is None or is_furiten(round_state, seat, discard_type):
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
        ron_checker = _public_engine_function("can_ron_on_last_discard", can_ron_on_last_discard)
        can_ron, _ = ron_checker(game, other)
        if can_ron:
            return True
    return False

def kuikae_forbidden_tile_types(action_type: str, discard_tile_id: int, consumed_ids: list[int]) -> list[int]:
    rust_result = rust_core.kuikae_forbidden_tile_types(action_type, discard_tile_id, consumed_ids)
    if rust_result is not None:
        return rust_result

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
    return bool(tenpai_wait_tile_types(remaining, mode=game["mode"], melds_data=round_state["melds"][seat]))

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
                    f"摸切 {tile_label(drawn, game)}",
                    tile_id=drawn,
                    meta={"forced_tsumogiri": True},
                )
            ]
        return []
    forbidden_types = set(round_state["kuikae_forbidden_types"][seat])
    actions: list[ActionChoice] = []
    seen: set[tuple[int, bool]] = set()
    riichi_seen_labels: set[str] = set()
    for tile_id in sort_tiles(round_state["hands"][seat], game):
        key = (tile_type(tile_id), is_red(tile_id, game))
        if key in seen:
            continue
        seen.add(key)
        if tile_type(tile_id) in forbidden_types:
            continue
        actions.append(ActionChoice(f"discard|{tile_id}", "discard", seat, f"打出 {tile_label(tile_id, game)}", tile_id=tile_id))
        riichi_label_key = tile_label(tile_id, game)
        if riichi_label_key not in riichi_seen_labels and can_riichi_after_discard(game, seat, tile_id):
            riichi_seen_labels.add(riichi_label_key)
            actions.append(ActionChoice(f"riichi|{tile_id}", "riichi", seat, f"立直并打出 {tile_label(tile_id, game)}", tile_id=tile_id))
    return actions

def build_closed_kan_actions(game: dict[str, Any], seat: int) -> list[ActionChoice]:
    round_state = game["round_state"]
    if (
        round_state["kan_count"] >= 4
        or not round_state["rinshan_tiles"]
        or not round_state["live_wall"]
        or round_state["current_draw"] is None
    ):
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
        for tile_id in sort_tiles(round_state["hands"][seat], game):
            if tile_type(tile_id) == 30:
                if round_state["riichi"][seat] and tile_id != drawn:
                    continue
                actions.append(ActionChoice(f"kita|{tile_id}", "kita", seat, f"拔北 {tile_label(tile_id, game)}", tile_id=tile_id))
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
    if any(action.type in {"tsumo", "closed_kan", "kita"} for action in choices):
        return None
    return discard_choices[0]

def chi_candidates(hand_tiles: list[int], discard_tile: int) -> list[list[int]]:
    rust_result = rust_core.chi_candidates(hand_tiles, discard_tile)
    if rust_result is not None:
        return rust_result

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
    ron_checker = _public_engine_function("can_ron_on_last_discard", can_ron_on_last_discard)
    head_bump_checker = _public_engine_function("is_head_bump_blocked", is_head_bump_blocked)
    can_ron, ron_result = ron_checker(game, seat)
    if can_ron and not head_bump_checker(game, seat):
        actions.append(ActionChoice("ron", "ron", seat, f"荣和 {tile_label(discard_tile, game)}", tile_id=discard_tile))
    if discard.get("source") in {"kan", "kita"}:
        return [action for action in actions if action.type == "ron"]
    if not round_state["live_wall"] and round_state["last_draw_source"][discard["seat"]] == "wall":
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
            labels = " ".join(tile_label(tile, game) for tile in sort_tiles(consumed + [discard_tile], game))
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

__all__ = [
    "has_shape_win_on_last_discard",
    "apply_forced_furiten_for_current_discard",
    "can_ron_on_last_discard",
    "is_head_bump_blocked",
    "kuikae_forbidden_tile_types",
    "legal_post_call_discards",
    "can_declare_riichi_closed_kan",
    "can_riichi_after_discard",
    "can_double_riichi",
    "build_discard_actions",
    "build_closed_kan_actions",
    "build_turn_actions",
    "forced_riichi_tsumogiri_action",
    "chi_candidates",
    "build_reaction_actions",
    "legal_actions_for_human",
]
