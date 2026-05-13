//! 计分相关的小型纯函数。
//!
//! 完整番符仍由 Python 的 `mahjong` 库和后端规则层处理；Rust 目前只承接
//! 可独立验证的基础数学，例如百点进位、支付拆分等，避免在 Python 热路径中
//! 重复执行简单但高频的数值处理。

pub fn round_up_to_100(value: f64) -> Option<i32> {
    if !value.is_finite() {
        return None;
    }
    let ceiling = value.ceil() as i32;
    Some(((ceiling + 99) / 100) * 100)
}

pub fn score_result_total(
    total: Option<i32>,
    main: i32,
    main_bonus: i32,
    additional: i32,
    additional_bonus: i32,
) -> i32 {
    total.unwrap_or(main + main_bonus + additional * 2 + additional_bonus * 2)
}

pub fn full_honba_value(mode: u8, honba: i32) -> i32 {
    let per_honba = if mode == 3 { 200 } else { 300 };
    honba.max(0) * per_honba
}

pub fn minimum_han_satisfied(
    han: i32,
    yakuman_total_han: i32,
    has_local_yaku: bool,
    minimum_han: i32,
) -> bool {
    if yakuman_total_han > 0 {
        return true;
    }
    let effective_han = if has_local_yaku { han.max(5) } else { han };
    effective_han >= minimum_han
}

pub fn tsumo_payment_map(
    mode: u8,
    north_bisection: bool,
    player_count: usize,
    winner: usize,
    dealer: usize,
    main: i32,
    main_bonus: i32,
    additional: i32,
    additional_bonus: i32,
) -> Option<[i32; 4]> {
    if !(player_count == 3 || player_count == 4) || winner >= player_count || dealer >= player_count
    {
        return None;
    }

    let mut payments = [0_i32; 4];
    let dealer_payment = main + main_bonus;
    let child_payment = additional + additional_bonus;

    for loser in 0..player_count {
        if loser == winner {
            continue;
        }
        payments[loser] = if mode == 3 && north_bisection {
            if winner == dealer {
                let bisection = round_up_to_100(dealer_payment as f64 / 2.0)?;
                dealer_payment + bisection
            } else {
                let bisection = round_up_to_100(child_payment as f64 / 2.0)?;
                (if loser == dealer {
                    dealer_payment
                } else {
                    child_payment
                }) + bisection
            }
        } else if winner == dealer || loser == dealer {
            dealer_payment
        } else {
            child_payment
        };
    }

    Some(payments)
}

pub fn is_nagashi_mangan_candidate(tile_ids: &[i32], called_flags: &[u8]) -> Option<bool> {
    // 流局满贯只看该玩家自己的弃牌河：必须至少弃过牌、所有弃牌都没有被别人鸣走，
    // 且每张都是幺九牌。called_flags 与 tile_ids 按相同下标对应，Python 侧从弃牌
    // 字典拆成两个数组后传进来；长度不足代表桥接输入不完整，按“不成立”处理。
    if tile_ids.is_empty() || called_flags.len() < tile_ids.len() {
        return Some(false);
    }
    for (index, &tile_id) in tile_ids.iter().enumerate() {
        if called_flags[index] != 0 {
            return Some(false);
        }
        // 这里传入的是实体 tile_id，需要先转成 0-33 的 tile type 后才能判断
        // “一九牌”或“字牌”。tile_type 返回 None 说明上层状态里混入了非法牌 ID。
        let tile_index = crate::tiles::tile_type(tile_id)?;
        let terminal = tile_index < 27 && matches!(tile_index % 9, 0 | 8);
        let honor = tile_index >= 27;
        if !terminal && !honor {
            return Some(false);
        }
    }
    Some(true)
}

