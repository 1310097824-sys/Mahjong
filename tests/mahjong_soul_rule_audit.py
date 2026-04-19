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

from app.config import settings
from app.engine import (
    HEAD_BUMP_ENABLED,
    TARGET_POINTS,
    build_reaction_actions,
    build_ron_winners,
    build_round,
    build_wall,
    can_double_riichi,
    evaluate_pending_abortive_draw_after_discard,
    ensure_game_defaults,
    ensure_round_state_defaults,
    is_chankan_state,
    is_houtei_state,
    is_renhou_state,
    new_game,
    register_liability_for_call,
    settle_ron,
    tsumo_payment_map,
)
from app.main import CreateGameRequest


ENGINE_PATH = ROOT / "app" / "engine.py"
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
    assert seen_winds <= {"E", "S", "W"}, "当前实现会进入北场"

    return ok(
        "sanma_round_structure",
        "三麻牌山与场风结构",
        "三麻使用 8 张岭上牌，延长战最多进入西场，不进入北场。",
        SOURCES[0],
    )


def test_kita_chain_rules() -> AuditItem:
    import app.engine as engine

    game = new_game("审计", "3P", "EAST", [1, 2], enable_koyaku=False)
    rs = game["round_state"]
    ensure_round_state_defaults(rs)
    seat = rs["dealer_seat"]
    rs["double_riichi_pending"][seat] = True
    rs["double_riichi"][seat] = True
    rs["ippatsu"][seat] = True
    rs["pending_abortive_draw"] = {"kind": "KYUUSHU_KYUUHAI", "headline": "九种九牌流局"}
    north_tile = 120
    rs["hands"][seat][0] = north_tile
    engine.begin_kita_reaction(game, seat, north_tile)
    assert rs["double_riichi_pending"][seat] is False and rs["double_riichi"][seat] is False, "拔北未打断两立直"
    assert rs["pending_abortive_draw"] is None, "拔北未打断九种九牌"
    engine.resolve_pending_kita(game)
    assert rs["ippatsu"][seat] is False, "拔北未打断一发"
    assert is_chankan_state({"last_discard": {"seat": seat, "tile": north_tile, "source": "kita"}}, is_tsumo=False) is False, "拔北被误算成抢杠"

    return ok(
        "kita_interrupt_rules",
        "拔北打断链",
        "拔北会打断两立直待确认、九种九牌与一发，且不会被当作抢杠。",
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
    engine_text = ENGINE_PATH.read_text(encoding="utf-8")
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


CHECKS: list[Callable[[], AuditItem]] = [
    test_ranked_starting_points,
    test_target_scores,
    test_multi_ron_head_bump_disabled,
    test_multi_ron_mahjong_soul_dealer_keeps,
    test_sanma_tsumo_loss,
    test_sanma_no_chi,
    test_sanma_dead_wall_and_no_north_round,
    test_kita_chain_rules,
    test_kita_not_houtei_or_renhou,
    test_abortive_draws_4p_only,
    test_pao_only_daisangen_daisuushii,
    test_local_yaku_completeness,
    detect_missing_sanma_scoring_toggle,
    detect_missing_rule_profiles,
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
