//! C ABI 边界。
//!
//! 所有暴露给 Python ctypes 的函数都集中在这里。FFI 层只做三件事：
//! 校验指针和数组长度、把原始指针转换成 Rust slice、调用内部纯计算函数。
//! 业务逻辑不要直接写在 FFI 函数里，方便后续测试和继续拆分模块。

use crate::analysis::{
    discard_metrics_from_counts, draw_tiles_from_counts, effective_tiles_from_counts,
    hand_route_profile_from_counts, hand_route_profiles_after_discards,
};
use crate::ev::{
    alpha_terminal_projection_ev, deal_in_loss_profile, defense_override_profile,
    defensive_discard_profile, global_reward_delta_profile, push_fold_profile,
    structured_discard_ev, AlphaTerminalInput, DealInLossInput, DefenseOverrideInput,
    DefensiveDiscardInput, GlobalRewardInput, PushFoldInput, StructuredDiscardInput,
};
use crate::risk::{
    aggregate_safety_scores, safe_tile_reserve_profile, safe_tile_reserve_profiles_after_discards,
    tile_danger_table, tile_value_bonus, DangerInput,
};
use crate::rules::{
    can_abortive_draw_nine_terminals, can_double_riichi, chi_candidate_pairs, goal_score_reached,
    is_chankan_state, is_chiihou_state, is_furiten, is_haitei_state, is_houtei_state,
    is_renhou_state, is_tenhou_state, is_win_like_round_result, kuikae_forbidden_tile_types,
    max_round_count, next_seat, pending_abortive_draw_kind, player_count, ranked_settlement_scores,
    round_target_count, seat_distance, seat_wind_code, should_abort_for_four_kans,
    should_auto_stop_all_last_dealer,
};
use crate::scoring::{
    full_honba_value, is_nagashi_mangan_candidate, liability_context_profile,
    liability_key_for_call, local_han_yaku_mask, local_mangan_yaku_code, local_pattern_yaku_mask,
    local_yakuman_yaku_code, minimum_han_satisfied, round_up_to_100, score_result_total,
    tsumo_payment_map,
};
use crate::shanten::calculate_shanten;
use crate::shape::{
    is_complete_hand_shape as complete_hand_shape_from_counts,
    tenpai_wait_tile_types as tenpai_wait_tile_types_from_counts,
    unique_terminal_honor_types_from_tiles,
};
use crate::tiles::{
    active_aka_dora_ids, counts_from_tiles, default_aka_dora_count, dora_from_indicator,
    is_legal_tile_type, is_red_tile, legal_tile_types_for_mode, normalize_aka_dora_count,
    read_counts_34, remove_tile_once, representative_tile_id, scoring_indicator_tile_id,
    tile_flags, tile_type, visible_counts_from_tiles, write_counts_34, TILE_ID_COUNT,
    TILE_TYPE_COUNT,
};

const ERR_INVALID_INPUT: i32 = -999;
// ctypes 侧把 None 当成“Rust 不可用或输入不适合 Rust 路径”的统一兜底信号。
// 因此所有返回 i32 的 FFI 函数都用同一个明显越界的哨兵值，而业务层的 false/0
// 仍然可以作为正常结果返回，不会和错误状态混在一起。

#[no_mangle]
pub extern "C" fn mahjong_core_version() -> u32 {
    30
}

