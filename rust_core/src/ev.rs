//! AI 数值评估公式。
//!
//! 这个模块保存与解释文本无关的 EV 计算：弃牌综合 EV、押退、防守覆盖、
//! 放铳损失、顺位收益和 Alpha 风格叶子估值。Python 仍负责组织局面和中文
//! 推荐理由，Rust 则专注快速、确定性地返回数值。

pub struct StructuredDiscardInput {
    pub shanten_value: i32,
    pub ukeire: i32,
    pub risk: f64,
    pub value_penalty: f64,
    pub route_bonus: f64,
    pub route_count: i32,
    pub level: i32,
    pub progress: f64,
    pub max_loss: i32,
    pub max_threat: f64,
    pub max_push_pressure: f64,
    pub own_points: i32,
    pub top_points: i32,
    pub bottom_points: i32,
    pub is_dealer: bool,
    pub is_closed: bool,
    pub live_tile_count: i32,
    pub strategy_scale: f64,
    pub attack_bias: f64,
    pub defense_bias: f64,
    pub value_bias: f64,
    pub placement: i32,
    pub placement_count: i32,
    pub gap_to_above: i32,
    pub is_all_last: bool,
    pub level_one_noise: f64,
}

pub struct StructuredDiscardOutput {
    pub speed_ev: f64,
    pub value_ev: f64,
    pub defense_ev: f64,
    pub table_ev: f64,
    pub final_ev: f64,
}

pub struct PushFoldInput {
    pub shanten_value: i32,
    pub risk: f64,
    pub safety_score: f64,
    pub hand_value_ev: f64,
    pub estimated_han: f64,
    pub wait_quality: f64,
    pub progress: f64,
    pub max_threat: f64,
    pub max_push_pressure: f64,
    pub max_loss: i32,
    pub riichi_count: i32,
    pub critical_count: i32,
    pub high_count: i32,
    pub defense_scale: f64,
    pub strategy_scale: f64,
    pub attack_bias: f64,
    pub defense_bias: f64,
    pub value_bias: f64,
    pub is_dealer: bool,
    pub placement: i32,
    pub placement_count: i32,
    pub is_all_last: bool,
}

pub struct PushFoldOutput {
    pub ev: f64,
    pub pressure: f64,
    pub commitment: f64,
    pub mode_code: u8,
    pub label_code: u8,
}

pub struct DefenseOverrideInput {
    pub shanten_value: i32,
    pub risk: f64,
    pub safety_score: f64,
    pub hand_value_ev: f64,
    pub estimated_han: f64,
    pub wait_quality: f64,
    pub level: i32,
    pub progress: f64,
    pub max_threat: f64,
    pub max_push_pressure: f64,
    pub max_loss: i32,
    pub riichi_count: i32,
    pub critical_count: i32,
    pub high_count: i32,
    pub open_monster_count: i32,
    pub attack_bias: f64,
    pub defense_bias: f64,
    pub value_bias: f64,
    pub placement: i32,
    pub placement_count: i32,
    pub is_all_last: bool,
}

pub struct DefenseOverrideOutput {
    pub ev: f64,
    pub fold_need: f64,
    pub mode_code: u8,
    pub label_code: u8,
}

pub struct DealInLossInput<'a> {
    pub dangers: &'a [f64],
    pub safeties: &'a [f64],
    pub push_pressures: &'a [f64],
    pub estimated_losses: &'a [i32],
    pub threat_level_codes: &'a [u8],
    pub threat_type_codes: &'a [u8],
    pub progress: f64,
}

pub struct DealInLossOutput {
    pub loss_ev: f64,
    pub max_rate: f64,
    pub total_expected_points: i32,
    pub top_index: i32,
}

pub struct DefensiveDiscardInput {
    pub safety_score: f64,
    pub shanten_value: i32,
    pub level_scale: f64,
    pub progress: f64,
    pub max_threat: f64,
    pub max_push_pressure: f64,
    pub max_loss: i32,
    pub high_threat_count: i32,
}

