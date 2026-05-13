from __future__ import annotations

import copy
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mahjong.shanten import Shanten
from mahjong.tile import TilesConverter

from app import rust_core
from app.config import settings
from app.engine import (
    HEAD_BUMP_ENABLED,
    TARGET_POINTS,
    active_aka_dora_ids,
    apply_forced_furiten_for_current_discard,
    apply_discard,
    alpha_search_config,
    auto_advance,
    build_reaction_actions,
    build_turn_actions,
    build_ron_winners,
    build_round,
    build_wall,
    can_double_riichi,
    can_abortive_draw_nine_terminals,
    can_ron_on_last_discard,
    calculate_tenpai_seats,
    chi_candidates,
    default_aka_dora_count,
    evaluate_pending_abortive_draw_after_discard,
    ensure_game_defaults,
    ensure_round_state_defaults,
    execute_action,
    effective_tiles_after_discard,
    finish_game,
    forced_riichi_tsumogiri_action,
    full_honba_value,
    goal_score_reached,
    hand_route_profile,
    is_chankan_state,
    is_chiihou_state,
    is_haitei_state,
    is_houtei_state,
    is_honor,
    is_furiten,
    is_renhou_state,
    is_simple,
    is_terminal,
    is_tenhou_state,
    is_win_like_round_result,
    liability_context,
    kuikae_forbidden_tile_types,
    legal_tile_types_for_mode,
    local_han_yaku_entries,
    local_mangan_yaku_name,
    local_pattern_entries_for_hand,
    local_yakuman_entries,
    minimum_han_satisfied,
    new_game,
    normalize_aka_dora_count,
    nagashi_mangan_winners,
    perform_call,
    register_liability_for_call,
    representative_tile_id,
    rotate_turn,
    round_up_to_100,
    scoring_indicator_tile_id,
    score_result_total,
    seat_wind_label,
    should_abort_for_four_kans,
    should_auto_stop_all_last_dealer,
    settle_abortive_draw,
    settle_exhaustive_draw,
    settle_ron,
    sorted_discard_profiles,
    tenpai_wait_tile_types,
    tile_value_bonus,
    tsumo_payment_map,
    unique_terminal_honor_types,
    winning_tile_types_for_layout,
    visible_tile_type_counts,
)
from app.main import CreateGameRequest


ENGINE_PATH = ROOT / "app" / "engine.py"
ENGINE_MODULE_PATHS = [
    ENGINE_PATH,
    ROOT / "app" / "engine_common.py",
    ROOT / "app" / "engine_constants.py",
    ROOT / "app" / "engine_flow.py",
    ROOT / "app" / "engine_game.py",
    ROOT / "app" / "engine_mutations.py",
    ROOT / "app" / "engine_execute.py",
    ROOT / "app" / "engine_actions.py",
    ROOT / "app" / "engine_ai.py",
    ROOT / "app" / "engine_ai_call.py",
    ROOT / "app" / "engine_ai_decision.py",
    ROOT / "app" / "engine_ai_discard.py",
    ROOT / "app" / "engine_ai_hint.py",
    ROOT / "app" / "engine_risk.py",
    ROOT / "app" / "engine_rules.py",
    ROOT / "app" / "engine_round.py",
    ROOT / "app" / "engine_scoring.py",
    ROOT / "app" / "engine_settlement.py",
    ROOT / "app" / "engine_shape.py",
    ROOT / "app" / "engine_state.py",
    ROOT / "app" / "engine_tiles.py",
]
TABLE_PATH = ROOT / "riichi-mahjong-ui" / "src" / "components" / "Mahjong" / "Table.tsx"
OUTPUT_PATH = ROOT / "output" / "mahjong_soul_rule_audit.json"

SOURCES = [
    "https://riichi.wiki/index.php?mobileaction=toggle_view_desktop&title=Mahjong_Soul",
    "https://riichi.wiki/Comparison_of_popular_rulesets",
    "https://riichi.wiki/Template%3AMajsoul/Local_yaku_table",
    "https://riichi.wiki/Houtei_raoyui",
    "https://riichi.wiki/Rinshan_kaihou",
]

EXPECTED_LOCAL_YAKU = {
    "Renhou",
    "Daisharin",
    "Daisuurin",
    "Daichikurin",
    "Daichisei",
    "Iipin moyue",
    "Chuupin raoyui",
    "Tsubame gaeshi",
    "Kanburi",
    "Ishi no ue ni mo sannen",
    "Shiiaru raotai",
    "Uumensai",
    "Sanrenkou",
    "Isshoku sanjun",
}

ENGINE_SUPPORT_MARKERS = {
    "Renhou": "renhou_as_yakuman",
    "Daisharin": "has_daisharin_other_suits",
    "Daisuurin": "has_daisharin_other_suits",
    "Daichikurin": "has_daisharin_other_suits",
    "Daichisei": "has_daichisei",
}


@dataclass
class AuditItem:
    id: str
    title: str
    status: str
    detail: str
    source: str


def ok(rule_id: str, title: str, detail: str, source: str) -> AuditItem:
    return AuditItem(rule_id, title, "PASS", detail, source)


def missing(rule_id: str, title: str, detail: str, source: str) -> AuditItem:
    return AuditItem(rule_id, title, "MISSING", detail, source)


def failed(rule_id: str, title: str, detail: str, source: str) -> AuditItem:
    return AuditItem(rule_id, title, "FAIL", detail, source)


def run_check(fn: Callable[[], AuditItem]) -> AuditItem:
    try:
        return fn()
    except AssertionError as exc:
        return failed(fn.__name__, fn.__name__, str(exc) or "断言失败", SOURCES[0])
    except Exception as exc:  # pragma: no cover - audit script should keep reporting
        return failed(fn.__name__, fn.__name__, f"{type(exc).__name__}: {exc}", SOURCES[0])


def test_ranked_starting_points() -> AuditItem:
    game_4p = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    game_3p = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
    assert all(player["points"] == 25000 for player in game_4p["players"]), "四麻起点不是 25000"
    assert all(player["points"] == 35000 for player in game_3p["players"]), "三麻起点不是 35000"
    return ok(
        "ranked_starting_points",
        "段位默认起点",
        "四麻 25000 / 三麻 35000，符合雀魂在线默认开局点数。",
        SOURCES[1],
    )


def test_target_scores() -> AuditItem:
    assert TARGET_POINTS["4P"] == 30000, "四麻目标点不是 30000"
    assert TARGET_POINTS["3P"] == 40000, "三麻目标点不是 40000"
    return ok(
        "ranked_target_scores",
        "段位默认目标点",
        "四麻 30000 / 三麻 40000，符合雀魂在线默认收束目标点。",
        SOURCES[1],
    )


def test_ranked_uma_oka_settlement() -> AuditItem:
    game_4p = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    for player, points in zip(game_4p["players"], [30000, 26000, 24000, 20000]):
        player["points"] = points
    finish_game(game_4p)
    placements_4p = game_4p["result_summary"]["placements"]
    assert placements_4p[0]["rank_score"] == 20.0, "四麻头名未按素点差 +15.0 顺位马结算"
    assert placements_4p[1]["rank_score"] == 6.0, "四麻二位顺位马/素点差结算错误"
    assert placements_4p[0]["oka"] == 0.0, "雀魂段位场不应应用 Oka/头名赏"
    assert round(sum(item["rank_score"] for item in placements_4p), 1) == 0.0, "四麻段位结算分应零和"

    rounded_game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    for player, points in zip(rounded_game["players"], [30100, 25900, 24000, 20000]):
        player["points"] = points
    finish_game(rounded_game)
    rounded_top = rounded_game["result_summary"]["placements"][0]
    assert rounded_top["rank_score_raw"] == 20.1, "段位结算分原始值未按素点差 + 顺位马保存"
    assert rounded_top["rank_score"] == 21, "雀魂段位结算分应按向上取整显示"

    game_3p = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
    for player, points in zip(game_3p["players"], [40000, 35000, 30000]):
        player["points"] = points
    finish_game(game_3p)
    placements_3p = game_3p["result_summary"]["placements"]
    assert placements_3p[0]["rank_score"] == 20.0, "三麻头名未按素点差 +15.0 顺位马结算"
    assert placements_3p[1]["rank_score"] == 0.0, "三麻二位素点差结算错误"
    assert placements_3p[0]["oka"] == 0.0, "雀魂三麻段位场不应应用 Oka/头名赏"
    assert round(sum(item["rank_score"] for item in placements_3p), 1) == 0.0, "三麻段位结算分应零和"

    return ok(
        "ranked_uma_oka_settlement",
        "段位场顺位马与素点差",
        "终局结果保留原始点棒，同时额外输出雀魂段位场口径的素点差、顺位马与段位结算分；Oka/头名赏保持不适用。",
        SOURCES[1],
    )


def test_multi_ron_head_bump_disabled() -> AuditItem:
    assert HEAD_BUMP_ENABLED is False, "当前仍开启了头跳"
    return ok(
        "multi_ron_head_bump",
        "多家荣和不头跳",
        "当前实现允许双响/三响，不使用头跳。",
        SOURCES[1],
    )


