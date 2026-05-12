//! 危险度、安全度和安全牌储备计算。
//!
//! Python 负责推断对手模型和生成解释标签；Rust 负责把可见牌、弃牌河、宝牌、
//! 威胁等级等输入转成每张牌的数值风险。这里的函数通常会按 34/136 张牌批量
//! 输出，减少 AI 对多个候选弃牌逐张重复计算的成本。

use crate::tiles::{is_legal_tile_type, tile_type, TILE_ID_COUNT, TILE_TYPE_COUNT};

pub const THREAT_RIICHI: u8 = 1;
pub const THREAT_FLUSH: u8 = 2;
pub const THREAT_YAKUHAI: u8 = 3;
pub const THREAT_FAST_OPEN: u8 = 4;

pub const LEVEL_MEDIUM: u8 = 1;
pub const LEVEL_HIGH: u8 = 2;
pub const LEVEL_CRITICAL: u8 = 3;
pub const SAFE_RESERVE_LABEL_GOOD: u8 = 1;
pub const SAFE_RESERVE_LABEL_SPENT_SAFE: u8 = 2;
pub const SAFE_RESERVE_LABEL_SHORT: u8 = 3;
pub const SAFE_RESERVE_LABEL_OK: u8 = 4;

pub struct SafeReserveResult {
    pub ev: f64,
    pub reserve_score: f64,
    pub label_code: u8,
}

pub struct SafeReserveBatch {
    pub ev: [f64; TILE_TYPE_COUNT],
    pub reserve_score: [f64; TILE_TYPE_COUNT],
    pub label_code: [u8; TILE_TYPE_COUNT],
}

pub struct DangerInput<'a> {
    pub visible_counts: &'a [u8; TILE_TYPE_COUNT],
    pub opponent_discards: &'a [u8; TILE_TYPE_COUNT],
    pub value_honor_mask: &'a [u8; TILE_TYPE_COUNT],
    pub dora_mask: &'a [u8; TILE_TYPE_COUNT],
    pub red_tile_mask: &'a [u8; TILE_ID_COUNT as usize],
    pub threat: f64,
    pub estimated_loss: i32,
    pub progress: f64,
    pub threat_type: u8,
    pub threat_level: u8,
    pub flush_suit: i32,
    pub flush_with_honors: bool,
    pub toitoi: bool,
    pub tanyao_route: bool,
    pub yakuhai_route: bool,
    pub riichi: bool,
    pub open_meld_count: i32,
}

pub fn tile_danger_table(input: &DangerInput<'_>) -> [f64; TILE_ID_COUNT as usize] {
    let mut result = [0.0_f64; TILE_ID_COUNT as usize];
    for tile_id in 0..TILE_ID_COUNT {
        result[tile_id as usize] = tile_danger(tile_id, input);
    }
    result
}

pub fn aggregate_safety_scores(
    visible_counts: &[u8; TILE_TYPE_COUNT],
    opponent_discards: &[[u8; TILE_TYPE_COUNT]],
    value_honor_masks: &[[u8; TILE_TYPE_COUNT]],
    weights: &[f64],
    tanyao_routes: &[u8],
) -> [f64; TILE_TYPE_COUNT] {
    let mut result = [0.0_f64; TILE_TYPE_COUNT];
    if opponent_discards.is_empty() || opponent_discards.len() != weights.len() {
        return result;
    }

    for tile_index in 0..TILE_TYPE_COUNT {
        let mut weighted_safety = 0.0_f64;
        let mut total_weight = 0.0_f64;
        for opponent_index in 0..opponent_discards.len() {
            let weight = weights[opponent_index].max(0.0);
            if weight <= 0.0 {
                continue;
            }
            let safety = tile_safety_score(
                tile_index,
                visible_counts,
                &opponent_discards[opponent_index],
                &value_honor_masks[opponent_index],
                tanyao_routes.get(opponent_index).copied().unwrap_or(0) != 0,
            );
            weighted_safety += safety * weight;
            total_weight += weight;
        }
        result[tile_index] = if total_weight > 0.0 {
            weighted_safety / total_weight
        } else {
            0.0
        };
    }
    result
}

