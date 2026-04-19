export type Suit = 'm' | 'p' | 's' | 'z';
export type Wind = 'E' | 'S' | 'W' | 'N';
export type GameMode = '4P' | '3P';
export type RoundLength = 'EAST' | 'HANCHAN';
export type SanmaScoringMode = 'TSUMO_LOSS' | 'NORTH_BISECTION';
export type RuleProfile = 'RANKED' | 'FRIEND' | 'KOYAKU';

export interface Tile {
  suit: Suit;
  value: number;
  isRed?: boolean;
}

export interface BackendTile {
  id: number;
  label: string;
  red: boolean;
}

export interface BackendDiscard {
  tile: string;
  riichi: boolean;
  called: boolean;
}

export interface BackendMeld {
  type: 'chi' | 'pon' | 'open_kan' | 'closed_kan' | 'added_kan' | 'kita';
  opened: boolean;
  tiles: string[];
  from_seat?: number | null;
}

export interface PlayerView {
  seat: number;
  name: string;
  is_human: boolean;
  ai_level: number;
  points: number;
  dealer: boolean;
  riichi: boolean;
  seat_wind: Wind;
  hand_size: number;
  hand: BackendTile[];
  melds: BackendMeld[];
  discards: BackendDiscard[];
  nuki_count: number;
  last_reason: string;
}

export interface HintDiscard {
  tile: string;
  ukeire: number;
  risk: number;
  score: number;
  waits: string[];
  routes?: string[];
}

export interface HintView {
  shanten: number | null;
  top_discards: HintDiscard[];
}

export interface LegalAction {
  id: string;
  type: string;
  seat: number;
  label: string;
  tile_id?: number | null;
}

export interface ActionLogEntry {
  seq: number;
  round: string;
  seat?: number;
  actor: string;
  type: string;
  tile: string;
  details: string;
}

export interface LiabilityInfo {
  liable_seat: number;
  liable_name: string;
  keys: string[];
  mode: 'split' | 'full';
}

export interface FuDetail {
  fu: number;
  reason: string;
}

export interface RoundWinnerPayment {
  from_seat?: number | null;
  from_name: string;
  amount: number;
  kind: string;
}

export interface RoundWinner {
  seat: number;
  name: string;
  han?: number;
  fu?: number;
  yaku?: string[];
  yaku_level?: string;
  fu_details?: FuDetail[];
  is_tsumo?: boolean;
  win_tile_label?: string;
  payments?: RoundWinnerPayment[];
  amount?: number;
  liability?: LiabilityInfo | null;
}

export interface ResultPlacement {
  seat: number;
  name: string;
  points: number;
  placement: number;
  is_human?: boolean;
}

export type RoundResult = {
  headline?: string;
  kind?: string;
  subtype?: string;
  winners?: RoundWinner[];
  loser?: string;
  tenpai?: string[];
  score_changes?: number[];
  [key: string]: unknown;
};

export interface ResultSummary {
  placements?: ResultPlacement[];
  finished_at?: string;
  leftover_riichi_bonus?: number;
  [key: string]: unknown;
}

export interface PublicGameView {
  game_id: string;
  status: string;
  mode: GameMode;
  round_length: RoundLength;
  rule_profile: RuleProfile;
  koyaku_enabled: boolean;
  sanma_scoring_mode: SanmaScoringMode;
  round_label: string;
  phase: string;
  human_seat: number;
  turn_seat: number;
  dealer_seat: number;
  remaining_tiles: number;
  riichi_sticks: number;
  honba: number;
  players: PlayerView[];
  human_hand: BackendTile[];
  dora_indicators: string[];
  last_discard: { seat: number; tile: string } | null;
  legal_actions: LegalAction[];
  prompt: string;
  log_tail: ActionLogEntry[];
  replay_steps: number;
  round_result: RoundResult | null;
  result_summary?: ResultSummary | null;
  created_at?: string | null;
  updated_at?: string | null;
  hint?: HintView | null;
}

export interface ReplaySnapshot {
  seq: number;
  type: string;
  round: string;
  state: PublicGameView;
}

export interface ReplayView {
  game_id: string;
  snapshots: ReplaySnapshot[];
}

export interface SavedGameSummary {
  game_id: string;
  player_name: string;
  mode: GameMode;
  round_length: RoundLength;
  rule_profile?: RuleProfile;
  sanma_scoring_mode?: SanmaScoringMode;
  round_label: string;
  status: string;
  points: number[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PlayerStats {
  games_played: number;
  wins: number;
  avg_placement: number | null;
  best_score: number | null;
}
