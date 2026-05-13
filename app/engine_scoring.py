"""和牌计分与役种补充层。

基础番符计算依赖 `mahjong` 第三方库；本模块在其上补齐本系统需要的规则语义：
三麻拔北、三麻自摸损/北家折半、责任支付、古役开关、特殊役满、多响供托本场等。
动作模块只需要调用 `evaluate_hand()`，不直接接触底层番符库。
"""

from __future__ import annotations

from typing import Any

from mahjong.constants import CHUN, HAKU, HATSU
from mahjong.hand_calculating.divider import HandDivider
from mahjong.hand_calculating.fu import FuCalculator
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules
from mahjong.hand_calculating.scores import ScoresCalculator
from mahjong.meld import Meld

from app import rust_core
from app.engine_constants import (
    DRAGON_TYPES,
    OPEN_MELD_TYPES,
    TRIPLET_MELD_TYPES,
    WIND_CONSTANTS,
    WIND_TILE_TYPES,
)
from app.engine_round import (
    is_chankan_state,
    is_chiihou_state,
    is_haitei_state,
    is_houtei_state,
    is_renhou_state,
    is_tenhou_state,
)
from app.engine_rules import (
    build_rule_options,
    current_dora_indicators,
    current_ura_indicators,
    ensure_round_state_defaults,
    is_closed_hand,
    minimum_han,
    round_up_to_100,
    sanma_scoring_mode,
    seat_wind_label,
)
from app.engine_shape import is_complete_hand_shape, tenpai_wait_tile_types
from app.engine_tiles import (
    dora_from_indicator,
    is_honor,
    is_red,
    is_terminal,
    scoring_indicator_tile_id,
    sort_tiles,
    tile_label,
    tile_type,
    to_34_array,
)


calculator = HandCalculator()


def scoring_dora_indicators(game: dict[str, Any], round_state: dict[str, Any], *, ura: bool = False) -> list[int]:
    indicators = current_ura_indicators(round_state) if ura else current_dora_indicators(round_state)
    return [scoring_indicator_tile_id(tile_id, mode=game["mode"]) for tile_id in indicators]

def extract_special_yakuman_han(yaku_items: list[Any]) -> tuple[dict[str, int], int]:
    yakuman_keys: dict[str, int] = {}
    total_han = 0
    for yaku in yaku_items:
        if not getattr(yaku, "is_yakuman", False):
            continue
        han_value = max(getattr(yaku, "han_closed", 0) or 0, getattr(yaku, "han_open", 0) or 0)
        total_han += han_value
        type_name = type(yaku).__name__.lower()
        key = None
        if "kokushi" in type_name:
            key = "KOKUSHI"
        elif "daisangen" in type_name:
            key = "DAISANGEN"
        elif "daisuushii" in type_name:
            key = "DAISUUSHI"
        elif "suukantsu" in type_name:
            key = "SUUKANTSU"
        if key is not None:
            yakuman_keys[key] = max(yakuman_keys.get(key, 0), han_value)
    return yakuman_keys, total_han

def calculate_limit_hand_cost(
    game: dict[str, Any],
    seat: int,
    *,
    han: int,
    is_tsumo: bool,
    honba: int = 0,
) -> dict[str, Any]:
    round_state = game["round_state"]
    config = HandConfig(
        is_tsumo=is_tsumo,
        player_wind=WIND_CONSTANTS[seat_wind_label(round_state, seat)],
        round_wind=WIND_CONSTANTS[round_state["prevalent_wind"]],
        kyoutaku_number=0,
        tsumi_number=honba,
        options=OptionalRules(has_open_tanyao=True, has_aka_dora=False),
    )
    return dict(ScoresCalculator.calculate_scores(han=han, fu=30, config=config, is_yakuman=han >= 13))

def score_result_total(cost: dict[str, Any]) -> int:
    rust_value = rust_core.score_result_total(cost)
    if rust_value is not None:
        return rust_value
    total = cost.get("total")
    if isinstance(total, int):
        return total
    return (
        int(cost.get("main", 0))
        + int(cost.get("main_bonus", 0))
        + int(cost.get("additional", 0)) * 2
        + int(cost.get("additional_bonus", 0)) * 2
    )

def local_mangan_yaku_name(game: dict[str, Any], seat: int, win_tile_id: int, *, is_tsumo: bool) -> str | None:
    if not bool(game.get("koyaku_enabled", False)):
        return None
    round_state = game["round_state"]
    win_tile_type = tile_type(win_tile_id)
    haitei = is_haitei_state(round_state, seat, is_tsumo=is_tsumo)
    houtei = is_houtei_state(round_state, is_tsumo=is_tsumo)
    # 古役满贯只需要开关、和牌方式、时机状态和胡牌牌种。Rust 用 code 返回命中项，
    # Python 保留展示名，避免 FFI 传字符串。
    rust_name = rust_core.local_mangan_yaku_name(
        bool(game.get("koyaku_enabled", False)),
        is_tsumo,
        haitei,
        houtei,
        win_tile_type,
    )
    if rust_name is not None:
        return rust_name or None
    if is_tsumo and haitei and win_tile_type == 9:
        return "Iipin moyue"
    if not is_tsumo and houtei and win_tile_type == 17:
        return "Chuupin raoyui"
    return None

def local_yakuman_entries(
    game: dict[str, Any],
    seat: int,
    win_tile_id: int,
    *,
    is_tsumo: bool,
) -> list[tuple[str, int]]:
    if not bool(game.get("koyaku_enabled", False)):
        return []

    round_state = game["round_state"]
    double_riichi = bool(round_state["double_riichi"][seat])
    closed_hand = is_closed_hand(round_state, seat)
    haitei = is_haitei_state(round_state, seat, is_tsumo=is_tsumo)
    houtei = is_houtei_state(round_state, is_tsumo=is_tsumo)
    # “石の上にも三年” 的条件已经能压平成几个布尔位；Rust 返回 entries 或空列表，
    # Python 仍保留最终 [(name, han)] 结构，便于和其它本地役合并。
    rust_entries = rust_core.local_yakuman_entries(
        bool(game.get("koyaku_enabled", False)),
        double_riichi,
        closed_hand,
        haitei,
        houtei,
    )
    if rust_entries is not None:
        return rust_entries
    if not double_riichi or not closed_hand:
        return []

    if haitei or houtei:
        return [("Ishi no ue ni mo sannen", 13)]
    return []