pub struct DefensiveDiscardOutput {
    pub safety_score: f64,
    pub safety_ev: f64,
    pub defense_mode: bool,
}

pub struct GlobalRewardInput<'a> {
    pub points: &'a [i32],
    pub seat: usize,
    pub shanten_value: i32,
    pub ukeire: i32,
    pub wait_quality: f64,
    pub estimated_value: i32,
    pub estimated_han: f64,
    pub deal_in_rate: f64,
    pub deal_in_points: i32,
    pub level: i32,
    pub progress: f64,
    pub riichi_sticks: i32,
    pub honba: i32,
    pub placement: i32,
    pub placement_count: i32,
    pub is_all_last: bool,
}

pub struct GlobalRewardOutput {
    pub ev: f64,
    pub win_rank_delta: i32,
    pub loss_rank_delta: i32,
}

pub struct AlphaTerminalInput {
    pub shanten_value: i32,
    pub ukeire: i32,
    pub route_bonus: f64,
    pub hand_value_ev: f64,
    pub attack_bias: f64,
    pub defense_bias: f64,
    pub value_bias: f64,
    pub max_threat: f64,
    pub max_push_pressure: f64,
    pub max_loss: i32,
    pub wait_quality: f64,
    pub level: i32,
}

pub fn structured_discard_ev(input: &StructuredDiscardInput) -> StructuredDiscardOutput {
    let speed_weight = 1.65 + (input.level as f64 * 0.62);
    let shanten_weight = 104.0 + (input.level as f64 * 4.0);
    let mut speed_ev =
        (-shanten_weight * input.shanten_value as f64) + (input.ukeire as f64 * speed_weight);
    if input.shanten_value == 0 {
        speed_ev += 18.0 + (input.ukeire as f64 * 0.45).min(18.0);
    } else if input.shanten_value == 1 {
        speed_ev += 7.0;
    }

    let value_scale = if input.level == 1 {
        0.7
    } else if input.level == 2 {
        0.92
    } else {
        1.08
    };
    let mut value_ev =
        (input.route_bonus * value_scale) - (input.value_penalty * (2.0 + input.level as f64));
    if input.shanten_value == 0
        && input.is_closed
        && input.own_points >= 1000
        && input.live_tile_count >= 4
    {
        value_ev += 8.5;
    }
    if input.route_count > 0 && input.shanten_value <= 2 {
        value_ev += (input.route_count as f64 * 1.8).min(6.0);
    }

    let mut caution = if input.level == 1 {
        0.72
    } else if input.level == 2 {
        1.0
    } else {
        1.18
    };
    if input.own_points == input.top_points {
        caution += 0.22;
    }
    if input.max_loss >= 8000 {
        caution += 0.16;
    }
    let danger_scale = 1.0
        + (input.progress * 0.55)
        + (input.max_threat * 0.18)
        + (input.max_push_pressure * 0.12)
        + (input.max_loss as f64 / 32000.0).min(0.45);
    let defense_ev = -(input.risk * 15.5 * caution * danger_scale);

    let table_ev = table_pressure_ev(input);
    let mut final_ev = speed_ev + value_ev + defense_ev + table_ev;
    if input.level == 1 {
        final_ev += input.level_one_noise;
    }

    StructuredDiscardOutput {
        speed_ev: round3(speed_ev),
        value_ev: round3(value_ev),
        defense_ev: round3(defense_ev),
        table_ev: round3(table_ev),
        final_ev: round3(final_ev),
    }
}