def test_multi_ron_nearest_recipient_and_renchan() -> AuditItem:
    import app.engine as engine

    original_evaluate_hand = engine.evaluate_hand
    original_finalize_round = engine.finalize_round
    original_record_action = engine.record_action
    captured: list[bool] = []

    def fake_evaluate_hand(game: dict[str, Any], seat: int, discard_tile_id: int, is_tsumo: bool = False, kyoutaku_override: int = 0) -> dict[str, Any]:
        return {
            "han": 1,
            "fu": 30,
            "cost": {"main": 1000},
            "yaku": ["Riichi 1 han"],
            "fu_details": [],
            "is_tsumo": False,
            "win_tile_label": "1m",
            "yakuman_keys": {},
            "yakuman_total_han": 0,
        }

    def fake_finalize_round(game: dict[str, Any], *, dealer_continues: bool) -> None:
        captured.append(dealer_continues)

    def fake_record_action(*args: Any, **kwargs: Any) -> None:
        return None

    try:
        engine.evaluate_hand = fake_evaluate_hand
        engine.finalize_round = fake_finalize_round
        engine.record_action = fake_record_action

        base_round_state = {
            "player_count": 4,
            "dealer_seat": 2,
            "last_discard": {"seat": 0, "tile": 0},
            "riichi_sticks": 2,
            "pending_abortive_draw": None,
            "pending_kan": None,
            "pending_kita": None,
            "pending_dora_reveals": 0,
            "phase": "REACTION",
            "discards": [[], [], [], []],
            "liability_payments": [{} for _ in range(4)],
            "honba": 1,
        }

        def make_game() -> dict[str, Any]:
            game = {
                "players": [
                    {"name": "A", "points": 25000, "seat": 0},
                    {"name": "B", "points": 25000, "seat": 1},
                    {"name": "C", "points": 25000, "seat": 2},
                    {"name": "D", "points": 25000, "seat": 3},
                ],
                "honba": 1,
                "riichi_sticks": 2,
                "round_state": copy.deepcopy(base_round_state),
            }
            ensure_game_defaults(
                {
                    "mode": "4P",
                    "round_length": "SOUTH",
                    "base_rounds": 8,
                    "max_rounds": 12,
                    "target_score": 30000,
                    "koyaku_enabled": False,
                }
            )
            ensure_round_state_defaults(game["round_state"])
            return game

        game = make_game()
        settle_ron(game, [1, 2])
        assert game["players"][1]["points"] == 28300, "最近荣和家没有独占本场与立直棒"
        assert game["players"][2]["points"] == 26000, "较远荣和家不应拿到本场/立直棒"
        assert captured[-1] is False, "庄家不是最近荣和家时不应连庄"

        game = make_game()
        game["round_state"]["dealer_seat"] = 1
        settle_ron(game, [1, 2])
        assert captured[-1] is True, "庄家是最近荣和家时应连庄"
    finally:
        engine.evaluate_hand = original_evaluate_hand
        engine.finalize_round = original_finalize_round
        engine.record_action = original_record_action

    return ok(
        "multi_ron_nearest_rules",
        "多响最近家规则",
        "本场与立直棒只给最近荣和家，连庄也按最近荣和家判断。",
        SOURCES[1],
    )


def test_multi_ron_mahjong_soul_dealer_keeps() -> AuditItem:
    import app.engine as engine

    original_evaluate_hand = engine.evaluate_hand
    original_finalize_round = engine.finalize_round
    original_record_action = engine.record_action
    captured: list[bool] = []

    def fake_evaluate_hand(
        game: dict[str, Any],
        seat: int,
        discard_tile_id: int,
        is_tsumo: bool = False,
        kyoutaku_override: int = 0,
    ) -> dict[str, Any]:
        return {
            "han": 1,
            "fu": 30,
            "cost": {"main": 1000},
            "yaku": ["Riichi 1 han"],
            "fu_details": [],
            "is_tsumo": False,
            "win_tile_label": "1m",
            "yakuman_keys": {},
            "yakuman_total_han": 0,
        }

    def fake_finalize_round(game: dict[str, Any], *, dealer_continues: bool) -> None:
        captured.append(dealer_continues)

    def fake_record_action(*args: Any, **kwargs: Any) -> None:
        return None

    try:
        engine.evaluate_hand = fake_evaluate_hand
        engine.finalize_round = fake_finalize_round
        engine.record_action = fake_record_action

        base_round_state = {
            "player_count": 4,
            "dealer_seat": 2,
            "last_discard": {"seat": 0, "tile": 0},
            "riichi_sticks": 2,
            "pending_abortive_draw": None,
            "pending_kan": None,
            "pending_kita": None,
            "pending_dora_reveals": 0,
            "phase": "REACTION",
            "discards": [[], [], [], []],
            "liability_payments": [{} for _ in range(4)],
            "honba": 1,
        }

        def make_game() -> dict[str, Any]:
            game = {
                "players": [
                    {"name": "A", "points": 25000, "seat": 0},
                    {"name": "B", "points": 25000, "seat": 1},
                    {"name": "C", "points": 25000, "seat": 2},
                    {"name": "D", "points": 25000, "seat": 3},
                ],
                "honba": 1,
                "riichi_sticks": 2,
                "round_state": copy.deepcopy(base_round_state),
            }
            ensure_game_defaults(
                {
                    "mode": "4P",
                    "round_length": "SOUTH",
                    "base_rounds": 8,
                    "max_rounds": 12,
                    "target_score": 30000,
                    "koyaku_enabled": False,
                }
            )
            ensure_round_state_defaults(game["round_state"])
            return game

        game = make_game()
        settle_ron(game, [1, 2])
        assert game["players"][1]["points"] == 28300, "最近荣和家没有独占本场与立直棒"
        assert game["players"][2]["points"] == 26000, "较远荣和家不应拿到本场与立直棒"
        assert captured[-1] is True, "多响时庄家只要也荣和就应连庄"

        game = make_game()
        game["round_state"]["dealer_seat"] = 1
        settle_ron(game, [1, 2])
        assert captured[-1] is True, "庄家是最近荣和家时应连庄"
    finally:
        engine.evaluate_hand = original_evaluate_hand
        engine.finalize_round = original_finalize_round
        engine.record_action = original_record_action

    return ok(
        "multi_ron_mahjong_soul_dealer_keeps",
        "多响连庄按雀魂在线口径",
        "本场与立直棒只给最近荣和家，但多响时庄家只要也荣和就会连庄。",
        SOURCES[0],
    )


def test_riichi_sticks_carry_on_draws() -> AuditItem:
    import app.engine as engine

    original_calculate_tenpai = engine.calculate_tenpai_seats
    try:
        engine.calculate_tenpai_seats = lambda game: []

        exhaustive = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
        exhaustive["riichi_sticks"] = 1
        exhaustive["round_state"]["riichi_sticks"] = 3
        settle_exhaustive_draw(exhaustive)
        assert exhaustive["riichi_sticks"] == 3, "荒牌流局未把本局立直棒带入下一局"
        assert exhaustive["round_state"]["riichi_sticks"] == 3, "荒牌流局结果中立直棒被错误清空"

        abortive = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
        abortive["riichi_sticks"] = 1
        abortive["round_state"]["riichi_sticks"] = 4
        settle_abortive_draw(abortive, "SUUCHA_RIICHI")
        assert abortive["riichi_sticks"] == 4, "途中流局未保留供托立直棒"
        assert abortive["round_state"]["riichi_sticks"] == 4, "途中流局结果中供托立直棒被错误清空"
    finally:
        engine.calculate_tenpai_seats = original_calculate_tenpai

    return ok(
        "riichi_stick_carry_on_draw",
        "流局供托立直棒继承",
        "荒牌流局与途中流局不会吞掉本局已经成立的立直棒，供托会进入下一局。",
        SOURCES[1],
    )


def test_nagashi_mangan_keeps_riichi_sticks() -> AuditItem:
    import app.engine as engine

    original_calculate_tenpai = engine.calculate_tenpai_seats
    try:
        engine.calculate_tenpai_seats = lambda game: []

        game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
        round_state = game["round_state"]
        game["riichi_sticks"] = 2
        round_state["riichi_sticks"] = 2
        round_state["discards"][1] = [
            {"tile": 0, "riichi": False, "called": False},
            {"tile": 31 * 4, "riichi": False, "called": False},
        ]

        settle_exhaustive_draw(game)
        assert round_state["round_result"]["subtype"] == "NAGASHI_MANGAN", "审计前提失败：未触发流局满贯"
        assert game["riichi_sticks"] == 2, "流局满贯错误收走供托立直棒"
        assert round_state["riichi_sticks"] == 2, "流局满贯结果中供托立直棒被错误清空"
        assert all(
            payment.get("kind") != "riichi_bonus"
            for winner in round_state["round_result"].get("winners", [])
            for payment in winner.get("payments", [])
        ), "流局满贯不应显示立直棒收入"
    finally:
        engine.calculate_tenpai_seats = original_calculate_tenpai

    return ok(
        "nagashi_mangan_keeps_riichi_sticks",
        "流局满贯保留供托",
        "流局满贯按流局处理，只结算满贯自摸等价点数；供托立直棒留在场中等待下一次正常和牌。",
        SOURCES[1],
    )


def test_open_meld_tenpai_shape_counts_melds() -> AuditItem:
    game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    seat = 0
    round_state = game["round_state"]
    round_state["hands"][seat] = [
        0,
        4,
        8,
        36,
        40,
        44,
        72,
        76,
        80,
        28 * 4,
    ]
    round_state["melds"][seat] = [
        {
            "type": "pon",
            "tiles": [31 * 4, 31 * 4 + 1, 31 * 4 + 2],
            "opened": True,
            "called_tile": 31 * 4,
            "from_seat": 1,
        }
    ]

    waits = winning_tile_types_for_layout(game, seat, round_state["hands"][seat], round_state["melds"][seat])
    assert waits == {28}, f"带碰牌面子时听牌形状未按副露计算: {waits}"
    assert seat in calculate_tenpai_seats(game), "荒牌听牌判定未把副露面子计入"
    assert not tenpai_wait_tile_types(round_state["hands"][seat], mode="4P"), "纯手牌听牌路径不应误判 10 张散手"
    return ok(
        "open_meld_tenpai_shape",
        "副露后的听牌形状",
        "听牌/荒牌罚符会把碰、吃、杠等已完成面子计入，避免开放手牌被误判为不听。",
        SOURCES[1],
    )


def test_open_meld_missed_ron_sets_temporary_furiten() -> AuditItem:
    game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    seat = 1
    round_state = game["round_state"]
    round_state["phase"] = "REACTION"
    round_state["last_discard"] = {"seat": 0, "tile": 28 * 4}
    round_state["reaction_passed"][seat] = True
    round_state["hands"][seat] = [
        0,
        4,
        8,
        36,
        40,
        44,
        72,
        76,
        80,
        28 * 4 + 1,
    ]
    round_state["melds"][seat] = [
        {
            "type": "pon",
            "tiles": [31 * 4, 31 * 4 + 1, 31 * 4 + 2],
            "opened": True,
            "called_tile": 31 * 4,
            "from_seat": 2,
        }
    ]

    apply_forced_furiten_for_current_discard(game)
    assert round_state["temporary_furiten"][seat] is True, "副露手见逃荣和未进入同巡振听"
    return ok(
        "open_meld_missed_ron_furiten",
        "副露手见逃振听",
        "开放手牌错过可荣牌时，也会把已完成副露面子计入形状并进入同巡振听。",
        SOURCES[1],
    )