def discard_follows_kan(game: dict[str, Any], discarder: int) -> bool:
    actions = game.get("action_log", [])
    if len(actions) < 3:
        return False
    last_action = actions[-1]
    draw_action = actions[-2]
    kan_action = actions[-3]
    return (
        last_action.get("type") == "DISCARD"
        and draw_action.get("type") == "DRAW"
        and kan_action.get("type") == "KAN"
        and last_action.get("seat") == discarder
        and draw_action.get("seat") == discarder
        and kan_action.get("seat") == discarder
    )

def local_han_yaku_entries(
    game: dict[str, Any],
    seat: int,
    win_tile_id: int,
    *,
    is_tsumo: bool,
) -> list[tuple[str, int]]:
    if not bool(game.get("koyaku_enabled", False)) or is_tsumo:
        return []

    round_state = game["round_state"]
    discard = round_state.get("last_discard")
    has_last_discard = discard is not None
    discard_is_self = has_last_discard and discard.get("seat") == seat
    discard_from_replacement = has_last_discard and discard.get("source") in {"kan", "kita"}
    discard_riichi = bool(discard.get("riichi")) if has_last_discard else False
    follows_kan = (
        discard_follows_kan(game, discard["seat"])
        if has_last_discard and not discard_is_self and not discard_from_replacement
        else False
    )
    # Tsubame gaeshi / Kanburi 都是 1 番本地役。Rust 用 bit mask 表示命中集合，
    # Python 再按既有顺序组装名字，避免变动前端和结算显示。
    rust_entries = rust_core.local_han_yaku_entries(
        bool(game.get("koyaku_enabled", False)),
        is_tsumo,
        has_last_discard,
        discard_is_self,
        discard_from_replacement,
        discard_riichi,
        follows_kan,
    )
    if rust_entries is not None:
        return rust_entries
    if discard is None or discard.get("seat") == seat or discard.get("source") in {"kan", "kita"}:
        return []

    entries: list[tuple[str, int]] = []
    if discard.get("riichi"):
        entries.append(("Tsubame gaeshi", 1))
    if follows_kan:
        entries.append(("Kanburi", 1))
    return entries

def hand_has_sanrenkou(hand: list[list[int]]) -> bool:
    triplet_heads = sorted(
        {
            group[0]
            for group in hand
            if len(group) >= 3 and group[0] == group[1] == group[2] and group[0] < 27
        }
    )
    return any(
        triplet_heads[index : index + 3] == [triplet_heads[index], triplet_heads[index] + 1, triplet_heads[index] + 2]
        for index in range(max(0, len(triplet_heads) - 2))
    )

def hand_has_isshoku_sanjun(hand: list[list[int]]) -> bool:
    sequence_counts: dict[tuple[int, int, int], int] = {}
    for group in hand:
        if len(group) != 3:
            continue
        if group[0] >= 27:
            continue
        if group[0] + 1 == group[1] and group[1] + 1 == group[2]:
            key = (group[0], group[1], group[2])
            sequence_counts[key] = sequence_counts.get(key, 0) + 1
            if sequence_counts[key] >= 3:
                return True
    return False

def local_pattern_entries_for_hand(hand: list[list[int]], *, is_open_hand: bool) -> list[tuple[str, int]]:
    # HandDivider 已经给出按组拆好的牌型。Rust 路径只识别 pattern mask，Python 仍负责
    # 开门降番和展示名称，避免本地役文本散落到 FFI 层。
    rust_entries = rust_core.local_pattern_entries_for_hand(hand, is_open_hand)
    if rust_entries is not None:
        return rust_entries
    entries: list[tuple[str, int]] = []
    if hand_has_isshoku_sanjun(hand):
        entries.append(("Isshoku sanjun", 2 if is_open_hand else 3))
    if hand_has_sanrenkou(hand):
        entries.append(("Sanrenkou", 2))
    return entries

def choose_local_pattern_entries(
    candidates: list[list[tuple[str, int]]],
    *,
    reference_yaku_names: list[str] | None = None,
) -> list[tuple[str, int]]:
    if not candidates:
        return []

    if reference_yaku_names:
        triplet_signals = (
            "Toitoi ",
            "San Ankou ",
            "Sanshoku Doukou ",
            "Sankantsu ",
            "Suukantsu ",
            "Daisangen ",
            "Shousangen ",
            "Shousuushii ",
            "Daisuushii ",
        )
        sequence_signals = (
            "Iipeikou ",
            "Ryanpeikou ",
            "Pinfu ",
            "Sanshoku Doujun ",
            "Ittsu ",
        )
        has_triplet_signal = any(name.startswith(triplet_signals) for name in reference_yaku_names)
        has_sequence_signal = any(name.startswith(sequence_signals) for name in reference_yaku_names)

        if has_triplet_signal and not has_sequence_signal:
            triplet_candidates = [candidate for candidate in candidates if any(name == "Sanrenkou" for name, _ in candidate)]
            if triplet_candidates:
                candidates = triplet_candidates
        elif has_sequence_signal and not has_triplet_signal:
            sequence_candidates = [candidate for candidate in candidates if any(name == "Isshoku sanjun" for name, _ in candidate)]
            if sequence_candidates:
                candidates = sequence_candidates

    return max(candidates, key=lambda candidate: (sum(han for _, han in candidate), len(candidate)))