pub fn push_fold_profile(input: &PushFoldInput) -> PushFoldOutput {
    let mut pressure = input.max_threat * 0.82
        + input.max_push_pressure * 0.3
        + (input.max_loss as f64 / 18000.0).min(0.92)
        + (input.risk / 4.8).min(0.72)
        + input.progress * 0.42
        + input.riichi_count as f64 * 0.16
        + input.critical_count as f64 * 0.16
        + input.high_count as f64 * 0.08;
    pressure += input.defense_bias * 0.62;
    pressure -= input.attack_bias * 0.28;
    pressure *= 0.72 + input.defense_scale * 0.38;

    let mut commitment = if input.shanten_value <= 0 {
        0.92
    } else if input.shanten_value == 1 {
        0.58
    } else if input.shanten_value == 2 {
        0.22
    } else {
        -0.06
    };
    commitment += (input.hand_value_ev / 58.0).min(0.68);
    commitment += input.wait_quality * if input.shanten_value <= 1 { 0.26 } else { 0.08 };
    if input.estimated_han >= 5.0 {
        commitment += 0.22;
    } else if input.estimated_han >= 3.0 {
        commitment += 0.1;
    }
    if input.is_dealer && input.shanten_value <= 1 {
        commitment += 0.12;
    }
    if input.placement == input.placement_count && input.shanten_value <= 2 {
        commitment += 0.16;
    }
    if input.is_all_last && input.placement == 1 {
        commitment -= 0.26;
    }
    commitment += input.attack_bias * 0.42;
    commitment += input.value_bias * 0.28;
    commitment -= input.defense_bias * 0.36;
    commitment *= 0.74 + input.strategy_scale * 0.32;

    let margin = commitment - pressure;
    let (ev, mode_code, label_code) = if margin >= 0.28 {
        (
            (margin * 18.0 + (0.46 - input.risk).max(0.0) * 9.0).min(32.0),
            1,
            1,
        )
    } else if margin >= 0.02 {
        (margin * 14.0 + (input.safety_score - 0.32) * 8.0, 2, 2)
    } else if margin >= -0.34 {
        ((input.safety_score - 0.42) * 28.0 + margin * 18.0, 3, 3)
    } else {
        let mut ev = (input.safety_score - 0.36) * 82.0 + margin * 20.0;
        if input.safety_score >= 0.82 {
            ev += 15.0 + (pressure * 5.0).min(12.0);
        }
        if input.safety_score <= 0.18 {
            ev -= 16.0 + (pressure * 6.0).min(18.0);
        }
        (ev, 4, if input.shanten_value <= 1 { 4 } else { 5 })
    };

    PushFoldOutput {
        ev: round3(ev.clamp(-72.0, 72.0)),
        pressure: round3(pressure.clamp(0.0, 2.5)),
        commitment: round3(commitment.clamp(-0.4, 2.4)),
        mode_code,
        label_code,
    }
}