def test_equivalent_duplicate_tile_action_normalized() -> AuditItem:
    game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    seat = game["human_seat"]
    round_state = game["round_state"]
    round_state["phase"] = "DISCARD"
    round_state["turn_seat"] = seat
    round_state["current_draw"] = 32
    round_state["hands"][seat] = [0, 1, 4, 8, 36, 40, 44, 72, 76, 80, 108, 112, 116, 120]

    execute_action(game, "discard|1", actor_seat=seat, advance=False)
    remaining_1m = [tile for tile in round_state["hands"][seat] if tile // 4 == 0]
    assert len(remaining_1m) == 1, "同种牌的非首张 tile id 没有被归一化为合法弃牌"
    assert round_state["phase"] == "REACTION", "等价弃牌执行后未进入反应阶段"
    return ok(
        "duplicate_tile_action_normalized",
        "同种牌点击归一化",
        "同一种牌有多张时，任意一张的点击都会映射成当前合法动作，避免后两张无法打出的卡死感。",
        SOURCES[0],
    )


def test_double_riichi_kept_when_declaration_discard_called() -> AuditItem:
    game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    round_state = game["round_state"]
    declarer = 0
    caller = 1
    discard_tile = 108
    round_state["phase"] = "REACTION"
    round_state["turn_seat"] = declarer
    round_state["last_discard"] = {"seat": declarer, "tile": discard_tile}
    round_state["discards"][declarer].append({"tile": discard_tile, "riichi": True, "called": False})
    round_state["riichi"][declarer] = True
    round_state["double_riichi"][declarer] = True
    round_state["double_riichi_pending"][declarer] = True
    round_state["ippatsu"][declarer] = True
    round_state["hands"][caller] = [109, 110, 0, 4, 8, 36, 40, 44, 72, 76, 80, 112, 116]

    perform_call(game, caller, "pon", discard_tile, [109, 110])
    assert round_state["riichi"][declarer] is True, "宣言牌被碰后立直状态被错误取消"
    assert round_state["double_riichi"][declarer] is True, "宣言牌被碰后双立直不应被取消"
    assert round_state["double_riichi_pending"][declarer] is False, "宣言牌被碰后待确认标记应收束"
    assert round_state["ippatsu"][declarer] is False, "宣言牌被碰应打断一发"
    return ok(
        "double_riichi_called_declaration_discard",
        "双立直宣言牌被鸣不取消双立直",
        "宣言前无鸣牌即可成立双立直；宣言牌被副露只会打断一发，不会把双立直降回普通立直。",
        SOURCES[1],
    )


def test_open_kan_dora_reveals_after_safe_discard() -> AuditItem:
    game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    seat = 0
    round_state = game["round_state"]
    round_state["phase"] = "DISCARD"
    round_state["turn_seat"] = seat
    round_state["current_draw"] = 36
    round_state["hands"][seat] = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 72, 76, 80, 84]
    round_state["pending_dora_reveals"] = 1
    round_state["dora_revealed"] = 1
    before = round_state["dora_revealed"]

    apply_discard(game, seat, 36)
    assert round_state["dora_revealed"] == before, "明杠/加杠后的新宝牌不应在杠后弃牌荣和窗口前翻开"
    rotate_turn(game)
    assert round_state["dora_revealed"] == before + 1, "杠后弃牌安全通过后，应翻开 pending 杠宝牌"
    return ok(
        "kan_dora_after_safe_discard",
        "明杠/加杠宝牌翻开时机",
        "明杠/加杠的新宝牌不会参与杠后第一张弃牌的荣和，只有该弃牌安全通过后才翻开。",
        SOURCES[1],
    )


def test_four_kan_abort_waits_for_post_kan_discard() -> AuditItem:
    import app.engine as engine

    original_build_reaction_actions = engine.build_reaction_actions
    try:
        engine.build_reaction_actions = lambda game, seat: []

        game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
        rs = game["round_state"]
        caller = 1
        discard_tile = 31 * 4
        consumed = [31 * 4 + 1, 31 * 4 + 2, 31 * 4 + 3]
        rs["phase"] = "REACTION"
        rs["turn_seat"] = 0
        rs["last_discard"] = {"seat": 0, "tile": discard_tile}
        rs["discards"][0].append({"tile": discard_tile, "riichi": False, "called": False})
        rs["hands"][caller] = consumed + [0, 4, 8, 36, 40, 44, 72, 76, 80, 84]
        rs["melds"][0] = [{"type": "closed_kan", "tiles": [0, 1, 2, 3], "opened": False}]
        rs["melds"][2] = [
            {"type": "closed_kan", "tiles": [4, 5, 6, 7], "opened": False},
            {"type": "closed_kan", "tiles": [8, 9, 10, 11], "opened": False},
        ]
        rs["kan_count"] = 3

        perform_call(game, caller, "open_kan", discard_tile, consumed)
        assert rs["phase"] == "DISCARD", "第四杠成立后不应立刻四杠散了"
        assert rs["pending_abortive_draw"] and rs["pending_abortive_draw"]["kind"] == "SUUKAIKAN", "第四杠后应等待杠后弃牌安全通过"
        drawn = rs["current_draw"]
        assert drawn is not None, "第四杠后应先摸岭上牌"

        apply_discard(game, caller, drawn)
        auto_advance(game)
        assert rs["round_result"]["subtype"] == "SUUKAIKAN", "第四杠后的弃牌安全通过后才应四杠散了"
    finally:
        engine.build_reaction_actions = original_build_reaction_actions

    return ok(
        "four_kan_abort_after_discard",
        "四杠散了时机",
        "多人合计第四杠后先摸岭上牌；若杠后弃牌无人荣和，才触发四杠散了。",
        SOURCES[1],
    )


def test_last_discard_allows_only_ron_reaction() -> AuditItem:
    import app.engine as engine

    original_can_ron = engine.can_ron_on_last_discard
    try:
        engine.can_ron_on_last_discard = lambda game, seat, ignore_passed=False: (False, None)
        game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
        rs = game["round_state"]
        rs["phase"] = "REACTION"
        rs["live_wall"] = []
        rs["last_discard"] = {"seat": 0, "tile": 8}
        rs["last_draw_source"][0] = "wall"
        rs["reaction_passed"] = [False] * 4
        rs["hands"][1] = [9, 10, 0, 4, 12, 16, 20, 36, 40, 44, 72, 76, 80]
        rs["hands"][2] = [0, 4, 12, 16, 20, 36, 40, 44, 72, 76, 80, 84, 88]

        assert build_reaction_actions(game, 1) == [], "海底前最后一张弃牌不应允许碰/杠"
        assert build_reaction_actions(game, 2) == [], "海底前最后一张弃牌不应允许吃"
    finally:
        engine.can_ron_on_last_discard = original_can_ron

    return ok(
        "last_discard_ron_only",
        "最后弃牌只允许荣和",
        "荒牌前最后一张正常弃牌不会生成吃、碰、明杠反应，只保留可能的河底荣和。",
        SOURCES[1],
    )


def test_no_kan_on_haitei_draw() -> AuditItem:
    game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    rs = game["round_state"]
    seat = 0
    rs["phase"] = "DISCARD"
    rs["turn_seat"] = seat
    rs["live_wall"] = []
    rs["rinshan_tiles"] = [120, 121, 122, 123]
    rs["current_draw"] = 3
    rs["hands"][seat] = [0, 1, 2, 3, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40]

    actions = build_turn_actions(game, seat)
    assert all(action.type not in {"closed_kan", "added_kan"} for action in actions), "海底摸牌时不应允许暗杠/加杠"

    return ok(
        "no_kan_on_haitei_draw",
        "海底摸牌不可杠",
        "活牌墙为空的最后一摸只能和牌或弃牌，不再生成暗杠/加杠动作。",
        SOURCES[1],
    )


def test_extra_round_draw_reaching_target_ends_game() -> AuditItem:
    import app.engine as engine

    original_calculate_tenpai = engine.calculate_tenpai_seats
    try:
        game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
        game["round_cursor"] = game["base_rounds"]
        game["round_state"] = build_round(game)
        game["round_state"]["honba"] = game["honba"]
        game["players"][0]["points"] = 29000
        for seat in range(1, 4):
            game["players"][seat]["points"] = 27000
        engine.calculate_tenpai_seats = lambda current_game: [0]

        settle_exhaustive_draw(game)
        assert game["players"][0]["points"] >= game["target_score"], "审计前提失败：荒牌罚符未让玩家达标"
        assert game["status"] == "FINISHED", "延长战荒牌点数达标后未立即终局"
    finally:
        engine.calculate_tenpai_seats = original_calculate_tenpai

    return ok(
        "extra_round_draw_target_end",
        "延长战流局达标终局",
        "西入/延长战中即使是荒牌罚符导致达标，也会立即结束，而不是继续多打一局。",
        SOURCES[1],
    )


def test_sanma_tsumo_loss() -> AuditItem:
    game = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
    round_state = game["round_state"]
    dealer = round_state["dealer_seat"]
    child = (dealer + 1) % 3

    dealer_cost = {"main": 500, "main_bonus": 0, "additional": 0, "additional_bonus": 0}
    dealer_map = tsumo_payment_map(game, dealer, dealer_cost)
    assert sorted(dealer_map.values()) == [500, 500], "三麻庄家自摸不是 500 all"

    child_cost = {"main": 500, "main_bonus": 0, "additional": 300, "additional_bonus": 0}
    child_map = tsumo_payment_map(game, child, child_cost)
    dealer_payment = child_map[dealer]
    other_child_payment = next(value for loser, value in child_map.items() if loser != dealer)
    assert dealer_payment == 500 and other_child_payment == 300, "三麻闲家自摸不是 300/500"

    return ok(
        "sanma_tsumo_loss",
        "三麻默认 Tsumo-loss",
        "三麻自摸按庄家/闲家真实支付，不做 North-Bisection 平摊。",
        SOURCES[1],
    )