def local_pattern_yaku_entries(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
    reference_yaku_names: list[str] | None = None,
) -> list[tuple[str, int]]:
    if not bool(game.get("koyaku_enabled", False)):
        return []

    open_melds = [meld for meld in melds_data if meld["type"] != "kita"]
    meld_objects = build_meld_objects_from_data(melds_data, seat)
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    for meld in open_melds:
        all_tiles.extend(meld["tiles"])

    categories = {
        "man": False,
        "pin": False,
        "sou": False,
        "wind": False,
        "dragon": False,
    }
    for tile_id in all_tiles:
        t = tile_type(tile_id)
        if t < 9:
            categories["man"] = True
        elif t < 18:
            categories["pin"] = True
        elif t < 27:
            categories["sou"] = True
        elif t < 31:
            categories["wind"] = True
        else:
            categories["dragon"] = True

    entries: list[tuple[str, int]] = []
    hand_options = HandDivider.divide_hand(to_34_array(all_tiles), meld_objects)
    is_open_hand = any(meld["type"] in OPEN_MELD_TYPES for meld in melds_data)
    entries.extend(
        choose_local_pattern_entries(
            [local_pattern_entries_for_hand(hand, is_open_hand=is_open_hand) for hand in hand_options],
            reference_yaku_names=reference_yaku_names,
        )
    )
    if (
        len(open_melds) == 4
        and all(meld["opened"] for meld in open_melds)
        and (
            (is_tsumo and len(concealed_tiles) == 2 and tile_type(concealed_tiles[0]) == tile_type(concealed_tiles[1]))
            or (not is_tsumo and len(concealed_tiles) == 1 and tile_type(concealed_tiles[0]) == tile_type(win_tile_id))
        )
    ):
        entries.append(("Shiiaru raotai", 1))
    if all(categories.values()):
        entries.append(("Uumensai", 2))
    return entries

def combined_local_han_entries(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
    reference_yaku_names: list[str] | None = None,
) -> list[tuple[str, int]]:
    entries = local_han_yaku_entries(game, seat, win_tile_id, is_tsumo=is_tsumo)
    entries.extend(
        local_pattern_yaku_entries(
            game,
            seat,
            concealed_tiles,
            melds_data,
            win_tile_id,
            is_tsumo=is_tsumo,
            reference_yaku_names=reference_yaku_names,
        )
    )
    return entries

def apply_local_yakuman_entries(
    yaku_names: list[str],
    yakuman_keys: dict[str, int],
    yakuman_total_han: int,
    local_yakuman_entries: list[tuple[str, int]],
) -> tuple[list[str], dict[str, int], int]:
    if not local_yakuman_entries:
        return yaku_names, yakuman_keys, yakuman_total_han

    names = [name for name, _ in local_yakuman_entries]
    updated_names = list(names) if yakuman_total_han == 0 else yaku_names + names
    updated_keys = dict(yakuman_keys)
    for name, han in local_yakuman_entries:
        updated_keys[f"LOCAL:{name}"] = han
        yakuman_total_han += han
    return updated_names, updated_keys, yakuman_total_han

def apply_local_yaku_replacements(
    base_han: int,
    yaku_names: list[str],
    local_han_entries: list[tuple[str, int]],
) -> tuple[int, list[str]]:
    updated_han = base_han
    updated_yaku_names = list(yaku_names)

    if any(name == "Isshoku sanjun" for name, _ in local_han_entries):
        for index, item in enumerate(updated_yaku_names):
            if item.startswith("Iipeikou "):
                updated_han -= 1
                del updated_yaku_names[index]
                break

    return updated_han, updated_yaku_names

def is_agari_layout(
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
    mode: str = "4P",
) -> bool:
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    return is_complete_hand_shape(all_tiles, melds_data, mode=mode)

def apply_local_mangan_floor(
    game: dict[str, Any],
    seat: int,
    *,
    is_tsumo: bool,
    local_yaku_name: str | None,
    score_result: dict[str, Any],
    yaku_names: list[str],
) -> dict[str, Any]:
    if not local_yaku_name:
        return score_result
    if local_yaku_name not in yaku_names:
        yaku_names.append(local_yaku_name)
    mangan_cost = calculate_limit_hand_cost(game, seat, han=5, is_tsumo=is_tsumo, honba=0)
    if score_result_total(score_result) < score_result_total(mangan_cost):
        return mangan_cost
    return score_result

def local_bonus_tile_names(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
) -> tuple[int, list[str]]:
    round_state = game["round_state"]
    all_tiles = scoring_tiles_from_layout(concealed_tiles, melds_data, win_tile_id, is_tsumo=is_tsumo)

    bonus_han = 0
    names: list[str] = []

    dora_types = [dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_dora_indicators(round_state)]
    dora_han = sum(1 for tile_id in all_tiles if tile_type(tile_id) in dora_types)
    if dora_han:
        bonus_han += dora_han
        names.append(f"Dora {dora_han} han")

    aka_han = active_aka_dora_han(game, all_tiles)
    if aka_han:
        bonus_han += aka_han
        names.append(f"Aka Dora {aka_han} han")

    if round_state["riichi"][seat]:
        ura_types = [dora_from_indicator(tile_id, mode=game["mode"]) for tile_id in current_ura_indicators(round_state)]
        ura_han = sum(1 for tile_id in all_tiles if tile_type(tile_id) in ura_types)
        if ura_han:
            bonus_han += ura_han
            names.append(f"Ura Dora {ura_han} han")

    nuki_han = round_state["nuki_count"][seat] if game["mode"] == "3P" else 0
    if nuki_han:
        bonus_han += nuki_han
        names.append(f"Nuki Dora {nuki_han} han")

    return bonus_han, names

def scoring_tiles_from_layout(
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
) -> list[int]:
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    for meld in melds_data:
        if meld["type"] != "kita":
            all_tiles.extend(meld["tiles"])
    return all_tiles

