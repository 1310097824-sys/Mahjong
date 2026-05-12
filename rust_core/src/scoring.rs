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

#[cfg(test)]
mod tests {
    use super::{
        full_honba_value, minimum_han_satisfied, round_up_to_100, score_result_total,
        tsumo_payment_map,
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
}
