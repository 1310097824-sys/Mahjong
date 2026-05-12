//! 牌 ID 与牌种的基础工具。
//!
//! Python 引擎使用 0-135 表示每一张实体牌，Rust 侧的多数算法使用 0-33 的
//! 牌种计数数组。这个模块负责转换、三麻合法牌过滤、赤宝牌配置和座位相关
//! 小工具，是其他 Rust 模块的底层依赖。

pub const TILE_TYPE_COUNT: usize = 34;
pub const TILE_ID_COUNT: i32 = 136;
const SANMA_REMOVED_MANZU_TYPES: &[usize] = &[1, 2, 3, 4, 5, 6, 7];

pub fn default_aka_dora_count(mode: u8) -> i32 {
    if mode == 3 {
        2
    } else {
        3
    }
}

pub fn normalize_aka_dora_count(mode: u8, ranked: bool, value: Option<i32>) -> i32 {
    let default = default_aka_dora_count(mode);
    if ranked {
        return default;
    }
    let Some(count) = value else {
        return default;
    };
    if valid_aka_dora_count(mode, count) {
        count
    } else {
        default
    }
}

pub fn active_aka_dora_ids(mode: u8, count: i32) -> Vec<i32> {
    let normalized = normalize_aka_dora_count(mode, false, Some(count));
    match (mode, normalized) {
        (3, 2) => vec![52, 88],
        (4, 3) => vec![16, 52, 88],
        (4, 4) => vec![16, 52, 53, 88],
        _ => Vec::new(),
    }
}

pub fn is_red_tile(mode: u8, count: i32, tile_id: i32) -> bool {
    active_aka_dora_ids(mode, count).contains(&tile_id)
}

pub fn tile_type(tile_id: i32) -> Option<usize> {
    if (0..TILE_ID_COUNT).contains(&tile_id) {
        Some((tile_id / 4) as usize)
    } else {
        None
    }
}

pub fn tile_flags(tile_index: usize) -> Option<u8> {
    if tile_index >= TILE_TYPE_COUNT {
        return None;
    }
    let honor = tile_index >= 27;
    let terminal = tile_index < 27 && tile_index % 9 == 0 || tile_index < 27 && tile_index % 9 == 8;
    let simple = tile_index < 27 && !terminal;
    Some(u8::from(honor) | (u8::from(terminal) << 1) | (u8::from(simple) << 2))
}

pub fn is_legal_tile_type(mode: u8, tile_index: usize) -> bool {
    tile_index < TILE_TYPE_COUNT && (mode != 3 || !SANMA_REMOVED_MANZU_TYPES.contains(&tile_index))
}

pub fn legal_tile_types_for_mode(mode: u8) -> Vec<usize> {
    (0..TILE_TYPE_COUNT)
        .filter(|&tile_index| is_legal_tile_type(mode, tile_index))
        .collect()
}

pub fn representative_tile_id(tile_index: usize, blocked_ids: &[i32]) -> Option<i32> {
    if tile_index >= TILE_TYPE_COUNT {
        return None;
    }
    let start = (tile_index as i32) * 4;
    let mut candidate_ids = [start, start + 1, start + 2, start + 3];
    if matches!(tile_index, 4 | 13 | 22) {
        candidate_ids = [start + 1, start + 2, start + 3, start];
    }
    for tile_id in candidate_ids {
        if !blocked_ids.contains(&tile_id) {
            return Some(tile_id);
        }
    }
    Some(candidate_ids[0])
}

pub fn dora_from_indicator(mode: u8, indicator_tile_id: i32) -> Option<usize> {
    let indicator = tile_type(indicator_tile_id)?;
    if indicator < 27 {
        if mode == 3 && indicator == 0 {
            return Some(8);
        }
        let suit_base = (indicator / 9) * 9;
        let rank = indicator % 9;
        return Some(suit_base + ((rank + 1) % 9));
    }
    if indicator <= 30 {
        let winds = [27, 28, 29, 30];
        let offset = winds.iter().position(|&item| item == indicator)?;
        return Some(winds[(offset + 1) % winds.len()]);
    }
    if indicator <= 33 {
        let dragons = [31, 32, 33];
        let offset = dragons.iter().position(|&item| item == indicator)?;
        return Some(dragons[(offset + 1) % dragons.len()]);
    }
    None
}

pub fn scoring_indicator_tile_id(mode: u8, indicator_tile_id: i32) -> Option<i32> {
    if mode != 3 || tile_type(indicator_tile_id)? != 0 {
        return Some(indicator_tile_id);
    }
    Some(7 * 4 + indicator_tile_id.rem_euclid(4))
}

pub fn counts_from_tiles(tiles: &[i32]) -> Option<[u8; TILE_TYPE_COUNT]> {
    let mut counts = [0_u8; TILE_TYPE_COUNT];
    for &tile_id in tiles {
        let tile_index = tile_type(tile_id)?;
        counts[tile_index] = counts[tile_index].checked_add(1)?;
        if counts[tile_index] > 4 {
            return None;
        }
    }
    Some(counts)
}