def active_aka_dora_han(game: dict[str, Any], tiles: list[int]) -> int:
    return sum(1 for tile_id in tiles if is_red(tile_id, game))

def evaluate_local_only_hand(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
    local_han_entries: list[tuple[str, int]],
    local_yaku_name: str | None = None,
) -> dict[str, Any] | None:
    if not local_han_entries and not local_yaku_name:
        return None
    if not is_agari_layout(concealed_tiles, melds_data, win_tile_id, is_tsumo=is_tsumo, mode=game["mode"]):
        return None

    meld_objects = build_meld_objects_from_data(melds_data, seat)
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    for meld in melds_data:
        if meld["type"] != "kita":
            all_tiles.extend(meld["tiles"])

    hand_options = HandDivider.divide_hand(to_34_array(all_tiles), meld_objects)
    opened_melds = [meld.tiles_34 for meld in meld_objects if meld.opened]
    config = build_hand_config(game, seat, is_tsumo=is_tsumo, kyoutaku_override=kyoutaku_override)
    valued_tiles = [HAKU, HATSU, CHUN, config.player_wind, config.round_wind]
    bonus_han, bonus_names = local_bonus_tile_names(
        game,
        seat,
        concealed_tiles,
        melds_data,
        win_tile_id,
        is_tsumo=is_tsumo,
    )
    local_han_total = sum(han for _, han in local_han_entries)
    total_han = local_han_total + bonus_han
    if total_han <= 0 and not local_yaku_name:
        return None
    if not minimum_han_satisfied(game, total_han, local_yaku_name=local_yaku_name):
        return None

    base_yaku_names = [f"{name} {han} han" for name, han in local_han_entries] + bonus_names
    score_han = max(total_han, 1 if local_yaku_name else 0)
    display_han = max(total_han, 5 if local_yaku_name else 0)
    best_result: dict[str, Any] | None = None
    best_rank: tuple[int, int, int] | None = None
    for hand in hand_options:
        for win_group in HandCalculator._find_win_groups(win_tile_id, hand, opened_melds):
            fu_details, fu = FuCalculator.calculate_fu(hand, win_tile_id, win_group, config, valued_tiles, meld_objects)
            cost = dict(ScoresCalculator.calculate_scores(han=score_han, fu=fu, config=config, is_yakuman=False))
            yaku_names = list(base_yaku_names)
            cost = apply_local_mangan_floor(
                game,
                seat,
                is_tsumo=is_tsumo,
                local_yaku_name=local_yaku_name,
                score_result=cost,
                yaku_names=yaku_names,
            )
            rank = (score_result_total(cost), display_han, fu)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_result = {
                    "han": display_han,
                    "fu": fu,
                    "cost": cost,
                    "yaku": yaku_names,
                    "fu_details": [dict(item) for item in fu_details],
                    "is_tsumo": is_tsumo,
                    "win_tile_label": tile_label(win_tile_id, game),
                    "yakuman_keys": {},
                    "yakuman_total_han": 0,
                }
    return best_result

def full_honba_value(game: dict[str, Any], *, is_tsumo: bool) -> int:
    round_state = game["round_state"]
    rust_value = rust_core.full_honba_value(game.get("mode", "4P"), round_state["honba"])
    if rust_value is not None:
        return rust_value
    if game.get("mode") == "3P":
        return round_state["honba"] * 200
    return round_state["honba"] * 300

def minimum_han_satisfied(
    game: dict[str, Any],
    han: int,
    *,
    yakuman_total_han: int = 0,
    local_yaku_name: str | None = None,
) -> bool:
    rust_value = rust_core.minimum_han_satisfied(
        han,
        yakuman_total_han,
        local_yaku_name is not None,
        minimum_han(game),
    )
    if rust_value is not None:
        return rust_value
    if yakuman_total_han > 0:
        return True
    effective_han = han
    if local_yaku_name:
        effective_han = max(effective_han, 5)
    return effective_han >= minimum_han(game)

def append_payment_detail(
    game: dict[str, Any],
    payments: list[dict[str, Any]],
    *,
    from_seat: int | None,
    amount: int,
    kind: str,
) -> None:
    if amount <= 0:
        return
    from_name = "供托" if from_seat is None else game["players"][from_seat]["name"]
    payments.append(
        {
            "from_seat": from_seat,
            "from_name": from_name,
            "amount": amount,
            "kind": kind,
        }
    )

def tsumo_payment_kind(round_state: dict[str, Any], payer_seat: int) -> str:
    return "tsumo_dealer" if payer_seat == round_state["dealer_seat"] else "tsumo_child"

def tsumo_payment_map(game: dict[str, Any], seat: int, cost: dict[str, Any]) -> dict[int, int]:
    round_state = game["round_state"]
    dealer = round_state["dealer_seat"]
    rust_payments = rust_core.tsumo_payment_map(
        game["mode"],
        sanma_scoring_mode(game),
        round_state["player_count"],
        seat,
        dealer,
        cost,
    )
    if rust_payments is not None:
        return rust_payments
    losers = [loser for loser in range(round_state["player_count"]) if loser != seat]
    if game["mode"] == "3P" and sanma_scoring_mode(game) == "NORTH_BISECTION":
        if seat == dealer:
            per_loser = cost["main"] + cost.get("main_bonus", 0)
            bisection = round_up_to_100(per_loser / 2)
            return {loser: per_loser + bisection for loser in losers}

        dealer_payment = cost["main"] + cost.get("main_bonus", 0)
        child_payment = cost["additional"] + cost.get("additional_bonus", 0)
        bisection = round_up_to_100(child_payment / 2)
        return {
            loser: (dealer_payment if loser == dealer else child_payment) + bisection
            for loser in losers
        }
    if seat == dealer:
        per_loser = cost["main"] + cost.get("main_bonus", 0)
        return {loser: per_loser for loser in losers}

    dealer_payment = cost["main"] + cost.get("main_bonus", 0)
    child_payment = cost["additional"] + cost.get("additional_bonus", 0)
    return {
        loser: (dealer_payment if loser == dealer else child_payment)
        for loser in losers
    }

