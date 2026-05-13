//! 轻量规则辅助函数。
//!
//! 这里放不依赖完整 game 状态的小规则：玩家人数、座位距离、局数上限、
//! 赤宝牌数量归一化、三麻/四麻基础配置等。Python 调用这些函数可以减少
//! 热路径里的字符串判断和重复分支。

use crate::tiles::{tile_type, TILE_TYPE_COUNT};

pub fn player_count(mode: u8) -> i32 {
    if mode == 4 {
        4
    } else {
        3
    }
}

pub fn next_seat(seat: i32, count: i32) -> Option<i32> {
    valid_count(count).then_some((seat + 1).rem_euclid(count))
}

pub fn seat_distance(origin: i32, target: i32, count: i32) -> Option<i32> {
    valid_count(count).then_some((target - origin).rem_euclid(count))
}

pub fn seat_wind_code(player_count: usize, dealer: usize, seat: usize) -> Option<u8> {
    if !(player_count == 3 || player_count == 4) || dealer >= player_count || seat >= player_count {
        return None;
    }

    // Python 层最终仍然用 "E/S/W/N" 字符串展示；Rust 只返回稳定的小整数编码，
    // 避免跨 FFI 传字符串，也让三麻缺北家的规则在一个地方被校验。
    match (seat + player_count - dealer) % player_count {
        0 => Some(0),                      // E
        1 => Some(1),                      // S
        2 => Some(2),                      // W
        3 if player_count == 4 => Some(3), // N
        _ => None,
    }
}

pub fn round_target_count(mode: u8, east_only: bool) -> i32 {
    let base = player_count(mode);
    if east_only {
        base
    } else {
        base * 2
    }
}

pub fn max_round_count(mode: u8, east_only: bool) -> i32 {
    round_target_count(mode, east_only) + player_count(mode)
}

pub struct RankedSettlementScores {
    pub point_score_tenths: [i32; 4],
    pub uma_tenths: [i32; 4],
    pub rank_score: [i32; 4],
}

pub fn ranked_settlement_scores(
    mode: u8,
    start_points: i32,
    placement_points: &[i32],
) -> Option<RankedSettlementScores> {
    let count = player_count(mode) as usize;
    if placement_points.len() != count {
        return None;
    }
    let uma_tenths: &[i32] = if mode == 3 {
        &[150, 0, -150]
    } else {
        &[150, 50, -50, -150]
    };
    let mut result = RankedSettlementScores {
        point_score_tenths: [0; 4],
        uma_tenths: [0; 4],
        rank_score: [0; 4],
    };
    for index in 0..count {
        let point_tenths = ((placement_points[index] - start_points) as f64 / 100.0).round() as i32;
        let raw_tenths = point_tenths + uma_tenths[index];
        result.point_score_tenths[index] = point_tenths;
        result.uma_tenths[index] = uma_tenths[index];
        result.rank_score[index] = (raw_tenths as f64 / 10.0).ceil() as i32;
    }
    Some(result)
}

fn valid_count(count: i32) -> bool {
    count == 3 || count == 4
}

pub fn kuikae_forbidden_tile_types(
    action_type: u8,
    discard_tile_id: i32,
    consumed_ids: &[i32],
) -> Option<Vec<usize>> {
    let called_type = tile_type(discard_tile_id)?;
    match action_type {
        2 => Some(vec![called_type]),
        1 => {
            let mut meld_types = Vec::with_capacity(consumed_ids.len() + 1);
            for &tile_id in consumed_ids {
                meld_types.push(tile_type(tile_id)?);
            }
            meld_types.push(called_type);
            if meld_types.len() != 3 || called_type >= 27 {
                return Some(Vec::new());
            }
            meld_types.sort_unstable();
            let suit_base = (called_type / 9) * 9;
            if meld_types[0] / 9 != called_type / 9
                || meld_types[1] / 9 != called_type / 9
                || meld_types[2] / 9 != called_type / 9
                || meld_types[0] + 1 != meld_types[1]
                || meld_types[1] + 1 != meld_types[2]
            {
                return None;
            }
            let mut forbidden = vec![called_type];
            if called_type == meld_types[0] && meld_types[2] < suit_base + 8 {
                forbidden.push(meld_types[2] + 1);
            } else if called_type == meld_types[2] && meld_types[0] > suit_base {
                forbidden.push(meld_types[0] - 1);
            }
            forbidden.sort_unstable();
            forbidden.dedup();
            Some(forbidden)
        }
        _ => Some(Vec::new()),
    }
}