pub fn liability_key_for_call(
    action_type: u8,
    called_tile_type: i32,
    same_seat: bool,
    has_daisangen_liability: bool,
    has_daisuushi_liability: bool,
    triplet_tile_types: &[i32],
) -> Option<u8> {
    // 返回码仍然使用 C ABI 友好的小整数：0 = 不触发包牌，1 = 大三元，2 = 大四喜。
    // Python 侧已经把 meld 字典压成了“刻子/杠子的牌种列表”，这里按牌种去重后计数，
    // 与旧实现中的 set 行为保持一致，避免同一类副露重复计数。
    if same_seat || !matches!(action_type, 1 | 2) {
        return Some(0);
    }
    if !(0..34).contains(&called_tile_type) {
        return None;
    }

    let mut present = [false; 34];
    for &tile_type in triplet_tile_types {
        if !(0..34).contains(&tile_type) {
            return None;
        }
        present[tile_type as usize] = true;
    }

    let dragon_count = (31..=33).filter(|&tile_type| present[tile_type]).count();
    if (31..=33).contains(&(called_tile_type as usize))
        && !has_daisangen_liability
        && dragon_count == 3
    {
        return Some(1);
    }

    let wind_count = (27..=30).filter(|&tile_type| present[tile_type]).count();
    if (27..=30).contains(&(called_tile_type as usize))
        && !has_daisuushi_liability
        && wind_count == 4
    {
        return Some(2);
    }

    Some(0)
}

pub fn liability_context_profile(
    player_count: usize,
    yakuman_total_han: i32,
    daisangen_eval_han: i32,
    daisangen_liable_seat: i32,
    daisangen_liability_han: i32,
    daisuushi_eval_han: i32,
    daisuushi_liable_seat: i32,
    daisuushi_liability_han: i32,
) -> Option<[i32; 4]> {
    // 输出数组编码为 [liable_seat, liable_han, remainder_han, key_mask]。
    // key_mask bit0 = DAISANGEN，bit1 = DAISUUSHI；key_mask 为 0 表示“规则判断成功，
    // 但当前牌型/责任记录不构成包牌结算上下文”。
    if !(player_count == 3 || player_count == 4) {
        return None;
    }
    if yakuman_total_han < 13 {
        return Some([-1, 0, 0, 0]);
    }

    let mut key_mask = 0_i32;
    let mut liable_seat: Option<i32> = None;
    let mut liable_han = 0_i32;

    for (bit, eval_han, seat, liability_han) in [
        (
            1_i32,
            daisangen_eval_han,
            daisangen_liable_seat,
            daisangen_liability_han,
        ),
        (
            2_i32,
            daisuushi_eval_han,
            daisuushi_liable_seat,
            daisuushi_liability_han,
        ),
    ] {
        if eval_han <= 0 || liability_han <= 0 {
            continue;
        }
        if seat < 0 || seat as usize >= player_count {
            return None;
        }
        if let Some(existing) = liable_seat {
            if existing != seat {
                return Some([-1, 0, 0, 0]);
            }
        } else {
            liable_seat = Some(seat);
        }
        key_mask |= bit;
        liable_han += liability_han.min(eval_han);
    }

    let Some(seat) = liable_seat else {
        return Some([-1, 0, 0, 0]);
    };
    if liable_han <= 0 {
        return Some([-1, 0, 0, 0]);
    }
    Some([
        seat,
        liable_han.min(yakuman_total_han),
        (yakuman_total_han - liable_han).max(0),
        key_mask,
    ])
}

pub fn local_mangan_yaku_code(
    koyaku_enabled: bool,
    is_tsumo: bool,
    is_haitei: bool,
    is_houtei: bool,
    win_tile_type: i32,
) -> Option<u8> {
    // 返回码只在 Rust/Python 边界使用：0 = 无本地满贯役，1 = Iipin moyue，
    // 2 = Chuupin raoyui。Python 侧继续持有展示名称，避免 Rust 字符串跨 FFI。
    if !(0..34).contains(&win_tile_type) {
        return None;
    }
    if !koyaku_enabled {
        return Some(0);
    }
    if is_tsumo && is_haitei && win_tile_type == 9 {
        return Some(1);
    }
    if !is_tsumo && is_houtei && win_tile_type == 17 {
        return Some(2);
    }
    Some(0)
}

