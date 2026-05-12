//! 手牌分析与批量进张计算。
//!
//! 该模块把“打一张后向听/进张”“摸入候选牌”“弃牌批量指标”和“牌型路线”
//! 做成纯数组计算，供 Python AI 一次性取回。批量化后可以减少 Python 循环和
//! ctypes 往返次数，是晚巡性能优化的重点之一。

use crate::shanten::calculate_shanten;
use crate::tiles::{is_legal_tile_type, TILE_TYPE_COUNT};

pub const ROUTE_TANYAO: u32 = 1 << 0;
pub const ROUTE_YAKUHAI: u32 = 1 << 1;
pub const ROUTE_CHINITSU: u32 = 1 << 2;
pub const ROUTE_HONITSU: u32 = 1 << 3;
pub const ROUTE_CHIITOITSU: u32 = 1 << 4;
pub const ROUTE_TOITOI: u32 = 1 << 5;

pub struct EffectiveTiles {
    pub total_ukeire: i32,
    pub remaining: [i32; TILE_TYPE_COUNT],
    pub next_shanten: [i32; TILE_TYPE_COUNT],
}

pub struct DiscardMetrics {
    pub shanten: [i32; TILE_TYPE_COUNT],
    pub ukeire: [i32; TILE_TYPE_COUNT],
    pub remaining_matrix: [i32; TILE_TYPE_COUNT * TILE_TYPE_COUNT],
}

pub struct RouteProfiles {
    pub bonus_milli: [i32; TILE_TYPE_COUNT],
    pub route_mask: [u32; TILE_TYPE_COUNT],
}

pub fn effective_tiles_from_counts(
    mode: u8,
    counts: &[u8; TILE_TYPE_COUNT],
    visible_counts: &[u8; TILE_TYPE_COUNT],
    used_counts: &[u8; TILE_TYPE_COUNT],
    base_shanten: Option<i32>,
) -> EffectiveTiles {
    let current_shanten = base_shanten.unwrap_or_else(|| calculate_shanten(counts));
    let mut result = EffectiveTiles {
        total_ukeire: 0,
        remaining: [0; TILE_TYPE_COUNT],
        next_shanten: [99; TILE_TYPE_COUNT],
    };

    for tile_index in 0..TILE_TYPE_COUNT {
        if !is_legal_tile_type(mode, tile_index) || counts[tile_index] >= 4 {
            continue;
        }
        let remaining = 4_i32 - visible_counts[tile_index] as i32 - used_counts[tile_index] as i32;
        if remaining <= 0 {
            continue;
        }

        let mut test_counts = *counts;
        test_counts[tile_index] += 1;
        let next_shanten = calculate_shanten(&test_counts);
        if next_shanten < current_shanten || (current_shanten == 0 && next_shanten == -1) {
            result.remaining[tile_index] = remaining;
            result.next_shanten[tile_index] = next_shanten;
            result.total_ukeire += remaining;
        }
    }

    result
}

pub fn draw_tiles_from_counts(
    mode: u8,
    counts: &[u8; TILE_TYPE_COUNT],
    visible_counts: &[u8; TILE_TYPE_COUNT],
    used_counts: &[u8; TILE_TYPE_COUNT],
) -> EffectiveTiles {
    let mut result = EffectiveTiles {
        total_ukeire: 0,
        remaining: [0; TILE_TYPE_COUNT],
        next_shanten: [99; TILE_TYPE_COUNT],
    };

    for tile_index in 0..TILE_TYPE_COUNT {
        if !is_legal_tile_type(mode, tile_index) || counts[tile_index] >= 4 {
            continue;
        }
        let remaining = 4_i32 - visible_counts[tile_index] as i32 - used_counts[tile_index] as i32;
        if remaining <= 0 {
            continue;
        }

        let mut test_counts = *counts;
        test_counts[tile_index] += 1;
        result.remaining[tile_index] = remaining;
        result.next_shanten[tile_index] = calculate_shanten(&test_counts);
        result.total_ukeire += remaining;
    }

    result
}

pub fn discard_metrics_from_counts(
    mode: u8,
    source_counts: &[u8; TILE_TYPE_COUNT],
    base_visible_counts: &[u8; TILE_TYPE_COUNT],
) -> DiscardMetrics {
    let mut result = DiscardMetrics {
        shanten: [99; TILE_TYPE_COUNT],
        ukeire: [0; TILE_TYPE_COUNT],
        remaining_matrix: [0; TILE_TYPE_COUNT * TILE_TYPE_COUNT],
    };
    let used_counts = [0_u8; TILE_TYPE_COUNT];

    for discard_type in 0..TILE_TYPE_COUNT {
        if source_counts[discard_type] == 0 || !is_legal_tile_type(mode, discard_type) {
            continue;
        }

        let mut counts_after = *source_counts;
        counts_after[discard_type] -= 1;
        let shanten = calculate_shanten(&counts_after);
        let visible_counts = visible_counts_after_discard(base_visible_counts, &counts_after);
        let effective = effective_tiles_from_counts(
            mode,
            &counts_after,
            &visible_counts,
            &used_counts,
            Some(shanten),
        );

        result.shanten[discard_type] = shanten;
        result.ukeire[discard_type] = effective.total_ukeire;
        for tile_index in 0..TILE_TYPE_COUNT {
            result.remaining_matrix[discard_type * TILE_TYPE_COUNT + tile_index] =
                effective.remaining[tile_index];
        }
    }

    result
}