def apply_tsumo_payments(
    game: dict[str, Any],
    seat: int,
    cost: dict[str, Any],
    score_changes: list[int],
    payments: list[dict[str, Any]] | None = None,
    *,
    kind: str = "tsumo",
) -> None:
    round_state = game["round_state"]
    for loser, payment in tsumo_payment_map(game, seat, cost).items():
        score_changes[loser] -= payment
        score_changes[seat] += payment
        if payments is not None:
            append_payment_detail(
                game,
                payments,
                from_seat=loser,
                amount=payment,
                kind=tsumo_payment_kind(round_state, loser) if kind == "tsumo" else kind,
            )

def nagashi_mangan_winners(round_state: dict[str, Any]) -> list[int]:
    winners: list[int] = []
    for seat, discards in enumerate(round_state["discards"]):
        # 流局满贯候选只依赖这一家的弃牌河：弃了哪些实体牌、这些弃牌是否被鸣走。
        # Rust 路径返回 None 时代表不可用，不能把 None 当成 False，否则会吞掉兜底判断。
        rust_value = rust_core.is_nagashi_mangan_candidate(
            [item["tile"] for item in discards],
            [bool(item.get("called", False)) for item in discards],
        )
        if rust_value is not None:
            if rust_value:
                winners.append(seat)
            continue
        if not discards:
            continue
        if any(item.get("called", False) for item in discards):
            continue
        if any(not (is_terminal(tile_type(item["tile"])) or is_honor(tile_type(item["tile"]))) for item in discards):
            continue
        winners.append(seat)
    return winners

def triplet_family_types(melds: list[dict[str, Any]], family_types: set[int]) -> set[int]:
    return {
        tile_type(meld["tiles"][0])
        for meld in melds
        if meld["type"] in TRIPLET_MELD_TYPES and meld["tiles"] and tile_type(meld["tiles"][0]) in family_types
    }

def register_liability_for_call(round_state: dict[str, Any], seat: int, action_type: str, tile_id: int, discarder: int) -> None:
    if action_type not in {"pon", "open_kan"} or seat == discarder:
        return
    liability = round_state["liability_payments"][seat]
    melds = round_state["melds"][seat]
    tile_index = tile_type(tile_id)
    triplet_types = [
        tile_type(meld["tiles"][0])
        for meld in melds
        if meld["type"] in TRIPLET_MELD_TYPES and meld["tiles"]
    ]
    # 包牌触发只需要“本次鸣的牌种”和当前刻子/杠子牌种集合。Python 仍负责写入
    # liability_payments 字典，Rust 只返回要新增的责任役 key，保持状态变更集中在这里。
    rust_key = rust_core.liability_key_for_call(
        action_type,
        tile_index,
        seat == discarder,
        set(liability),
        triplet_types,
    )
    if rust_key is not None:
        if rust_key == "DAISANGEN":
            liability["DAISANGEN"] = {"liable_seat": discarder, "han": 13}
        elif rust_key == "DAISUUSHI":
            liability["DAISUUSHI"] = {"liable_seat": discarder, "han": 26}
        return
    if tile_index in DRAGON_TYPES and "DAISANGEN" not in liability:
        if len(triplet_family_types(melds, DRAGON_TYPES)) == 3:
            liability["DAISANGEN"] = {"liable_seat": discarder, "han": 13}
    if tile_index in WIND_TILE_TYPES and "DAISUUSHI" not in liability:
        if len(triplet_family_types(melds, WIND_TILE_TYPES)) == 4:
            liability["DAISUUSHI"] = {"liable_seat": discarder, "han": 26}

def liability_context(game: dict[str, Any], winner_seat: int, evaluation: dict[str, Any] | None) -> dict[str, Any] | None:
    if evaluation is None or evaluation.get("yakuman_total_han", 0) < 13:
        return None
    round_state = game["round_state"]
    ensure_round_state_defaults(round_state)
    liability_map = round_state["liability_payments"][winner_seat]
    yakuman_keys = evaluation.get("yakuman_keys", {})
    daisangen_liability = liability_map.get("DAISANGEN", {})
    daisuushi_liability = liability_map.get("DAISUUSHI", {})
    # Rust 负责把“哪些责任役同时命中、是否同一个责任人、应负责多少役满”算成一个
    # 小 profile；Python 保留最终 dict 形状和 key 顺序，避免结算层接口发生变化。
    rust_profile = rust_core.liability_context_profile(
        round_state["player_count"],
        int(evaluation.get("yakuman_total_han", 0)),
        int(yakuman_keys.get("DAISANGEN", 0)),
        int(daisangen_liability.get("liable_seat", -1)) if isinstance(daisangen_liability, dict) else -1,
        int(daisangen_liability.get("han", 0)) if isinstance(daisangen_liability, dict) else 0,
        int(yakuman_keys.get("DAISUUSHI", 0)),
        int(daisuushi_liability.get("liable_seat", -1)) if isinstance(daisuushi_liability, dict) else -1,
        int(daisuushi_liability.get("han", 0)) if isinstance(daisuushi_liability, dict) else 0,
    )
    if rust_profile is not None:
        liable_seat, liable_han, remainder_han, key_mask = rust_profile
        if key_mask == 0:
            return None
        return {
            "liable_seat": liable_seat,
            "liable_han": liable_han,
            "remainder_han": remainder_han,
            "keys": [key for bit, key in ((1, "DAISANGEN"), (2, "DAISUUSHI")) if key_mask & bit],
        }
    matched_keys = [
        key for key in ("DAISANGEN", "DAISUUSHI") if key in evaluation.get("yakuman_keys", {}) and key in liability_map
    ]
    if not matched_keys:
        return None
    liable_seats = {liability_map[key]["liable_seat"] for key in matched_keys}
    if len(liable_seats) != 1:
        return None
    liable_han = sum(min(liability_map[key]["han"], evaluation["yakuman_keys"][key]) for key in matched_keys)
    if liable_han <= 0:
        return None
    total_yakuman_han = evaluation.get("yakuman_total_han", 0)
    return {
        "liable_seat": next(iter(liable_seats)),
        "liable_han": min(liable_han, total_yakuman_han),
        "remainder_han": max(0, total_yakuman_han - liable_han),
        "keys": matched_keys,
    }