pub fn safe_tile_reserve_profile(
    mode: u8,
    remaining_tiles: &[i32],
    discarded_tile_id: i32,
    shanten_value: i32,
    progress: f64,
    max_pressure: f64,
    aggregate_safety_scores: &[f64; TILE_TYPE_COUNT],
) -> Option<SafeReserveResult> {
    let target_reserve = if shanten_value <= 0 && max_pressure < 1.28 {
        0.58
    } else if shanten_value <= 1 {
        0.9
    } else {
        1.2
    };

    let mut best_reserves = [0.0_f64, 0.0_f64];
    for &tile_id in remaining_tiles {
        let tile_index = tile_type(tile_id)?;
        if !is_legal_tile_type(mode, tile_index) {
            continue;
        }
        let score = aggregate_safety_scores[tile_index];
        if score > best_reserves[0] {
            best_reserves[1] = best_reserves[0];
            best_reserves[0] = score;
        } else if score > best_reserves[1] {
            best_reserves[1] = score;
        }
    }

    let reserve_score = best_reserves[0] + best_reserves[1];
    let discarded_type = tile_type(discarded_tile_id)?;
    let discarded_safety = aggregate_safety_scores[discarded_type];
    let pressure_scale = 0.58 + (max_pressure / 1.65).min(1.0) + progress * 0.24;
    let reserve_gap = (target_reserve - reserve_score).max(0.0);
    let mut reserve_ev = -reserve_gap * (12.0 + pressure_scale * 9.0);

    if discarded_safety >= 0.74 && reserve_score < target_reserve {
        reserve_ev -= (discarded_safety - best_reserves[0]) * (9.0 + pressure_scale * 8.0);
    } else if reserve_score >= target_reserve + 0.28 {
        reserve_ev += ((reserve_score - target_reserve) * (6.0 + pressure_scale * 3.0)).min(8.0);
    }

    let label_code = if reserve_score >= target_reserve + 0.28 {
        SAFE_RESERVE_LABEL_GOOD
    } else if discarded_safety >= 0.74 && reserve_score < target_reserve {
        SAFE_RESERVE_LABEL_SPENT_SAFE
    } else if reserve_score < target_reserve {
        SAFE_RESERVE_LABEL_SHORT
    } else {
        SAFE_RESERVE_LABEL_OK
    };

    Some(SafeReserveResult {
        ev: reserve_ev.clamp(-42.0, 18.0),
        reserve_score,
        label_code,
    })
}

pub fn safe_tile_reserve_profiles_after_discards(
    mode: u8,
    source_tiles: &[i32],
    shanten_by_discard: &[i32; TILE_TYPE_COUNT],
    progress: f64,
    max_pressure: f64,
    aggregate_safety_scores: &[f64; TILE_TYPE_COUNT],
) -> Option<SafeReserveBatch> {
    let mut source_counts = [0_u8; TILE_TYPE_COUNT];
    for &tile_id in source_tiles {
        let tile_index = tile_type(tile_id)?;
        source_counts[tile_index] = source_counts[tile_index].checked_add(1)?;
    }

    let mut batch = SafeReserveBatch {
        ev: [0.0; TILE_TYPE_COUNT],
        reserve_score: [0.0; TILE_TYPE_COUNT],
        label_code: [0; TILE_TYPE_COUNT],
    };

    for discard_type in 0..TILE_TYPE_COUNT {
        if source_counts[discard_type] == 0
            || shanten_by_discard[discard_type] == 99
            || !is_legal_tile_type(mode, discard_type)
        {
            continue;
        }

        let mut removed = false;
        let mut remaining_tiles = Vec::with_capacity(source_tiles.len().saturating_sub(1));
        for &tile_id in source_tiles {
            if !removed && tile_type(tile_id)? == discard_type {
                removed = true;
                continue;
            }
            remaining_tiles.push(tile_id);
        }
        if !removed {
            continue;
        }

        let result = safe_tile_reserve_profile(
            mode,
            &remaining_tiles,
            (discard_type as i32) * 4,
            shanten_by_discard[discard_type],
            progress,
            max_pressure,
            aggregate_safety_scores,
        )?;
        batch.ev[discard_type] = result.ev;
        batch.reserve_score[discard_type] = result.reserve_score;
        batch.label_code[discard_type] = result.label_code;
    }

    Some(batch)
}

