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

#[cfg(test)]
mod tests {
    use super::{
        chi_candidate_pairs, kuikae_forbidden_tile_types, max_round_count, next_seat,
        ranked_settlement_scores, round_target_count, seat_distance,
    };

    #[test]
    fn seat_math_wraps_by_player_count() {
        assert_eq!(next_seat(3, 4), Some(0));
        assert_eq!(next_seat(2, 3), Some(0));
        assert_eq!(seat_distance(3, 1, 4), Some(2));
        assert_eq!(seat_distance(2, 1, 3), Some(2));
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
}
