"""局内特殊状态判断。

这个模块存放与“当前这一局的时机”有关的判断，例如天和、地和、人和、海底、
河底、抢杠、九种九牌、四风连打等。它们通常不是普通牌型计算能解决的问题，
需要结合摸牌来源、第一巡、是否有鸣牌、最后弃牌来源等局内上下文。
"""

from __future__ import annotations

from typing import Any

from app import rust_core
from app.engine_constants import ABORTIVE_DRAW_HEADLINES
from app.engine_rules import ensure_game_defaults, ensure_round_state_defaults
from app.engine_shape import unique_terminal_honor_types
from app.engine_tiles import tile_type


def round_has_any_calls(round_state: dict[str, Any]) -> bool:
    return any(round_state["melds"][seat] for seat in range(round_state["player_count"]))

def seat_is_on_first_turn(round_state: dict[str, Any], seat: int) -> bool:
    return not round_state["discards"][seat]

def round_is_uninterrupted(round_state: dict[str, Any]) -> bool:
    return not round_has_any_calls(round_state)

def is_tenhou_state(round_state: dict[str, Any], seat: int, *, is_tsumo: bool) -> bool:
    # 和牌时机类规则仍由 Python round_state 供数，再把少量稳定字段压平给 Rust。
    # 这样 Rust 不需要理解整份局面字典，旧 DLL 缺少接口时也能落回下面的原逻辑。
    rust_value = rust_core.is_tenhou_state(
        round_state["player_count"],
        seat,
        round_state["dealer_seat"],
        is_tsumo,
        round_has_any_calls(round_state),
        [len(round_state["discards"][idx]) for idx in range(round_state["player_count"])],
    )
    if rust_value is not None:
        return rust_value
    if not is_tsumo or seat != round_state["dealer_seat"]:
        return False
    if not round_is_uninterrupted(round_state):
        return False
    return not any(round_state["discards"][idx] for idx in range(round_state["player_count"]))

def is_chiihou_state(round_state: dict[str, Any], seat: int, *, is_tsumo: bool) -> bool:
    rust_value = rust_core.is_chiihou_state(
        round_state["player_count"],
        seat,
        round_state["dealer_seat"],
        is_tsumo,
        round_has_any_calls(round_state),
        len(round_state["discards"][seat]),
    )
    if rust_value is not None:
        return rust_value
    if not is_tsumo or seat == round_state["dealer_seat"]:
        return False
    if not round_is_uninterrupted(round_state):
        return False
    return seat_is_on_first_turn(round_state, seat)

def is_renhou_state(game: dict[str, Any], seat: int, *, is_tsumo: bool) -> bool:
    if is_tsumo or not bool(game.get("koyaku_enabled", False)):
        return False
    round_state = game["round_state"]
    discard = round_state["last_discard"]
    # 人和依赖的上下文比较分散：古役开关、自己是否摸过牌、最后弃牌来源等。
    # 这里统一压成标量传给 Rust，避免 Rust 直接依赖 Python 的嵌套字典结构。
    rust_value = rust_core.is_renhou_state(
        round_state["player_count"],
        seat,
        round_state["dealer_seat"],
        is_tsumo,
        bool(game.get("koyaku_enabled", False)),
        round_has_any_calls(round_state),
        bool(round_state["last_draw_source"][seat]),
        discard is not None,
        discard["seat"] if discard is not None else 0,
        discard.get("source") in {"kan", "kita"} if discard is not None else False,
        len(round_state["discards"][seat]),
    )
    if rust_value is not None:
        return rust_value
    if seat == round_state["dealer_seat"]:
        return False
    if not round_is_uninterrupted(round_state):
        return False
    if round_state["last_draw_source"][seat]:
        return False
    if discard is None or discard["seat"] == seat or discard.get("source") in {"kan", "kita"}:
        return False
    return seat_is_on_first_turn(round_state, seat)

def is_haitei_state(round_state: dict[str, Any], seat: int, *, is_tsumo: bool) -> bool:
    rust_value = rust_core.is_haitei_state(
        is_tsumo,
        round_state["current_draw"] is not None,
        round_state["current_draw_source"] == "wall",
        round_state["turn_seat"] == seat,
        not round_state["live_wall"],
    )
    if rust_value is not None:
        return rust_value
    if not is_tsumo or round_state["current_draw"] is None:
        return False
    return round_state["current_draw_source"] == "wall" and round_state["turn_seat"] == seat and not round_state["live_wall"]

def is_houtei_state(round_state: dict[str, Any], *, is_tsumo: bool) -> bool:
    discard = round_state["last_discard"]
    replacement_source = not is_tsumo and discard is not None and discard.get("source") in {"kan", "kita"}
    discarder_last_draw_from_wall = (
        not is_tsumo
        and discard is not None
        and not replacement_source
        and round_state["last_draw_source"][discard["seat"]] == "wall"
    )
    rust_value = rust_core.is_houtei_state(
        is_tsumo,
        discard is not None,
        replacement_source,
        discarder_last_draw_from_wall,
        not round_state["live_wall"],
    )
    if rust_value is not None:
        return rust_value
    if is_tsumo:
        return False
    if discard is None or discard.get("source") in {"kan", "kita"}:
        return False
    return round_state["last_draw_source"][discard["seat"]] == "wall" and not round_state["live_wall"]

def is_chankan_state(round_state: dict[str, Any], *, is_tsumo: bool) -> bool:
    discard = round_state["last_discard"]
    discard_source_is_kan = not is_tsumo and discard is not None and discard.get("source") == "kan"
    kan_type_is_closed = discard_source_is_kan and discard.get("kan_type") == "closed_kan"
    rust_value = rust_core.is_chankan_state(
        is_tsumo,
        discard is not None,
        discard_source_is_kan,
        kan_type_is_closed,
    )
    if rust_value is not None:
        return rust_value
    if is_tsumo:
        return False
    if discard is None or discard.get("source") != "kan":
        return False
    return discard.get("kan_type") != "closed_kan"

