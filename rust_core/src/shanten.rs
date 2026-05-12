//! 向听数计算。
//!
//! 这里实现标准形、七对子、国士无双三类向听的最小值。该函数被进张分析、
//! Alpha 风格搜索和 Python 兜底规则反复调用，所以迁移到 Rust 能明显降低
//! 候选弃牌评估时的开销。

use crate::tiles::TILE_TYPE_COUNT;

const TERMINAL_HONOR_TYPES: &[usize] = &[0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];
const AGARI_STATE: i32 = -1;

pub fn calculate_shanten(counts: &[u8; TILE_TYPE_COUNT]) -> i32 {
    let total: usize = counts.iter().map(|&count| count as usize).sum();
    if total > 14 || total % 3 == 0 {
        return 8;
    }

    let mut best = RegularShanten::new(counts).calculate(total);
    if total >= 13 {
        best = best
            .min(chiitoitsu_shanten(counts))
            .min(kokushi_shanten(counts));
    }
    best
}

struct RegularShanten {
    tiles: [i32; TILE_TYPE_COUNT],
    number_melds: i32,
    number_tatsu: i32,
    number_pairs: i32,
    number_jidahai: i32,
    flag_four_copies: u32,
    flag_isolated_tiles: u32,
    min_shanten: i32,
}

impl RegularShanten {
    fn new(counts: &[u8; TILE_TYPE_COUNT]) -> Self {
        let mut tiles = [0_i32; TILE_TYPE_COUNT];
        for (index, count) in counts.iter().enumerate() {
            tiles[index] = *count as i32;
        }

        Self {
            tiles,
            number_melds: 0,
            number_tatsu: 0,
            number_pairs: 0,
            number_jidahai: 0,
            flag_four_copies: 0,
            flag_isolated_tiles: 0,
            min_shanten: 8,
        }
    }

    fn calculate(mut self, count_of_tiles: usize) -> i32 {
        self.remove_character_tiles(count_of_tiles);
        let init_mentsu = ((14 - count_of_tiles) / 3) as i32;
        self.scan(init_mentsu);
        self.min_shanten
    }

    fn scan(&mut self, init_mentsu: i32) {
        for i in 0..27 {
            if self.tiles[i] == 4 {
                self.flag_four_copies |= 1 << i;
            }
        }
        self.number_melds += init_mentsu;
        self.run(0);
    }