pub fn chi_candidate_pairs(hand_tiles: &[i32], discard_tile_id: i32) -> Option<Vec<(i32, i32)>> {
    let discard_type = tile_type(discard_tile_id)?;
    if discard_type >= 27 {
        return Some(Vec::new());
    }
    let suit = discard_type / 9;
    let rank = discard_type % 9;
    let mut first_ids = [None; TILE_TYPE_COUNT];
    for &tile_id in hand_tiles {
        let tile_index = tile_type(tile_id)?;
        if first_ids[tile_index].is_none() {
            first_ids[tile_index] = Some(tile_id);
        }
    }

    let mut candidates = Vec::new();
    for (left_delta, right_delta) in [(-2_i32, -1_i32), (-1, 1), (1, 2)] {
        let left_rank = rank as i32 + left_delta;
        let right_rank = rank as i32 + right_delta;
        if !(0..=8).contains(&left_rank) || !(0..=8).contains(&right_rank) {
            continue;
        }
        let left_type = suit * 9 + left_rank as usize;
        let right_type = suit * 9 + right_rank as usize;
        if let (Some(left_id), Some(right_id)) = (first_ids[left_type], first_ids[right_type]) {
            candidates.push((left_id, right_id));
        }
    }
    Some(candidates)
}

pub fn is_furiten(
    win_tile_type: usize,
    discard_tile_types: &[i32],
    temporary: bool,
    riichi: bool,
) -> bool {
    // 振听判断只需要“牌种”级别的信息：同一种牌的 4 张实体 ID 都会映射到同一个
    // tile type。Python 侧已经把自己的弃牌实体 ID 转成了 tile type，这里不要再按
    // tile_id / 4 转换一次，否则赤牌或具体实体编号会把判断带偏。
    temporary
        || riichi
        || discard_tile_types
            .iter()
            .any(|&tile_index| tile_index >= 0 && tile_index as usize == win_tile_type)
}

pub fn can_double_riichi(has_discards: bool, has_calls: bool) -> bool {
    !has_discards && !has_calls
}

pub fn pending_abortive_draw_kind(
    player_count: usize,
    first_discard_tile_ids: &[i32],
    discard_counts: &[i32],
    riichi_flags: &[u8],
    has_calls: bool,
) -> Option<i32> {
    // 返回值穿过 C ABI 时保持成小整数，避免 Rust 字符串生命周期和 Python ctypes
    // 解码问题。约定为：0 = 没有待结算流局，1 = 四风连打，2 = 四家立直。
    // None 表示输入结构不满足桥接前提，Python 会自动落回原实现继续判断。
    if player_count != 4
        || first_discard_tile_ids.len() < player_count
        || discard_counts.len() < player_count
        || riichi_flags.len() < player_count
    {
        return None;
    }
    if discard_counts[..player_count]
        .iter()
        .all(|&count| count == 1)
        && !has_calls
    {
        // 四风连打要比较第一巡所有人的“第一张弃牌牌种”，而不是实体牌 ID。
        // 例如东风可能是 108/109/110/111，四张都应该视为同一种东风。
        let first_type = tile_type(first_discard_tile_ids[0])?;
        if (27..=30).contains(&first_type)
            && first_discard_tile_ids[..player_count]
                .iter()
                .all(|&tile_id| tile_type(tile_id) == Some(first_type))
        {
            return Some(1);
        }
    }
    if riichi_flags[..player_count].iter().all(|&flag| flag != 0) {
        return Some(2);
    }
    Some(0)
}

pub fn should_abort_for_four_kans(kan_count: i32, kan_owner_flags: &[u8]) -> bool {
    // 四杠散了只在“累计四个杠且杠的拥有者超过一人”时成立；如果同一人四杠，
    // 后续应继续走四杠子/抢杠等结算路径，所以这里只数 owner flag 的人数。
    kan_count >= 4 && kan_owner_flags.iter().filter(|&&flag| flag != 0).count() > 1
}