def can_abortive_draw_nine_terminals(game: dict[str, Any], seat: int) -> bool:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    phase_is_discard = round_state["phase"] == "DISCARD"
    turn_is_seat = round_state["turn_seat"] == seat
    has_current_draw = round_state["current_draw"] is not None
    seat_has_discards = bool(round_state["discards"][seat])
    has_calls = round_has_any_calls(round_state)
    # 幺九牌去重只有在前置时机可能成立时才计算，保持旧逻辑的短路特性。
    unique_count = (
        len(unique_terminal_honor_types(round_state["hands"][seat]))
        if phase_is_discard and turn_is_seat and has_current_draw and not seat_has_discards and not has_calls
        else 0
    )
    rust_value = rust_core.can_abortive_draw_nine_terminals(
        phase_is_discard,
        turn_is_seat,
        has_current_draw,
        seat_has_discards,
        has_calls,
        unique_count,
    )
    if rust_value is not None:
        return rust_value
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
    rust_value = rust_core.goal_score_reached(
        [int(player["points"]) for player in game["players"]],
        game["target_score"],
    )
    if rust_value is not None:
        return rust_value
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
    subtype = round_result_subtype(game)
    rust_value = rust_core.is_win_like_round_result(kind, subtype)
    if rust_value is not None:
        return rust_value
    if kind in {"RON", "TSUMO"}:
        return True
    return kind == "DRAW" and subtype == "NAGASHI_MANGAN"

def should_auto_stop_all_last_dealer(game: dict[str, Any], *, dealer_continues: bool) -> bool:
    ensure_game_defaults(game)
    round_state = game["round_state"]
    # 自动终局判断只需要 all-last 位置、结果类型、庄家座位和分数列表。Rust 侧复刻
    # Python 的“同分低座位优先为头名”规则，Python 保留 round_result 字典解析。
    rust_value = rust_core.should_auto_stop_all_last_dealer(
        dealer_continues,
        game["round_cursor"],
        game["base_rounds"],
        round_result_kind(game),
        round_state["dealer_seat"],
        [int(player["points"]) for player in game["players"]],
        game["target_score"],
    )
    if rust_value is not None:
        return rust_value
    if not dealer_continues:
        return False
    if game["round_cursor"] != game["base_rounds"] - 1:
        return False
    if round_result_kind(game) == "ABORTIVE_DRAW":
        return False
    dealer = round_state["dealer_seat"]
    return top_player_entry(game)["seat"] == dealer and goal_score_reached(game)

def evaluate_pending_abortive_draw_after_discard(game: dict[str, Any]) -> dict[str, str] | None:
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    if round_state["player_count"] != 4:
        return None

    # Rust 只接收扁平数组，所以这里把 round_state 拆成三个稳定序列：
    # 每家的第一张弃牌实体 ID、每家的弃牌数量、每家的立直状态。若 Rust DLL 不存在
    # 或版本较旧，wrapper 会返回 None，下面的 Python 分支仍然保持原行为。
    rust_kind = rust_core.pending_abortive_draw_kind(
        round_state["player_count"],
        [
            round_state["discards"][seat][0]["tile"] if round_state["discards"][seat] else -1
            for seat in range(round_state["player_count"])
        ],
        [len(round_state["discards"][seat]) for seat in range(round_state["player_count"])],
        list(round_state["riichi"]),
        round_has_any_calls(round_state),
    )
    if rust_kind is not None:
        if rust_kind:
            return {"kind": rust_kind, "headline": ABORTIVE_DRAW_HEADLINES[rust_kind]}
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
    kan_types = {"open_kan", "closed_kan", "added_kan"}
    # 复杂 meld 字典仍由 Python 解释，Rust 只接收“每个座位是否拥有过杠”的布尔数组。
    # 这样迁移规则判断时不会把 Python 的状态结构硬编码进 Rust FFI。
    rust_value = rust_core.should_abort_for_four_kans(
        round_state["kan_count"],
        [
            any(meld["type"] in kan_types for meld in round_state["melds"][seat])
            for seat in range(round_state["player_count"])
        ],
    )
    if rust_value is not None:
        return rust_value
    return round_state["kan_count"] >= 4 and kan_owner_count(round_state) > 1

def four_kan_abortive_draw_payload() -> dict[str, str]:
    return {"kind": "SUUKAIKAN", "headline": ABORTIVE_DRAW_HEADLINES["SUUKAIKAN"]}

def should_abort_for_triple_ron(game: dict[str, Any], winners: list[int]) -> bool:
    return False

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

__all__ = [
    "round_has_any_calls",
    "seat_is_on_first_turn",
    "round_is_uninterrupted",
    "is_tenhou_state",
    "is_chiihou_state",
    "is_renhou_state",
    "is_haitei_state",
    "is_houtei_state",
    "is_chankan_state",
    "can_abortive_draw_nine_terminals",
    "top_player_entry",
    "goal_score_reached",
    "round_result_kind",
    "round_result_subtype",
    "is_win_like_round_result",
    "should_auto_stop_all_last_dealer",
    "evaluate_pending_abortive_draw_after_discard",
    "kan_owner_count",
    "should_abort_for_four_kans",
    "four_kan_abortive_draw_payload",
    "should_abort_for_triple_ron",
    "is_kokushi_result",
    "kan_reaction_tile",
    "kita_reaction_tile",
]