pub fn visible_counts_from_tiles(mode: u8, tiles: &[i32]) -> Option<[u8; TILE_TYPE_COUNT]> {
    let mut counts = [0_u8; TILE_TYPE_COUNT];
    for &tile_id in tiles {
        let tile_index = tile_type(tile_id)?;
        counts[tile_index] = counts[tile_index].saturating_add(1).min(4);
    }
    if mode == 3 {
        for &tile_index in SANMA_REMOVED_MANZU_TYPES {
            counts[tile_index] = 4;
        }
    }
    Some(counts)
}

pub fn remove_tile_once(tiles: &[i32], discard_tile_id: i32) -> Option<Vec<i32>> {
    let mut removed = false;
    let mut result = Vec::with_capacity(tiles.len().saturating_sub(1));
    for &tile_id in tiles {
        if !removed && tile_id == discard_tile_id {
            removed = true;
            continue;
        }
        result.push(tile_id);
    }
    removed.then_some(result)
}

pub fn read_counts_34(ptr: *const u8, len: usize) -> Option<[u8; TILE_TYPE_COUNT]> {
    if ptr.is_null() || len != TILE_TYPE_COUNT {
        return None;
    }
    let slice = unsafe { std::slice::from_raw_parts(ptr, len) };
    let mut counts = [0_u8; TILE_TYPE_COUNT];
    counts.copy_from_slice(slice);
    if counts.iter().any(|&count| count > 4) {
        return None;
    }
    Some(counts)
}

pub fn write_counts_34(counts: &[u8; TILE_TYPE_COUNT], out_ptr: *mut u8, out_len: usize) -> bool {
    if out_ptr.is_null() || out_len != TILE_TYPE_COUNT {
        return false;
    }
    let out = unsafe { std::slice::from_raw_parts_mut(out_ptr, out_len) };
    out.copy_from_slice(counts);
    true
}

fn valid_aka_dora_count(mode: u8, count: i32) -> bool {
    match mode {
        3 => matches!(count, 0 | 2),
        _ => matches!(count, 0 | 3 | 4),
    }
}

#[cfg(test)]
mod tests {
    use super::{
        active_aka_dora_ids, default_aka_dora_count, dora_from_indicator, is_legal_tile_type,
        is_red_tile, legal_tile_types_for_mode, normalize_aka_dora_count, representative_tile_id,
        scoring_indicator_tile_id, tile_flags, visible_counts_from_tiles,
    };

    #[test]
    fn sanma_one_man_indicator_points_to_nine_man() {
        assert_eq!(dora_from_indicator(3, 0), Some(8));
        assert_eq!(scoring_indicator_tile_id(3, 0), Some(28));
        assert_eq!(scoring_indicator_tile_id(3, 8 * 4), Some(8 * 4));
    }

    #[test]
    fn sanma_legal_tiles_exclude_two_through_eight_man() {
        for tile_index in 1..=7 {
            assert!(!is_legal_tile_type(3, tile_index));
        }
        assert!(is_legal_tile_type(3, 0));
        assert!(is_legal_tile_type(3, 8));
        assert!(is_legal_tile_type(4, 4));
        assert_eq!(legal_tile_types_for_mode(3).len(), 27);
    }

    #[test]
    fn aka_dora_options_match_modes() {
        assert_eq!(default_aka_dora_count(3), 2);
        assert_eq!(default_aka_dora_count(4), 3);
        assert_eq!(normalize_aka_dora_count(4, true, Some(4)), 3);
        assert_eq!(normalize_aka_dora_count(4, false, Some(4)), 4);
        assert_eq!(normalize_aka_dora_count(3, false, Some(3)), 2);
        assert_eq!(active_aka_dora_ids(4, 4), vec![16, 52, 53, 88]);
        assert_eq!(active_aka_dora_ids(3, 2), vec![52, 88]);
        assert!(is_red_tile(4, 3, 16));
        assert!(!is_red_tile(3, 2, 16));
    }

    #[test]
    fn representative_tile_prefers_non_red_five() {
        assert_eq!(representative_tile_id(4, &[]), Some(17));
        assert_eq!(representative_tile_id(4, &[17, 18, 19]), Some(16));
        assert_eq!(representative_tile_id(31, &[124, 125]), Some(126));
    }

    #[test]
    fn tile_flags_classify_tile_types() {
        assert_eq!(tile_flags(0).unwrap() & 0b010, 0b010);
        assert_eq!(tile_flags(4).unwrap() & 0b100, 0b100);
        assert_eq!(tile_flags(27).unwrap() & 0b001, 0b001);
    }

    #[test]
    fn visible_counts_saturate_and_mark_sanma_removed_tiles() {
        let counts = visible_counts_from_tiles(3, &[0, 1, 2, 3, 4, 4, 4, 4, 4]).unwrap();
        assert_eq!(counts[0], 4);
        for tile_index in 1..=7 {
            assert_eq!(counts[tile_index], 4);
        }
        assert_eq!(counts[8], 0);
    }
}