pub fn is_tenhou_state(
    player_count: usize,
    seat: usize,
    dealer: usize,
    is_tsumo: bool,
    has_calls: bool,
    discard_counts: &[i32],
) -> Option<bool> {
    if !(player_count == 3 || player_count == 4)
        || seat >= player_count
        || dealer >= player_count
        || discard_counts.len() < player_count
    {
        return None;
    }
    // 天和必须是庄家自摸、无人鸣牌打断，且全场还没有任何弃牌。这里看的是每家
    // 弃牌数量而不是 last_discard，因为开局状态里 last_discard 可能尚未初始化。
    Some(
        is_tsumo
            && seat == dealer
            && !has_calls
            && discard_counts[..player_count]
                .iter()
                .all(|&count| count == 0),
    )
}

pub fn is_chiihou_state(
    player_count: usize,
    seat: usize,
    dealer: usize,
    is_tsumo: bool,
    has_calls: bool,
    seat_discard_count: i32,
) -> Option<bool> {
    if !(player_count == 3 || player_count == 4) || seat >= player_count || dealer >= player_count {
        return None;
    }
    // 地和的本地定义与 Python 旧逻辑保持一致：子家第一次摸牌自摸，且本局没有鸣牌。
    // 不要求其他玩家没有弃牌，因为子家首次摸牌前，前手可能已经完成过正常弃牌。
    Some(is_tsumo && seat != dealer && !has_calls && seat_discard_count == 0)
}

pub fn is_haitei_state(
    is_tsumo: bool,
    has_current_draw: bool,
    current_draw_from_wall: bool,
    turn_is_seat: bool,
    live_wall_empty: bool,
) -> bool {
    // 海底摸月必须来自牌山最后一张的自摸。岭上牌、拔北补牌等来源即使 live_wall
    // 已空，也不能被算作海底，所以 current_draw_source 由 Python 侧压成布尔位传入。
    is_tsumo && has_current_draw && current_draw_from_wall && turn_is_seat && live_wall_empty
}

pub fn is_houtei_state(
    is_tsumo: bool,
    has_last_discard: bool,
    discard_from_replacement_source: bool,
    discarder_last_draw_from_wall: bool,
    live_wall_empty: bool,
) -> bool {
    // 河底捞鱼只认最后一张正常摸牌后的弃牌；杠后弃牌、拔北后的弃牌等补牌来源
    // 通过 discard_from_replacement_source 排除，避免和抢杠/拔北反应窗口混淆。
    !is_tsumo
        && has_last_discard
        && !discard_from_replacement_source
        && discarder_last_draw_from_wall
        && live_wall_empty
}

pub fn is_chankan_state(
    is_tsumo: bool,
    has_last_discard: bool,
    discard_source_is_kan: bool,
    kan_type_is_closed: bool,
) -> bool {
    // 抢杠只发生在别人加杠/明杠形成的荣和窗口。闭杠只允许国士等特殊处理在
    // Python 动作层判断，这个基础状态位保持“闭杠不算普通抢杠”。
    !is_tsumo && has_last_discard && discard_source_is_kan && !kan_type_is_closed
}

pub fn is_renhou_state(
    player_count: usize,
    seat: usize,
    dealer: usize,
    is_tsumo: bool,
    koyaku_enabled: bool,
    has_calls: bool,
    seat_has_last_draw_source: bool,
    has_last_discard: bool,
    last_discard_seat: usize,
    last_discard_from_replacement_source: bool,
    seat_discard_count: i32,
) -> Option<bool> {
    if !(player_count == 3 || player_count == 4)
        || seat >= player_count
        || dealer >= player_count
        || (has_last_discard && last_discard_seat >= player_count)
    {
        return None;
    }
    // 人和是古役开关下的荣和时机役，旧 Python 逻辑要求：子家、未被鸣牌打断、
    // 自己尚未摸过牌/弃过牌，且最后一张反应牌不是杠后或拔北这类补牌来源。
    Some(
        !is_tsumo
            && koyaku_enabled
            && seat != dealer
            && !has_calls
            && !seat_has_last_draw_source
            && has_last_discard
            && last_discard_seat != seat
            && !last_discard_from_replacement_source
            && seat_discard_count == 0,
    )
}