pub fn local_yakuman_yaku_code(
    koyaku_enabled: bool,
    double_riichi: bool,
    closed_hand: bool,
    is_haitei: bool,
    is_houtei: bool,
) -> u8 {
    // 目前古役役满只有 “Ishi no ue ni mo sannen”。用 code 预留扩展空间，
    // 后续新增本地役满时可以继续在 Python 侧按 code 映射名字和役满数。
    if koyaku_enabled && double_riichi && closed_hand && (is_haitei || is_houtei) {
        1
    } else {
        0
    }
}

pub fn local_han_yaku_mask(
    koyaku_enabled: bool,
    is_tsumo: bool,
    has_last_discard: bool,
    discard_is_self: bool,
    discard_from_replacement_source: bool,
    discard_riichi: bool,
    discard_follows_kan: bool,
) -> u8 {
    // bit0 = Tsubame gaeshi，bit1 = Kanburi。这里不关心番数，因为两者当前都是 1 番；
    // Python 侧保留最终 [(name, han)] 结构，便于和其它本地役组合。
    if !koyaku_enabled
        || is_tsumo
        || !has_last_discard
        || discard_is_self
        || discard_from_replacement_source
    {
        return 0;
    }
    u8::from(discard_riichi) | (u8::from(discard_follows_kan) << 1)
}

pub fn local_pattern_yaku_mask(flat_tiles: &[i32], group_lens: &[usize]) -> Option<u8> {
    // HandDivider 给 Python 的 hand 是若干组 0-33 牌种。FFI 侧把它压平成 flat_tiles +
    // group_lens，Rust 按长度把分组切回来。bit0 = Isshoku sanjun，bit1 = Sanrenkou。
    let expected_len: usize = group_lens.iter().sum();
    if expected_len != flat_tiles.len() {
        return None;
    }

    let mut sequence_counts = [0_u8; 34];
    let mut triplet_heads = [false; 27];
    let mut cursor = 0_usize;
    for &len in group_lens {
        let end = cursor + len;
        let group = &flat_tiles[cursor..end];
        cursor = end;
        if group.is_empty() {
            continue;
        }
        if group.iter().any(|&tile_type| !(0..34).contains(&tile_type)) {
            return None;
        }
        if group.len() >= 3 && group[0] == group[1] && group[1] == group[2] && group[0] < 27 {
            triplet_heads[group[0] as usize] = true;
        }
        if group.len() == 3 && group[0] < 27 && group[0] + 1 == group[1] && group[1] + 1 == group[2]
        {
            let index = group[0] as usize;
            sequence_counts[index] = sequence_counts[index].saturating_add(1);
        }
    }

    let isshoku_sanjun = sequence_counts.iter().any(|&count| count >= 3);
    let sanrenkou = (0..25).any(|index| {
        index % 9 <= 6
            && triplet_heads[index]
            && triplet_heads[index + 1]
            && triplet_heads[index + 2]
    });
    Some(u8::from(isshoku_sanjun) | (u8::from(sanrenkou) << 1))
}

#[cfg(test)]
mod tests {
    use super::{
        full_honba_value, is_nagashi_mangan_candidate, liability_context_profile,
        liability_key_for_call, local_han_yaku_mask, local_mangan_yaku_code,
        local_pattern_yaku_mask, local_yakuman_yaku_code, minimum_han_satisfied, round_up_to_100,
        score_result_total, tsumo_payment_map,
    };

    #[test]
    fn payment_helpers_match_riichi_rounding() {
        assert_eq!(round_up_to_100(0.0), Some(0));
        assert_eq!(round_up_to_100(1.0), Some(100));
        assert_eq!(round_up_to_100(550.0), Some(600));
        assert_eq!(score_result_total(None, 2000, 300, 1000, 300), 4900);
        assert_eq!(score_result_total(Some(8000), 0, 0, 0, 0), 8000);
        assert_eq!(full_honba_value(3, 2), 400);
        assert_eq!(full_honba_value(4, 2), 600);
        assert!(minimum_han_satisfied(1, 13, false, 4));
        assert!(minimum_han_satisfied(1, 0, true, 4));
        assert!(!minimum_han_satisfied(1, 0, false, 2));
    }