fn visible_counts_after_discard(
    base_visible_counts: &[u8; TILE_TYPE_COUNT],
    counts_after: &[u8; TILE_TYPE_COUNT],
) -> [u8; TILE_TYPE_COUNT] {
    let mut visible_counts = [0_u8; TILE_TYPE_COUNT];
    for index in 0..TILE_TYPE_COUNT {
        visible_counts[index] = base_visible_counts[index]
            .saturating_add(counts_after[index])
            .min(4);
    }
    visible_counts
}

pub fn hand_route_profile_from_counts(
    concealed_counts: &[u8; TILE_TYPE_COUNT],
    all_counts: &[u8; TILE_TYPE_COUNT],
    value_honor_mask: &[u8; TILE_TYPE_COUNT],
    triplet_meld_count: i32,
    value_honor_triplet_meld_count: i32,
    closed: bool,
    has_melds: bool,
    shanten_value: i32,
) -> (i32, u32) {
    let simple_count = count_by_predicate(all_counts, is_simple);
    let terminal_count = count_by_predicate(all_counts, is_terminal);
    let honor_count = count_by_predicate(all_counts, is_honor);
    let total_tile_count = all_counts.iter().map(|&count| count as i32).sum::<i32>();

    let mut suit_counts = [0_i32; 3];
    for (tile_index, &count) in all_counts.iter().enumerate().take(27) {
        suit_counts[tile_index / 9] += count as i32;
    }
    let dominant_suit = (0..3).max_by_key(|&suit| suit_counts[suit]).unwrap_or(0);

    let pair_count = concealed_counts.iter().filter(|&&count| count >= 2).count() as i32;
    let triplet_count =
        concealed_counts.iter().filter(|&&count| count >= 3).count() as i32 + triplet_meld_count;
    let value_honor_sets = value_honor_mask
        .iter()
        .enumerate()
        .filter(|(index, &enabled)| enabled > 0 && concealed_counts[*index] >= 2)
        .count() as i32
        + value_honor_triplet_meld_count;

    let route_scale = if shanten_value <= 2 {
        1000
    } else if shanten_value <= 4 {
        800
    } else {
        600
    };
    let mut bonus_milli = 0_i32;
    let mut mask = 0_u32;

    if honor_count == 0 && terminal_count <= 2 && simple_count >= 8.max(total_tile_count - 2) {
        mask |= ROUTE_TANYAO;
        bonus_milli += 6500;
    }

    if value_honor_sets > 0 {
        mask |= ROUTE_YAKUHAI;
        bonus_milli += 4500 + value_honor_sets * 1800;
    }

    let dominant_count = suit_counts[dominant_suit];
    let off_suit_count = suit_counts.iter().sum::<i32>() - dominant_count;
    if dominant_count >= 9 && off_suit_count == 0 && honor_count == 0 {
        mask |= ROUTE_CHINITSU;
        bonus_milli += 14000;
    } else if dominant_count >= 8 && off_suit_count <= 1 && honor_count >= 1 {
        mask |= ROUTE_HONITSU;
        bonus_milli += 10000;
    }

    if closed && !has_melds && pair_count >= 4 {
        mask |= ROUTE_CHIITOITSU;
        bonus_milli += 3500 + pair_count * 1600;
    }

    if triplet_count >= 2 && pair_count >= 2 {
        mask |= ROUTE_TOITOI;
        bonus_milli += 4000 + triplet_count * 1800;
    }

    ((bonus_milli * route_scale) / 1000, mask)
}

pub fn hand_route_profiles_after_discards(
    mode: u8,
    source_concealed_counts: &[u8; TILE_TYPE_COUNT],
    meld_counts: &[u8; TILE_TYPE_COUNT],
    value_honor_mask: &[u8; TILE_TYPE_COUNT],
    triplet_meld_count: i32,
    value_honor_triplet_meld_count: i32,
    closed: bool,
    has_melds: bool,
    shanten_by_discard: &[i32; TILE_TYPE_COUNT],
) -> RouteProfiles {
    let mut result = RouteProfiles {
        bonus_milli: [0; TILE_TYPE_COUNT],
        route_mask: [0; TILE_TYPE_COUNT],
    };

    for discard_type in 0..TILE_TYPE_COUNT {
        if source_concealed_counts[discard_type] == 0
            || !is_legal_tile_type(mode, discard_type)
            || shanten_by_discard[discard_type] == 99
        {
            continue;
        }

        let mut concealed_counts = *source_concealed_counts;
        concealed_counts[discard_type] -= 1;
        let mut all_counts = concealed_counts;
        for tile_index in 0..TILE_TYPE_COUNT {
            all_counts[tile_index] = all_counts[tile_index]
                .saturating_add(meld_counts[tile_index])
                .min(4);
        }
        let (bonus_milli, route_mask) = hand_route_profile_from_counts(
            &concealed_counts,
            &all_counts,
            value_honor_mask,
            triplet_meld_count,
            value_honor_triplet_meld_count,
            closed,
            has_melds,
            shanten_by_discard[discard_type],
        );
        result.bonus_milli[discard_type] = bonus_milli;
        result.route_mask[discard_type] = route_mask;
    }

    result
}

fn count_by_predicate(counts: &[u8; TILE_TYPE_COUNT], predicate: fn(usize) -> bool) -> i32 {
    counts
        .iter()
        .enumerate()
        .filter(|(index, _)| predicate(*index))
        .map(|(_, &count)| count as i32)
        .sum()
}

fn is_honor(tile_index: usize) -> bool {
    tile_index >= 27
}

fn is_terminal(tile_index: usize) -> bool {
    tile_index < 27 && (tile_index % 9 == 0 || tile_index % 9 == 8)
}

fn is_simple(tile_index: usize) -> bool {
    tile_index < 27 && !is_terminal(tile_index)
}