#[no_mangle]
pub extern "C" fn mahjong_core_tile_type(tile_id: i32) -> i32 {
    tile_type(tile_id)
        .map(|value| value as i32)
        .unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_default_aka_dora_count(mode: u8) -> i32 {
    default_aka_dora_count(mode)
}

#[no_mangle]
pub extern "C" fn mahjong_core_normalize_aka_dora_count(
    mode: u8,
    ranked: u8,
    has_value: u8,
    value: i32,
) -> i32 {
    normalize_aka_dora_count(mode, ranked != 0, (has_value != 0).then_some(value))
}

#[no_mangle]
pub extern "C" fn mahjong_core_active_aka_dora_ids(
    mode: u8,
    count: i32,
    out_ids_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if out_ids_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let ids = active_aka_dora_ids(mode, count);
    if ids.len() > out_len {
        return ERR_INVALID_INPUT;
    }
    let out_ids = unsafe { std::slice::from_raw_parts_mut(out_ids_ptr, out_len) };
    out_ids.fill(-1);
    for (index, tile_id) in ids.iter().enumerate() {
        out_ids[index] = *tile_id;
    }
    ids.len() as i32
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_red_tile(mode: u8, count: i32, tile_id: i32) -> i32 {
    i32::from(is_red_tile(mode, count, tile_id))
}

#[no_mangle]
pub extern "C" fn mahjong_core_tile_flags(tile_index: i32) -> i32 {
    if tile_index < 0 {
        return ERR_INVALID_INPUT;
    }
    tile_flags(tile_index as usize)
        .map(i32::from)
        .unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_legal_tile_type(mode: u8, tile_index: i32) -> i32 {
    if tile_index < 0 {
        return 0;
    }
    i32::from(is_legal_tile_type(mode, tile_index as usize))
}

#[no_mangle]
pub extern "C" fn mahjong_core_legal_tile_types(
    mode: u8,
    out_types_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if out_types_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let types = legal_tile_types_for_mode(mode);
    if types.len() > out_len {
        return ERR_INVALID_INPUT;
    }
    let out_types = unsafe { std::slice::from_raw_parts_mut(out_types_ptr, out_len) };
    out_types.fill(-1);
    for (index, tile_type) in types.iter().enumerate() {
        out_types[index] = *tile_type as i32;
    }
    types.len() as i32
}

#[no_mangle]
pub extern "C" fn mahjong_core_representative_tile_id(
    tile_index: i32,
    blocked_ids_ptr: *const i32,
    blocked_ids_len: usize,
) -> i32 {
    if tile_index < 0 || blocked_ids_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let blocked_ids = unsafe { std::slice::from_raw_parts(blocked_ids_ptr, blocked_ids_len) };
    representative_tile_id(tile_index as usize, blocked_ids).unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_dora_from_indicator(mode: u8, indicator_tile_id: i32) -> i32 {
    dora_from_indicator(mode, indicator_tile_id)
        .map(|value| value as i32)
        .unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_scoring_indicator_tile_id(mode: u8, indicator_tile_id: i32) -> i32 {
    scoring_indicator_tile_id(mode, indicator_tile_id).unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_player_count(mode: u8) -> i32 {
    player_count(mode)
}

#[no_mangle]
pub extern "C" fn mahjong_core_next_seat(seat: i32, count: i32) -> i32 {
    next_seat(seat, count).unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_seat_distance(origin: i32, target: i32, count: i32) -> i32 {
    seat_distance(origin, target, count).unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_seat_wind_code(
    player_count: usize,
    dealer: usize,
    seat: usize,
) -> i32 {
    // 座风跨 FFI 只传编码：0=东、1=南、2=西、3=北。
    // Python 继续负责展示文字，这样旧的前端/日志格式不用跟着 Rust 改。
    seat_wind_code(player_count, dealer, seat)
        .map(i32::from)
        .unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_round_target_count(mode: u8, east_only: u8) -> i32 {
    round_target_count(mode, east_only != 0)
}

#[no_mangle]
pub extern "C" fn mahjong_core_max_round_count(mode: u8, east_only: u8) -> i32 {
    max_round_count(mode, east_only != 0)
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_win_like_round_result(kind_code: u8, subtype_code: u8) -> i32 {
    i32::from(is_win_like_round_result(kind_code, subtype_code))
}

#[no_mangle]
pub extern "C" fn mahjong_core_goal_score_reached(
    player_points_ptr: *const i32,
    player_points_len: usize,
    target_score: i32,
) -> i32 {
    if player_points_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let player_points = unsafe { std::slice::from_raw_parts(player_points_ptr, player_points_len) };
    i32::from(goal_score_reached(player_points, target_score))
}

#[no_mangle]
pub extern "C" fn mahjong_core_should_auto_stop_all_last_dealer(
    dealer_continues: u8,
    round_cursor: i32,
    base_rounds: i32,
    round_result_kind_code: u8,
    dealer_seat: usize,
    player_points_ptr: *const i32,
    player_points_len: usize,
    target_score: i32,
) -> i32 {
    // points 数组由 Python 按 seat 顺序传入，Rust 用同分低座位优先规则计算当前头名。
    // 返回 -999 只代表输入结构非法；正常的“不自动终局”仍返回 0。
    if player_points_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let player_points = unsafe { std::slice::from_raw_parts(player_points_ptr, player_points_len) };
    should_auto_stop_all_last_dealer(
        dealer_continues != 0,
        round_cursor,
        base_rounds,
        round_result_kind_code,
        dealer_seat,
        player_points,
        target_score,
    )
    .map(i32::from)
    .unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_ranked_settlement_scores(
    mode: u8,
    start_points: i32,
    points_ptr: *const i32,
    points_len: usize,
    out_point_score_tenths_ptr: *mut i32,
    out_uma_tenths_ptr: *mut i32,
    out_rank_score_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if points_ptr.is_null()
        || out_point_score_tenths_ptr.is_null()
        || out_uma_tenths_ptr.is_null()
        || out_rank_score_ptr.is_null()
    {
        return ERR_INVALID_INPUT;
    }
    let count = player_count(mode) as usize;
    if points_len != count || out_len < count {
        return ERR_INVALID_INPUT;
    }
    let points = unsafe { std::slice::from_raw_parts(points_ptr, points_len) };
    let Some(scores) = ranked_settlement_scores(mode, start_points, points) else {
        return ERR_INVALID_INPUT;
    };
    let point_out = unsafe { std::slice::from_raw_parts_mut(out_point_score_tenths_ptr, out_len) };
    let uma_out = unsafe { std::slice::from_raw_parts_mut(out_uma_tenths_ptr, out_len) };
    let rank_out = unsafe { std::slice::from_raw_parts_mut(out_rank_score_ptr, out_len) };
    for index in 0..count {
        point_out[index] = scores.point_score_tenths[index];
        uma_out[index] = scores.uma_tenths[index];
        rank_out[index] = scores.rank_score[index];
    }
    count as i32
}

#[no_mangle]
pub extern "C" fn mahjong_core_kuikae_forbidden_tile_types(
    action_type: u8,
    discard_tile_id: i32,
    consumed_ids_ptr: *const i32,
    consumed_ids_len: usize,
    out_types_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if consumed_ids_ptr.is_null() || out_types_ptr.is_null() || out_len < 2 {
        return ERR_INVALID_INPUT;
    }
    let consumed_ids = unsafe { std::slice::from_raw_parts(consumed_ids_ptr, consumed_ids_len) };
    let Some(forbidden) = kuikae_forbidden_tile_types(action_type, discard_tile_id, consumed_ids)
    else {
        return ERR_INVALID_INPUT;
    };
    if forbidden.len() > out_len {
        return ERR_INVALID_INPUT;
    }
    let out_types = unsafe { std::slice::from_raw_parts_mut(out_types_ptr, out_len) };
    out_types.fill(-1);
    for (index, tile_type) in forbidden.iter().enumerate() {
        out_types[index] = *tile_type as i32;
    }
    forbidden.len() as i32
}

#[no_mangle]
pub extern "C" fn mahjong_core_chi_candidate_pairs(
    hand_tiles_ptr: *const i32,
    hand_tiles_len: usize,
    discard_tile_id: i32,
    out_tile_ids_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if hand_tiles_ptr.is_null() || out_tile_ids_ptr.is_null() || out_len < 6 {
        return ERR_INVALID_INPUT;
    }
    let hand_tiles = unsafe { std::slice::from_raw_parts(hand_tiles_ptr, hand_tiles_len) };
    let Some(candidates) = chi_candidate_pairs(hand_tiles, discard_tile_id) else {
        return ERR_INVALID_INPUT;
    };
    if candidates.len() * 2 > out_len {
        return ERR_INVALID_INPUT;
    }
    let out_tile_ids = unsafe { std::slice::from_raw_parts_mut(out_tile_ids_ptr, out_len) };
    out_tile_ids.fill(-1);
    for (index, (left, right)) in candidates.iter().enumerate() {
        out_tile_ids[index * 2] = *left;
        out_tile_ids[index * 2 + 1] = *right;
    }
    candidates.len() as i32
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_furiten(
    win_tile_type: i32,
    discard_types_ptr: *const i32,
    discard_types_len: usize,
    temporary: u8,
    riichi: u8,
) -> i32 {
    // Python 传入的是弃牌“牌种”数组，不是实体牌 ID 数组。temporary/riichi 用 u8
    // 承载布尔值，是因为 C ABI 没有稳定的 Rust bool 布局承诺；0 视为 false，
    // 其他值都视为 true。
    if win_tile_type < 0 || discard_types_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let discard_types = unsafe { std::slice::from_raw_parts(discard_types_ptr, discard_types_len) };
    i32::from(is_furiten(
        win_tile_type as usize,
        discard_types,
        temporary != 0,
        riichi != 0,
    ))
}

#[no_mangle]
pub extern "C" fn mahjong_core_can_double_riichi(has_discards: u8, has_calls: u8) -> i32 {
    i32::from(can_double_riichi(has_discards != 0, has_calls != 0))
}

#[no_mangle]
pub extern "C" fn mahjong_core_pending_abortive_draw_kind(
    player_count: usize,
    first_discard_tiles_ptr: *const i32,
    first_discard_tiles_len: usize,
    discard_counts_ptr: *const i32,
    discard_counts_len: usize,
    riichi_flags_ptr: *const u8,
    riichi_flags_len: usize,
    has_calls: u8,
) -> i32 {
    // 三组数组都以 player_count 为逻辑长度读取：第一张弃牌实体 ID、每家弃牌数量、
    // 每家立直状态。Rust 不拥有这些内存，只在本函数调用期间借用 slice，所以不能
    // 把 slice 或指针保存到任何全局状态里。
    if first_discard_tiles_ptr.is_null()
        || discard_counts_ptr.is_null()
        || riichi_flags_ptr.is_null()
    {
        return ERR_INVALID_INPUT;
    }
    let first_discards =
        unsafe { std::slice::from_raw_parts(first_discard_tiles_ptr, first_discard_tiles_len) };
    let discard_counts =
        unsafe { std::slice::from_raw_parts(discard_counts_ptr, discard_counts_len) };
    let riichi_flags = unsafe { std::slice::from_raw_parts(riichi_flags_ptr, riichi_flags_len) };
    pending_abortive_draw_kind(
        player_count,
        first_discards,
        discard_counts,
        riichi_flags,
        has_calls != 0,
    )
    .unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_should_abort_for_four_kans(
    kan_count: i32,
    kan_owner_flags_ptr: *const u8,
    kan_owner_flags_len: usize,
) -> i32 {
    // owner_flags 是 Python 从 melds 里预先归纳出的“该座位是否拥有至少一个杠”。
    // FFI 层不解析 meld 字典，保持 Rust 核心只依赖扁平数组，后续更容易做批量迁移。
    if kan_owner_flags_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let owner_flags =
        unsafe { std::slice::from_raw_parts(kan_owner_flags_ptr, kan_owner_flags_len) };
    i32::from(should_abort_for_four_kans(kan_count, owner_flags))
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_tenhou_state(
    player_count: usize,
    seat: usize,
    dealer: usize,
    is_tsumo: u8,
    has_calls: u8,
    discard_counts_ptr: *const i32,
    discard_counts_len: usize,
) -> i32 {
    // discard_counts 是每家弃牌数量的扁平快照，Rust 只借用到函数返回为止。
    // 返回 -999 时 Python 会回到原来的字典判断，避免旧 DLL 或异常状态直接中断游戏。
    if discard_counts_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let discard_counts =
        unsafe { std::slice::from_raw_parts(discard_counts_ptr, discard_counts_len) };
    let Some(result) = is_tenhou_state(
        player_count,
        seat,
        dealer,
        is_tsumo != 0,
        has_calls != 0,
        discard_counts,
    ) else {
        return ERR_INVALID_INPUT;
    };
    i32::from(result)
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_chiihou_state(
    player_count: usize,
    seat: usize,
    dealer: usize,
    is_tsumo: u8,
    has_calls: u8,
    seat_discard_count: i32,
) -> i32 {
    let Some(result) = is_chiihou_state(
        player_count,
        seat,
        dealer,
        is_tsumo != 0,
        has_calls != 0,
        seat_discard_count,
    ) else {
        return ERR_INVALID_INPUT;
    };
    i32::from(result)
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_haitei_state(
    is_tsumo: u8,
    has_current_draw: u8,
    current_draw_from_wall: u8,
    turn_is_seat: u8,
    live_wall_empty: u8,
) -> i32 {
    i32::from(is_haitei_state(
        is_tsumo != 0,
        has_current_draw != 0,
        current_draw_from_wall != 0,
        turn_is_seat != 0,
        live_wall_empty != 0,
    ))
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_houtei_state(
    is_tsumo: u8,
    has_last_discard: u8,
    discard_from_replacement_source: u8,
    discarder_last_draw_from_wall: u8,
    live_wall_empty: u8,
) -> i32 {
    i32::from(is_houtei_state(
        is_tsumo != 0,
        has_last_discard != 0,
        discard_from_replacement_source != 0,
        discarder_last_draw_from_wall != 0,
        live_wall_empty != 0,
    ))
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_chankan_state(
    is_tsumo: u8,
    has_last_discard: u8,
    discard_source_is_kan: u8,
    kan_type_is_closed: u8,
) -> i32 {
    i32::from(is_chankan_state(
        is_tsumo != 0,
        has_last_discard != 0,
        discard_source_is_kan != 0,
        kan_type_is_closed != 0,
    ))
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_renhou_state(
    player_count: usize,
    seat: usize,
    dealer: usize,
    is_tsumo: u8,
    koyaku_enabled: u8,
    has_calls: u8,
    seat_has_last_draw_source: u8,
    has_last_discard: u8,
    last_discard_seat: usize,
    last_discard_from_replacement_source: u8,
    seat_discard_count: i32,
) -> i32 {
    // 人和需要的状态位比较多，但仍然都是标量：Python 负责从 round_state 中提取
    // “最后弃牌来自谁/是否补牌来源”等语义，Rust 只做纯规则组合和边界校验。
    let Some(result) = is_renhou_state(
        player_count,
        seat,
        dealer,
        is_tsumo != 0,
        koyaku_enabled != 0,
        has_calls != 0,
        seat_has_last_draw_source != 0,
        has_last_discard != 0,
        last_discard_seat,
        last_discard_from_replacement_source != 0,
        seat_discard_count,
    ) else {
        return ERR_INVALID_INPUT;
    };
    i32::from(result)
}

#[no_mangle]
pub extern "C" fn mahjong_core_can_abortive_draw_nine_terminals(
    phase_is_discard: u8,
    turn_is_seat: u8,
    has_current_draw: u8,
    seat_has_discards: u8,
    has_calls: u8,
    unique_terminal_honor_count: usize,
) -> i32 {
    i32::from(can_abortive_draw_nine_terminals(
        phase_is_discard != 0,
        turn_is_seat != 0,
        has_current_draw != 0,
        seat_has_discards != 0,
        has_calls != 0,
        unique_terminal_honor_count,
    ))
}

#[no_mangle]
pub extern "C" fn mahjong_core_unique_terminal_honor_types(
    tiles_ptr: *const i32,
    tiles_len: usize,
    out_types_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if tiles_ptr.is_null() || out_types_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let tiles = unsafe { std::slice::from_raw_parts(tiles_ptr, tiles_len) };
    let Some(types) = unique_terminal_honor_types_from_tiles(tiles) else {
        return ERR_INVALID_INPUT;
    };
    if types.len() > out_len {
        return ERR_INVALID_INPUT;
    }
    let out_types = unsafe { std::slice::from_raw_parts_mut(out_types_ptr, out_len) };
    out_types.fill(-1);
    for (index, tile_type) in types.iter().enumerate() {
        out_types[index] = *tile_type as i32;
    }
    types.len() as i32
}

#[no_mangle]
pub extern "C" fn mahjong_core_round_up_to_100(value: f64) -> i32 {
    round_up_to_100(value).unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_score_result_total(
    total: i32,
    main: i32,
    main_bonus: i32,
    additional: i32,
    additional_bonus: i32,
) -> i32 {
    let total = if total >= 0 { Some(total) } else { None };
    score_result_total(total, main, main_bonus, additional, additional_bonus)
}

#[no_mangle]
pub extern "C" fn mahjong_core_full_honba_value(mode: u8, honba: i32) -> i32 {
    full_honba_value(mode, honba)
}

#[no_mangle]
pub extern "C" fn mahjong_core_minimum_han_satisfied(
    han: i32,
    yakuman_total_han: i32,
    has_local_yaku: u8,
    minimum_han: i32,
) -> i32 {
    i32::from(minimum_han_satisfied(
        han,
        yakuman_total_han,
        has_local_yaku != 0,
        minimum_han,
    ))
}

#[no_mangle]
pub extern "C" fn mahjong_core_tsumo_payment_map(
    mode: u8,
    north_bisection: u8,
    player_count: usize,
    winner: usize,
    dealer: usize,
    main: i32,
    main_bonus: i32,
    additional: i32,
    additional_bonus: i32,
    out_payments_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if out_payments_ptr.is_null() || out_len < player_count || out_len > 4 {
        return ERR_INVALID_INPUT;
    }
    let Some(payments) = tsumo_payment_map(
        mode,
        north_bisection != 0,
        player_count,
        winner,
        dealer,
        main,
        main_bonus,
        additional,
        additional_bonus,
    ) else {
        return ERR_INVALID_INPUT;
    };
    let out_payments = unsafe { std::slice::from_raw_parts_mut(out_payments_ptr, out_len) };
    out_payments.fill(0);
    out_payments[..player_count].copy_from_slice(&payments[..player_count]);
    player_count as i32
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_nagashi_mangan_candidate(
    tile_ids_ptr: *const i32,
    tile_ids_len: usize,
    called_flags_ptr: *const u8,
    called_flags_len: usize,
) -> i32 {
    // tile_ids 与 called_flags 一一对应：called_flags[index] 非 0 表示这张弃牌被鸣。
    // 流局满贯不需要完整 round_state，把这两个紧凑数组传入即可让 Rust 复用规则。
    if tile_ids_ptr.is_null() || called_flags_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let tile_ids = unsafe { std::slice::from_raw_parts(tile_ids_ptr, tile_ids_len) };
    let called_flags = unsafe { std::slice::from_raw_parts(called_flags_ptr, called_flags_len) };
    let Some(result) = is_nagashi_mangan_candidate(tile_ids, called_flags) else {
        return ERR_INVALID_INPUT;
    };
    i32::from(result)
}

#[no_mangle]
pub extern "C" fn mahjong_core_liability_key_for_call(
    action_type: u8,
    called_tile_type: i32,
    same_seat: u8,
    has_daisangen_liability: u8,
    has_daisuushi_liability: u8,
    triplet_tile_types_ptr: *const i32,
    triplet_tile_types_len: usize,
) -> i32 {
    // triplet_tile_types 是 Python 从 melds 中抽出的刻子/杠子牌种列表；FFI 层不接收
    // meld 字典，也不判断副露是否 opened。返回 0/1/2 给 Python 映射成既有责任役 key。
    if triplet_tile_types_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let triplet_tile_types =
        unsafe { std::slice::from_raw_parts(triplet_tile_types_ptr, triplet_tile_types_len) };
    liability_key_for_call(
        action_type,
        called_tile_type,
        same_seat != 0,
        has_daisangen_liability != 0,
        has_daisuushi_liability != 0,
        triplet_tile_types,
    )
    .map(i32::from)
    .unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_liability_context_profile(
    player_count: usize,
    yakuman_total_han: i32,
    daisangen_eval_han: i32,
    daisangen_liable_seat: i32,
    daisangen_liability_han: i32,
    daisuushi_eval_han: i32,
    daisuushi_liable_seat: i32,
    daisuushi_liability_han: i32,
    out_profile_ptr: *mut i32,
    out_profile_len: usize,
) -> i32 {
    // out_profile 固定写入 4 个 i32：[liable_seat, liable_han, remainder_han, key_mask]。
    // key_mask 为 0 不是错误，而是“没有包牌上下文”；错误仍统一使用 -999。
    if out_profile_ptr.is_null() || out_profile_len < 4 {
        return ERR_INVALID_INPUT;
    }
    let Some(profile) = liability_context_profile(
        player_count,
        yakuman_total_han,
        daisangen_eval_han,
        daisangen_liable_seat,
        daisangen_liability_han,
        daisuushi_eval_han,
        daisuushi_liable_seat,
        daisuushi_liability_han,
    ) else {
        return ERR_INVALID_INPUT;
    };
    let out_profile = unsafe { std::slice::from_raw_parts_mut(out_profile_ptr, out_profile_len) };
    out_profile[..4].copy_from_slice(&profile);
    0
}

#[no_mangle]
pub extern "C" fn mahjong_core_local_mangan_yaku_code(
    koyaku_enabled: u8,
    is_tsumo: u8,
    is_haitei: u8,
    is_houtei: u8,
    win_tile_type: i32,
) -> i32 {
    // 返回小整数 code，Python 再映射成既有英文展示名；这样 FFI 不暴露字符串所有权。
    local_mangan_yaku_code(
        koyaku_enabled != 0,
        is_tsumo != 0,
        is_haitei != 0,
        is_houtei != 0,
        win_tile_type,
    )
    .map(i32::from)
    .unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_local_yakuman_yaku_code(
    koyaku_enabled: u8,
    double_riichi: u8,
    closed_hand: u8,
    is_haitei: u8,
    is_houtei: u8,
) -> i32 {
    i32::from(local_yakuman_yaku_code(
        koyaku_enabled != 0,
        double_riichi != 0,
        closed_hand != 0,
        is_haitei != 0,
        is_houtei != 0,
    ))
}

#[no_mangle]
pub extern "C" fn mahjong_core_local_han_yaku_mask(
    koyaku_enabled: u8,
    is_tsumo: u8,
    has_last_discard: u8,
    discard_is_self: u8,
    discard_from_replacement_source: u8,
    discard_riichi: u8,
    discard_follows_kan: u8,
) -> i32 {
    i32::from(local_han_yaku_mask(
        koyaku_enabled != 0,
        is_tsumo != 0,
        has_last_discard != 0,
        discard_is_self != 0,
        discard_from_replacement_source != 0,
        discard_riichi != 0,
        discard_follows_kan != 0,
    ))
}

#[no_mangle]
pub extern "C" fn mahjong_core_local_pattern_yaku_mask(
    flat_tiles_ptr: *const i32,
    flat_tiles_len: usize,
    group_lens_ptr: *const usize,
    group_lens_len: usize,
) -> i32 {
    // hand groups 经 Python 压平成两段数组：所有牌种 flat_tiles，以及每组长度 group_lens。
    // Rust 根据 group_lens 还原边界；如果长度总和不匹配，返回 -999 让 Python 兜底。
    if flat_tiles_ptr.is_null() || group_lens_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let flat_tiles = unsafe { std::slice::from_raw_parts(flat_tiles_ptr, flat_tiles_len) };
    let group_lens = unsafe { std::slice::from_raw_parts(group_lens_ptr, group_lens_len) };
    local_pattern_yaku_mask(flat_tiles, group_lens)
        .map(i32::from)
        .unwrap_or(ERR_INVALID_INPUT)
}

#[no_mangle]
pub extern "C" fn mahjong_core_counts_from_tiles(
    tiles_ptr: *const i32,
    tiles_len: usize,
    out_counts_ptr: *mut u8,
    out_counts_len: usize,
) -> i32 {
    if tiles_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let tiles = unsafe { std::slice::from_raw_parts(tiles_ptr, tiles_len) };
    let Some(counts) = counts_from_tiles(tiles) else {
        return ERR_INVALID_INPUT;
    };
    if !write_counts_34(&counts, out_counts_ptr, out_counts_len) {
        return ERR_INVALID_INPUT;
    }
    0
}

#[no_mangle]
pub extern "C" fn mahjong_core_visible_counts_from_tiles(
    mode: u8,
    tiles_ptr: *const i32,
    tiles_len: usize,
    out_counts_ptr: *mut u8,
    out_counts_len: usize,
) -> i32 {
    if tiles_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let tiles = unsafe { std::slice::from_raw_parts(tiles_ptr, tiles_len) };
    let Some(counts) = visible_counts_from_tiles(mode, tiles) else {
        return ERR_INVALID_INPUT;
    };
    if !write_counts_34(&counts, out_counts_ptr, out_counts_len) {
        return ERR_INVALID_INPUT;
    }
    0
}

#[no_mangle]
pub extern "C" fn mahjong_core_tile_value_bonus(
    discard_tile_id: i32,
    is_red: u8,
    own_wind_type: i32,
    round_wind_type: i32,
    dora_mask_ptr: *const u8,
    dora_mask_len: usize,
) -> f64 {
    let Some(dora_mask) = read_counts_34(dora_mask_ptr, dora_mask_len) else {
        return ERR_INVALID_INPUT as f64;
    };
    if own_wind_type < 0 || round_wind_type < 0 {
        return ERR_INVALID_INPUT as f64;
    }
    tile_value_bonus(
        discard_tile_id,
        is_red != 0,
        own_wind_type as usize,
        round_wind_type as usize,
        &dora_mask,
    )
    .unwrap_or(ERR_INVALID_INPUT as f64)
}

#[no_mangle]
pub extern "C" fn mahjong_core_shanten_34(counts_ptr: *const u8, counts_len: usize) -> i32 {
    let Some(counts) = read_counts_34(counts_ptr, counts_len) else {
        return ERR_INVALID_INPUT;
    };
    calculate_shanten(&counts)
}

#[no_mangle]
pub extern "C" fn mahjong_core_is_complete_hand_shape(
    mode: u8,
    counts_ptr: *const u8,
    counts_len: usize,
    meld_count: i32,
) -> i32 {
    let Some(counts) = read_counts_34(counts_ptr, counts_len) else {
        return ERR_INVALID_INPUT;
    };
    if !(0..=4).contains(&meld_count) {
        return ERR_INVALID_INPUT;
    }
    i32::from(complete_hand_shape_from_counts(mode, &counts, meld_count))
}

#[no_mangle]
pub extern "C" fn mahjong_core_tenpai_waits_from_counts(
    mode: u8,
    concealed_counts_ptr: *const u8,
    concealed_counts_len: usize,
    owned_counts_ptr: *const u8,
    owned_counts_len: usize,
    meld_count: i32,
    out_wait_mask_ptr: *mut u8,
    out_wait_mask_len: usize,
) -> i32 {
    if out_wait_mask_ptr.is_null() || out_wait_mask_len != TILE_TYPE_COUNT {
        return ERR_INVALID_INPUT;
    }
    let Some(concealed_counts) = read_counts_34(concealed_counts_ptr, concealed_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(owned_counts) = read_counts_34(owned_counts_ptr, owned_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    if !(0..=4).contains(&meld_count)
        || (0..TILE_TYPE_COUNT).any(|index| owned_counts[index] < concealed_counts[index])
    {
        return ERR_INVALID_INPUT;
    }

    let waits =
        tenpai_wait_tile_types_from_counts(mode, &concealed_counts, &owned_counts, meld_count);
    let wait_mask_out =
        unsafe { std::slice::from_raw_parts_mut(out_wait_mask_ptr, out_wait_mask_len) };
    wait_mask_out.copy_from_slice(&waits.mask);
    waits.count
}

#[no_mangle]
pub extern "C" fn mahjong_core_effective_tiles_after_discard(
    mode: u8,
    source_tiles_ptr: *const i32,
    source_tiles_len: usize,
    discard_tile_id: i32,
    visible_counts_ptr: *const u8,
    visible_counts_len: usize,
    base_shanten: i32,
    out_remaining_ptr: *mut i32,
    out_next_shanten_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if source_tiles_ptr.is_null()
        || out_remaining_ptr.is_null()
        || out_next_shanten_ptr.is_null()
        || out_len != TILE_TYPE_COUNT
    {
        return ERR_INVALID_INPUT;
    }

    let source_tiles = unsafe { std::slice::from_raw_parts(source_tiles_ptr, source_tiles_len) };
    let Some(tiles_after_discard) = remove_tile_once(source_tiles, discard_tile_id) else {
        clear_i32_output(out_remaining_ptr, out_next_shanten_ptr, out_len);
        return 0;
    };
    let Some(counts) = counts_from_tiles(&tiles_after_discard) else {
        return ERR_INVALID_INPUT;
    };
    let Some(visible_counts) = read_counts_34(visible_counts_ptr, visible_counts_len) else {
        return ERR_INVALID_INPUT;
    };

    let used_counts = [0_u8; TILE_TYPE_COUNT];
    write_effective_result(
        effective_tiles_from_counts(
            mode,
            &counts,
            &visible_counts,
            &used_counts,
            normalize_base_shanten(base_shanten),
        ),
        out_remaining_ptr,
        out_next_shanten_ptr,
        out_len,
    )
}

#[no_mangle]
pub extern "C" fn mahjong_core_effective_tiles_from_counts(
    mode: u8,
    counts_ptr: *const u8,
    counts_len: usize,
    visible_counts_ptr: *const u8,
    visible_counts_len: usize,
    used_counts_ptr: *const u8,
    used_counts_len: usize,
    base_shanten: i32,
    out_remaining_ptr: *mut i32,
    out_next_shanten_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if out_remaining_ptr.is_null() || out_next_shanten_ptr.is_null() || out_len != TILE_TYPE_COUNT {
        return ERR_INVALID_INPUT;
    }
    let Some(counts) = read_counts_34(counts_ptr, counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(visible_counts) = read_counts_34(visible_counts_ptr, visible_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(used_counts) = read_counts_34(used_counts_ptr, used_counts_len) else {
        return ERR_INVALID_INPUT;
    };

    write_effective_result(
        effective_tiles_from_counts(
            mode,
            &counts,
            &visible_counts,
            &used_counts,
            normalize_base_shanten(base_shanten),
        ),
        out_remaining_ptr,
        out_next_shanten_ptr,
        out_len,
    )
}

#[no_mangle]
pub extern "C" fn mahjong_core_draw_tiles_from_counts(
    mode: u8,
    counts_ptr: *const u8,
    counts_len: usize,
    visible_counts_ptr: *const u8,
    visible_counts_len: usize,
    used_counts_ptr: *const u8,
    used_counts_len: usize,
    out_remaining_ptr: *mut i32,
    out_next_shanten_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    if out_remaining_ptr.is_null() || out_next_shanten_ptr.is_null() || out_len != TILE_TYPE_COUNT {
        return ERR_INVALID_INPUT;
    }
    let Some(counts) = read_counts_34(counts_ptr, counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(visible_counts) = read_counts_34(visible_counts_ptr, visible_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(used_counts) = read_counts_34(used_counts_ptr, used_counts_len) else {
        return ERR_INVALID_INPUT;
    };

    write_effective_result(
        draw_tiles_from_counts(mode, &counts, &visible_counts, &used_counts),
        out_remaining_ptr,
        out_next_shanten_ptr,
        out_len,
    )
}

#[no_mangle]
pub extern "C" fn mahjong_core_hand_route_profile(
    concealed_counts_ptr: *const u8,
    concealed_counts_len: usize,
    all_counts_ptr: *const u8,
    all_counts_len: usize,
    value_honor_mask_ptr: *const u8,
    value_honor_mask_len: usize,
    triplet_meld_count: i32,
    value_honor_triplet_meld_count: i32,
    closed: u8,
    has_melds: u8,
    shanten_value: i32,
    out_route_mask_ptr: *mut u32,
) -> i32 {
    if out_route_mask_ptr.is_null() {
        return ERR_INVALID_INPUT;
    }
    let Some(concealed_counts) = read_counts_34(concealed_counts_ptr, concealed_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(all_counts) = read_counts_34(all_counts_ptr, all_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(value_honor_mask) = read_counts_34(value_honor_mask_ptr, value_honor_mask_len) else {
        return ERR_INVALID_INPUT;
    };

    let (bonus_milli, route_mask) = hand_route_profile_from_counts(
        &concealed_counts,
        &all_counts,
        &value_honor_mask,
        triplet_meld_count,
        value_honor_triplet_meld_count,
        closed != 0,
        has_melds != 0,
        shanten_value,
    );
    unsafe {
        *out_route_mask_ptr = route_mask;
    }
    bonus_milli
}

#[no_mangle]
pub extern "C" fn mahjong_core_hand_route_profiles_after_discards(
    mode: u8,
    source_concealed_counts_ptr: *const u8,
    source_concealed_counts_len: usize,
    meld_counts_ptr: *const u8,
    meld_counts_len: usize,
    value_honor_mask_ptr: *const u8,
    value_honor_mask_len: usize,
    shanten_by_discard_ptr: *const i32,
    shanten_by_discard_len: usize,
    triplet_meld_count: i32,
    value_honor_triplet_meld_count: i32,
    closed: u8,
    has_melds: u8,
    out_bonus_milli_ptr: *mut i32,
    out_route_mask_ptr: *mut u32,
    out_len: usize,
) -> i32 {
    if out_bonus_milli_ptr.is_null() || out_route_mask_ptr.is_null() || out_len != TILE_TYPE_COUNT {
        return ERR_INVALID_INPUT;
    }
    let Some(source_concealed_counts) =
        read_counts_34(source_concealed_counts_ptr, source_concealed_counts_len)
    else {
        return ERR_INVALID_INPUT;
    };
    let Some(meld_counts) = read_counts_34(meld_counts_ptr, meld_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(value_honor_mask) = read_counts_34(value_honor_mask_ptr, value_honor_mask_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(shanten_by_discard) = read_i32_34(shanten_by_discard_ptr, shanten_by_discard_len)
    else {
        return ERR_INVALID_INPUT;
    };

    let result = hand_route_profiles_after_discards(
        mode,
        &source_concealed_counts,
        &meld_counts,
        &value_honor_mask,
        triplet_meld_count,
        value_honor_triplet_meld_count,
        closed != 0,
        has_melds != 0,
        &shanten_by_discard,
    );
    let bonus_out = unsafe { std::slice::from_raw_parts_mut(out_bonus_milli_ptr, out_len) };
    let mask_out = unsafe { std::slice::from_raw_parts_mut(out_route_mask_ptr, out_len) };
    bonus_out.copy_from_slice(&result.bonus_milli);
    mask_out.copy_from_slice(&result.route_mask);
    0
}

#[no_mangle]
pub extern "C" fn mahjong_core_discard_metrics_from_counts(
    mode: u8,
    source_counts_ptr: *const u8,
    source_counts_len: usize,
    base_visible_counts_ptr: *const u8,
    base_visible_counts_len: usize,
    out_shanten_ptr: *mut i32,
    out_ukeire_ptr: *mut i32,
    out_remaining_matrix_ptr: *mut i32,
    out_counts_len: usize,
    out_matrix_len: usize,
) -> i32 {
    if out_shanten_ptr.is_null()
        || out_ukeire_ptr.is_null()
        || out_remaining_matrix_ptr.is_null()
        || out_counts_len != TILE_TYPE_COUNT
        || out_matrix_len != TILE_TYPE_COUNT * TILE_TYPE_COUNT
    {
        return ERR_INVALID_INPUT;
    }
    let Some(source_counts) = read_counts_34(source_counts_ptr, source_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(base_visible_counts) =
        read_counts_34(base_visible_counts_ptr, base_visible_counts_len)
    else {
        return ERR_INVALID_INPUT;
    };

    let result = discard_metrics_from_counts(mode, &source_counts, &base_visible_counts);
    let shanten_out = unsafe { std::slice::from_raw_parts_mut(out_shanten_ptr, out_counts_len) };
    let ukeire_out = unsafe { std::slice::from_raw_parts_mut(out_ukeire_ptr, out_counts_len) };
    let remaining_matrix_out =
        unsafe { std::slice::from_raw_parts_mut(out_remaining_matrix_ptr, out_matrix_len) };
    shanten_out.copy_from_slice(&result.shanten);
    ukeire_out.copy_from_slice(&result.ukeire);
    remaining_matrix_out.copy_from_slice(&result.remaining_matrix);
    0
}

#[no_mangle]
pub extern "C" fn mahjong_core_tile_danger_for_opponent(
    visible_counts_ptr: *const u8,
    visible_counts_len: usize,
    opponent_discards_ptr: *const u8,
    opponent_discards_len: usize,
    value_honor_mask_ptr: *const u8,
    value_honor_mask_len: usize,
    dora_mask_ptr: *const u8,
    dora_mask_len: usize,
    red_tile_mask_ptr: *const u8,
    red_tile_mask_len: usize,
    threat: f64,
    estimated_loss: i32,
    progress: f64,
    threat_type: u8,
    threat_level: u8,
    flush_suit: i32,
    flush_with_honors: u8,
    toitoi: u8,
    tanyao_route: u8,
    yakuhai_route: u8,
    riichi: u8,
    open_meld_count: i32,
    out_danger_ptr: *mut f64,
    out_len: usize,
) -> i32 {
    if out_danger_ptr.is_null() || out_len != TILE_ID_COUNT as usize {
        return ERR_INVALID_INPUT;
    }
    let Some(visible_counts) = read_counts_34(visible_counts_ptr, visible_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(opponent_discards) = read_counts_34(opponent_discards_ptr, opponent_discards_len)
    else {
        return ERR_INVALID_INPUT;
    };
    let Some(value_honor_mask) = read_counts_34(value_honor_mask_ptr, value_honor_mask_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(dora_mask) = read_counts_34(dora_mask_ptr, dora_mask_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(red_tile_mask) = read_mask_136(red_tile_mask_ptr, red_tile_mask_len) else {
        return ERR_INVALID_INPUT;
    };

    let input = DangerInput {
        visible_counts: &visible_counts,
        opponent_discards: &opponent_discards,
        value_honor_mask: &value_honor_mask,
        dora_mask: &dora_mask,
        red_tile_mask: &red_tile_mask,
        threat,
        estimated_loss,
        progress,
        threat_type,
        threat_level,
        flush_suit,
        flush_with_honors: flush_with_honors != 0,
        toitoi: toitoi != 0,
        tanyao_route: tanyao_route != 0,
        yakuhai_route: yakuhai_route != 0,
        riichi: riichi != 0,
        open_meld_count,
    };
    let danger = tile_danger_table(&input);
    let out = unsafe { std::slice::from_raw_parts_mut(out_danger_ptr, out_len) };
    out.copy_from_slice(&danger);
    0
}

#[no_mangle]
pub extern "C" fn mahjong_core_aggregate_safety_scores(
    visible_counts_ptr: *const u8,
    visible_counts_len: usize,
    opponent_discards_ptr: *const u8,
    opponent_discards_len: usize,
    value_honor_masks_ptr: *const u8,
    value_honor_masks_len: usize,
    weights_ptr: *const f64,
    weights_len: usize,
    tanyao_routes_ptr: *const u8,
    tanyao_routes_len: usize,
    opponent_count: usize,
    out_scores_ptr: *mut f64,
    out_scores_len: usize,
) -> i32 {
    if out_scores_ptr.is_null()
        || out_scores_len != TILE_TYPE_COUNT
        || weights_ptr.is_null()
        || weights_len != opponent_count
        || tanyao_routes_ptr.is_null()
        || tanyao_routes_len != opponent_count
    {
        return ERR_INVALID_INPUT;
    }
    let Some(visible_counts) = read_counts_34(visible_counts_ptr, visible_counts_len) else {
        return ERR_INVALID_INPUT;
    };
    let Some(opponent_discards) =
        read_mask_rows_34(opponent_discards_ptr, opponent_discards_len, opponent_count)
    else {
        return ERR_INVALID_INPUT;
    };
    let Some(value_honor_masks) =
        read_mask_rows_34(value_honor_masks_ptr, value_honor_masks_len, opponent_count)
    else {
        return ERR_INVALID_INPUT;
    };
    let weights = unsafe { std::slice::from_raw_parts(weights_ptr, weights_len) };
    let tanyao_routes = unsafe { std::slice::from_raw_parts(tanyao_routes_ptr, tanyao_routes_len) };
    let scores = aggregate_safety_scores(
        &visible_counts,
        &opponent_discards,
        &value_honor_masks,
        weights,
        tanyao_routes,
    );
    let out = unsafe { std::slice::from_raw_parts_mut(out_scores_ptr, out_scores_len) };
    out.copy_from_slice(&scores);
    0
}

#[no_mangle]
pub extern "C" fn mahjong_core_safe_tile_reserve_profile(
    mode: u8,
    remaining_tiles_ptr: *const i32,
    remaining_tiles_len: usize,
    discarded_tile_id: i32,
    shanten_value: i32,
    progress: f64,
    max_pressure: f64,
    aggregate_scores_ptr: *const f64,
    aggregate_scores_len: usize,
    out_ev_ptr: *mut f64,
    out_score_ptr: *mut f64,
    out_label_code_ptr: *mut u8,
) -> i32 {
    if remaining_tiles_ptr.is_null()
        || aggregate_scores_ptr.is_null()
        || aggregate_scores_len != TILE_TYPE_COUNT
        || out_ev_ptr.is_null()
        || out_score_ptr.is_null()
        || out_label_code_ptr.is_null()
    {
        return ERR_INVALID_INPUT;
    }
    let remaining_tiles =
        unsafe { std::slice::from_raw_parts(remaining_tiles_ptr, remaining_tiles_len) };
    let aggregate_slice =
        unsafe { std::slice::from_raw_parts(aggregate_scores_ptr, aggregate_scores_len) };
    let mut aggregate_scores = [0.0_f64; TILE_TYPE_COUNT];
    aggregate_scores.copy_from_slice(aggregate_slice);

    let Some(result) = safe_tile_reserve_profile(
        mode,
        remaining_tiles,
        discarded_tile_id,
        shanten_value,
        progress,
        max_pressure,
        &aggregate_scores,
    ) else {
        return ERR_INVALID_INPUT;
    };
    unsafe {
        *out_ev_ptr = result.ev;
        *out_score_ptr = result.reserve_score;
        *out_label_code_ptr = result.label_code;
    }
    0
}

#[no_mangle]
pub extern "C" fn mahjong_core_safe_tile_reserve_profiles_after_discards(
    mode: u8,
    source_tiles_ptr: *const i32,
    source_tiles_len: usize,
    shanten_by_discard_ptr: *const i32,
    shanten_by_discard_len: usize,
    progress: f64,
    max_pressure: f64,
    aggregate_scores_ptr: *const f64,
    aggregate_scores_len: usize,
    out_ev_ptr: *mut f64,
    out_score_ptr: *mut f64,
    out_label_code_ptr: *mut u8,
    out_len: usize,
) -> i32 {
    if source_tiles_ptr.is_null()
        || aggregate_scores_ptr.is_null()
        || aggregate_scores_len != TILE_TYPE_COUNT
        || out_ev_ptr.is_null()
        || out_score_ptr.is_null()
        || out_label_code_ptr.is_null()
        || out_len != TILE_TYPE_COUNT
    {
        return ERR_INVALID_INPUT;
    }
    let source_tiles = unsafe { std::slice::from_raw_parts(source_tiles_ptr, source_tiles_len) };
    let Some(shanten_by_discard) = read_i32_34(shanten_by_discard_ptr, shanten_by_discard_len)
    else {
        return ERR_INVALID_INPUT;
    };
    let aggregate_slice =
        unsafe { std::slice::from_raw_parts(aggregate_scores_ptr, aggregate_scores_len) };
    let mut aggregate_scores = [0.0_f64; TILE_TYPE_COUNT];
    aggregate_scores.copy_from_slice(aggregate_slice);

    let Some(result) = safe_tile_reserve_profiles_after_discards(
        mode,
        source_tiles,
        &shanten_by_discard,
        progress,
        max_pressure,
        &aggregate_scores,
    ) else {
        return ERR_INVALID_INPUT;
    };

    let ev_out = unsafe { std::slice::from_raw_parts_mut(out_ev_ptr, out_len) };
    let score_out = unsafe { std::slice::from_raw_parts_mut(out_score_ptr, out_len) };
    let label_out = unsafe { std::slice::from_raw_parts_mut(out_label_code_ptr, out_len) };
    ev_out.copy_from_slice(&result.ev);
    score_out.copy_from_slice(&result.reserve_score);
    label_out.copy_from_slice(&result.label_code);
    0
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn mahjong_core_structured_discard_ev(
    shanten_value: i32,
    ukeire: i32,
    risk: f64,
    value_penalty: f64,
    route_bonus: f64,
    route_count: i32,
    level: i32,
    progress: f64,
    max_loss: i32,
    max_threat: f64,
    max_push_pressure: f64,
    own_points: i32,
    top_points: i32,
    bottom_points: i32,
    is_dealer: u8,
    is_closed: u8,
    live_tile_count: i32,
    strategy_scale: f64,
    attack_bias: f64,
    defense_bias: f64,
    value_bias: f64,
    placement: i32,
    placement_count: i32,
    gap_to_above: i32,
    is_all_last: u8,
    level_one_noise: f64,
    out_values_ptr: *mut f64,
    out_len: usize,
) -> i32 {
    if out_values_ptr.is_null() || out_len != 5 || !(1..=3).contains(&level) {
        return ERR_INVALID_INPUT;
    }
    let output = structured_discard_ev(&StructuredDiscardInput {
        shanten_value,
        ukeire,
        risk,
        value_penalty,
        route_bonus,
        route_count,
        level,
        progress,
        max_loss,
        max_threat,
        max_push_pressure,
        own_points,
        top_points,
        bottom_points,
        is_dealer: is_dealer != 0,
        is_closed: is_closed != 0,
        live_tile_count,
        strategy_scale,
        attack_bias,
        defense_bias,
        value_bias,
        placement,
        placement_count,
        gap_to_above,
        is_all_last: is_all_last != 0,
        level_one_noise,
    });
    let out = unsafe { std::slice::from_raw_parts_mut(out_values_ptr, out_len) };
    out[0] = output.speed_ev;
    out[1] = output.value_ev;
    out[2] = output.defense_ev;
    out[3] = output.table_ev;
    out[4] = output.final_ev;
    0
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn mahjong_core_push_fold_profile(
    shanten_value: i32,
    risk: f64,
    safety_score: f64,
    hand_value_ev: f64,
    estimated_han: f64,
    wait_quality: f64,
    progress: f64,
    max_threat: f64,
    max_push_pressure: f64,
    max_loss: i32,
    riichi_count: i32,
    critical_count: i32,
    high_count: i32,
    defense_scale: f64,
    strategy_scale: f64,
    attack_bias: f64,
    defense_bias: f64,
    value_bias: f64,
    is_dealer: u8,
    placement: i32,
    placement_count: i32,
    is_all_last: u8,
    out_values_ptr: *mut f64,
    out_codes_ptr: *mut u8,
    out_values_len: usize,
    out_codes_len: usize,
) -> i32 {
    if out_values_ptr.is_null()
        || out_codes_ptr.is_null()
        || out_values_len != 3
        || out_codes_len != 2
    {
        return ERR_INVALID_INPUT;
    }
    let output = push_fold_profile(&PushFoldInput {
        shanten_value,
        risk,
        safety_score,
        hand_value_ev,
        estimated_han,
        wait_quality,
        progress,
        max_threat,
        max_push_pressure,
        max_loss,
        riichi_count,
        critical_count,
        high_count,
        defense_scale,
        strategy_scale,
        attack_bias,
        defense_bias,
        value_bias,
        is_dealer: is_dealer != 0,
        placement,
        placement_count,
        is_all_last: is_all_last != 0,
    });
    let values_out = unsafe { std::slice::from_raw_parts_mut(out_values_ptr, out_values_len) };
    let codes_out = unsafe { std::slice::from_raw_parts_mut(out_codes_ptr, out_codes_len) };
    values_out[0] = output.ev;
    values_out[1] = output.pressure;
    values_out[2] = output.commitment;
    codes_out[0] = output.mode_code;
    codes_out[1] = output.label_code;
    0
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn mahjong_core_defense_override_profile(
    shanten_value: i32,
    risk: f64,
    safety_score: f64,
    hand_value_ev: f64,
    estimated_han: f64,
    wait_quality: f64,
    level: i32,
    progress: f64,
    max_threat: f64,
    max_push_pressure: f64,
    max_loss: i32,
    riichi_count: i32,
    critical_count: i32,
    high_count: i32,
    open_monster_count: i32,
    attack_bias: f64,
    defense_bias: f64,
    value_bias: f64,
    placement: i32,
    placement_count: i32,
    is_all_last: u8,
    out_values_ptr: *mut f64,
    out_codes_ptr: *mut u8,
    out_values_len: usize,
    out_codes_len: usize,
) -> i32 {
    if out_values_ptr.is_null()
        || out_codes_ptr.is_null()
        || out_values_len != 2
        || out_codes_len != 2
        || level <= 1
    {
        return ERR_INVALID_INPUT;
    }
    let output = defense_override_profile(&DefenseOverrideInput {
        shanten_value,
        risk,
        safety_score,
        hand_value_ev,
        estimated_han,
        wait_quality,
        level,
        progress,
        max_threat,
        max_push_pressure,
        max_loss,
        riichi_count,
        critical_count,
        high_count,
        open_monster_count,
        attack_bias,
        defense_bias,
        value_bias,
        placement,
        placement_count,
        is_all_last: is_all_last != 0,
    });
    let values_out = unsafe { std::slice::from_raw_parts_mut(out_values_ptr, out_values_len) };
    let codes_out = unsafe { std::slice::from_raw_parts_mut(out_codes_ptr, out_codes_len) };
    values_out[0] = output.ev;
    values_out[1] = output.fold_need;
    codes_out[0] = output.mode_code;
    codes_out[1] = output.label_code;
    0
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn mahjong_core_deal_in_loss_profile(
    dangers_ptr: *const f64,
    safeties_ptr: *const f64,
    push_pressures_ptr: *const f64,
    estimated_losses_ptr: *const i32,
    threat_level_codes_ptr: *const u8,
    threat_type_codes_ptr: *const u8,
    item_len: usize,
    progress: f64,
    out_values_ptr: *mut f64,
    out_top_index_ptr: *mut i32,
    out_values_len: usize,
) -> i32 {
    if dangers_ptr.is_null()
        || safeties_ptr.is_null()
        || push_pressures_ptr.is_null()
        || estimated_losses_ptr.is_null()
        || threat_level_codes_ptr.is_null()
        || threat_type_codes_ptr.is_null()
        || out_values_ptr.is_null()
        || out_top_index_ptr.is_null()
        || out_values_len != 3
    {
        return ERR_INVALID_INPUT;
    }
    let dangers = unsafe { std::slice::from_raw_parts(dangers_ptr, item_len) };
    let safeties = unsafe { std::slice::from_raw_parts(safeties_ptr, item_len) };
    let push_pressures = unsafe { std::slice::from_raw_parts(push_pressures_ptr, item_len) };
    let estimated_losses = unsafe { std::slice::from_raw_parts(estimated_losses_ptr, item_len) };
    let threat_level_codes =
        unsafe { std::slice::from_raw_parts(threat_level_codes_ptr, item_len) };
    let threat_type_codes = unsafe { std::slice::from_raw_parts(threat_type_codes_ptr, item_len) };
    let output = deal_in_loss_profile(&DealInLossInput {
        dangers,
        safeties,
        push_pressures,
        estimated_losses,
        threat_level_codes,
        threat_type_codes,
        progress,
    });
    let values_out = unsafe { std::slice::from_raw_parts_mut(out_values_ptr, out_values_len) };
    values_out[0] = output.loss_ev;
    values_out[1] = output.max_rate;
    values_out[2] = output.total_expected_points as f64;
    unsafe {
        *out_top_index_ptr = output.top_index;
    }
    0
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn mahjong_core_defensive_discard_profile(
    safety_score: f64,
    shanten_value: i32,
    level_scale: f64,
    progress: f64,
    max_threat: f64,
    max_push_pressure: f64,
    max_loss: i32,
    high_threat_count: i32,
    out_values_ptr: *mut f64,
    out_defense_mode_ptr: *mut u8,
    out_values_len: usize,
) -> i32 {
    if out_values_ptr.is_null() || out_defense_mode_ptr.is_null() || out_values_len != 2 {
        return ERR_INVALID_INPUT;
    }
    let output = defensive_discard_profile(&DefensiveDiscardInput {
        safety_score,
        shanten_value,
        level_scale,
        progress,
        max_threat,
        max_push_pressure,
        max_loss,
        high_threat_count,
    });
    let values_out = unsafe { std::slice::from_raw_parts_mut(out_values_ptr, out_values_len) };
    values_out[0] = output.safety_score;
    values_out[1] = output.safety_ev;
    unsafe {
        *out_defense_mode_ptr = if output.defense_mode { 1 } else { 0 };
    }
    0
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn mahjong_core_global_reward_delta_profile(
    points_ptr: *const i32,
    points_len: usize,
    seat: usize,
    shanten_value: i32,
    ukeire: i32,
    wait_quality: f64,
    estimated_value: i32,
    estimated_han: f64,
    deal_in_rate: f64,
    deal_in_points: i32,
    level: i32,
    progress: f64,
    riichi_sticks: i32,
    honba: i32,
    placement: i32,
    placement_count: i32,
    is_all_last: u8,
    out_values_ptr: *mut f64,
    out_rank_deltas_ptr: *mut i32,
    out_values_len: usize,
    out_rank_deltas_len: usize,
) -> i32 {
    if points_ptr.is_null()
        || out_values_ptr.is_null()
        || out_rank_deltas_ptr.is_null()
        || out_values_len != 1
        || out_rank_deltas_len != 2
        || points_len == 0
        || points_len > 4
        || seat >= points_len
        || !(1..=3).contains(&level)
    {
        return ERR_INVALID_INPUT;
    }
    let points = unsafe { std::slice::from_raw_parts(points_ptr, points_len) };
    let Some(output) = global_reward_delta_profile(&GlobalRewardInput {
        points,
        seat,
        shanten_value,
        ukeire,
        wait_quality,
        estimated_value,
        estimated_han,
        deal_in_rate,
        deal_in_points,
        level,
        progress,
        riichi_sticks,
        honba,
        placement,
        placement_count,
        is_all_last: is_all_last != 0,
    }) else {
        return ERR_INVALID_INPUT;
    };
    let values_out = unsafe { std::slice::from_raw_parts_mut(out_values_ptr, out_values_len) };
    let rank_deltas_out =
        unsafe { std::slice::from_raw_parts_mut(out_rank_deltas_ptr, out_rank_deltas_len) };
    values_out[0] = output.ev;
    rank_deltas_out[0] = output.win_rank_delta;
    rank_deltas_out[1] = output.loss_rank_delta;
    0
}

#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "C" fn mahjong_core_alpha_terminal_projection_ev(
    shanten_value: i32,
    ukeire: i32,
    route_bonus: f64,
    hand_value_ev: f64,
    attack_bias: f64,
    defense_bias: f64,
    value_bias: f64,
    max_threat: f64,
    max_push_pressure: f64,
    max_loss: i32,
    wait_quality: f64,
    level: i32,
    out_value_ptr: *mut f64,
) -> i32 {
    if out_value_ptr.is_null() || !(1..=3).contains(&level) {
        return ERR_INVALID_INPUT;
    }
    let output = alpha_terminal_projection_ev(&AlphaTerminalInput {
        shanten_value,
        ukeire,
        route_bonus,
        hand_value_ev,
        attack_bias,
        defense_bias,
        value_bias,
        max_threat,
        max_push_pressure,
        max_loss,
        wait_quality,
        level,
    });
    unsafe {
        *out_value_ptr = output;
    }
    0
}

fn normalize_base_shanten(base_shanten: i32) -> Option<i32> {
    (-1..=8).contains(&base_shanten).then_some(base_shanten)
}

fn write_effective_result(
    result: crate::analysis::EffectiveTiles,
    out_remaining_ptr: *mut i32,
    out_next_shanten_ptr: *mut i32,
    out_len: usize,
) -> i32 {
    let remaining_out = unsafe { std::slice::from_raw_parts_mut(out_remaining_ptr, out_len) };
    let next_shanten_out = unsafe { std::slice::from_raw_parts_mut(out_next_shanten_ptr, out_len) };
    remaining_out.copy_from_slice(&result.remaining);
    next_shanten_out.copy_from_slice(&result.next_shanten);
    result.total_ukeire
}

fn clear_i32_output(out_remaining_ptr: *mut i32, out_next_shanten_ptr: *mut i32, out_len: usize) {
    if out_remaining_ptr.is_null() || out_next_shanten_ptr.is_null() {
        return;
    }
    let remaining_out = unsafe { std::slice::from_raw_parts_mut(out_remaining_ptr, out_len) };
    let next_shanten_out = unsafe { std::slice::from_raw_parts_mut(out_next_shanten_ptr, out_len) };
    for index in 0..out_len {
        remaining_out[index] = 0;
        next_shanten_out[index] = 99;
    }
}

fn read_mask_136(ptr: *const u8, len: usize) -> Option<[u8; TILE_ID_COUNT as usize]> {
    if ptr.is_null() || len != TILE_ID_COUNT as usize {
        return None;
    }
    let slice = unsafe { std::slice::from_raw_parts(ptr, len) };
    let mut mask = [0_u8; TILE_ID_COUNT as usize];
    mask.copy_from_slice(slice);
    if mask.iter().any(|&value| value > 1) {
        return None;
    }
    Some(mask)
}

fn read_mask_rows_34(
    ptr: *const u8,
    len: usize,
    row_count: usize,
) -> Option<Vec<[u8; TILE_TYPE_COUNT]>> {
    if ptr.is_null() || len != row_count * TILE_TYPE_COUNT {
        return None;
    }
    let slice = unsafe { std::slice::from_raw_parts(ptr, len) };
    let mut rows = Vec::with_capacity(row_count);
    for row in slice.chunks_exact(TILE_TYPE_COUNT) {
        let mut mask = [0_u8; TILE_TYPE_COUNT];
        mask.copy_from_slice(row);
        if mask.iter().any(|&value| value > 1) {
            return None;
        }
        rows.push(mask);
    }
    Some(rows)
}

fn read_i32_34(ptr: *const i32, len: usize) -> Option<[i32; TILE_TYPE_COUNT]> {
    if ptr.is_null() || len != TILE_TYPE_COUNT {
        return None;
    }
    let slice = unsafe { std::slice::from_raw_parts(ptr, len) };
    let mut values = [0_i32; TILE_TYPE_COUNT];
    values.copy_from_slice(slice);
    if values
        .iter()
        .any(|&value| !((-1..=8).contains(&value) || value == 99))
    {
        return None;
    }
    Some(values)
}