def test_sanma_honba_value() -> AuditItem:
    game = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
    game["round_state"]["honba"] = 2

    assert full_honba_value(game, is_tsumo=False) == 400, "三麻荣和本场棒不是每本场 200 点"
    assert full_honba_value(game, is_tsumo=True) == 400, "三麻自摸责任支付本场棒不是每本场 200 点"

    return ok(
        "sanma_honba_value",
        "三麻本场棒每本场 200 点",
        "三麻荣和与责任支付中的完整本场棒都按雀魂三麻规则每本场 200 点计算。",
        SOURCES[0],
    )


def test_sanma_no_chi() -> AuditItem:
    import app.engine as engine

    original_can_ron = engine.can_ron_on_last_discard
    try:
        engine.can_ron_on_last_discard = lambda game, seat, ignore_passed=False: (False, None)
        game = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
        rs = game["round_state"]
        rs["phase"] = "REACTION"
        rs["last_discard"] = {"seat": 0, "tile": 0}
        rs["reaction_passed"] = [False] * 3
        rs["hands"][1] = sorted([4, 8] + rs["hands"][1][2:])
        actions = build_reaction_actions(game, 1)
        assert all(action.type != "chi" for action in actions), "三麻仍然出现吃牌动作"
    finally:
        engine.can_ron_on_last_discard = original_can_ron

    return ok(
        "sanma_no_chi",
        "三麻不可吃",
        "三麻反应动作中不会生成吃牌。",
        SOURCES[0],
    )


def test_sanma_dead_wall_and_no_north_round() -> AuditItem:
    game = new_game("审计", "3P", "SOUTH", [1, 2], enable_koyaku=False)
    rs = game["round_state"]
    assert len(rs["rinshan_tiles"]) == 8, "三麻岭上牌不是 8 张"
    assert game["max_rounds"] == 9, "三麻南风战最大局数不应超过西 3 局"

    seen_winds = set()
    for cursor in range(game["max_rounds"]):
        snapshot = copy.deepcopy(game)
        snapshot["round_cursor"] = cursor
        round_state = build_round(snapshot)
        seen_winds.add(round_state["prevalent_wind"])
    assert "W" in seen_winds, "南风战延长局未进入西场"
    game_4p = new_game("审计", "4P", "SOUTH", [1, 2, 3], enable_koyaku=False)
    seen_4p_winds = set()
    for cursor in range(game_4p["max_rounds"]):
        snapshot = copy.deepcopy(game_4p)
        snapshot["round_cursor"] = cursor
        seen_4p_winds.add(build_round(snapshot)["prevalent_wind"])
    assert "W" in seen_4p_winds and "N" not in seen_4p_winds, "四麻南风战延长场风不符合西入范围"
    assert seen_winds <= {"E", "S", "W"}, "当前实现会进入北场"

    return ok(
        "sanma_round_structure",
        "三麻牌山与场风结构",
        "三麻使用 8 张岭上牌，延长战最多进入西场，不进入北场。",
        SOURCES[0],
    )


def test_sanma_one_man_indicator_scores_nine_man() -> AuditItem:
    adapted_indicator = scoring_indicator_tile_id(0, mode="3P")
    assert adapted_indicator // 4 == 7, "三麻 1万宝牌指示牌未适配为 9万宝牌"
    assert scoring_indicator_tile_id(8 * 4, mode="3P") // 4 == 8, "三麻 9万指示牌不应被错误改写"

    return ok(
        "sanma_1m_dora_indicator",
        "三麻 1万指示牌指向 9万",
        "三麻移除 2-8 万后，后端传给计分库的 1万指示牌会适配成虚拟 8万指示牌，从而正确计为 9万宝牌。",
        SOURCES[1],
    )


def test_sanma_effective_tiles_exclude_removed_manzu() -> AuditItem:
    game = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
    removed = set(range(1, 8))
    legal_types = set(legal_tile_types_for_mode("3P"))
    assert not (legal_types & removed), "三麻合法牌型仍包含 2-8 万"

    seat = 0
    hand = [0, 3, 32, 36, 40, 44, 72, 76, 80, 84, 108, 112, 116, 120]
    _ukeire, good_tiles = effective_tiles_after_discard(game, seat, hand, 120)
    good_types = {item["type"] for item in good_tiles}
    assert not (good_types & removed), "三麻有效进张不应出现 2-8 万"

    return ok(
        "sanma_effective_tiles_filter",
        "三麻进张排除 2-8 万",
        "AI 进张与听牌提示只枚举三麻真实存在的牌型，避免把 2-8 万算作有效牌。",
        SOURCES[0],
    )


