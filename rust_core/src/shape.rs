//! 牌型形状判断。
//!
//! 这里承接部分可用 34 计数数组完成的形状判断，例如完整手牌、听牌等待、
//! 三麻合法牌过滤等。与 `shanten` 不同，本模块更偏“是否成形/有哪些等待”，
//! 会被和牌判断和行动提示复用。

use crate::tiles::{is_legal_tile_type, tile_type, TILE_TYPE_COUNT};

const TERMINAL_HONOR_TYPES: &[usize] = &[0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];

pub struct WaitTypes {
    pub count: i32,
    pub mask: [u8; TILE_TYPE_COUNT],
}

pub fn is_complete_hand_shape(
    _mode: u8,
    concealed_counts: &[u8; TILE_TYPE_COUNT],
    meld_count: i32,
) -> bool {
    is_standard_complete_with_melds(concealed_counts, meld_count)
        || is_chiitoitsu_complete(concealed_counts, meld_count)
        || is_kokushi_complete(concealed_counts, meld_count)
}

pub fn tenpai_wait_tile_types(
    mode: u8,
    concealed_counts: &[u8; TILE_TYPE_COUNT],
    owned_counts: &[u8; TILE_TYPE_COUNT],
    meld_count: i32,
) -> WaitTypes {
    let mut result = WaitTypes {
        count: 0,
        mask: [0; TILE_TYPE_COUNT],
    };

    for tile_index in 0..TILE_TYPE_COUNT {
        if !is_legal_tile_type(mode, tile_index) || owned_counts[tile_index] >= 4 {
            continue;
        }
        let mut candidate_counts = *concealed_counts;
        if candidate_counts[tile_index] >= 4 {
            continue;
        }
        candidate_counts[tile_index] += 1;
        if is_complete_hand_shape(mode, &candidate_counts, meld_count) {
            result.mask[tile_index] = 1;
            result.count += 1;
        }
    }

    result
}

pub fn unique_terminal_honor_types_from_tiles(tiles: &[i32]) -> Option<Vec<usize>> {
    let mut mask = [false; TILE_TYPE_COUNT];
    for &tile_id in tiles {
        let tile_index = tile_type(tile_id)?;
        if TERMINAL_HONOR_TYPES.contains(&tile_index) {
            mask[tile_index] = true;
        }
    }
    Some(
        TERMINAL_HONOR_TYPES
            .iter()
            .copied()
            .filter(|&tile_index| mask[tile_index])
            .collect(),
    )
}

fn is_standard_complete_with_melds(counts: &[u8; TILE_TYPE_COUNT], meld_count: i32) -> bool {
    let needed_sets = 4 - meld_count;
    if !(0..=4).contains(&needed_sets) {
        return false;
    }
    if tile_count(counts) != needed_sets as usize * 3 + 2 {
        return false;
    }

    let mut counts = *counts;
    for pair_index in 0..TILE_TYPE_COUNT {
        if counts[pair_index] < 2 {
            continue;
        }
        counts[pair_index] -= 2;
        if can_form_standard_sets(&mut counts, needed_sets) {
            return true;
        }
        counts[pair_index] += 2;
    }
    false
}

fn can_form_standard_sets(counts: &mut [u8; TILE_TYPE_COUNT], needed_sets: i32) -> bool {
    if needed_sets == 0 {
        return counts.iter().all(|&count| count == 0);
    }

    let Some(first) = counts.iter().position(|&count| count > 0) else {
        return needed_sets == 0;
    };

    if counts[first] >= 3 {
        counts[first] -= 3;
        if can_form_standard_sets(counts, needed_sets - 1) {
            counts[first] += 3;
            return true;
        }
        counts[first] += 3;
    }

    if first < 27 && first % 9 <= 6 && counts[first + 1] > 0 && counts[first + 2] > 0 {
        counts[first] -= 1;
        counts[first + 1] -= 1;
        counts[first + 2] -= 1;
        if can_form_standard_sets(counts, needed_sets - 1) {
            counts[first] += 1;
            counts[first + 1] += 1;
            counts[first + 2] += 1;
            return true;
        }
        counts[first] += 1;
        counts[first + 1] += 1;
        counts[first + 2] += 1;
    }

    false
}

fn is_chiitoitsu_complete(counts: &[u8; TILE_TYPE_COUNT], meld_count: i32) -> bool {
    meld_count == 0
        && tile_count(counts) == 14
        && counts.iter().filter(|&&count| count == 2).count() == 7
}

fn is_kokushi_complete(counts: &[u8; TILE_TYPE_COUNT], meld_count: i32) -> bool {
    meld_count == 0
        && tile_count(counts) == 14
        && TERMINAL_HONOR_TYPES
            .iter()
            .all(|&tile_index| counts[tile_index] > 0)
        && TERMINAL_HONOR_TYPES
            .iter()
            .any(|&tile_index| counts[tile_index] >= 2)
}

fn tile_count(counts: &[u8; TILE_TYPE_COUNT]) -> usize {
    counts.iter().map(|&count| count as usize).sum()
}

#[cfg(test)]
mod tests {
    use super::{
        is_complete_hand_shape, tenpai_wait_tile_types, unique_terminal_honor_types_from_tiles,
    };
    use crate::tiles::counts_from_tiles;

    #[test]
    fn complete_closed_standard_hand_is_detected() {
        let counts =
            counts_from_tiles(&[0, 4, 8, 12, 16, 20, 36, 40, 44, 72, 76, 80, 108, 109]).unwrap();
        assert!(is_complete_hand_shape(4, &counts, 0));
    }

    #[test]
    fn complete_open_standard_hand_counts_existing_melds() {
        let counts = counts_from_tiles(&[0, 4, 8, 36, 40, 44, 108, 109]).unwrap();
        assert!(is_complete_hand_shape(4, &counts, 2));
    }

    #[test]
    fn tenpai_waits_return_legal_wait_mask() {
        let counts =
            counts_from_tiles(&[0, 4, 8, 36, 40, 44, 72, 76, 80, 108, 109, 12, 16]).unwrap();
        let waits = tenpai_wait_tile_types(4, &counts, &counts, 0);
        assert_eq!(waits.count, 2);
        assert_eq!(waits.mask[2], 1);
        assert_eq!(waits.mask[5], 1);
    }

    #[test]
    fn unique_terminal_honor_types_are_sorted() {
        assert_eq!(
            unique_terminal_honor_types_from_tiles(&[0, 1, 32, 108, 109, 124]).unwrap(),
            vec![0, 8, 27, 31]
        );
    }
}