def serialize_yaku_names(yaku_items: list[Any]) -> list[str]:
    result: list[str] = []
    for yaku in yaku_items:
        name = getattr(yaku, "name", str(yaku))
        han_open = getattr(yaku, "han_open", None)
        han_closed = getattr(yaku, "han_closed", None)
        han_value = han_closed if han_closed is not None else han_open
        if han_value is None:
            result.append(name)
        else:
            result.append(f"{name} {han_value} han")
    return result

def build_meld_objects_from_data(melds_data: list[dict[str, Any]], seat: int) -> list[Meld]:
    meld_objects: list[Meld] = []
    for meld in melds_data:
        if meld["type"] == "kita":
            continue
        meld_type = {
            "chi": Meld.CHI,
            "pon": Meld.PON,
            "open_kan": Meld.KAN,
            "closed_kan": Meld.KAN,
            "added_kan": Meld.SHOUMINKAN,
        }[meld["type"]]
        meld_objects.append(
            Meld(
                meld_type=meld_type,
                tiles=tuple(meld["tiles"]),
                opened=meld["opened"],
                called_tile=meld.get("called_tile"),
                who=seat,
                from_who=meld.get("from_seat"),
            )
        )
    return meld_objects

def build_meld_objects(round_state: dict[str, Any], seat: int) -> list[Meld]:
    return build_meld_objects_from_data(round_state["melds"][seat], seat)

def build_hand_config(
    game: dict[str, Any],
    seat: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
    riichi_override: bool | None = None,
    ippatsu_override: bool | None = None,
    rinshan_override: bool | None = None,
    chankan_override: bool | None = None,
    haitei_override: bool | None = None,
    houtei_override: bool | None = None,
    daburu_override: bool | None = None,
    tenhou_override: bool | None = None,
    chiihou_override: bool | None = None,
) -> HandConfig:
    round_state = game["round_state"]
    return HandConfig(
        is_tsumo=is_tsumo,
        is_riichi=round_state["riichi"][seat] if riichi_override is None else riichi_override,
        is_ippatsu=round_state["ippatsu"][seat] if ippatsu_override is None else ippatsu_override,
        is_rinshan=(round_state["last_draw_source"][seat] == "rinshan") if rinshan_override is None else rinshan_override,
        is_chankan=is_chankan_state(round_state, is_tsumo=is_tsumo) if chankan_override is None else chankan_override,
        is_haitei=is_haitei_state(round_state, seat, is_tsumo=is_tsumo) if haitei_override is None else haitei_override,
        is_houtei=is_houtei_state(round_state, is_tsumo=is_tsumo) if houtei_override is None else houtei_override,
        is_daburu_riichi=round_state["double_riichi"][seat] if daburu_override is None else daburu_override,
        is_tenhou=is_tenhou_state(round_state, seat, is_tsumo=is_tsumo) if tenhou_override is None else tenhou_override,
        is_renhou=is_renhou_state(game, seat, is_tsumo=is_tsumo),
        is_chiihou=is_chiihou_state(round_state, seat, is_tsumo=is_tsumo) if chiihou_override is None else chiihou_override,
        player_wind=WIND_CONSTANTS[seat_wind_label(round_state, seat)],
        round_wind=WIND_CONSTANTS[round_state["prevalent_wind"]],
        kyoutaku_number=round_state["riichi_sticks"] if kyoutaku_override is None else kyoutaku_override,
        tsumi_number=round_state["honba"],
        options=build_rule_options(game),
    )

def estimate_hand_value_for_layout(
    game: dict[str, Any],
    seat: int,
    concealed_tiles: list[int],
    melds_data: list[dict[str, Any]],
    win_tile_id: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
    riichi_override: bool | None = None,
    ippatsu_override: bool | None = None,
    rinshan_override: bool | None = None,
    chankan_override: bool | None = None,
    haitei_override: bool | None = None,
    houtei_override: bool | None = None,
    daburu_override: bool | None = None,
    tenhou_override: bool | None = None,
    chiihou_override: bool | None = None,
) -> Any:
    round_state = game["round_state"]
    all_tiles = list(concealed_tiles)
    if not is_tsumo:
        all_tiles.append(win_tile_id)
    for meld in melds_data:
        if meld["type"] != "kita":
            all_tiles.extend(meld["tiles"])
    config = build_hand_config(
        game,
        seat,
        is_tsumo=is_tsumo,
        kyoutaku_override=kyoutaku_override,
        riichi_override=riichi_override,
        ippatsu_override=ippatsu_override,
        rinshan_override=rinshan_override,
        chankan_override=chankan_override,
        haitei_override=haitei_override,
        houtei_override=houtei_override,
        daburu_override=daburu_override,
        tenhou_override=tenhou_override,
        chiihou_override=chiihou_override,
    )
    return calculator.estimate_hand_value(
        all_tiles,
        win_tile_id,
        melds=build_meld_objects_from_data(melds_data, seat),
        dora_indicators=scoring_dora_indicators(game, round_state),
        ura_dora_indicators=scoring_dora_indicators(game, round_state, ura=True)
        if (round_state["riichi"][seat] if riichi_override is None else riichi_override)
        else None,
        config=config,
    )