pub fn can_abortive_draw_nine_terminals(
    phase_is_discard: bool,
    turn_is_seat: bool,
    has_current_draw: bool,
    seat_has_discards: bool,
    has_calls: bool,
    unique_terminal_honor_count: usize,
) -> bool {
    // 九种九牌是“当前轮到本人打牌、刚摸入一张、此前未弃过牌、无人鸣牌”时的宣告。
    // 牌型侧只需要幺九牌去重后的数量；具体去重仍复用 shape/tiles 模块。
    phase_is_discard
        && turn_is_seat
        && has_current_draw
        && !seat_has_discards
        && !has_calls
        && unique_terminal_honor_count >= 9
}

pub fn is_win_like_round_result(kind_code: u8, subtype_code: u8) -> bool {
    // kind_code: 1 = RON, 2 = TSUMO, 3 = DRAW, 4 = ABORTIVE_DRAW。
    // subtype_code: 1 = NAGASHI_MANGAN。字符串仍由 Python 解析，Rust 只处理稳定枚举码。
    matches!(kind_code, 1 | 2) || (kind_code == 3 && subtype_code == 1)
}

pub fn goal_score_reached(player_points: &[i32], target_score: i32) -> bool {
    player_points.iter().any(|&points| points >= target_score)
}

pub fn should_auto_stop_all_last_dealer(
    dealer_continues: bool,
    round_cursor: i32,
    base_rounds: i32,
    round_result_kind_code: u8,
    dealer_seat: usize,
    player_points: &[i32],
    target_score: i32,
) -> Option<bool> {
    if dealer_seat >= player_points.len() || player_points.is_empty() {
        return None;
    }
    // 旧规则：只有 all-last、亲家续庄开关打开、结果不是途中流局、且亲家已经是头名并
    // 有人达到目标分时，才自动终局。头名同分时按座位号小者优先，等价于 Python 的
    // min(players, key=(-points, seat))。
    if !dealer_continues || round_cursor != base_rounds - 1 || round_result_kind_code == 4 {
        return Some(false);
    }
    let top_seat = player_points
        .iter()
        .enumerate()
        .max_by_key(|&(seat, points)| (*points, -(seat as i32)))
        .map(|(seat, _)| seat)?;
    Some(top_seat == dealer_seat && goal_score_reached(player_points, target_score))
}

#[cfg(test)]
mod tests {
    use super::{
        can_abortive_draw_nine_terminals, can_double_riichi, chi_candidate_pairs,
        goal_score_reached, is_chankan_state, is_chiihou_state, is_furiten, is_haitei_state,
        is_houtei_state, is_renhou_state, is_tenhou_state, is_win_like_round_result,
        kuikae_forbidden_tile_types, max_round_count, next_seat, pending_abortive_draw_kind,
        ranked_settlement_scores, round_target_count, seat_distance, seat_wind_code,
        should_abort_for_four_kans, should_auto_stop_all_last_dealer,
    };

    #[test]
    fn seat_math_wraps_by_player_count() {
        assert_eq!(next_seat(3, 4), Some(0));
        assert_eq!(next_seat(2, 3), Some(0));
        assert_eq!(seat_distance(3, 1, 4), Some(2));
        assert_eq!(seat_distance(2, 1, 3), Some(2));
        assert_eq!(seat_wind_code(4, 1, 0), Some(3));
        assert_eq!(seat_wind_code(3, 1, 0), Some(2));
        assert_eq!(seat_wind_code(3, 1, 3), None);
    }

    #[test]
    fn round_counts_match_mode_and_length() {
        assert_eq!(round_target_count(4, true), 4);
        assert_eq!(round_target_count(4, false), 8);
        assert_eq!(round_target_count(3, true), 3);
        assert_eq!(max_round_count(3, false), 9);
    }

    #[test]
    fn kuikae_forbidden_tiles_match_called_edge() {
        assert_eq!(
            kuikae_forbidden_tile_types(1, 0, &[4, 8]).unwrap(),
            vec![0, 3]
        );
        assert_eq!(kuikae_forbidden_tile_types(1, 8, &[0, 4]).unwrap(), vec![2]);
        assert_eq!(
            kuikae_forbidden_tile_types(2, 31 * 4, &[31 * 4 + 1, 31 * 4 + 2]).unwrap(),
            vec![31]
        );
    }