    fn run(&mut self, mut depth: usize) {
        if self.min_shanten == AGARI_STATE {
            return;
        }

        while depth < 27 && self.tiles[depth] == 0 {
            depth += 1;
        }

        if depth >= 27 {
            self.update_result();
            return;
        }

        let mut i = depth;
        if i > 8 {
            i -= 9;
        }
        if i > 8 {
            i -= 9;
        }

        if self.tiles[depth] == 4 {
            self.increase_set(depth);
            if i < 7 && self.tiles[depth + 2] > 0 {
                if self.tiles[depth + 1] > 0 {
                    self.increase_syuntsu(depth);
                    self.run(depth + 1);
                    self.decrease_syuntsu(depth);
                }
                self.increase_tatsu_second(depth);
                self.run(depth + 1);
                self.decrease_tatsu_second(depth);
            }

            if i < 8 && self.tiles[depth + 1] > 0 {
                self.increase_tatsu_first(depth);
                self.run(depth + 1);
                self.decrease_tatsu_first(depth);
            }

            self.increase_isolated_tile(depth);
            self.run(depth + 1);
            self.decrease_isolated_tile(depth);
            self.decrease_set(depth);
            self.increase_pair(depth);

            if i < 7 && self.tiles[depth + 2] > 0 {
                if self.tiles[depth + 1] > 0 {
                    self.increase_syuntsu(depth);
                    self.run(depth);
                    self.decrease_syuntsu(depth);
                }
                self.increase_tatsu_second(depth);
                self.run(depth + 1);
                self.decrease_tatsu_second(depth);
            }

            if i < 8 && self.tiles[depth + 1] > 0 {
                self.increase_tatsu_first(depth);
                self.run(depth + 1);
                self.decrease_tatsu_first(depth);
            }

            self.decrease_pair(depth);
        }

        if self.tiles[depth] == 3 {
            self.increase_set(depth);
            self.run(depth + 1);
            self.decrease_set(depth);
            self.increase_pair(depth);

            if i < 7 && self.tiles[depth + 1] > 0 && self.tiles[depth + 2] > 0 {
                self.increase_syuntsu(depth);
                self.run(depth + 1);
                self.decrease_syuntsu(depth);
            } else {
                if i < 7 && self.tiles[depth + 2] > 0 {
                    self.increase_tatsu_second(depth);
                    self.run(depth + 1);
                    self.decrease_tatsu_second(depth);
                }

                if i < 8 && self.tiles[depth + 1] > 0 {
                    self.increase_tatsu_first(depth);
                    self.run(depth + 1);
                    self.decrease_tatsu_first(depth);
                }
            }

            self.decrease_pair(depth);

            if i < 7 && self.tiles[depth + 2] >= 2 && self.tiles[depth + 1] >= 2 {
                self.increase_syuntsu(depth);
                self.increase_syuntsu(depth);
                self.run(depth);
                self.decrease_syuntsu(depth);
                self.decrease_syuntsu(depth);
            }
        }

        if self.tiles[depth] == 2 {
            self.increase_pair(depth);
            self.run(depth + 1);
            self.decrease_pair(depth);
            if i < 7 && self.tiles[depth + 2] > 0 && self.tiles[depth + 1] > 0 {
                self.increase_syuntsu(depth);
                self.run(depth);
                self.decrease_syuntsu(depth);
            }
        }

        if self.tiles[depth] == 1 {
            if i < 6
                && self.tiles[depth + 1] == 1
                && self.tiles[depth + 2] > 0
                && self.tiles[depth + 3] != 4
            {
                self.increase_syuntsu(depth);
                self.run(depth + 2);
                self.decrease_syuntsu(depth);
            } else {
                self.increase_isolated_tile(depth);
                self.run(depth + 1);
                self.decrease_isolated_tile(depth);

                if i < 7 && self.tiles[depth + 2] > 0 {
                    if self.tiles[depth + 1] > 0 {
                        self.increase_syuntsu(depth);
                        self.run(depth + 1);
                        self.decrease_syuntsu(depth);
                    }
                    self.increase_tatsu_second(depth);
                    self.run(depth + 1);
                    self.decrease_tatsu_second(depth);
                }

                if i < 8 && self.tiles[depth + 1] > 0 {
                    self.increase_tatsu_first(depth);
                    self.run(depth + 1);
                    self.decrease_tatsu_first(depth);
                }
            }
        }
    }

    fn update_result(&mut self) {
        let mut ret_shanten = 8 - self.number_melds * 2 - self.number_tatsu - self.number_pairs;
        let mut n_mentsu_kouho = self.number_melds + self.number_tatsu;
        if self.number_pairs > 0 {
            n_mentsu_kouho += self.number_pairs - 1;
        } else if self.flag_four_copies != 0
            && self.flag_isolated_tiles != 0
            && (self.flag_four_copies | self.flag_isolated_tiles) == self.flag_four_copies
        {
            ret_shanten += 1;
        }

        if n_mentsu_kouho > 4 {
            ret_shanten += n_mentsu_kouho - 4;
        }

        if ret_shanten != AGARI_STATE && ret_shanten < self.number_jidahai {
            ret_shanten = self.number_jidahai;
        }

        self.min_shanten = self.min_shanten.min(ret_shanten);
    }

    fn increase_set(&mut self, k: usize) {
        self.tiles[k] -= 3;
        self.number_melds += 1;
    }

    fn decrease_set(&mut self, k: usize) {
        self.tiles[k] += 3;
        self.number_melds -= 1;
    }

    fn increase_pair(&mut self, k: usize) {
        self.tiles[k] -= 2;
        self.number_pairs += 1;
    }

    fn decrease_pair(&mut self, k: usize) {
        self.tiles[k] += 2;
        self.number_pairs -= 1;
    }

    fn increase_syuntsu(&mut self, k: usize) {
        self.tiles[k] -= 1;
        self.tiles[k + 1] -= 1;
        self.tiles[k + 2] -= 1;
        self.number_melds += 1;
    }