def tile_type_count_in_layout(concealed_tiles: list[int], melds_data: list[dict[str, Any]], tile_index: int) -> int:
    total = sum(1 for tile in concealed_tiles if tile_type(tile) == tile_index)
    for meld in melds_data:
        if meld["type"] == "kita":
            continue
        total += sum(1 for tile in meld["tiles"] if tile_type(tile) == tile_index)
    return total

def winning_tile_types_for_layout(
    game: dict[str, Any], seat: int, concealed_tiles: list[int], melds_data: list[dict[str, Any]]
) -> set[int]:
    return tenpai_wait_tile_types(concealed_tiles, mode=game["mode"], melds_data=melds_data)

def evaluate_hand(
    game: dict[str, Any],
    seat: int,
    win_tile_id: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
) -> dict[str, Any] | None:
    round_state = game["round_state"]
    local_yaku_name = local_mangan_yaku_name(game, seat, win_tile_id, is_tsumo=is_tsumo)
    local_yakuman = local_yakuman_entries(game, seat, win_tile_id, is_tsumo=is_tsumo)
    if is_tsumo and is_tenhou_state(round_state, seat, is_tsumo=True):
        best: dict[str, Any] | None = None
        for candidate_tile_id in sort_tiles(round_state["hands"][seat]):
            candidate_result = estimate_hand_value_for_layout(
                game,
                seat,
                round_state["hands"][seat],
                round_state["melds"][seat],
                candidate_tile_id,
                is_tsumo=True,
                kyoutaku_override=kyoutaku_override,
                tenhou_override=True,
            )
            if candidate_result.error:
                continue
            serialized = serialize_evaluation_result(
                game,
                seat,
                candidate_result,
                candidate_tile_id,
                is_tsumo=True,
                kyoutaku_override=kyoutaku_override,
                tenhou_override=True,
            )
            if serialized is None:
                continue
            if best is None or evaluation_result_rank(serialized) > evaluation_result_rank(best):
                best = serialized
        return best
    config = build_hand_config(game, seat, is_tsumo=is_tsumo, kyoutaku_override=kyoutaku_override)
    result = estimate_hand_value_for_layout(
        game,
        seat,
        round_state["hands"][seat],
        round_state["melds"][seat],
        win_tile_id,
        is_tsumo=is_tsumo,
        kyoutaku_override=kyoutaku_override,
    )
    if result.error:
        local_han_entries = combined_local_han_entries(
            game,
            seat,
            round_state["hands"][seat],
            round_state["melds"][seat],
            win_tile_id,
            is_tsumo=is_tsumo,
        )
        if (
            local_yaku_name
            and not local_han_entries
            and is_agari_layout(
                round_state["hands"][seat],
                round_state["melds"][seat],
                win_tile_id,
                is_tsumo=is_tsumo,
                mode=game["mode"],
            )
        ):
            if not minimum_han_satisfied(game, 0, local_yaku_name=local_yaku_name):
                return None
            return {
                "han": 5,
                "fu": 30,
                "cost": calculate_limit_hand_cost(game, seat, han=5, is_tsumo=is_tsumo, honba=0),
                "yaku": [local_yaku_name],
                "fu_details": [],
                "is_tsumo": is_tsumo,
                "win_tile_label": tile_label(win_tile_id, game),
                "yakuman_keys": {},
                "yakuman_total_han": 0,
            }
        local_only_result = evaluate_local_only_hand(
            game,
            seat,
            round_state["hands"][seat],
            round_state["melds"][seat],
            win_tile_id,
            is_tsumo=is_tsumo,
            kyoutaku_override=kyoutaku_override,
            local_han_entries=local_han_entries,
            local_yaku_name=local_yaku_name,
        )
        if local_only_result is not None:
            return local_only_result
        return None
    yakuman_keys, yakuman_total_han = extract_special_yakuman_han(result.yaku)
    yaku_names = serialize_yaku_names(result.yaku)
    local_han_entries = combined_local_han_entries(
        game,
        seat,
        round_state["hands"][seat],
        round_state["melds"][seat],
        win_tile_id,
        is_tsumo=is_tsumo,
        reference_yaku_names=yaku_names,
    )
    yaku_names, yakuman_keys, yakuman_total_han = apply_local_yakuman_entries(
        yaku_names,
        yakuman_keys,
        yakuman_total_han,
        local_yakuman,
    )
    is_yakuman_hand = yakuman_total_han > 0
    base_han = result.han
    if not is_yakuman_hand:
        base_han, yaku_names = apply_local_yaku_replacements(base_han, yaku_names, local_han_entries)
    local_han_total = 0 if is_yakuman_hand else sum(han for _, han in local_han_entries)
    han = yakuman_total_han if is_yakuman_hand else base_han + local_han_total
    if not is_yakuman_hand:
        yaku_names.extend(f"{name} {han_value} han" for name, han_value in local_han_entries)
        aka_han = active_aka_dora_han(
            game,
            scoring_tiles_from_layout(
                round_state["hands"][seat],
                round_state["melds"][seat],
                win_tile_id,
                is_tsumo=is_tsumo,
            ),
        )
        if aka_han:
            han += aka_han
            yaku_names.append(f"Aka Dora {aka_han} han")
    nuki = round_state["nuki_count"][seat] if game["mode"] == "3P" and not is_yakuman_hand else 0
    if nuki:
        han += nuki
        yaku_names.append(f"Nuki Dora {nuki} han")
    if not minimum_han_satisfied(
        game,
        han,
        yakuman_total_han=yakuman_total_han,
        local_yaku_name=None if is_yakuman_hand else local_yaku_name,
    ):
        return None
    score_result = ScoresCalculator.calculate_scores(
        han=han,
        fu=result.fu,
        config=config,
        is_yakuman=is_yakuman_hand,
    )
    score_result = apply_local_mangan_floor(
        game,
        seat,
        is_tsumo=is_tsumo,
        local_yaku_name=None if is_yakuman_hand else local_yaku_name,
        score_result=dict(score_result),
        yaku_names=yaku_names,
    )
    return {
        "han": han,
        "fu": result.fu,
        "cost": dict(score_result),
        "yaku": yaku_names,
        "fu_details": [dict(item) for item in result.fu_details],
        "is_tsumo": is_tsumo,
        "win_tile_label": tile_label(win_tile_id, game),
        "yakuman_keys": yakuman_keys,
        "yakuman_total_han": yakuman_total_han,
    }