def test_rust_core_bridge_consistency() -> AuditItem:
    if not rust_core.is_available():
        return ok(
            "rust_core_bridge",
            "Rust 底层桥接",
            "未检测到 Rust 动态库，系统会自动回退到 Python 逻辑，不影响启动。",
            SOURCES[0],
        )

    fixtures = [
        [0, 1],
        [0, 1, 4, 5, 8, 9, 12, 13, 16, 17, 20, 21, 24],
        [0, 1, 2, 4, 8, 12, 36, 40, 44, 72, 76, 80, 108, 109],
        [0, 32, 36, 68, 72, 104, 108, 112, 116, 120, 124, 128, 132],
        [0, 3, 32, 36, 40, 44, 72, 76, 80, 84, 108, 112, 116, 120],
    ]
    python_shanten = Shanten()
    for tiles in fixtures:
        python_counts = TilesConverter.to_34_array(tiles)
        rust_counts = rust_core.to_34_array(tiles)
        assert rust_counts == python_counts, f"Rust 34 计数与 Python 不一致: {tiles}"
        assert rust_core.shanten_of_tiles(tiles) == python_shanten.calculate_shanten(python_counts), (
            f"Rust 向听与 Python 不一致: {tiles}"
        )

    hand = [0, 3, 32, 36, 40, 44, 72, 76, 80, 84, 108, 112, 116, 120]
    counts = rust_core.to_34_array(hand)
    assert counts is not None, "Rust 计数失败"
    base_shanten = rust_core.shanten_from_counts(counts)
    rust_effective = rust_core.effective_tiles_after_discard("3P", hand, 120, counts, base_shanten)
    assert rust_effective is not None, "Rust 进张计算失败"
    _ukeire, good_tiles = rust_effective
    assert not ({item["type"] for item in good_tiles} & set(range(1, 8))), "Rust 三麻进张不应包含 2-8 万"
    rust_draws = rust_core.draw_tiles_from_counts("3P", counts, counts, None)
    assert rust_draws is not None, "Rust 摸牌候选计算失败"
    _remaining, draw_tiles = rust_draws
    assert not ({item["type"] for item in draw_tiles} & set(range(1, 8))), "Rust 三麻摸牌候选不应包含 2-8 万"

    rust_kuikae = kuikae_forbidden_tile_types("chi", 0, [4, 8])
    rust_chi = chi_candidates([0, 4, 12, 16], 8)
    original_kuikae = rust_core.kuikae_forbidden_tile_types
    original_chi = rust_core.chi_candidates
    try:
        rust_core.kuikae_forbidden_tile_types = lambda *args, **kwargs: None
        rust_core.chi_candidates = lambda *args, **kwargs: None
        python_kuikae = kuikae_forbidden_tile_types("chi", 0, [4, 8])
        python_chi = chi_candidates([0, 4, 12, 16], 8)
    finally:
        rust_core.kuikae_forbidden_tile_types = original_kuikae
        rust_core.chi_candidates = original_chi
    assert rust_kuikae == python_kuikae, "Rust kuikae bridge changed Python fallback behavior"
    assert rust_chi == python_chi, "Rust chi bridge changed Python fallback behavior"

    visible_game = new_game("audit", "3P", "EAST", [1, 2], enable_koyaku=False)
    rust_visible_counts = visible_tile_type_counts(visible_game, 0)
    original_visible_counts = rust_core.visible_counts_from_tiles
    try:
        rust_core.visible_counts_from_tiles = lambda *args, **kwargs: None
        python_visible_counts = visible_tile_type_counts(visible_game, 0)
    finally:
        rust_core.visible_counts_from_tiles = original_visible_counts
    assert rust_visible_counts == python_visible_counts, "Rust visible tile counts changed Python fallback behavior"

    rust_tile_bonus = tile_value_bonus(visible_game, 0, visible_game["round_state"]["hands"][0][0])
    original_tile_value_bonus = rust_core.tile_value_bonus
    try:
        rust_core.tile_value_bonus = lambda *args, **kwargs: None
        python_tile_bonus = tile_value_bonus(visible_game, 0, visible_game["round_state"]["hands"][0][0])
    finally:
        rust_core.tile_value_bonus = original_tile_value_bonus
    assert rust_tile_bonus == python_tile_bonus, "Rust tile value bonus changed Python fallback behavior"

    tile_helper_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False, aka_dora_count=4)
    rust_tile_helpers = (
        default_aka_dora_count("4P"),
        default_aka_dora_count("3P"),
        normalize_aka_dora_count("4P", "RANKED", 4),
        normalize_aka_dora_count("4P", "FRIEND", 4),
        normalize_aka_dora_count("3P", "FRIEND", 3),
        active_aka_dora_ids(tile_helper_game),
        is_honor(27),
        is_terminal(8),
        is_simple(13),
        legal_tile_types_for_mode("3P"),
        representative_tile_id(4, [17, 18, 19]),
    )
    original_default_aka = rust_core.default_aka_dora_count
    original_normalize_aka = rust_core.normalize_aka_dora_count
    original_active_aka = rust_core.active_aka_dora_ids
    original_is_red = rust_core.is_red_tile
    original_tile_flags = rust_core.tile_flags
    original_legal_types = rust_core.legal_tile_types
    original_representative = rust_core.representative_tile_id
    try:
        rust_core.default_aka_dora_count = lambda *args, **kwargs: None
        rust_core.normalize_aka_dora_count = lambda *args, **kwargs: None
        rust_core.active_aka_dora_ids = lambda *args, **kwargs: None
        rust_core.is_red_tile = lambda *args, **kwargs: None
        rust_core.tile_flags = lambda *args, **kwargs: None
        rust_core.legal_tile_types = lambda *args, **kwargs: None
        rust_core.representative_tile_id = lambda *args, **kwargs: None
        python_tile_helpers = (
            default_aka_dora_count("4P"),
            default_aka_dora_count("3P"),
            normalize_aka_dora_count("4P", "RANKED", 4),
            normalize_aka_dora_count("4P", "FRIEND", 4),
            normalize_aka_dora_count("3P", "FRIEND", 3),
            active_aka_dora_ids(tile_helper_game),
            is_honor(27),
            is_terminal(8),
            is_simple(13),
            legal_tile_types_for_mode("3P"),
            representative_tile_id(4, [17, 18, 19]),
        )
    finally:
        rust_core.default_aka_dora_count = original_default_aka
        rust_core.normalize_aka_dora_count = original_normalize_aka
        rust_core.active_aka_dora_ids = original_active_aka
        rust_core.is_red_tile = original_is_red
        rust_core.tile_flags = original_tile_flags
        rust_core.legal_tile_types = original_legal_types
        rust_core.representative_tile_id = original_representative
    assert rust_tile_helpers == python_tile_helpers, "Rust tile helper functions changed Python fallback behavior"

    terminal_tiles = [0, 1, 32, 108, 109, 124]
    rust_terminal_types = unique_terminal_honor_types(terminal_tiles)
    original_terminal_types = rust_core.unique_terminal_honor_types
    try:
        rust_core.unique_terminal_honor_types = lambda *args, **kwargs: None
        python_terminal_types = unique_terminal_honor_types(terminal_tiles)
    finally:
        rust_core.unique_terminal_honor_types = original_terminal_types
    assert rust_terminal_types == python_terminal_types, "Rust terminal/honor type extraction changed Python fallback behavior"

    scoring_game = new_game("audit", "3P", "EAST", [1, 2], enable_koyaku=True)
    scoring_game["rule_profile"] = "FRIEND"
    scoring_game["minimum_han"] = 4
    scoring_game["sanma_scoring_mode"] = "NORTH_BISECTION"
    scoring_game["round_state"]["honba"] = 2
    scoring_game["round_state"]["dealer_seat"] = 0
    scoring_cost = {"main": 3900, "main_bonus": 0, "additional": 2000, "additional_bonus": 0}
    liability_rust_state = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)["round_state"]
    liability_rust_state["melds"][1] = [
        {"type": "pon", "tiles": [124, 125, 126]},
        {"type": "pon", "tiles": [128, 129, 130]},
        {"type": "pon", "tiles": [132, 133, 134]},
    ]
    register_liability_for_call(liability_rust_state, 1, "pon", 132, 2)
    rust_liability = copy.deepcopy(liability_rust_state["liability_payments"][1])
    liability_eval = {"yakuman_total_han": 13, "yakuman_keys": {"DAISANGEN": 13}}
    liability_context_rust_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    liability_context_rust_game["round_state"]["liability_payments"][1] = copy.deepcopy(rust_liability)
    rust_liability_context = liability_context(liability_context_rust_game, 1, liability_eval)
    local_rust_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=True)
    local_rust_state = local_rust_game["round_state"]
    local_rust_state["current_draw"] = 36
    local_rust_state["current_draw_source"] = "wall"
    local_rust_state["turn_seat"] = 0
    local_rust_state["live_wall"] = []
    local_rust_state["double_riichi"][0] = True
    local_han_rust_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=True)
    local_han_rust_game["round_state"]["last_discard"] = {"seat": 1, "tile": 36, "source": "wall", "riichi": True}
    local_han_rust_game["action_log"] = [
        {"type": "KAN", "seat": 1},
        {"type": "DRAW", "seat": 1},
        {"type": "DISCARD", "seat": 1},
    ]
    rust_local_yaku = (
        local_mangan_yaku_name(local_rust_game, 0, 36, is_tsumo=True),
        local_yakuman_entries(local_rust_game, 0, 36, is_tsumo=True),
        local_han_yaku_entries(local_han_rust_game, 0, 36, is_tsumo=False),
        local_pattern_entries_for_hand(
            [[0, 1, 2], [0, 1, 2], [0, 1, 2], [3, 3, 3], [4, 4, 4], [5, 5, 5]],
            is_open_hand=False,
        ),
    )
    rust_scoring_helpers = (
        round_up_to_100(550),
        score_result_total({"main": 2000, "main_bonus": 300, "additional": 1000, "additional_bonus": 300}),
        full_honba_value(scoring_game, is_tsumo=True),
        minimum_han_satisfied(scoring_game, 1, local_yaku_name="Iipin moyue"),
        tsumo_payment_map(scoring_game, 1, scoring_cost),
        rust_liability,
        rust_liability_context,
        rust_local_yaku,
    )
    original_round_up = rust_core.round_up_to_100
    original_score_total = rust_core.score_result_total
    original_honba = rust_core.full_honba_value
    original_minimum_han = rust_core.minimum_han_satisfied
    original_tsumo_payments = rust_core.tsumo_payment_map
    original_liability_key = rust_core.liability_key_for_call
    original_liability_context = rust_core.liability_context_profile
    original_local_mangan = rust_core.local_mangan_yaku_name
    original_local_yakuman = rust_core.local_yakuman_entries
    original_local_han = rust_core.local_han_yaku_entries
    original_local_pattern = rust_core.local_pattern_entries_for_hand
    try:
        rust_core.round_up_to_100 = lambda *args, **kwargs: None
        rust_core.score_result_total = lambda *args, **kwargs: None
        rust_core.full_honba_value = lambda *args, **kwargs: None
        rust_core.minimum_han_satisfied = lambda *args, **kwargs: None
        rust_core.tsumo_payment_map = lambda *args, **kwargs: None
        rust_core.liability_key_for_call = lambda *args, **kwargs: None
        rust_core.liability_context_profile = lambda *args, **kwargs: None
        rust_core.local_mangan_yaku_name = lambda *args, **kwargs: None
        rust_core.local_yakuman_entries = lambda *args, **kwargs: None
        rust_core.local_han_yaku_entries = lambda *args, **kwargs: None
        rust_core.local_pattern_entries_for_hand = lambda *args, **kwargs: None
        liability_python_state = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)["round_state"]
        liability_python_state["melds"][1] = [
            {"type": "pon", "tiles": [124, 125, 126]},
            {"type": "pon", "tiles": [128, 129, 130]},
            {"type": "pon", "tiles": [132, 133, 134]},
        ]
        register_liability_for_call(liability_python_state, 1, "pon", 132, 2)
        python_liability = copy.deepcopy(liability_python_state["liability_payments"][1])
        liability_context_python_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
        liability_context_python_game["round_state"]["liability_payments"][1] = copy.deepcopy(python_liability)
        python_liability_context = liability_context(liability_context_python_game, 1, liability_eval)
        local_python_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=True)
        local_python_state = local_python_game["round_state"]
        local_python_state["current_draw"] = 36
        local_python_state["current_draw_source"] = "wall"
        local_python_state["turn_seat"] = 0
        local_python_state["live_wall"] = []
        local_python_state["double_riichi"][0] = True
        local_han_python_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=True)
        local_han_python_game["round_state"]["last_discard"] = {"seat": 1, "tile": 36, "source": "wall", "riichi": True}
        local_han_python_game["action_log"] = [
            {"type": "KAN", "seat": 1},
            {"type": "DRAW", "seat": 1},
            {"type": "DISCARD", "seat": 1},
        ]
        python_local_yaku = (
            local_mangan_yaku_name(local_python_game, 0, 36, is_tsumo=True),
            local_yakuman_entries(local_python_game, 0, 36, is_tsumo=True),
            local_han_yaku_entries(local_han_python_game, 0, 36, is_tsumo=False),
            local_pattern_entries_for_hand(
                [[0, 1, 2], [0, 1, 2], [0, 1, 2], [3, 3, 3], [4, 4, 4], [5, 5, 5]],
                is_open_hand=False,
            ),
        )
        python_scoring_helpers = (
            round_up_to_100(550),
            score_result_total({"main": 2000, "main_bonus": 300, "additional": 1000, "additional_bonus": 300}),
            full_honba_value(scoring_game, is_tsumo=True),
            minimum_han_satisfied(scoring_game, 1, local_yaku_name="Iipin moyue"),
            tsumo_payment_map(scoring_game, 1, scoring_cost),
            python_liability,
            python_liability_context,
            python_local_yaku,
        )
    finally:
        rust_core.round_up_to_100 = original_round_up
        rust_core.score_result_total = original_score_total
        rust_core.full_honba_value = original_honba
        rust_core.minimum_han_satisfied = original_minimum_han
        rust_core.tsumo_payment_map = original_tsumo_payments
        rust_core.liability_key_for_call = original_liability_key
        rust_core.liability_context_profile = original_liability_context
        rust_core.local_mangan_yaku_name = original_local_mangan
        rust_core.local_yakuman_entries = original_local_yakuman
        rust_core.local_han_yaku_entries = original_local_han
        rust_core.local_pattern_entries_for_hand = original_local_pattern
    assert rust_scoring_helpers == python_scoring_helpers, "Rust scoring payment helpers changed Python fallback behavior"

    seat_wind_state = new_game("audit", "3P", "EAST", [1, 2], enable_koyaku=False)["round_state"]
    seat_wind_state["dealer_seat"] = 1
    round_rule_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    round_state = round_rule_game["round_state"]
    round_state["discards"][0] = [{"tile": 108, "called": False}]
    round_state["temporary_furiten"][0] = True
    four_wind_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    four_wind_state = four_wind_game["round_state"]
    for seat in range(4):
        four_wind_state["discards"][seat] = [{"tile": 108 + seat, "called": False}]
    four_kan_state = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)["round_state"]
    four_kan_state["kan_count"] = 4
    four_kan_state["melds"][0] = [{"type": "closed_kan", "tiles": [0, 1, 2, 3]}]
    four_kan_state["melds"][2] = [{"type": "open_kan", "tiles": [108, 109, 110, 111]}]
    nagashi_state = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)["round_state"]
    nagashi_state["discards"][0] = [{"tile": 0, "called": False}, {"tile": 32, "called": False}, {"tile": 108, "called": False}]
    nagashi_state["discards"][1] = [{"tile": 4, "called": False}]
    timing_state = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)["round_state"]
    timing_state["current_draw"] = 0
    timing_state["current_draw_source"] = "wall"
    timing_state["turn_seat"] = 0
    timing_state["live_wall"] = []
    houtei_state = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)["round_state"]
    houtei_state["last_discard"] = {"seat": 1, "tile": 0, "source": "wall"}
    houtei_state["last_draw_source"][1] = "wall"
    houtei_state["live_wall"] = []
    chankan_state = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)["round_state"]
    chankan_state["last_discard"] = {"seat": 1, "tile": 0, "source": "kan", "kan_type": "added_kan"}
    renhou_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=True)
    renhou_game["round_state"]["last_discard"] = {"seat": 0, "tile": 0, "source": "wall"}
    nine_game = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    nine_state = nine_game["round_state"]
    nine_state["phase"] = "DISCARD"
    nine_state["turn_seat"] = 0
    nine_state["current_draw"] = 0
    nine_state["hands"][0] = [0, 32, 36, 68, 72, 104, 108, 112, 116]
    end_rule_game = new_game("audit", "4P", "SOUTH", [1, 2, 3], enable_koyaku=False)
    end_rule_game["base_rounds"] = 8
    end_rule_game["round_cursor"] = 7
    end_rule_game["target_score"] = 30000
    end_rule_game["round_state"]["dealer_seat"] = 0
    end_rule_game["round_state"]["round_result"] = {"kind": "TSUMO"}
    end_rule_game["players"][0]["points"] = 32000
    end_rule_game["players"][1]["points"] = 30000
    end_rule_game["players"][2]["points"] = 20000
    end_rule_game["players"][3]["points"] = 18000
    rust_round_helpers = (
        is_furiten(round_state, 0, 27),
        can_double_riichi(round_state, 1),
        seat_wind_label(seat_wind_state, 0),
        evaluate_pending_abortive_draw_after_discard(four_wind_game),
        should_abort_for_four_kans(four_kan_state),
        nagashi_mangan_winners(nagashi_state),
        is_tenhou_state(timing_state, 0, is_tsumo=True),
        is_chiihou_state(timing_state, 1, is_tsumo=True),
        is_haitei_state(timing_state, 0, is_tsumo=True),
        is_houtei_state(houtei_state, is_tsumo=False),
        is_chankan_state(chankan_state, is_tsumo=False),
        is_renhou_state(renhou_game, 1, is_tsumo=False),
        can_abortive_draw_nine_terminals(nine_game, 0),
        is_win_like_round_result(end_rule_game),
        goal_score_reached(end_rule_game),
        should_auto_stop_all_last_dealer(end_rule_game, dealer_continues=True),
    )
    original_is_furiten = rust_core.is_furiten
    original_can_double = rust_core.can_double_riichi
    original_seat_wind = rust_core.seat_wind_code
    original_pending_abort = rust_core.pending_abortive_draw_kind
    original_four_kans = rust_core.should_abort_for_four_kans
    original_nagashi = rust_core.is_nagashi_mangan_candidate
    original_tenhou = rust_core.is_tenhou_state
    original_chiihou = rust_core.is_chiihou_state
    original_haitei = rust_core.is_haitei_state
    original_houtei = rust_core.is_houtei_state
    original_chankan = rust_core.is_chankan_state
    original_renhou = rust_core.is_renhou_state
    original_nine_terminals = rust_core.can_abortive_draw_nine_terminals
    original_win_like = rust_core.is_win_like_round_result
    original_goal_score = rust_core.goal_score_reached
    original_auto_stop = rust_core.should_auto_stop_all_last_dealer
    try:
        rust_core.is_furiten = lambda *args, **kwargs: None
        rust_core.can_double_riichi = lambda *args, **kwargs: None
        rust_core.seat_wind_code = lambda *args, **kwargs: None
        rust_core.pending_abortive_draw_kind = lambda *args, **kwargs: None
        rust_core.should_abort_for_four_kans = lambda *args, **kwargs: None
        rust_core.is_nagashi_mangan_candidate = lambda *args, **kwargs: None
        rust_core.is_tenhou_state = lambda *args, **kwargs: None
        rust_core.is_chiihou_state = lambda *args, **kwargs: None
        rust_core.is_haitei_state = lambda *args, **kwargs: None
        rust_core.is_houtei_state = lambda *args, **kwargs: None
        rust_core.is_chankan_state = lambda *args, **kwargs: None
        rust_core.is_renhou_state = lambda *args, **kwargs: None
        rust_core.can_abortive_draw_nine_terminals = lambda *args, **kwargs: None
        rust_core.is_win_like_round_result = lambda *args, **kwargs: None
        rust_core.goal_score_reached = lambda *args, **kwargs: None
        rust_core.should_auto_stop_all_last_dealer = lambda *args, **kwargs: None
        python_round_helpers = (
            is_furiten(round_state, 0, 27),
            can_double_riichi(round_state, 1),
            seat_wind_label(seat_wind_state, 0),
            evaluate_pending_abortive_draw_after_discard(four_wind_game),
            should_abort_for_four_kans(four_kan_state),
            nagashi_mangan_winners(nagashi_state),
            is_tenhou_state(timing_state, 0, is_tsumo=True),
            is_chiihou_state(timing_state, 1, is_tsumo=True),
            is_haitei_state(timing_state, 0, is_tsumo=True),
            is_houtei_state(houtei_state, is_tsumo=False),
            is_chankan_state(chankan_state, is_tsumo=False),
            is_renhou_state(renhou_game, 1, is_tsumo=False),
            can_abortive_draw_nine_terminals(nine_game, 0),
            is_win_like_round_result(end_rule_game),
            goal_score_reached(end_rule_game),
            should_auto_stop_all_last_dealer(end_rule_game, dealer_continues=True),
        )
    finally:
        rust_core.is_furiten = original_is_furiten
        rust_core.can_double_riichi = original_can_double
        rust_core.seat_wind_code = original_seat_wind
        rust_core.pending_abortive_draw_kind = original_pending_abort
        rust_core.should_abort_for_four_kans = original_four_kans
        rust_core.is_nagashi_mangan_candidate = original_nagashi
        rust_core.is_tenhou_state = original_tenhou
        rust_core.is_chiihou_state = original_chiihou
        rust_core.is_haitei_state = original_haitei
        rust_core.is_houtei_state = original_houtei
        rust_core.is_chankan_state = original_chankan
        rust_core.is_renhou_state = original_renhou
        rust_core.can_abortive_draw_nine_terminals = original_nine_terminals
        rust_core.is_win_like_round_result = original_win_like
        rust_core.goal_score_reached = original_goal_score
        rust_core.should_auto_stop_all_last_dealer = original_auto_stop
    assert rust_round_helpers == python_round_helpers, "Rust round-state rule helpers changed Python fallback behavior"

    route_game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    route_seat = 0
    route_game["round_state"]["hands"][route_seat] = [36, 37, 40, 41, 44, 45, 48, 49, 52, 53, 56, 57, 60]
    shanten_value = rust_core.shanten_of_tiles(route_game["round_state"]["hands"][route_seat])
    assert shanten_value is not None, "Rust 路线测试向听计算失败"
    rust_routes = hand_route_profile(
        route_game,
        route_seat,
        route_game["round_state"]["hands"][route_seat],
        shanten_value=shanten_value,
    )
    original_route_profile = rust_core.hand_route_profile
    try:
        rust_core.hand_route_profile = lambda *args, **kwargs: None
        python_routes = hand_route_profile(
            route_game,
            route_seat,
            route_game["round_state"]["hands"][route_seat],
            shanten_value=shanten_value,
        )
    finally:
        rust_core.hand_route_profile = original_route_profile
    assert rust_routes == python_routes, "Rust 手牌路线分析与 Python 回退不一致"

    profile_game = new_game("审计", "4P", "EAST", [1, 2, 3], enable_koyaku=False)
    rust_profiles = sorted_discard_profiles(profile_game, 0, 3, deep_search=False)
    original_discard_metrics = rust_core.discard_metrics_from_counts
    try:
        rust_core.discard_metrics_from_counts = lambda *args, **kwargs: None
        python_profiles = sorted_discard_profiles(profile_game, 0, 3, deep_search=False)
    finally:
        rust_core.discard_metrics_from_counts = original_discard_metrics
    assert len(rust_profiles) == len(python_profiles), "Rust 批量弃牌预计算改变了候选数量"
    for rust_item, python_item in zip(rust_profiles, python_profiles):
        for key in ("tile_id", "shanten", "ukeire", "waits", "shape_ev", "final_ev", "score"):
            assert rust_item.get(key) == python_item.get(key), f"Rust 批量弃牌预计算改变了 {key}"

    return ok(
        "rust_core_bridge",
        "Rust 底层桥接",
        "Rust 牌计数、向听、进张枚举、摸牌候选过滤、手牌路线分析与候选弃牌批量预计算已和 Python 逻辑保持一致。",
        SOURCES[0],
    )