    fn decrease_syuntsu(&mut self, k: usize) {
        self.tiles[k] += 1;
        self.tiles[k + 1] += 1;
        self.tiles[k + 2] += 1;
        self.number_melds -= 1;
    }

    fn increase_tatsu_first(&mut self, k: usize) {
        self.tiles[k] -= 1;
        self.tiles[k + 1] -= 1;
        self.number_tatsu += 1;
    }

    fn decrease_tatsu_first(&mut self, k: usize) {
        self.tiles[k] += 1;
        self.tiles[k + 1] += 1;
        self.number_tatsu -= 1;
    }

    fn increase_tatsu_second(&mut self, k: usize) {
        self.tiles[k] -= 1;
        self.tiles[k + 2] -= 1;
        self.number_tatsu += 1;
    }

    fn decrease_tatsu_second(&mut self, k: usize) {
        self.tiles[k] += 1;
        self.tiles[k + 2] += 1;
        self.number_tatsu -= 1;
    }

    fn increase_isolated_tile(&mut self, k: usize) {
        self.tiles[k] -= 1;
        self.flag_isolated_tiles |= 1 << k;
    }

    fn decrease_isolated_tile(&mut self, k: usize) {
        self.tiles[k] += 1;
        self.flag_isolated_tiles &= !(1 << k);
    }

    fn remove_character_tiles(&mut self, count_of_tiles: usize) {
        let mut four_copies = 0_u32;
        let mut isolated = 0_u32;

        for i in 27..34 {
            if self.tiles[i] == 4 {
                self.number_melds += 1;
                self.number_jidahai += 1;
                four_copies |= 1 << (i - 27);
                isolated |= 1 << (i - 27);
            }

            if self.tiles[i] == 3 {
                self.number_melds += 1;
            }

            if self.tiles[i] == 2 {
                self.number_pairs += 1;
            }

            if self.tiles[i] == 1 {
                isolated |= 1 << (i - 27);
            }
        }

        if self.number_jidahai > 0 && count_of_tiles % 3 == 2 {
            self.number_jidahai -= 1;
        }

        if isolated != 0 {
            self.flag_isolated_tiles |= 1 << 27;
            if (four_copies | isolated) == four_copies {
                self.flag_four_copies |= 1 << 27;
            }
        }
    }
}

fn chiitoitsu_shanten(counts: &[u8; TILE_TYPE_COUNT]) -> i32 {
    let pairs = counts.iter().filter(|&&count| count >= 2).count() as i32;
    if pairs == 7 {
        return AGARI_STATE;
    }
    let unique = counts.iter().filter(|&&count| count > 0).count() as i32;
    6 - pairs + (7 - unique).max(0)
}

fn kokushi_shanten(counts: &[u8; TILE_TYPE_COUNT]) -> i32 {
    let unique = TERMINAL_HONOR_TYPES
        .iter()
        .filter(|&&index| counts[index] > 0)
        .count() as i32;
    let has_pair = TERMINAL_HONOR_TYPES.iter().any(|&index| counts[index] >= 2);
    13 - unique - if has_pair { 1 } else { 0 }
}

#[cfg(test)]
mod tests {
    use super::calculate_shanten;
    use crate::tiles::counts_from_tiles;

    #[test]
    fn complete_standard_hand_is_minus_one() {
        let counts =
            counts_from_tiles(&[0, 1, 2, 4, 8, 12, 36, 40, 44, 72, 76, 80, 108, 109]).unwrap();
        assert_eq!(calculate_shanten(&counts), -1);
    }

    #[test]
    fn chiitoitsu_tenpai_is_zero() {
        let counts = counts_from_tiles(&[0, 1, 4, 5, 8, 9, 12, 13, 16, 17, 20, 21, 24]).unwrap();
        assert_eq!(calculate_shanten(&counts), 0);
    }

    #[test]
    fn kokushi_tenpai_is_zero() {
        let counts =
            counts_from_tiles(&[0, 32, 36, 68, 72, 104, 108, 112, 116, 120, 124, 128, 132])
                .unwrap();
        assert_eq!(calculate_shanten(&counts), 0);
    }
}