def serialize_evaluation_result(
    game: dict[str, Any],
    seat: int,
    result: Any,
    win_tile_id: int,
    *,
    is_tsumo: bool,
    kyoutaku_override: int | None = None,
    tenhou_override: bool | None = None,
) -> dict[str, Any] | None:
    round_state = game["round_state"]
    local_yaku_name = local_mangan_yaku_name(game, seat, win_tile_id, is_tsumo=is_tsumo)
    local_yakuman = local_yakuman_entries(game, seat, win_tile_id, is_tsumo=is_tsumo)
    config = build_hand_config(
        game,
        seat,
        is_tsumo=is_tsumo,
        kyoutaku_override=kyoutaku_override,
        tenhou_override=tenhou_override,
    )
    yakuman_keys, yakuman_total_han = extract_special_yakuman_han(result.yaku)
    yaku_names = serialize_yaku_names(result.yaku)
    local_han_entries = combined_local_han_entries(
        game,
        seat,
        round_state["hands"][seat],
        round_state["melds"][seat],
        win_tile_id,
        is_tsumo=is_tsumo,
        reference_yaku_names=yaku_names,
    )
    yaku_names, yakuman_keys, yakuman_total_han = apply_local_yakuman_entries(
        yaku_names,
        yakuman_keys,
        yakuman_total_han,
        local_yakuman,
    )
    is_yakuman_hand = yakuman_total_han > 0
    base_han = result.han
    if not is_yakuman_hand:
        base_han, yaku_names = apply_local_yaku_replacements(base_han, yaku_names, local_han_entries)
    local_han_total = 0 if is_yakuman_hand else sum(han_value for _, han_value in local_han_entries)
    han = yakuman_total_han if is_yakuman_hand else base_han + local_han_total
    if not is_yakuman_hand:
        yaku_names.extend(f"{name} {han_value} han" for name, han_value in local_han_entries)
        aka_han = active_aka_dora_han(
            game,
            scoring_tiles_from_layout(
                round_state["hands"][seat],
                round_state["melds"][seat],
                win_tile_id,
                is_tsumo=is_tsumo,
            ),
        )
        if aka_han:
            han += aka_han
            yaku_names.append(f"Aka Dora {aka_han} han")
    nuki = round_state["nuki_count"][seat] if game["mode"] == "3P" and not is_yakuman_hand else 0
    if nuki:
        han += nuki
        yaku_names.append(f"Nuki Dora {nuki} han")
    if not minimum_han_satisfied(
        game,
        han,
        yakuman_total_han=yakuman_total_han,
        local_yaku_name=None if is_yakuman_hand else local_yaku_name,
    ):
        return None
    score_result = ScoresCalculator.calculate_scores(
        han=han,
        fu=result.fu,
        config=config,
        is_yakuman=is_yakuman_hand,
    )
    score_result = apply_local_mangan_floor(
        game,
        seat,
        is_tsumo=is_tsumo,
        local_yaku_name=None if is_yakuman_hand else local_yaku_name,
        score_result=dict(score_result),
        yaku_names=yaku_names,
    )
    return {
        "han": han,
        "fu": result.fu,
        "cost": dict(score_result),
        "yaku": yaku_names,
        "fu_details": [dict(item) for item in result.fu_details],
        "is_tsumo": is_tsumo,
        "win_tile_label": tile_label(win_tile_id, game),
        "yakuman_keys": yakuman_keys,
        "yakuman_total_han": yakuman_total_han,
    }

def evaluation_result_rank(item: dict[str, Any]) -> tuple[int, int, int, int]:
    cost = item["cost"]
    total = cost.get("total")
    if total is None:
        total = (
            cost.get("main", 0)
            + cost.get("main_bonus", 0)
            + cost.get("additional", 0) * 2
            + cost.get("additional_bonus", 0) * 2
        )
    return (
        item["yakuman_total_han"],
        int(total),
        item["han"],
        item["fu"],
    )

__all__ = [
    "scoring_dora_indicators",
    "extract_special_yakuman_han",
    "calculate_limit_hand_cost",
    "score_result_total",
    "local_mangan_yaku_name",
    "local_yakuman_entries",
    "discard_follows_kan",
    "local_han_yaku_entries",
    "hand_has_sanrenkou",
    "hand_has_isshoku_sanjun",
    "local_pattern_entries_for_hand",
    "choose_local_pattern_entries",
    "local_pattern_yaku_entries",
    "combined_local_han_entries",
    "apply_local_yakuman_entries",
    "apply_local_yaku_replacements",
    "is_agari_layout",
    "apply_local_mangan_floor",
    "local_bonus_tile_names",
    "scoring_tiles_from_layout",
    "active_aka_dora_han",
    "evaluate_local_only_hand",
    "full_honba_value",
    "minimum_han_satisfied",
    "append_payment_detail",
    "tsumo_payment_kind",
    "tsumo_payment_map",
    "apply_tsumo_payments",
    "nagashi_mangan_winners",
    "triplet_family_types",
    "register_liability_for_call",
    "liability_context",
    "serialize_yaku_names",
    "build_meld_objects_from_data",
    "build_meld_objects",
    "build_hand_config",
    "estimate_hand_value_for_layout",
    "tile_type_count_in_layout",
    "winning_tile_types_for_layout",
    "evaluate_hand",
    "serialize_evaluation_result",
    "evaluation_result_rank",
]