def test_late_round_ai_search_is_compressed() -> AuditItem:
    game = new_game("审计", "4P", "EAST", [3, 3, 3], enable_koyaku=False)
    round_state = game["round_state"]
    round_state["riichi"][1] = True
    round_state["riichi"][2] = True
    round_state["live_wall"] = round_state["live_wall"][:18]

    config = alpha_search_config(game, 0)
    assert config["depth"] <= 1, "晚巡深搜仍使用多层搜索，可能导致打牌延迟"
    assert config["draw_beam"] <= 2, "晚巡摸牌 beam 未压缩"
    assert config["discard_beam"] <= 1, "晚巡弃牌 beam 未压缩"

    return ok(
        "late_round_ai_search_compression",
        "晚巡 AI 搜索压缩",
        "晚巡或高压局面会自动降低 Alpha 风格前瞻深度和 beam，避免越到后巡越卡。",
        SOURCES[0],
    )


def test_kita_chain_rules() -> AuditItem:
    import app.engine as engine

    game = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
    rs = game["round_state"]
    ensure_round_state_defaults(rs)
    seat = rs["dealer_seat"]
    rs["ippatsu"][seat] = True
    rs["pending_abortive_draw"] = {"kind": "KYUUSHU_KYUUHAI", "headline": "九种九牌流局"}
    north_tile = 120
    rs["hands"][seat][0] = north_tile
    future_seat = (seat + 1) % rs["player_count"]
    assert can_double_riichi(rs, future_seat) is True, "审计前提失败：拔北前应仍可两立直"
    engine.begin_kita_reaction(game, seat, north_tile)
    assert can_double_riichi(rs, future_seat) is False, "拔北未打断之后玩家的两立直资格"
    assert rs["pending_abortive_draw"] is None, "拔北未打断九种九牌"
    engine.resolve_pending_kita(game)
    assert rs["ippatsu"][seat] is False, "拔北未打断一发"
    assert is_chankan_state({"last_discard": {"seat": seat, "tile": north_tile, "source": "kita"}}, is_tsumo=False) is False, "拔北被误算成抢杠"

    return ok(
        "kita_interrupt_rules",
        "拔北打断链",
        "拔北会打断后续两立直资格、九种九牌与一发，且不会被当作抢杠。",
        SOURCES[0],
    )