    #[test]
    fn chi_candidates_return_available_pairs() {
        assert_eq!(
            chi_candidate_pairs(&[0, 4, 12, 16], 8).unwrap(),
            vec![(0, 4), (4, 12), (12, 16)]
        );
        assert!(chi_candidate_pairs(&[31 * 4, 32 * 4], 33 * 4)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn ranked_settlement_scores_match_ranked_profile() {
        let scores = ranked_settlement_scores(4, 25000, &[42000, 28000, 21000, 9000]).unwrap();
        assert_eq!(scores.point_score_tenths[..4], [170, 30, -40, -160]);
        assert_eq!(scores.uma_tenths[..4], [150, 50, -50, -150]);
        assert_eq!(scores.rank_score[..4], [32, 8, -9, -31]);

        let sanma = ranked_settlement_scores(3, 35000, &[50000, 35000, 20000]).unwrap();
        assert_eq!(sanma.uma_tenths[..3], [150, 0, -150]);
        assert_eq!(sanma.rank_score[..3], [30, 0, -30]);
    }

    #[test]
    fn round_state_helpers_match_abortive_draw_rules() {
        assert!(is_furiten(27, &[0, 27, 31], false, false));
        assert!(is_furiten(2, &[], true, false));
        assert!(!is_furiten(2, &[0, 1], false, false));
        assert!(can_double_riichi(false, false));
        assert!(!can_double_riichi(true, false));
        assert_eq!(
            pending_abortive_draw_kind(
                4,
                &[108, 109, 110, 111],
                &[1, 1, 1, 1],
                &[0, 0, 0, 0],
                false
            ),
            Some(1)
        );
        assert_eq!(
            pending_abortive_draw_kind(
                4,
                &[108, 112, 116, 120],
                &[2, 2, 2, 2],
                &[1, 1, 1, 1],
                false
            ),
            Some(2)
        );
        assert!(should_abort_for_four_kans(4, &[1, 0, 1, 0]));
        assert!(!should_abort_for_four_kans(4, &[1, 0, 0, 0]));
    }

    #[test]
    fn win_timing_helpers_preserve_replacement_tile_edges() {
        assert_eq!(
            is_tenhou_state(4, 0, 0, true, false, &[0, 0, 0, 0]),
            Some(true)
        );
        assert_eq!(
            is_tenhou_state(4, 0, 0, true, false, &[0, 1, 0, 0]),
            Some(false)
        );
        assert_eq!(is_chiihou_state(4, 1, 0, true, false, 0), Some(true));
        assert_eq!(is_chiihou_state(4, 0, 0, true, false, 0), Some(false));
        assert!(is_haitei_state(true, true, true, true, true));
        assert!(!is_haitei_state(true, true, false, true, true));
        assert!(is_houtei_state(false, true, false, true, true));
        assert!(!is_houtei_state(false, true, true, true, true));
        assert!(is_chankan_state(false, true, true, false));
        assert!(!is_chankan_state(false, true, true, true));
        assert_eq!(
            is_renhou_state(4, 1, 0, false, true, false, false, true, 0, false, 0),
            Some(true)
        );
        assert_eq!(
            is_renhou_state(4, 1, 0, false, true, true, false, true, 0, false, 0),
            Some(false)
        );
        assert!(can_abortive_draw_nine_terminals(
            true, true, true, false, false, 9
        ));
        assert!(!can_abortive_draw_nine_terminals(
            true, true, true, false, true, 9
        ));
    }

    #[test]
    fn end_condition_helpers_match_all_last_rules() {
        assert!(is_win_like_round_result(1, 0));
        assert!(is_win_like_round_result(3, 1));
        assert!(!is_win_like_round_result(4, 0));
        assert!(goal_score_reached(&[25000, 30100, 18000, 26900], 30000));
        assert_eq!(
            should_auto_stop_all_last_dealer(
                true,
                7,
                8,
                2,
                0,
                &[32000, 30000, 20000, 18000],
                30000
            ),
            Some(true)
        );
        assert_eq!(
            should_auto_stop_all_last_dealer(
                true,
                7,
                8,
                4,
                0,
                &[32000, 30000, 20000, 18000],
                30000
            ),
            Some(false)
        );
        assert_eq!(
            should_auto_stop_all_last_dealer(
                true,
                7,
                8,
                2,
                1,
                &[32000, 32000, 20000, 18000],
                30000
            ),
            Some(false)
        );
    }
}