pub fn defense_override_profile(input: &DefenseOverrideInput) -> DefenseOverrideOutput {
    let pressure = input.max_threat
        + input.max_push_pressure * 0.28
        + (input.max_loss as f64 / 17000.0).min(0.95)
        + (input.risk / 4.2).min(0.72)
        + input.progress * 0.46
        + input.riichi_count as f64 * 0.24
        + input.critical_count as f64 * 0.2
        + input.high_count as f64 * 0.1
        + input.open_monster_count as f64 * 0.16
        + input.defense_bias * 0.72;

    let mut commitment = if input.shanten_value <= 0 {
        1.08
    } else if input.shanten_value == 1 {
        0.62
    } else if input.shanten_value == 2 {
        0.22
    } else {
        -0.12
    };
    commitment += (input.hand_value_ev / 54.0).min(0.74);
    commitment += ((input.estimated_han - 2.0).max(0.0) * 0.09).min(0.32);
    commitment += input.wait_quality * if input.shanten_value <= 1 { 0.28 } else { 0.08 };
    commitment += input.attack_bias * 0.42 + input.value_bias * 0.26;
    commitment -= input.defense_bias * 0.44;
    if input.is_all_last && input.placement == 1 {
        commitment -= 0.34;
    }
    if input.placement == input.placement_count && input.shanten_value <= 1 {
        commitment += 0.22;
    }

    let fold_need = pressure - commitment;
    if fold_need < if input.level >= 3 { 0.5 } else { 0.72 } {
        return DefenseOverrideOutput {
            ev: 0.0,
            fold_need: round3(fold_need),
            mode_code: 0,
            label_code: 0,
        };
    }

    let mut ev = 0.0_f64;
    let mut mode_code = 1;
    let mut label_code = 1;
    if input.shanten_value >= 2 {
        mode_code = 2;
        label_code = 2;
        ev += 18.0 + fold_need * 18.0;
    } else if input.shanten_value == 1 && input.estimated_han < 3.0 && input.wait_quality < 0.62 {
        mode_code = 2;
        label_code = 3;
        ev += 10.0 + fold_need * 14.0;
    } else if input.shanten_value <= 0 && input.estimated_han >= 4.0 && input.wait_quality >= 0.62 {
        mode_code = 3;
        label_code = 4;
        ev += fold_need * 4.0;
    } else {
        ev += fold_need * 9.0;
    }

    if input.safety_score >= 0.92 {
        ev += 32.0 + (pressure * 6.0).min(18.0);
    } else if input.safety_score >= 0.78 {
        ev += 22.0 + (pressure * 4.0).min(12.0);
    } else if input.safety_score >= 0.58 && input.risk <= 0.55 {
        ev += 10.0;
    } else if input.safety_score <= 0.2 || input.risk >= 1.45 {
        ev -= 34.0 + (pressure * 7.0).min(24.0);
    }

    if input.riichi_count > 0 && input.shanten_value >= 1 && input.safety_score >= 0.78 {
        ev += 12.0;
    }
    if input.max_loss >= 12000 && input.safety_score <= 0.35 {
        ev -= 18.0;
    }
    if input.level == 2 {
        ev *= 0.72;
    }

    DefenseOverrideOutput {
        ev: round3(ev.clamp(-82.0, 104.0)),
        fold_need: round3(fold_need),
        mode_code,
        label_code,
    }
}

pub fn deal_in_loss_profile(input: &DealInLossInput<'_>) -> DealInLossOutput {
    let mut total_expected_points = 0.0_f64;
    let mut max_rate = 0.0_f64;
    let mut top_index = -1_i32;

    for index in 0..input.dangers.len() {
        let danger = input.dangers[index];
        if danger <= 0.0 {
            continue;
        }
        let level_rate = match input.threat_level_codes.get(index).copied().unwrap_or(0) {
            3 => 1.45,
            2 => 1.24,
            1 => 1.08,
            _ => 0.9,
        };
        let type_rate = match input.threat_type_codes.get(index).copied().unwrap_or(0) {
            1 => 1.18,
            2 => 1.1,
            5 => 1.08,
            3 => 1.06,
            4 => 1.05,
            _ => 1.0,
        };
        let safety = input.safeties.get(index).copied().unwrap_or(0.0);
        let safety_discount = (1.08 - safety * 0.68).max(0.38);
        let push_pressure = input.push_pressures.get(index).copied().unwrap_or(0.0);
        let mut raw_rate = danger * 0.034 * level_rate * type_rate * safety_discount;
        raw_rate *= 0.72 + input.progress * 0.62 + (push_pressure * 0.1).min(0.32);
        let deal_in_rate = raw_rate.clamp(0.0, 0.42);
        let estimated_loss = input.estimated_losses.get(index).copied().unwrap_or(0);
        total_expected_points += deal_in_rate * estimated_loss as f64;
        if deal_in_rate > max_rate {
            max_rate = deal_in_rate;
            top_index = index as i32;
        }
    }

    let loss_ev = (-(total_expected_points / 118.0)).clamp(-120.0, 0.0);
    DealInLossOutput {
        loss_ev: round3(loss_ev),
        max_rate: round3(max_rate),
        total_expected_points: total_expected_points.round() as i32,
        top_index,
    }
}