def test_riichi_north_draw_can_kita_in_sanma() -> AuditItem:
    game = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
    rs = game["round_state"]
    seat = 0
    north_tile = 120
    rs["phase"] = "DISCARD"
    rs["turn_seat"] = seat
    rs["riichi"][seat] = True
    rs["current_draw"] = north_tile
    rs["hands"][seat] = [0, 3, 32, 36, 40, 44, 72, 76, 80, 84, 108, 112, 116, north_tile]

    actions = build_turn_actions(game, seat)
    assert any(action.type == "kita" for action in actions), "三麻立直后摸北仍应出现拔北动作"
    assert forced_riichi_tsumogiri_action(game, seat, actions) is None, "立直后摸北不应被自动摸切吞掉拔北选择"

    rs["current_draw"] = 72
    rs["hands"][seat] = [0, 3, 32, 36, 40, 44, 72, 76, 80, 84, 108, 112, 116, north_tile]
    old_north_actions = build_turn_actions(game, seat)
    assert all(action.type != "kita" for action in old_north_actions), "立直后不能拔出非本巡摸到的旧北"

    return ok(
        "riichi_north_draw_can_kita",
        "三麻立直后摸北可拔北",
        "立直后的自动摸切会为自摸、合法暗杠和拔北让路，避免把摸到的北直接强制打出。",
        SOURCES[0],
    )


def test_kita_not_houtei_or_renhou() -> AuditItem:
    round_state = {
        "player_count": 3,
        "last_discard": {"seat": 0, "tile": 120, "source": "kita"},
        "last_draw_source": ["wall", None, None],
        "live_wall": [],
    }
    ensure_round_state_defaults(round_state)
    assert is_houtei_state(round_state, is_tsumo=False) is False, "拔北被误算成河底捞鱼"

    round_state["last_discard"] = {"seat": 0, "tile": 120, "source": "discard"}
    assert is_houtei_state(round_state, is_tsumo=False) is True, "最后一张正常河牌未算入河底"

    game = {
        "koyaku_enabled": True,
        "round_state": {
            "player_count": 3,
            "dealer_seat": 0,
            "last_discard": {"seat": 0, "tile": 120, "source": "kita"},
            "last_draw_source": [None, None, None],
            "discards": [[], [], []],
            "melds": [[], [], []],
        },
    }
    ensure_round_state_defaults(game["round_state"])
    assert is_renhou_state(game, 1, is_tsumo=False) is False, "拔北被误算成人和"

    return ok(
        "kita_not_houtei_or_renhou",
        "拔北不算河底/人和",
        "拔北可以被荣和，但不会额外触发河底捞鱼或人和。",
        SOURCES[3],
    )


def test_kita_ron_does_not_create_new_furiten() -> AuditItem:
    game = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
    rs = game["round_state"]
    ensure_round_state_defaults(rs)
    winner = 1
    rs["phase"] = "REACTION"
    rs["last_discard"] = {"seat": 0, "tile": 120, "source": "kita"}
    rs["hands"][winner] = [0, 1, 2, 40, 44, 48, 76, 80, 84, 96, 100, 104, 121]
    rs["riichi"][winner] = True
    can_ron, _ = can_ron_on_last_discard(game, winner)
    assert can_ron is True, "可役牌型不能荣和别人拔北的北"

    rs["discards"][winner].append({"tile": 122, "riichi": False, "called": False})
    can_ron_after_own_north, _ = can_ron_on_last_discard(game, winner)
    assert can_ron_after_own_north is False, "自己正常打过北后，别人拔北不应豁免舍牌振听"

    rs["discards"][winner].clear()
    rs["reaction_passed"][winner] = True
    apply_forced_furiten_for_current_discard(game)
    assert rs["riichi_furiten"][winner] is False, "错过别人拔北不应新产生立直振听"
    return ok(
        "kita_ron_no_new_furiten",
        "抢北不新增振听",
        "自己正常打过北仍会造成舍牌振听；但别人拔北这个事件本身不会因为见逃而新增同巡/立直振听。",
        SOURCES[0],
    )


def test_abortive_draws_4p_only() -> AuditItem:
    three_p = {
        "player_count": 3,
        "discards": [[{"tile": 27 * 4}], [{"tile": 27 * 4}], [{"tile": 27 * 4}]],
        "riichi": [True, True, True],
        "melds": [[], [], []],
    }
    ensure_round_state_defaults(three_p)
    assert evaluate_pending_abortive_draw_after_discard({"round_state": three_p}) is None, "三麻不应触发四风连打/四家立直"

    four_p = {
        "player_count": 4,
        "discards": [[{"tile": 27 * 4}], [{"tile": 27 * 4}], [{"tile": 27 * 4}], [{"tile": 27 * 4}]],
        "riichi": [False, False, False, False],
        "melds": [[], [], [], []],
    }
    ensure_round_state_defaults(four_p)
    pending = evaluate_pending_abortive_draw_after_discard({"round_state": four_p})
    assert pending is not None and pending["kind"] == "SUUFON_RENDA", "四麻四风连打未触发"

    return ok(
        "abortive_draw_scope",
        "途中流局作用范围",
        "四风连打/四家立直只在四麻触发，三麻不会误触发。",
        SOURCES[1],
    )


def test_pao_only_daisangen_daisuushii() -> AuditItem:
    round_state = {
        "player_count": 4,
        "liability_payments": [{} for _ in range(4)],
        "melds": [[], [], [], []],
    }
    ensure_round_state_defaults(round_state)
    seat = 1
    round_state["melds"][seat] = [
        {"type": "open_kan", "tiles": [0, 1, 2, 3]},
        {"type": "closed_kan", "tiles": [4, 5, 6, 7]},
        {"type": "added_kan", "tiles": [8, 9, 10, 11]},
        {"type": "open_kan", "tiles": [12, 13, 14, 15]},
    ]
    register_liability_for_call(round_state, seat, "open_kan", 12, 2)
    assert "SUUKANTSU" not in round_state["liability_payments"][seat], "四杠子不应触发雀魂包牌"
    return ok(
        "pao_scope",
        "包牌范围",
        "责任支付只覆盖大三元/大四喜，不覆盖四杠子。",
        SOURCES[1],
    )


def test_local_yaku_completeness() -> AuditItem:
    engine_text = "\n".join(path.read_text(encoding="utf-8") for path in ENGINE_MODULE_PATHS if path.exists())
    table_text = TABLE_PATH.read_text(encoding="utf-8")
    missing_engine = sorted(
        name
        for name in EXPECTED_LOCAL_YAKU
        if name not in engine_text and ENGINE_SUPPORT_MARKERS.get(name, "") not in engine_text
    )
    missing_ui = sorted(name for name in EXPECTED_LOCAL_YAKU if name not in table_text)
    assert not missing_engine, f"后端缺少古役：{', '.join(missing_engine)}"
    assert not missing_ui, f"前端缺少古役中文映射：{', '.join(missing_ui)}"
    return ok(
        "local_yaku_completeness",
        "雀魂古役房役种表",
        f"当前已覆盖 {len(EXPECTED_LOCAL_YAKU)} 项雀魂古役房役种，并具备前端中文映射。",
        SOURCES[2],
    )


def detect_missing_sanma_scoring_toggle() -> AuditItem:
    fields = set(CreateGameRequest.model_fields)
    if "sanma_scoring_mode" in fields:
        game = new_game(
            "审计",
            "3P",
            "EAST",
            [1, 2],
            enable_koyaku=False,
            sanma_scoring="NORTH_BISECTION",
            rule_profile_name="FRIEND",
        )
        round_state = game["round_state"]
        dealer = round_state["dealer_seat"]
        child = (dealer + 1) % 3

        dealer_cost = {"main": 500, "main_bonus": 0, "additional": 0, "additional_bonus": 0}
        dealer_map = tsumo_payment_map(game, dealer, dealer_cost)
        assert sorted(dealer_map.values()) == [800, 800], "North-Bisection 下庄家 500 all 应变为 800 all"

        child_cost = {"main": 500, "main_bonus": 0, "additional": 300, "additional_bonus": 0}
        child_map = tsumo_payment_map(game, child, child_cost)
        dealer_payment = child_map[dealer]
        other_child_payment = next(value for loser, value in child_map.items() if loser != dealer)
        assert dealer_payment == 700 and other_child_payment == 500, "North-Bisection 下闲家 300/500 应变为 500/700"

        return ok(
            "feature_sanma_scoring_mode",
            "三麻计分模式切换",
            "已支持 Tsumo-loss / North-Bisection 切换，且支付结果与雀魂友人场口径一致。",
            SOURCES[1],
        )
    return missing(
        "feature_sanma_scoring_mode",
        "缺少三麻友人场 North-Bisection 计分切换",
        "雀魂友人场支持在 Tsumo-loss 与 North-Bisection 间切换；当前建局接口没有该选项，系统只支持默认段位规则的 Tsumo-loss。",
        SOURCES[1],
    )