    #[test]
    fn tsumo_payments_cover_sanma_north_bisection() {
        let dealer_win = tsumo_payment_map(3, true, 3, 0, 0, 2000, 0, 0, 0).unwrap();
        assert_eq!(dealer_win[..3], [0, 3000, 3000]);

        let child_win = tsumo_payment_map(3, true, 3, 1, 0, 3900, 0, 2000, 0).unwrap();
        assert_eq!(child_win[..3], [4900, 0, 3000]);

        let four_player = tsumo_payment_map(4, false, 4, 1, 0, 3900, 300, 2000, 300).unwrap();
        assert_eq!(four_player, [4200, 0, 2300, 2300]);
    }

    #[test]
    fn nagashi_candidates_require_terminal_honor_uncalled_discards() {
        assert_eq!(
            is_nagashi_mangan_candidate(&[0, 32, 108, 124], &[0, 0, 0, 0]),
            Some(true)
        );
        assert_eq!(
            is_nagashi_mangan_candidate(&[0, 4, 108], &[0, 0, 0]),
            Some(false)
        );
        assert_eq!(is_nagashi_mangan_candidate(&[0, 32], &[0, 1]), Some(false));
        assert_eq!(is_nagashi_mangan_candidate(&[], &[]), Some(false));
    }

    #[test]
    fn liability_key_detects_only_jansou_style_responsibility_yakuman() {
        assert_eq!(
            liability_key_for_call(1, 33, false, false, false, &[31, 32, 33]),
            Some(1)
        );
        assert_eq!(
            liability_key_for_call(2, 30, false, false, false, &[27, 28, 29, 30]),
            Some(2)
        );
        assert_eq!(
            liability_key_for_call(1, 33, false, true, false, &[31, 32, 33]),
            Some(0)
        );
        assert_eq!(
            liability_key_for_call(1, 33, true, false, false, &[31, 32, 33]),
            Some(0)
        );
    }

    #[test]
    fn liability_context_profile_matches_existing_key_order() {
        assert_eq!(
            liability_context_profile(4, 26, 13, 2, 13, 26, 2, 26),
            Some([2, 26, 0, 3])
        );
        assert_eq!(
            liability_context_profile(4, 26, 13, 1, 13, 26, 2, 26),
            Some([-1, 0, 0, 0])
        );
        assert_eq!(
            liability_context_profile(4, 13, 0, -1, 0, 26, 2, 26),
            Some([2, 13, 0, 2])
        );
    }

    #[test]
    fn local_yaku_codes_keep_names_on_python_side() {
        assert_eq!(local_mangan_yaku_code(true, true, true, false, 9), Some(1));
        assert_eq!(
            local_mangan_yaku_code(true, false, false, true, 17),
            Some(2)
        );
        assert_eq!(local_mangan_yaku_code(false, true, true, false, 9), Some(0));
        assert_eq!(local_yakuman_yaku_code(true, true, true, true, false), 1);
        assert_eq!(local_yakuman_yaku_code(true, false, true, true, false), 0);
        assert_eq!(
            local_han_yaku_mask(true, false, true, false, false, true, true),
            0b11
        );
        assert_eq!(
            local_han_yaku_mask(true, false, true, true, false, true, true),
            0
        );
    }

    #[test]
    fn local_pattern_mask_reads_flattened_hand_groups() {
        let flat = [0, 1, 2, 0, 1, 2, 0, 1, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5];
        let lens = [3_usize, 3, 3, 3, 3, 3];
        assert_eq!(local_pattern_yaku_mask(&flat, &lens), Some(0b11));
        assert_eq!(local_pattern_yaku_mask(&[0, 1, 2], &[2]), None);
    }
}