pub fn tile_value_bonus(
    discard_tile_id: i32,
    is_red: bool,
    own_wind_type: usize,
    round_wind_type: usize,
    dora_mask: &[u8; TILE_TYPE_COUNT],
) -> Option<f64> {
    if own_wind_type >= TILE_TYPE_COUNT || round_wind_type >= TILE_TYPE_COUNT {
        return None;
    }
    let tile_index = tile_type(discard_tile_id)?;
    let mut bonus = 0.0_f64;
    if is_red {
        bonus += 1.0;
    }
    if dora_mask[tile_index] > 0 {
        bonus += 0.75;
    }
    if tile_index == own_wind_type {
        bonus += 0.35;
    }
    if tile_index == round_wind_type {
        bonus += 0.35;
    }
    Some(bonus)
}

fn tile_danger(tile_id: i32, input: &DangerInput<'_>) -> f64 {
    let Some(tile_index) = tile_type(tile_id) else {
        return 0.0;
    };
    if input.opponent_discards[tile_index] > 0 {
        return 0.0;
    }

    let mut tile_base = if is_honor(tile_index) {
        let mut base = if input.value_honor_mask[tile_index] > 0 {
            0.92
        } else {
            0.58
        };
        if input.visible_counts[tile_index] >= 2 {
            base *= 0.62;
        }
        base
    } else if is_terminal(tile_index) {
        0.58
    } else {
        match tile_index % 9 {
            1 | 7 => 0.82,
            2 | 6 => 0.96,
            _ => 1.08,
        }
    };

    if input.tanyao_route {
        tile_base *= if is_terminal(tile_index) || is_honor(tile_index) {
            0.55
        } else {
            1.1
        };
    }

    let suit_index = tile_suit_index(tile_index);
    if input.flush_suit >= 0 {
        if suit_index == Some(input.flush_suit as usize) {
            tile_base *= if input.flush_with_honors { 1.32 } else { 1.48 };
        } else if suit_index.is_some() {
            tile_base *= 0.42;
        } else if is_honor(tile_index) {
            tile_base *= if input.flush_with_honors { 1.18 } else { 0.52 };
        }
    }

    if input.yakuhai_route && input.value_honor_mask[tile_index] > 0 {
        tile_base *= if input.visible_counts[tile_index] <= 1 {
            1.38
        } else {
            0.78
        };
    }

    if input.toitoi
        && (is_terminal(tile_index)
            || is_honor(tile_index)
            || input.value_honor_mask[tile_index] > 0)
    {
        tile_base *= 1.22;
    }

    if input.threat_type == THREAT_RIICHI {
        tile_base *= 1.12;
    } else if input.threat_type == THREAT_FLUSH
        && suit_index == Some(input.flush_suit.max(0) as usize)
    {
        tile_base *= 1.08;
    } else if input.threat_type == THREAT_YAKUHAI
        && (is_honor(tile_index) || input.value_honor_mask[tile_index] > 0)
    {
        tile_base *= 1.12;
    } else if input.threat_type == THREAT_FAST_OPEN && !is_honor(tile_index) {
        tile_base *= 1.06;
    }

    tile_base *= match input.threat_level {
        LEVEL_CRITICAL => 1.18,
        LEVEL_HIGH => 1.1,
        LEVEL_MEDIUM => 1.03,
        _ => 1.0,
    };

    if input.red_tile_mask[tile_id as usize] > 0 || input.dora_mask[tile_index] > 0 {
        tile_base *= 1.34;
    }

    let mut suji_multiplier = suji_safety_multiplier(tile_index, input.opponent_discards);
    if input.toitoi {
        suji_multiplier = 1.0 - ((1.0 - suji_multiplier) * 0.35);
    }
    if input.flush_suit >= 0 && suit_index == Some(input.flush_suit as usize) {
        suji_multiplier = 1.0 - ((1.0 - suji_multiplier) * 0.55);
    }
    tile_base *= suji_multiplier;
    tile_base *= visible_wall_multiplier(tile_index, input.visible_counts);

    let loss_scale = 0.72 + (input.estimated_loss as f64 / 24000.0).min(0.68);
    if input.riichi {
        tile_base *= 1.0 + input.progress * 0.28;
    } else if input.open_meld_count >= 2 {
        tile_base *= 1.0 + input.progress * 0.18;
    }

    (tile_base * input.threat * loss_scale).max(0.0)
}