pub fn defensive_discard_profile(input: &DefensiveDiscardInput) -> DefensiveDiscardOutput {
    let pressure = input.max_threat
        + input.max_push_pressure * 0.22
        + (input.max_loss as f64 / 24000.0).min(0.72)
        + input.progress * 0.38
        + input.high_threat_count as f64 * 0.08;
    let offense_commitment = if input.shanten_value <= 0 {
        0.58
    } else if input.shanten_value == 1 {
        0.42
    } else if input.shanten_value == 2 {
        0.18
    } else {
        -0.06
    };
    let defense_need = (pressure - offense_commitment).max(0.0) * input.level_scale;
    let defense_mode = defense_need >= 0.72;

    let mut safety_ev = 0.0_f64;
    if defense_need > 0.0 {
        safety_ev = (input.safety_score - 0.35) * 46.0 * defense_need;
        if input.safety_score >= 0.82 && input.shanten_value >= 2 {
            safety_ev += 14.0 * defense_need;
        }
        if defense_mode && input.shanten_value >= 3 {
            safety_ev += (input.safety_score - 0.28) * 70.0 * defense_need;
        }
        if input.safety_score <= 0.18 && defense_mode {
            safety_ev -= 12.0 * defense_need;
        }
    }

    DefensiveDiscardOutput {
        safety_score: round3(input.safety_score),
        safety_ev: round3(safety_ev.clamp(-96.0, 120.0)),
        defense_mode,
    }
}

pub fn global_reward_delta_profile(input: &GlobalRewardInput<'_>) -> Option<GlobalRewardOutput> {
    if input.points.is_empty() || input.seat >= input.points.len() || input.points.len() > 4 {
        return None;
    }
    let player_count = input.points.len() as i32;
    let current_rank = placement_rank_for_points(input.points, input.seat) as i32;
    let current_utility = placement_utility(current_rank, player_count);

    let win_points =
        (input.estimated_value + input.riichi_sticks * 1000 + input.honba * 300).max(0);
    let mut win_points_state = input.points.to_vec();
    win_points_state[input.seat] += win_points;
    let win_rank = placement_rank_for_points(&win_points_state, input.seat) as i32;
    let win_delta = placement_utility(win_rank, player_count) - current_utility;

    let mut loss_points_state = input.points.to_vec();
    loss_points_state[input.seat] -= input.deal_in_points.max(0);
    let loss_rank = placement_rank_for_points(&loss_points_state, input.seat) as i32;
    let loss_delta = placement_utility(loss_rank, player_count) - current_utility;

    let speed_proxy = (4.0 - input.shanten_value.max(0) as f64).max(0.0) / 4.0;
    let mut win_probability_proxy = 0.03
        + speed_proxy * 0.12
        + (input.ukeire as f64 / 120.0).min(0.16)
        + input.wait_quality * 0.08;
    win_probability_proxy = win_probability_proxy.min(0.46);
    if input.shanten_value <= 0 {
        win_probability_proxy += 0.08;
    }
    if input.estimated_han >= 5.0 {
        win_probability_proxy += 0.03;
    }
    win_probability_proxy = win_probability_proxy.min(0.58);

    let loss_probability_proxy = (input.deal_in_rate * (0.85 + input.progress * 0.35)).min(0.42);
    let mut late_multiplier = 1.0;
    if input.is_all_last {
        late_multiplier += 0.35;
        if current_rank == 1 {
            late_multiplier += 0.25;
        } else if current_rank == player_count {
            late_multiplier += 0.18;
        }
    }

    let utility_ev =
        (win_delta * win_probability_proxy + loss_delta * loss_probability_proxy) * late_multiplier;
    let mut point_ev = (win_points as f64 * win_probability_proxy
        - input.deal_in_points as f64 * loss_probability_proxy)
        / 1700.0;
    if input.placement == 1 && input.is_all_last {
        point_ev *= 0.36;
    } else if input.placement == input.placement_count {
        point_ev *= 1.18;
    }

    let global_ev = (utility_ev * (0.55 + input.level as f64 * 0.08)) + point_ev;
    Some(GlobalRewardOutput {
        ev: round3(global_ev.clamp(-48.0, 52.0)),
        win_rank_delta: current_rank - win_rank,
        loss_rank_delta: current_rank - loss_rank,
    })
}