def detect_missing_rule_profiles() -> AuditItem:
    fields = set(CreateGameRequest.model_fields)
    if "rule_profile" in fields:
        ranked = new_game(
            "审计",
            "3P",
            "EAST",
            [1, 2],
            enable_koyaku=True,
            sanma_scoring="NORTH_BISECTION",
            rule_profile_name="RANKED",
        )
        assert ranked["rule_profile"] == "RANKED", "段位档位未写入"
        assert ranked["koyaku_enabled"] is False, "段位档位不应允许古役"
        assert ranked["sanma_scoring_mode"] == "TSUMO_LOSS", "段位档位应锁定 Tsumo-loss"

        friend = new_game(
            "审计",
            "3P",
            "EAST",
            [1, 2],
            enable_koyaku=False,
            sanma_scoring="NORTH_BISECTION",
            rule_profile_name="FRIEND",
        )
        assert friend["rule_profile"] == "FRIEND", "友人场档位未写入"
        assert friend["sanma_scoring_mode"] == "NORTH_BISECTION", "友人场档位未保留 North-Bisection"

        koyaku = new_game(
            "审计",
            "4P",
            "EAST",
            [1, 2, 3],
            enable_koyaku=False,
            rule_profile_name="KOYAKU",
        )
        assert koyaku["rule_profile"] == "KOYAKU", "古役房档位未写入"
        assert koyaku["koyaku_enabled"] is True, "古役房档位应自动开启古役"

        return ok(
            "feature_rule_profiles",
            "规则档位/自定义规则",
            "已具备雀魂段位默认 / 友人场 / 古役房三种规则档位，并会自动约束对应默认规则。",
            SOURCES[0],
        )
    return missing(
        "feature_rule_profiles",
        "缺少雀魂规则档位与自定义规则矩阵",
        "当前建局只支持 mode / round_length / ai_levels / enable_koyaku，缺少友人场/比赛场那类规则档位和成组自定义规则入口。",
        SOURCES[0],
    )


def test_minimum_han_requirement() -> AuditItem:
    import app.engine as engine
    import app.engine_scoring as engine_scoring

    fields = set(CreateGameRequest.model_fields)
    assert "minimum_han" in fields, "create-game request is missing minimum_han"
    assert CreateGameRequest(minimum_han=4).minimum_han == 4, "request model rejected minimum_han=4"

    ranked = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False, rule_profile_name="RANKED", minimum_han=4, aka_dora_count=0)
    assert ranked["minimum_han"] == 1, "ranked profile should lock minimum_han to 1"

    friend = new_game("audit", "4P", "EAST", [1, 2, 3], enable_koyaku=False, rule_profile_name="FRIEND", minimum_han=2, aka_dora_count=0)
    assert friend["minimum_han"] == 2, "friend profile did not keep custom minimum_han"
    assert friend["public_state"].get("minimum_han") == 2, "public state did not expose minimum_han"

    class FakeYaku:
        def __init__(self, name: str, han: int, *, is_yakuman: bool = False) -> None:
            self.name = name
            self.han_open = han
            self.han_closed = han
            self.is_yakuman = is_yakuman

    class FakeResult:
        def __init__(self, han: int, yaku: list[FakeYaku], fu: int = 30) -> None:
            self.error = False
            self.han = han
            self.yaku = yaku
            self.fu = fu
            self.fu_details = []

    original_estimate = engine_scoring.estimate_hand_value_for_layout
    try:
        engine_scoring.estimate_hand_value_for_layout = lambda *args, **kwargs: FakeResult(1, [FakeYaku("Riichi", 1)])
        one_han = engine.evaluate_hand(friend, 0, friend["round_state"]["hands"][0][-1], is_tsumo=True)
        assert one_han is None, "2-han minimum still allowed a 1-han win"

        engine_scoring.estimate_hand_value_for_layout = lambda *args, **kwargs: FakeResult(2, [FakeYaku("Riichi", 1), FakeYaku("Dora", 1)])
        two_han = engine.evaluate_hand(friend, 0, friend["round_state"]["hands"][0][-1], is_tsumo=True)
        assert two_han is not None, "2-han minimum incorrectly blocked a 2-han win"
    finally:
        engine_scoring.estimate_hand_value_for_layout = original_estimate

    return ok(
        "minimum_han_requirement",
        "Minimum Han Requirement",
        "Supports Mahjong Soul style 1/2/4 minimum han settings and blocks wins that do not meet the configured threshold.",
        SOURCES[0],
    )


def detect_minimum_han_toggle() -> AuditItem:
    table_text = TABLE_PATH.read_text(encoding="utf-8")
    assert "minimum_han" in table_text, "frontend is missing minimum_han wiring"
    assert "setMinimumHan" in table_text, "frontend is missing minimum_han controls"
    return ok(
        "feature_minimum_han_toggle",
        "Minimum Han Toggle",
        "The setup UI exposes 1/2/4 minimum han options and keeps ranked mode locked to 1 han.",
        SOURCES[0],
    )


def test_aka_dora_count_options() -> AuditItem:
    import app.engine as engine

    fields = set(CreateGameRequest.model_fields)
    assert "aka_dora_count" in fields, "create-game request is missing aka_dora_count"
    assert CreateGameRequest(aka_dora_count=4).aka_dora_count == 4, "request model rejected aka_dora_count=4"

    ranked_4p = new_game("audit", "4P", "EAST", [1, 2, 3], rule_profile_name="RANKED", aka_dora_count=0)
    ranked_3p = new_game("audit", "3P", "EAST", [1, 2], rule_profile_name="RANKED", aka_dora_count=0)
    assert ranked_4p["aka_dora_count"] == 3, "4P ranked should lock aka dora to default 3"
    assert ranked_3p["aka_dora_count"] == 2, "3P ranked should lock aka dora to default 2"

    no_aka = new_game("audit", "4P", "EAST", [1, 2, 3], rule_profile_name="FRIEND", aka_dora_count=0)
    assert no_aka["aka_dora_count"] == 0, "friend profile did not keep aka_dora_count=0"
    assert no_aka["public_state"].get("aka_dora_count") == 0, "public state did not expose aka_dora_count"
    assert engine.tile_label(52, no_aka) == "5p", "disabled red five should render as normal 5p"
    assert engine.is_red(52, no_aka) is False, "disabled red five still counted as aka"

    four_aka = new_game("audit", "4P", "EAST", [1, 2, 3], rule_profile_name="FRIEND", aka_dora_count=4)
    assert engine.tile_label(53, four_aka) == "0p", "4-red setting should enable the second red 5p"

    rs = four_aka["round_state"]
    seat = 0
    rs["hands"][seat] = [4, 8, 12, 40, 44, 48, 52, 53, 76, 80, 84, 92, 96, 100]
    rs["melds"][seat] = []
    rs["discards"][1].append({"tile": 132, "riichi": False, "called": False})
    result = engine.evaluate_hand(four_aka, seat, 53, is_tsumo=True)
    assert result is not None, "audit hand should be a valid tanyao tsumo shape"
    assert result["han"] >= 3, "4-red setting did not add both red 5p as aka dora"
    assert any("Aka Dora 2" in yaku for yaku in result["yaku"]), "result yaku list did not expose two aka dora"

    return ok(
        "aka_dora_count_options",
        "Red Five Count Options",
        "Friend-room style red-five settings are now configurable: none, 3P two reds, 4P three reds, and 4P four reds.",
        SOURCES[0],
    )


def detect_aka_dora_count_toggle() -> AuditItem:
    table_text = TABLE_PATH.read_text(encoding="utf-8")
    assert "aka_dora_count" in table_text, "frontend is missing aka_dora_count wiring"
    assert "setAkaDoraCount" in table_text, "frontend is missing aka dora controls"
    return ok(
        "feature_aka_dora_count_toggle",
        "Red Five Count Toggle",
        "The setup UI exposes Mahjong Soul style red-five count options and keeps ranked mode on the default count.",
        SOURCES[0],
    )


CHECKS: list[Callable[[], AuditItem]] = [
    test_ranked_starting_points,
    test_target_scores,
    test_ranked_uma_oka_settlement,
    test_multi_ron_head_bump_disabled,
    test_multi_ron_mahjong_soul_dealer_keeps,
    test_riichi_sticks_carry_on_draws,
    test_nagashi_mangan_keeps_riichi_sticks,
    test_open_meld_tenpai_shape_counts_melds,
    test_open_meld_missed_ron_sets_temporary_furiten,
    test_equivalent_duplicate_tile_action_normalized,
    test_double_riichi_kept_when_declaration_discard_called,
    test_open_kan_dora_reveals_after_safe_discard,
    test_four_kan_abort_waits_for_post_kan_discard,
    test_last_discard_allows_only_ron_reaction,
    test_no_kan_on_haitei_draw,
    test_extra_round_draw_reaching_target_ends_game,
    test_sanma_tsumo_loss,
    test_sanma_honba_value,
    test_sanma_no_chi,
    test_sanma_dead_wall_and_no_north_round,
    test_sanma_one_man_indicator_scores_nine_man,
    test_sanma_effective_tiles_exclude_removed_manzu,
    test_rust_core_bridge_consistency,
    test_late_round_ai_search_is_compressed,
    test_kita_chain_rules,
    test_riichi_north_draw_can_kita_in_sanma,
    test_kita_not_houtei_or_renhou,
    test_kita_ron_does_not_create_new_furiten,
    test_abortive_draws_4p_only,
    test_pao_only_daisangen_daisuushii,
    test_local_yaku_completeness,
    detect_missing_sanma_scoring_toggle,
    detect_missing_rule_profiles,
    test_minimum_han_requirement,
    detect_minimum_han_toggle,
    test_aka_dora_count_options,
    detect_aka_dora_count_toggle,
]


def build_report(items: list[AuditItem]) -> dict[str, Any]:
    passed = [item for item in items if item.status == "PASS"]
    missing_items = [item for item in items if item.status == "MISSING"]
    failed_items = [item for item in items if item.status == "FAIL"]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": SOURCES,
        "summary": {
            "passed": len(passed),
            "missing": len(missing_items),
            "failed": len(failed_items),
        },
        "passed": [asdict(item) for item in passed],
        "missing": [asdict(item) for item in missing_items],
        "failed": [asdict(item) for item in failed_items],
    }


def main() -> int:
    results = [run_check(check) for check in CHECKS]
    report = build_report(results)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Mahjong Soul Rule Audit ===")
    print(f"PASS: {report['summary']['passed']}")
    print(f"MISSING: {report['summary']['missing']}")
    print(f"FAIL: {report['summary']['failed']}")
    print()
    if report["missing"]:
        print("[缺失项]")
        for item in report["missing"]:
            print(f"- {item['title']}: {item['detail']}")
        print()
    if report["failed"]:
        print("[失败项]")
        for item in report["failed"]:
            print(f"- {item['title']}: {item['detail']}")
        print()
    print(f"报告已写入: {OUTPUT_PATH}")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