fn tile_safety_score(
    tile_index: usize,
    visible_counts: &[u8; TILE_TYPE_COUNT],
    opponent_discards: &[u8; TILE_TYPE_COUNT],
    value_honor_mask: &[u8; TILE_TYPE_COUNT],
    tanyao_route: bool,
) -> f64 {
    if opponent_discards[tile_index] > 0 {
        return 1.0;
    }
    if visible_counts[tile_index] >= 4 {
        return 0.88;
    }
    if is_honor(tile_index) {
        if visible_counts[tile_index] >= 3 {
            return 0.82;
        }
        if visible_counts[tile_index] >= 2 && value_honor_mask[tile_index] == 0 {
            return 0.66;
        }
        if value_honor_mask[tile_index] == 0 && tanyao_route {
            return 0.56;
        }
        return 0.22;
    }

    let suji_multiplier = suji_safety_multiplier(tile_index, opponent_discards);
    if suji_multiplier <= 0.56 {
        return 0.68;
    }
    if suji_multiplier <= 0.74 {
        return 0.52;
    }
    if is_terminal(tile_index) {
        return 0.38;
    }
    if tile_index < 27 {
        let rank = tile_index % 9;
        if matches!(rank, 1 | 7) {
            return 0.3;
        }
    }
    0.12
}

fn suji_safety_multiplier(tile_index: usize, opponent_discards: &[u8; TILE_TYPE_COUNT]) -> f64 {
    if tile_index >= 27 {
        return 1.0;
    }
    let rank = tile_index % 9;
    let mut safe_suji = 0;
    if rank >= 3 && opponent_discards[tile_index - 3] > 0 {
        safe_suji += 1;
    }
    if rank <= 5 && opponent_discards[tile_index + 3] > 0 {
        safe_suji += 1;
    }
    if safe_suji >= 2 {
        return 0.55;
    }
    if safe_suji == 1 {
        return if matches!(rank, 3 | 4 | 5) {
            0.68
        } else {
            0.74
        };
    }
    1.0
}

fn visible_wall_multiplier(tile_index: usize, visible_counts: &[u8; TILE_TYPE_COUNT]) -> f64 {
    let visible = visible_counts[tile_index];
    let mut multiplier = 1.0;
    if visible >= 3 {
        multiplier *= 0.64;
    } else if visible == 2 {
        multiplier *= 0.84;
    }

    if tile_index < 27 {
        let rank = tile_index % 9;
        if rank >= 1 && visible_counts[tile_index - 1] >= 4 {
            multiplier *= 0.86;
        }
        if rank <= 7 && visible_counts[tile_index + 1] >= 4 {
            multiplier *= 0.86;
        }
    }
    multiplier
}

fn tile_suit_index(tile_index: usize) -> Option<usize> {
    (tile_index < 27).then_some(tile_index / 9)
}

fn is_honor(tile_index: usize) -> bool {
    tile_index >= 27
}

fn is_terminal(tile_index: usize) -> bool {
    tile_index < 27 && (tile_index % 9 == 0 || tile_index % 9 == 8)
}

#[cfg(test)]
mod tests {
    use super::tile_value_bonus;
    use crate::tiles::TILE_TYPE_COUNT;

    #[test]
    fn tile_value_bonus_counts_red_dora_and_winds() {
        let mut dora_mask = [0_u8; TILE_TYPE_COUNT];
        dora_mask[27] = 1;
        let bonus = tile_value_bonus(27 * 4, true, 27, 27, &dora_mask).unwrap();
        assert!((bonus - 2.45).abs() < f64::EPSILON);

        let bonus = tile_value_bonus(31 * 4, false, 27, 28, &dora_mask).unwrap();
        assert_eq!(bonus, 0.0);
    }
}