pub fn alpha_terminal_projection_ev(input: &AlphaTerminalInput) -> f64 {
    if input.shanten_value <= -1 {
        return 260.0;
    }
    let mut ev = (-106.0 * input.shanten_value as f64)
        + (input.ukeire as f64 * (2.0 + input.level as f64 * 0.24));
    ev += input.route_bonus * 0.72;
    ev += input.hand_value_ev * 0.72;
    ev += input.attack_bias * 9.0 + input.value_bias * 7.0;
    ev -= input.defense_bias
        * (5.0 + input.max_push_pressure * 7.0 + input.max_threat * 3.0)
        * if input.shanten_value >= 2 { 1.0 } else { 0.42 };
    if input.shanten_value >= 2 {
        ev -= input.max_threat * 6.0
            + input.max_push_pressure * 5.0
            + (input.max_loss as f64 / 2400.0).min(10.0);
    } else if input.shanten_value <= 0 {
        ev += input.wait_quality * 18.0;
    }
    round3(ev.clamp(-380.0, 300.0))
}

fn table_pressure_ev(input: &StructuredDiscardInput) -> f64 {
    let mut ev = 0.0_f64;
    let point_gap = input.top_points - input.own_points;
    if point_gap > 8000 {
        ev += (point_gap as f64 / 1800.0).min(20.0)
            * if input.shanten_value <= 2 { 1.0 } else { 0.35 };
    }
    if input.own_points == input.top_points && input.risk > 0.0 {
        let lead = input.own_points - input.bottom_points;
        ev -= (lead as f64 / 2500.0).min(16.0) * (0.7 + input.progress);
    }
    if input.is_dealer && input.shanten_value <= 1 {
        ev += 5.5;
    }
    if input.progress > 0.72 {
        if input.shanten_value >= 2 {
            ev -= 7.5 + (input.risk * 5.0);
        } else {
            ev += 3.5;
        }
    }

    if input.shanten_value <= 1 {
        ev += input.attack_bias * 12.0 * input.strategy_scale;
        ev += input.value_bias * 7.0 * input.strategy_scale;
    } else {
        ev += input.attack_bias * 5.0 * input.strategy_scale;
        ev -= input.defense_bias * (5.0 + input.shanten_value as f64 * 1.6) * input.strategy_scale;
    }
    ev -= input.defense_bias * input.risk * (7.0 + input.progress * 6.0) * input.strategy_scale;
    if input.strategy_scale >= 0.6 && input.is_all_last && input.placement == 1 && input.risk > 0.0
    {
        ev -= (8.0 + input.risk * 5.0) * input.strategy_scale;
    }
    if input.strategy_scale >= 0.6
        && input.placement == input.placement_count
        && input.shanten_value <= 2
    {
        ev += (input.gap_to_above as f64 / 2200.0).min(10.0) * input.strategy_scale;
    }
    round3(ev)
}

fn placement_rank_for_points(points: &[i32], seat: usize) -> usize {
    let mut standings: Vec<usize> = (0..points.len()).collect();
    standings.sort_by(|&a, &b| points[b].cmp(&points[a]).then_with(|| a.cmp(&b)));
    standings
        .iter()
        .position(|&index| index == seat)
        .map(|index| index + 1)
        .unwrap_or(points.len())
}

fn placement_utility(rank: i32, player_count: i32) -> f64 {
    if player_count == 3 {
        return match rank {
            1 => 42.0,
            2 => 4.0,
            3 => -46.0,
            _ => -46.0,
        };
    }
    match rank {
        1 => 48.0,
        2 => 14.0,
        3 => -16.0,
        4 => -54.0,
        _ => -54.0,
    }
}

fn round3(value: f64) -> f64 {
    (value * 1000.0).round() / 1000.0
}
