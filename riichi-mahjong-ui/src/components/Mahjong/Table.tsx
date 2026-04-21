import React, { startTransition, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { BarChart3, Clapperboard, History, Lightbulb, Radar, ScrollText, Settings2, UserRound, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Hand } from './Hand';
import { MahjongTile } from './MahjongTile';
import { River, type RiverDiscardView } from './River';
import { WaterBackground } from './WaterBackground';
import type {
  ActionLogEntry,
  BackendDiscard,
  BackendMeld,
  BackendTile,
  GameMode,
  HintSpecialAction,
  HintView,
  LegalAction,
  PlayerStats,
  PlayerView,
  PublicGameView,
  ReplaySnapshot,
  ReplayView,
  RoundLength,
  RuleProfile,
  SanmaScoringMode,
  SavedGameSummary,
  Tile,
} from '@/src/types/mahjong';

const DEFAULT_AI_LEVELS: Record<GameMode, number[]> = {
  '4P': [1, 2, 3],
  '3P': [1, 2],
};
const AI_MOVE_DELAY_OPTIONS = [
  { value: 0, label: '关闭动画' },
  { value: 1000, label: '1 秒' },
  { value: 2000, label: '2 秒' },
  { value: 3000, label: '3 秒' },
] as const;

const AI_LEVEL_OPTION_TEXT: Record<number, string> = {
  1: '初阶（L1）',
  2: '进阶（L2）',
  3: '强攻（L3）',
};

const STATUS_TEXT: Record<string, string> = {
  RUNNING: '进行中',
  FINISHED: '已结束',
  ABORTED: '已中止',
};

const ACTION_TYPE_TEXT: Record<string, string> = {
  ROUND_START: '开局',
  DRAW: '摸牌',
  DISCARD: '打牌',
  RIICHI: '立直',
  CHI: '吃',
  PON: '碰',
  KAN: '杠',
  KITA: '拔北',
  RON: '荣和',
  TSUMO: '自摸',
  DRAW_END: '流局',
};

const ROUND_LENGTH_TEXT: Record<RoundLength, string> = {
  EAST: '东风场',
  HANCHAN: '半庄战',
};

const MODE_TEXT: Record<GameMode, string> = {
  '4P': '四麻',
  '3P': '三麻',
};

const SANMA_SCORING_TEXT: Record<SanmaScoringMode, string> = {
  TSUMO_LOSS: '自摸损',
  NORTH_BISECTION: '北家点数折半分摊',
};

const RULE_PROFILE_TEXT: Record<RuleProfile, string> = {
  RANKED: '\u96c0\u9b42\u6bb5\u4f4d\u9ed8\u8ba4',
  FRIEND: '\u96c0\u9b42\u53cb\u4eba\u573a',
  KOYAKU: '\u96c0\u9b42\u53e4\u5f79\u623f',
};

const WIND_TEXT: Record<string, string> = {
  E: '东',
  S: '南',
  W: '西',
  N: '北',
};

const CENTER_CORE_OCTAGON = 'polygon(12% 0%, 88% 0%, 100% 12%, 100% 88%, 88% 100%, 12% 100%, 0% 88%, 0% 12%)';
const CENTER_CORE_SCREEN = 'polygon(11% 0%, 89% 0%, 100% 20%, 100% 80%, 89% 100%, 11% 100%, 0% 80%, 0% 20%)';
const CENTER_CORE_DIRECTIONS = [
  { wind: '北', wrapClass: 'left-1/2 top-[6px] -translate-x-1/2 flex-col', railClass: 'h-[16px] w-[48px]' },
  { wind: '东', wrapClass: 'right-[6px] top-1/2 -translate-y-1/2 flex-row-reverse', railClass: 'h-[48px] w-[16px]' },
  { wind: '南', wrapClass: 'bottom-[6px] left-1/2 -translate-x-1/2 flex-col-reverse', railClass: 'h-[16px] w-[48px]' },
  { wind: '西', wrapClass: 'left-[6px] top-1/2 -translate-y-1/2 flex-row', railClass: 'h-[48px] w-[16px]' },
] as const;
const CENTER_CORE_CORNER_ACCENTS = [
  'left-[14px] top-[14px] border-l-2 border-t-2',
  'right-[14px] top-[14px] border-r-2 border-t-2',
  'left-[14px] bottom-[14px] border-b-2 border-l-2',
  'right-[14px] bottom-[14px] border-b-2 border-r-2',
] as const;
const CENTER_CORE_SIDE_GROOVES = [
  'left-[18px] top-[38px] h-[22px] w-[4px]',
  'left-[18px] bottom-[38px] h-[22px] w-[4px]',
  'right-[18px] top-[38px] h-[22px] w-[4px]',
  'right-[18px] bottom-[38px] h-[22px] w-[4px]',
  'left-[44px] top-[18px] h-[4px] w-[24px]',
  'right-[44px] top-[18px] h-[4px] w-[24px]',
  'left-[44px] bottom-[18px] h-[4px] w-[24px]',
  'right-[44px] bottom-[18px] h-[4px] w-[24px]',
] as const;
const CENTER_CORE_FRAME_STRIPS = [
  'left-[26px] top-[24px] h-[3px] w-[42px]',
  'right-[26px] top-[24px] h-[3px] w-[42px]',
  'left-[26px] bottom-[24px] h-[3px] w-[42px]',
  'right-[26px] bottom-[24px] h-[3px] w-[42px]',
  'left-[24px] top-[26px] h-[42px] w-[3px]',
  'left-[24px] bottom-[26px] h-[42px] w-[3px]',
  'right-[24px] top-[26px] h-[42px] w-[3px]',
  'right-[24px] bottom-[26px] h-[42px] w-[3px]',
] as const;
const CENTER_CORE_BOLTS = [
  'left-[30px] top-[30px]',
  'right-[30px] top-[30px]',
  'left-[30px] bottom-[30px]',
  'right-[30px] bottom-[30px]',
] as const;
const CENTER_CORE_DEALER_LAMP_PLACEMENT = {
  north: 'left-1/2 top-[24px] -translate-x-1/2',
  east: 'right-[24px] top-1/2 -translate-y-1/2',
  south: 'bottom-[24px] left-1/2 -translate-x-1/2',
  west: 'left-[24px] top-1/2 -translate-y-1/2',
} as const;
const CENTER_CORE_DEALER_LAMP_SIZE = {
  north: 'h-[9px] w-[30px]',
  east: 'h-[30px] w-[9px]',
  south: 'h-[9px] w-[30px]',
  west: 'h-[30px] w-[9px]',
} as const;
const CENTER_CORE_DEALER_BADGE_PLACEMENT = {
  north: 'left-1/2 top-[38px] -translate-x-1/2',
  east: 'right-[38px] top-1/2 -translate-y-1/2',
  south: 'bottom-[38px] left-1/2 -translate-x-1/2',
  west: 'left-[38px] top-1/2 -translate-y-1/2',
} as const;
const MECHA_CENTER_CORE_INNER = 'polygon(15% 0%, 85% 0%, 100% 15%, 100% 85%, 85% 100%, 15% 100%, 0% 85%, 0% 15%)';
const MECHA_CENTER_CORE_TOP_SCREEN = 'polygon(8% 0%, 92% 0%, 100% 18%, 100% 82%, 92% 100%, 8% 100%, 0% 82%, 0% 18%)';
const MECHA_CENTER_CORE_BOTTOM_SCREEN = 'polygon(11% 0%, 89% 0%, 100% 22%, 100% 78%, 89% 100%, 11% 100%, 0% 78%, 0% 22%)';
const MECHA_CENTER_CORE_FRAME_STRIPS = [
  'left-[34px] top-[20px] h-[3px] w-[30px]',
  'right-[34px] top-[20px] h-[3px] w-[30px]',
  'left-[34px] bottom-[20px] h-[3px] w-[30px]',
  'right-[34px] bottom-[20px] h-[3px] w-[30px]',
  'left-[20px] top-[34px] h-[30px] w-[3px]',
  'left-[20px] bottom-[34px] h-[30px] w-[3px]',
  'right-[20px] top-[34px] h-[30px] w-[3px]',
  'right-[20px] bottom-[34px] h-[30px] w-[3px]',
] as const;
const MECHA_CENTER_CORE_CORNER_ACCENTS = [
  'left-[18px] top-[18px] border-l-2 border-t-2',
  'right-[18px] top-[18px] border-r-2 border-t-2',
  'left-[18px] bottom-[18px] border-b-2 border-l-2',
  'right-[18px] bottom-[18px] border-b-2 border-r-2',
] as const;
const MECHA_CENTER_CORE_GROOVES = [
  'left-[14px] top-[58px] h-[42px] w-[20px]',
  'right-[14px] top-[58px] h-[42px] w-[20px]',
  'left-1/2 top-[14px] h-[20px] w-[56px] -translate-x-1/2',
  'left-1/2 bottom-[14px] h-[20px] w-[56px] -translate-x-1/2',
] as const;
const MECHA_CENTER_CORE_BOLTS = [
  'left-[30px] top-[28px]',
  'right-[30px] top-[28px]',
  'left-[30px] bottom-[28px]',
  'right-[30px] bottom-[28px]',
] as const;
const MECHA_CENTER_CORE_VENTS = [
  'left-[50px] top-[28px] h-[2px] w-[20px]',
  'left-[50px] top-[34px] h-[2px] w-[28px]',
  'right-[50px] top-[28px] h-[2px] w-[20px]',
  'right-[50px] top-[34px] h-[2px] w-[28px]',
  'left-[50px] bottom-[28px] h-[2px] w-[20px]',
  'left-[50px] bottom-[34px] h-[2px] w-[28px]',
  'right-[50px] bottom-[28px] h-[2px] w-[20px]',
  'right-[50px] bottom-[34px] h-[2px] w-[28px]',
] as const;
const MECHA_CENTER_CORE_CONNECTORS = [
  'left-[42px] top-1/2 h-[16px] w-[18px] -translate-y-1/2',
  'right-[42px] top-1/2 h-[16px] w-[18px] -translate-y-1/2',
  'left-1/2 top-[48px] h-[18px] w-[16px] -translate-x-1/2',
  'left-1/2 bottom-[48px] h-[18px] w-[16px] -translate-x-1/2',
] as const;

const ROUND_HAND_TEXT: Record<string, string> = {
  '1': '一',
  '2': '二',
  '3': '三',
  '4': '四',
};

const ROUND_WIND_ALIASES: Record<string, string> = {
  E: '东',
  S: '南',
  W: '西',
  N: '北',
  东: '东',
  東: '东',
  南: '南',
  西: '西',
  北: '北',
};

const ROUND_HAND_ALIASES: Record<string, string> = {
  '1': '1',
  '2': '2',
  '3': '3',
  '4': '4',
  一: '1',
  二: '2',
  三: '3',
  四: '4',
};

const HONOR_TEXT: Record<string, string> = {
  E: '东',
  S: '南',
  W: '西',
  N: '北',
  Wh: '白',
  G: '发',
  R: '中',
};

const SUIT_TEXT: Record<string, string> = {
  m: '万',
  p: '筒',
  s: '索',
};

const TILE_TOKEN_REGEX = /\b(?:Wh|[ESWNGR]|[0-9][mps])\b/g;

const MELD_TEXT: Record<string, string> = {
  chi: '吃',
  pon: '碰',
  open_kan: '明杠',
  closed_kan: '暗杠',
  added_kan: '加杠',
  kita: '拔北',
};

const LIABILITY_KEY_TEXT: Record<string, string> = {
  DAISANGEN: '\u5927\u4e09\u5143',
  DAISUUSHI: '\u5927\u56db\u559c',
  SUUKANTSU: '\u56db\u6760\u5b50',
};

const RESULT_SUBTYPE_TEXT: Record<string, string> = {
  NAGASHI_MANGAN: '\u6d41\u5c40\u6ee1\u8d2f',
};

const YAKU_NAME_TEXT: Record<string, string> = {
  'Menzen Tsumo': '\u95e8\u524d\u6e05\u81ea\u6478\u548c',
  Riichi: '\u7acb\u76f4',
  'Double Riichi': '\u4e24\u7acb\u76f4',
  Ippatsu: '\u4e00\u53d1',
  Chankan: '\u62a2\u6760',
  'Rinshan Kaihou': '\u5cad\u4e0a\u5f00\u82b1',
  'Haitei Raoyue': '\u6d77\u5e95\u6478\u6708',
  'Houtei Raoyui': '\u6cb3\u5e95\u635e\u9c7c',
  Pinfu: '\u5e73\u548c',
  Tanyao: '\u65ad\u5e7a\u4e5d',
  Iipeikou: '\u4e00\u676f\u53e3',
  Iipeiko: '\u4e00\u676f\u53e3',
  Ryanpeikou: '\u4e8c\u676f\u53e3',
  Ryanpeiko: '\u4e8c\u676f\u53e3',
  Chanta: '\u6df7\u5168\u5e26\u5e7a\u4e5d',
  Junchan: '\u7eaf\u5168\u5e26\u5e7a\u4e5d',
  Honroutou: '\u6df7\u8001\u5934',
  Toitoi: '\u5bf9\u5bf9\u548c',
  Sanankou: '\u4e09\u6697\u523b',
  Sankantsu: '\u4e09\u6760\u5b50',
  SanshokuDoujun: '\u4e09\u8272\u540c\u987a',
  'Sanshoku Doujun': '\u4e09\u8272\u540c\u987a',
  SanshokuDoukou: '\u4e09\u8272\u540c\u523b',
  'Sanshoku Doukou': '\u4e09\u8272\u540c\u523b',
  Chiitoitsu: '\u4e03\u5bf9\u5b50',
  Shousangen: '\u5c0f\u4e09\u5143',
  Honitsu: '\u6df7\u4e00\u8272',
  Chinitsu: '\u6e05\u4e00\u8272',
  Ittsu: '\u4e00\u6c14\u901a\u8d2f',
  Dora: '\u5b9d\u724c',
  'Aka Dora': '\u8d64\u5b9d\u724c',
  'Ura Dora': '\u91cc\u5b9d\u724c',
  'Nuki Dora': '\u62d4\u5317\u5b9d\u724c',
  'Nagashi mangan': '\u6d41\u5c40\u6ee1\u8d2f',
  Tenhou: '\u5929\u548c',
  Chiihou: '\u5730\u548c',
  Renhou: '\u4eba\u548c',
  'Renhou (yakuman)': '\u4eba\u548c',
  Daisangen: '\u5927\u4e09\u5143',
  Shousuushii: '\u5c0f\u56db\u559c',
  Daisuushii: '\u5927\u56db\u559c',
  Tsuuiisou: '\u5b57\u4e00\u8272',
  Chinroutou: '\u6e05\u8001\u5934',
  Ryuuiisou: '\u7eff\u4e00\u8272',
  Daisharin: '\u5927\u8f66\u8f6e',
  Daisuurin: '\u5927\u6570\u90bb',
  Daichikurin: '\u5927\u7af9\u6797',
  Daichisei: '\u5927\u4e03\u661f',
  'Iipin moyue': '\u4e00\u7b52\u6478\u6708',
  'Chuupin raoyui': '\u4e5d\u7b52\u635e\u9c7c',
  'Tsubame gaeshi': '\u71d5\u8fd4',
  Kanburi: '\u6760\u632f',
  'Ishi no ue ni mo sannen': '\u77f3\u4e0a\u4e09\u5e74',
  'Isshoku sanjun': '\u4e00\u8272\u4e09\u987a',
  Sanrenkou: '\u4e09\u8fde\u523b',
  'Shiiaru raotai': '\u5341\u4e8c\u843d\u62ac',
  Uumensai: '\u4e94\u95e8\u9f50',
  KokushiMusou: '\u56fd\u58eb\u65e0\u53cc',
  'Kokushi Musou': '\u56fd\u58eb\u65e0\u53cc',
  'Kokushi Musou 13-Men Machi': '\u56fd\u58eb\u65e0\u53cc\u5341\u4e09\u9762',
  Suuankou: '\u56db\u6697\u523b',
  'Suuankou Tanki': '\u56db\u6697\u523b\u5355\u9a91',
  Suukantsu: '\u56db\u6760\u5b50',
  'Chuuren Poutou': '\u4e5d\u83b2\u5b9d\u706f',
  'Junsei Chuuren Poutou': '\u7eaf\u6b63\u4e5d\u83b2\u5b9d\u706f',
};

const BONUS_YAKU_NAMES = new Set(['Dora', 'Aka Dora', 'Ura Dora', 'Nuki Dora']);
const YAKUMAN_YAKU_NAMES = new Set([
  'Tenhou',
  'Chiihou',
  'Renhou',
  'Renhou (yakuman)',
  'Ishi no ue ni mo sannen',
  'Daisangen',
  'Shousuushii',
  'Daisuushii',
  'Tsuuiisou',
  'Chinroutou',
  'Ryuuiisou',
  'Daisharin',
  'Daisuurin',
  'Daichikurin',
  'Daichisei',
  'KokushiMusou',
  'Kokushi Musou',
  'Kokushi Musou 13-Men Machi',
  'Suuankou',
  'Suuankou Tanki',
  'Suukantsu',
  'Chuuren Poutou',
  'Junsei Chuuren Poutou',
]);

const YAKU_LEVEL_TEXT: Record<string, string> = {
  mangan: '满贯',
  haneman: '跳满',
  baiman: '倍满',
  sanbaiman: '三倍满',
  yakuman: '役满',
  '2x yakuman': '2倍役满',
  '3x yakuman': '3倍役满',
  '4x yakuman': '4倍役满',
  '5x yakuman': '5倍役满',
  '6x yakuman': '6倍役满',
};

const FU_REASON_TEXT: Record<string, string> = {
  base: '底符',
  penchan: '边张',
  kanchan: '嵌张',
  valued_pair: '役牌雀头',
  double_valued_pair: '连风雀头',
  pair_wait: '单骑待',
  tsumo: '自摸符',
  hand_without_fu: '副底加符',
  closed_pon: '暗刻',
  open_pon: '明刻',
  closed_terminal_pon: '幺九暗刻',
  open_terminal_pon: '幺九明刻',
  closed_kan: '暗杠',
  open_kan: '明杠',
  closed_terminal_kan: '幺九暗杠',
  open_terminal_kan: '幺九明杠',
};

const PAYMENT_KIND_TEXT: Record<string, string> = {
  discard_ron: '放铳支付',
  tsumo_dealer: '庄家支付',
  tsumo_child: '闲家支付',
  liability_full: '包牌全额',
  liability_share: '包牌分担',
  riichi_bonus: '供托收取',
};

const HONOR_TILE_MAP: Record<string, Tile> = {
  E: { suit: 'z', value: 1 },
  S: { suit: 'z', value: 2 },
  W: { suit: 'z', value: 3 },
  N: { suit: 'z', value: 4 },
  Wh: { suit: 'z', value: 5 },
  G: { suit: 'z', value: 6 },
  R: { suit: 'z', value: 7 },
};

const EMPTY_TILE: Tile = { suit: 'z', value: 1 };

type SeatPosition = 'bottom' | 'right' | 'top' | 'left';
type ParsedYakuDetail = {
  rawName: string;
  localizedName: string;
  han: number | null;
  category: 'regular' | 'bonus' | 'yakuman';
};

type ResultHandPreview = {
  concealedTiles: Tile[];
  winningTile: Tile | null;
};

function parseTileLabel(label: string): Tile | null {
  if (!label || label === '##') {
    return null;
  }

  if (HONOR_TILE_MAP[label]) {
    return HONOR_TILE_MAP[label];
  }

  const match = /^([0-9])([mps])$/.exec(label);
  if (!match) {
    return null;
  }

  const [, rawValue, suit] = match;
  return {
    suit: suit as Tile['suit'],
    value: rawValue === '0' ? 5 : Number(rawValue),
    isRed: rawValue === '0',
  };
}

function toVisibleTiles(tiles: BackendTile[]): Tile[] {
  return tiles
    .map((tile) => parseTileLabel(tile.label))
    .filter((tile): tile is Tile => tile !== null);
}

function toFaceDownTiles(count: number): Tile[] {
  return Array.from({ length: Math.max(0, count) }, () => EMPTY_TILE);
}

function buildResultHandPreview(
  hand: BackendTile[] | null | undefined,
  winTileLabel?: string | null,
  isTsumo?: boolean
): ResultHandPreview {
  const concealedLabels = Array.isArray(hand) ? hand.map((tile) => tile.label) : [];
  let winningTile: Tile | null = null;

  if (typeof winTileLabel === 'string' && winTileLabel) {
    winningTile = parseTileLabel(winTileLabel);
    if (isTsumo) {
      const winningIndex = concealedLabels.lastIndexOf(winTileLabel);
      if (winningIndex >= 0) {
        concealedLabels.splice(winningIndex, 1);
      }
    }
  }

  return {
    concealedTiles: concealedLabels
      .map((label) => parseTileLabel(label))
      .filter((tile): tile is Tile => tile !== null),
    winningTile,
  };
}

function toRiverTiles(discards: BackendDiscard[]): RiverDiscardView[] {
  return discards
    .map((discard, index) => {
      const tile = parseTileLabel(discard.tile);
      if (!tile) {
        return null;
      }
      return {
        tile,
        riichi: Boolean(discard.riichi),
        called: Boolean(discard.called),
        key: `${discard.tile}-${index}-${discard.riichi ? 'riichi' : 'normal'}-${discard.called ? 'called' : 'keep'}`,
      };
    })
    .filter((discard): discard is RiverDiscardView => discard !== null);
}

function getDisplayName(name: string): string {
  if (!name) return '-';
  if (name === 'SYSTEM') return '系统';
  if (name === 'Guest') return '访客';
  const aiMatch = /^AI-L(\d)-(\d+)$/.exec(name);
  if (aiMatch) {
    return `电脑${aiMatch[2]}（L${aiMatch[1]}）`;
  }
  return name;
}

function parseRoundLabel(label?: string | null): { wind: string; hand: string; honba: string } | null {
  if (!label) return null;
  const normalized = label.trim();

  const legacyMatch = /^([ESWN])\s*(\d)\s+(\d+)\s*honba$/i.exec(normalized);
  if (legacyMatch) {
    return {
      wind: ROUND_WIND_ALIASES[legacyMatch[1].toUpperCase()] ?? legacyMatch[1],
      hand: legacyMatch[2],
      honba: legacyMatch[3],
    };
  }

  const zhMatch = /^([东東南西北])\s*([1234一二三四])\s*局(?:\s+(\d+)\s*本场)?$/.exec(normalized);
  if (zhMatch) {
    return {
      wind: ROUND_WIND_ALIASES[zhMatch[1]] ?? zhMatch[1],
      hand: ROUND_HAND_ALIASES[zhMatch[2]] ?? zhMatch[2],
      honba: zhMatch[3] ?? '0',
    };
  }

  return null;
}

function formatRoundLabel(label?: string | null): string {
  if (!label) return '等待开局';
  const parsed = parseRoundLabel(label);
  if (!parsed) return label;
  return `${parsed.wind}${ROUND_HAND_TEXT[parsed.hand] ?? parsed.hand}局 ${parsed.honba}本场`;
}

function formatCompactRoundLabel(label?: string | null): string {
  if (!label) return '等待开局';
  const parsed = parseRoundLabel(label);
  if (!parsed) return label;
  return `${parsed.wind}${ROUND_HAND_TEXT[parsed.hand] ?? parsed.hand}局`;
}

function formatPoints(points?: number): string {
  if (typeof points !== 'number') return '-';
  return new Intl.NumberFormat('zh-CN').format(points);
}

function formatTileLabelZh(label?: string | null): string {
  if (!label) return '-';
  if (HONOR_TEXT[label]) {
    return HONOR_TEXT[label];
  }

  const match = /^([0-9])([mps])$/.exec(label);
  if (!match) {
    return label;
  }

  const [, rawValue, suit] = match;
  const suitText = SUIT_TEXT[suit] ?? suit;
  if (rawValue === '0') {
    return `红${suitText}`;
  }
  return `${rawValue}${suitText}`;
}

function humanizeText(text?: string | null): string {
  if (!text) return '-';
  return text.replace(TILE_TOKEN_REGEX, (token) => formatTileLabelZh(token));
}

function formatAiLevelLabel(level?: number | null): string {
  if (typeof level !== 'number') {
    return '电脑陪打';
  }
  return AI_LEVEL_OPTION_TEXT[level] ?? `L${level}`;
}

function parsePlayerInsight(text?: string | null): {
  summary: string | null;
  metrics: Array<{ label: string; value: string }>;
  detail: string | null;
} {
  const normalized = humanizeText(text || '等待行动中。').trim();
  const parts = normalized
    .split('|')
    .map((part) => part.trim())
    .filter(Boolean);

  let summary: string | null = null;
  const metrics: Array<{ label: string; value: string }> = [];
  const extras: string[] = [];

  for (const part of parts) {
    let match = /^(?:L\d+\s*)?选择\s*(.+)$/.exec(part);
    if (match) {
      summary = `当前判断：${match[1]}`;
      continue;
    }

    match = /^向听\s*(.+)$/.exec(part);
    if (match) {
      metrics.push({ label: '向听', value: match[1] });
      continue;
    }

    match = /^进张\s*(.+)$/.exec(part);
    if (match) {
      metrics.push({ label: '进张', value: match[1] });
      continue;
    }

    match = /^(?:危险度|风险)\s*(.+)$/.exec(part);
    if (match) {
      metrics.push({ label: '风险', value: match[1] });
      continue;
    }

    extras.push(part.replace(/^L\d+\s*/, '').trim());
  }

  if (!summary && extras.length) {
    summary = extras.shift() ?? null;
  }

  return {
    summary,
    metrics,
    detail: extras.length ? extras.join(' · ') : null,
  };
}

function localizeYakuName(name: string): string {
  if (YAKU_NAME_TEXT[name]) {
    return YAKU_NAME_TEXT[name];
  }

  const yakuhaiMatch = /^Yakuhai \((.+)\)$/.exec(name);
  if (yakuhaiMatch) {
    const targetText: Record<string, string> = {
      haku: '\u767d',
      hatsu: '\u53d1',
      chun: '\u4e2d',
      'seat wind': '\u81ea\u98ce',
      'round wind': '\u573a\u98ce',
      'wind of place': '\u81ea\u98ce',
      'wind of round': '\u573a\u98ce',
    };
    return `${targetText[yakuhaiMatch[1]] ?? yakuhaiMatch[1]}\u5f79\u724c`;
  }

  return name;
}

function parseYakuDetail(value: unknown): ParsedYakuDetail | null {
  if (typeof value !== 'string' || !value) {
    return null;
  }

  const trimmed = value.trim();
  const match = /^(.*?)(?:\s+(\d+)\s+han)?$/.exec(trimmed);
  if (!match) {
    return {
      rawName: trimmed,
      localizedName: humanizeText(trimmed),
      han: null,
      category: 'regular',
    };
  }

  const [, rawName, rawHan] = match;
  const normalizedName = rawName.trim();
  const localizedName = humanizeText(localizeYakuName(normalizedName));
  const category = BONUS_YAKU_NAMES.has(normalizedName)
    ? 'bonus'
    : YAKUMAN_YAKU_NAMES.has(normalizedName)
      ? 'yakuman'
      : 'regular';

  return {
    rawName: normalizedName,
    localizedName,
    han: rawHan ? Number(rawHan) : null,
    category,
  };
}

function formatYakuLabel(value: unknown): string {
  const parsed = parseYakuDetail(value);
  if (!parsed) {
    return '-';
  }
  if (!parsed.han) {
    return parsed.localizedName;
  }
  return `${parsed.localizedName} ${parsed.han} \u756a`;
}

function localizeYakuLevel(level?: string | null, yaku?: unknown): string | null {
  if (!level) {
    return null;
  }

  if (level === 'yakuman') {
    const parsed = Array.isArray(yaku) ? yaku.map((item) => parseYakuDetail(item)).filter(Boolean) : [];
    const hasDirectYakuman = parsed.some((item) => item?.category === 'yakuman');
    return hasDirectYakuman ? '役满' : '数え役满';
  }

  return YAKU_LEVEL_TEXT[level] ?? level;
}

function formatFuReason(reason: unknown, fu: unknown): string {
  if (typeof reason !== 'string' || !reason) {
    return '-';
  }

  if (reason === 'base' && fu === 25) {
    return '七对子固定符';
  }

  return FU_REASON_TEXT[reason] ?? reason;
}

function formatPaymentKind(kind: unknown): string {
  if (typeof kind !== 'string' || !kind) {
    return '-';
  }
  return PAYMENT_KIND_TEXT[kind] ?? kind;
}

function formatScoreDelta(value: unknown): string {
  if (typeof value !== 'number') return '-';
  return `${value > 0 ? '+' : ''}${formatPoints(value)}`;
}

function formatResultSubtype(value: unknown): string | null {
  if (typeof value !== 'string' || !value) {
    return null;
  }
  return RESULT_SUBTYPE_TEXT[value] ?? value;
}

function formatLiabilitySummary(value: unknown): string | null {
  if (!isRecord(value)) {
    return null;
  }

  const liableName = typeof value.liable_name === 'string' ? getDisplayName(value.liable_name) : '';
  const keys = Array.isArray(value.keys)
    ? value.keys.map((item) => LIABILITY_KEY_TEXT[String(item)] ?? String(item)).filter(Boolean)
    : [];
  const modeText =
    value.mode === 'full'
      ? '\u8d23\u4efb\u5bb6\u5168\u989d\u627f\u62c5'
      : value.mode === 'split'
        ? '\u8d23\u4efb\u5bb6\u5206\u62c5\u5f79\u6ee1\u90e8\u5206'
        : '\u8d23\u4efb\u652f\u4ed8';
  const headText = keys.length ? keys.join('\u3001') : '\u8d23\u4efb\u652f\u4ed8';

  if (liableName) {
    return `${headText}\u5305\u724c\uff1a${liableName}\uff0c${modeText}`;
  }
  return `${headText}\u5305\u724c\uff1a${modeText}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function getStatusText(status?: string | null): string {
  if (!status) return '-';
  return STATUS_TEXT[status] ?? status;
}

function getActionTypeText(type?: string | null): string {
  if (!type) return '-';
  return ACTION_TYPE_TEXT[type] ?? type;
}

function getRelativeSeatPosition(view: PublicGameView, seat: number): SeatPosition {
  const relative = (seat - view.human_seat + view.players.length) % view.players.length;
  return (['bottom', 'right', 'top', 'left'][relative] as SeatPosition | undefined) ?? 'top';
}

function getPlayerByPosition(view: PublicGameView | null, position: SeatPosition): PlayerView | null {
  if (!view) return null;
  return view.players.find((player) => getRelativeSeatPosition(view, player.seat) === position) ?? null;
}

function getActionButtonClass(actionType: string): string {
  const base =
    'rounded-full border-4 border-white/95 px-4 py-3 text-sm font-black tracking-[0.18em] text-white shadow-[0_6px_0_rgba(0,0,0,0.25),0_16px_28px_rgba(0,0,0,0.16)] transition-all hover:-translate-y-1 hover:shadow-[0_8px_0_rgba(0,0,0,0.22),0_18px_30px_rgba(0,0,0,0.18)] active:translate-y-1 active:shadow-none disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:translate-y-0 disabled:hover:shadow-[0_6px_0_rgba(0,0,0,0.25)]';
  const palette: Record<string, string> = {
    ron: 'bg-[linear-gradient(180deg,#ff61b8,#d81b78)]',
    tsumo: 'bg-[linear-gradient(180deg,#52df92,#1da862)]',
    riichi: 'bg-[linear-gradient(180deg,#ffd968,#f1a317)] text-slate-900',
    pon: 'bg-[linear-gradient(180deg,#8e86ff,#6158e7)]',
    chi: 'bg-[linear-gradient(180deg,#58d7ff,#1497df)]',
    kan: 'bg-[linear-gradient(180deg,#c382ff,#8c52dd)]',
    kita: 'bg-[linear-gradient(180deg,#63f2ea,#1ab8c8)] text-slate-900',
    pass: 'bg-[linear-gradient(180deg,#8894a7,#566173)]',
    next_round: 'bg-[linear-gradient(180deg,#ffd35b,#ef9215)] text-slate-900',
  };
  return `${base} ${palette[actionType] ?? 'bg-slate-700'}`;
}

function getActionLogTone(type?: string | null): {
  shell: string;
  accent: string;
  badge: string;
  tile: string;
  detail: string;
} {
  type ActionLogTone = {
    shell: string;
    accent: string;
    badge: string;
    tile: string;
    detail: string;
  };

  const fallback: ActionLogTone = {
    shell:
      'border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(103,232,249,0.08),transparent_30%),linear-gradient(180deg,rgba(10,18,28,0.78),rgba(4,10,18,0.58))]',
    accent: 'bg-cyan-300 shadow-[0_0_18px_rgba(103,232,249,0.48)]',
    badge: 'border-cyan-300/25 bg-cyan-400/12 text-cyan-100',
    tile:
      'border-cyan-200/20 bg-[linear-gradient(180deg,rgba(34,211,238,0.18),rgba(9,45,58,0.72))] text-cyan-50',
    detail: 'text-white/78',
  };

  const palette: Record<string, ActionLogTone> = {
    ROUND_START: {
      shell:
        'border-amber-300/18 bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.16),transparent_32%),linear-gradient(180deg,rgba(40,26,9,0.76),rgba(18,12,6,0.6))]',
      accent: 'bg-amber-300 shadow-[0_0_18px_rgba(251,191,36,0.44)]',
      badge: 'border-amber-300/25 bg-amber-300/14 text-amber-100',
      tile:
        'border-amber-200/25 bg-[linear-gradient(180deg,rgba(251,191,36,0.2),rgba(66,34,7,0.76))] text-amber-50',
      detail: 'text-amber-50/88',
    },
    DRAW: {
      shell:
        'border-sky-300/18 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.14),transparent_32%),linear-gradient(180deg,rgba(6,22,36,0.76),rgba(4,10,18,0.6))]',
      accent: 'bg-sky-300 shadow-[0_0_18px_rgba(56,189,248,0.46)]',
      badge: 'border-sky-300/25 bg-sky-400/12 text-sky-100',
      tile:
        'border-sky-200/20 bg-[linear-gradient(180deg,rgba(56,189,248,0.18),rgba(10,36,57,0.74))] text-sky-50',
      detail: 'text-sky-50/84',
    },
    DISCARD: {
      shell:
        'border-orange-300/18 bg-[radial-gradient(circle_at_top_left,rgba(251,146,60,0.14),transparent_32%),linear-gradient(180deg,rgba(40,18,8,0.76),rgba(18,10,6,0.6))]',
      accent: 'bg-orange-300 shadow-[0_0_18px_rgba(251,146,60,0.44)]',
      badge: 'border-orange-300/25 bg-orange-400/12 text-orange-100',
      tile:
        'border-orange-200/20 bg-[linear-gradient(180deg,rgba(251,146,60,0.18),rgba(63,28,10,0.74))] text-orange-50',
      detail: 'text-orange-50/84',
    },
    RIICHI: {
      shell:
        'border-fuchsia-300/18 bg-[radial-gradient(circle_at_top_left,rgba(244,114,182,0.16),transparent_32%),linear-gradient(180deg,rgba(42,10,30,0.78),rgba(21,7,16,0.62))]',
      accent: 'bg-fuchsia-300 shadow-[0_0_18px_rgba(244,114,182,0.46)]',
      badge: 'border-fuchsia-300/28 bg-fuchsia-400/12 text-fuchsia-100',
      tile:
        'border-fuchsia-200/22 bg-[linear-gradient(180deg,rgba(244,114,182,0.18),rgba(64,12,40,0.74))] text-fuchsia-50',
      detail: 'text-fuchsia-50/86',
    },
    CHI: {
      shell:
        'border-cyan-300/18 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.16),transparent_32%),linear-gradient(180deg,rgba(8,28,40,0.76),rgba(5,12,18,0.6))]',
      accent: 'bg-cyan-300 shadow-[0_0_18px_rgba(34,211,238,0.44)]',
      badge: 'border-cyan-300/25 bg-cyan-400/12 text-cyan-100',
      tile:
        'border-cyan-200/22 bg-[linear-gradient(180deg,rgba(34,211,238,0.18),rgba(10,44,60,0.74))] text-cyan-50',
      detail: 'text-cyan-50/84',
    },
    PON: {
      shell:
        'border-violet-300/18 bg-[radial-gradient(circle_at_top_left,rgba(167,139,250,0.16),transparent_32%),linear-gradient(180deg,rgba(18,14,40,0.78),rgba(10,8,20,0.6))]',
      accent: 'bg-violet-300 shadow-[0_0_18px_rgba(167,139,250,0.42)]',
      badge: 'border-violet-300/25 bg-violet-400/12 text-violet-100',
      tile:
        'border-violet-200/22 bg-[linear-gradient(180deg,rgba(167,139,250,0.18),rgba(36,26,64,0.74))] text-violet-50',
      detail: 'text-violet-50/84',
    },
    KAN: {
      shell:
        'border-purple-300/18 bg-[radial-gradient(circle_at_top_left,rgba(192,132,252,0.16),transparent_32%),linear-gradient(180deg,rgba(26,12,40,0.78),rgba(12,8,22,0.62))]',
      accent: 'bg-purple-300 shadow-[0_0_18px_rgba(192,132,252,0.44)]',
      badge: 'border-purple-300/25 bg-purple-400/12 text-purple-100',
      tile:
        'border-purple-200/22 bg-[linear-gradient(180deg,rgba(192,132,252,0.18),rgba(44,22,60,0.74))] text-purple-50',
      detail: 'text-purple-50/84',
    },
    KITA: {
      shell:
        'border-teal-300/18 bg-[radial-gradient(circle_at_top_left,rgba(45,212,191,0.16),transparent_32%),linear-gradient(180deg,rgba(8,34,34,0.76),rgba(5,16,18,0.6))]',
      accent: 'bg-teal-300 shadow-[0_0_18px_rgba(45,212,191,0.42)]',
      badge: 'border-teal-300/25 bg-teal-400/12 text-teal-100',
      tile:
        'border-teal-200/22 bg-[linear-gradient(180deg,rgba(45,212,191,0.18),rgba(8,50,48,0.74))] text-teal-50',
      detail: 'text-teal-50/84',
    },
    RON: {
      shell:
        'border-rose-300/18 bg-[radial-gradient(circle_at_top_left,rgba(251,113,133,0.18),transparent_32%),linear-gradient(180deg,rgba(42,12,18,0.8),rgba(20,8,10,0.64))]',
      accent: 'bg-rose-300 shadow-[0_0_18px_rgba(251,113,133,0.48)]',
      badge: 'border-rose-300/28 bg-rose-400/14 text-rose-100',
      tile:
        'border-rose-200/22 bg-[linear-gradient(180deg,rgba(251,113,133,0.2),rgba(68,20,26,0.76))] text-rose-50',
      detail: 'text-rose-50/88',
    },
    TSUMO: {
      shell:
        'border-emerald-300/18 bg-[radial-gradient(circle_at_top_left,rgba(74,222,128,0.18),transparent_32%),linear-gradient(180deg,rgba(10,34,20,0.78),rgba(6,18,10,0.62))]',
      accent: 'bg-emerald-300 shadow-[0_0_18px_rgba(74,222,128,0.44)]',
      badge: 'border-emerald-300/26 bg-emerald-400/12 text-emerald-100',
      tile:
        'border-emerald-200/22 bg-[linear-gradient(180deg,rgba(74,222,128,0.18),rgba(16,58,32,0.74))] text-emerald-50',
      detail: 'text-emerald-50/86',
    },
    DRAW_END: {
      shell:
        'border-slate-300/16 bg-[radial-gradient(circle_at_top_left,rgba(148,163,184,0.16),transparent_32%),linear-gradient(180deg,rgba(18,24,34,0.78),rgba(10,12,18,0.64))]',
      accent: 'bg-slate-300 shadow-[0_0_18px_rgba(148,163,184,0.32)]',
      badge: 'border-slate-300/22 bg-slate-400/12 text-slate-100',
      tile:
        'border-slate-200/18 bg-[linear-gradient(180deg,rgba(148,163,184,0.16),rgba(24,30,40,0.74))] text-slate-50',
      detail: 'text-slate-100/80',
    },
  };

  return palette[type ?? ''] ?? fallback;
}

function getActionLogFallbackText(type?: string | null): string {
  const fallback: Record<string, string> = {
    ROUND_START: '新的一局开始。',
    DRAW: '摸入一张手牌。',
    DISCARD: '打出一张舍牌。',
    RIICHI: '宣告立直。',
    CHI: '吃入来牌组成顺子。',
    PON: '碰出相同牌组。',
    KAN: '完成一次杠牌。',
    KITA: '拔出一张北牌。',
    RON: '荣和成功。',
    TSUMO: '自摸和牌。',
    DRAW_END: '本局以流局结束。',
  };

  return fallback[type ?? ''] ?? '牌局阶段已推进。';
}

function getActionLogNarrative(entry: ActionLogEntry): string {
  const detailText = humanizeText(entry.details).trim();
  const tileLabel = entry.tile ? formatTileLabelZh(entry.tile) : '';

  if (!detailText || detailText === '-') {
    return getActionLogFallbackText(entry.type);
  }

  if (tileLabel && detailText === tileLabel) {
    return getActionLogFallbackText(entry.type);
  }

  return detailText;
}

function formatHintValue(value: number): string {
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(Math.abs(value) >= 10 ? 0 : 1);
}

function getHintRiskLabel(risk: number): string {
  if (risk <= 0) return '安全';
  if (risk <= 1) return '稳妥';
  if (risk <= 2) return '谨慎';
  return '高危';
}

function getHintCardTone(index: number, risk: number): {
  shell: string;
  rank: string;
  risk: string;
} {
  if (index === 0) {
    return {
      shell:
        'border-amber-300/18 bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.16),transparent_30%),linear-gradient(180deg,rgba(40,26,9,0.78),rgba(18,12,6,0.62))]',
      rank: 'border-amber-300/30 bg-amber-300/14 text-amber-100',
      risk:
        risk <= 1
          ? 'border-emerald-300/26 bg-emerald-400/12 text-emerald-100'
          : 'border-amber-300/28 bg-amber-400/12 text-amber-100',
    };
  }

  if (index === 1) {
    return {
      shell:
        'border-cyan-300/18 bg-[radial-gradient(circle_at_top_left,rgba(103,232,249,0.14),transparent_30%),linear-gradient(180deg,rgba(8,20,32,0.78),rgba(6,10,18,0.6))]',
      rank: 'border-cyan-300/24 bg-cyan-400/12 text-cyan-100',
      risk:
        risk <= 1
          ? 'border-cyan-300/24 bg-cyan-400/12 text-cyan-100'
          : 'border-amber-300/24 bg-amber-400/12 text-amber-100',
    };
  }

  return {
    shell:
      'border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(148,163,184,0.1),transparent_28%),linear-gradient(180deg,rgba(18,24,34,0.76),rgba(10,12,18,0.58))]',
    rank: 'border-white/14 bg-white/6 text-white/72',
    risk:
      risk <= 1
        ? 'border-slate-300/20 bg-slate-400/10 text-slate-100'
        : 'border-rose-300/20 bg-rose-400/10 text-rose-100',
  };
}

function getSpecialActionTypeText(type: string): string {
  const map: Record<string, string> = {
    chi: '吃',
    pon: '碰',
    open_kan: '大明杠',
    closed_kan: '暗杠',
    added_kan: '加杠',
    riichi: '立直',
    tsumo: '自摸',
    ron: '荣和',
    pass: '过',
    kita: '拔北',
    abortive_draw: '流局',
  };
  return map[type] ?? type;
}

const HINTABLE_SPECIAL_ACTION_TYPES = new Set([
  'chi',
  'pon',
  'open_kan',
  'closed_kan',
  'added_kan',
  'riichi',
  'tsumo',
  'ron',
  'pass',
  'kita',
  'abortive_draw',
]);

function isHintableSpecialActionType(type: string): boolean {
  return HINTABLE_SPECIAL_ACTION_TYPES.has(type);
}

function buildFallbackSpecialActionHints(actions: LegalAction[] = []): HintSpecialAction[] {
  return actions
    .filter((action) => isHintableSpecialActionType(action.type))
    .map((action) => ({
      id: action.id,
      type: action.type,
      label: action.label,
      tile: null,
      routes: [getSpecialActionTypeText(action.type)],
      recommended: action.type === 'ron' || action.type === 'tsumo',
      reason: '已检测到当前可执行的特殊操作；如果这里没有 EV 拆分，说明本次状态刷新没有带回后端 AI 评估，下一次刷新会继续尝试显示完整分析。',
      analysis_pending: true,
    }));
}

function formatOptionalHintValue(value?: number | null): string {
  return typeof value === 'number' ? formatHintValue(value) : '-';
}

function getSpecialActionDecisionText(action: HintSpecialAction): string {
  if (action.analysis_pending) {
    return action.type === 'ron' || action.type === 'tsumo' ? '建议和牌' : '可选操作';
  }
  if (action.type === 'ron' || action.type === 'tsumo') {
    return '建议和牌';
  }
  if (action.type === 'pass') {
    return action.recommended ? '建议过' : '不建议过';
  }
  return action.recommended ? '建议执行' : '建议跳过';
}

function getSpecialActionTone(action: HintSpecialAction): {
  shell: string;
  pill: string;
  badge: string;
} {
  if (action.type === 'ron' || action.type === 'tsumo') {
    return {
      shell:
        'border-amber-200/24 bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.18),transparent_32%),linear-gradient(180deg,rgba(45,29,8,0.82),rgba(15,11,5,0.62))]',
      pill: 'border-amber-200/36 bg-amber-300/16 text-amber-50',
      badge: 'border-amber-200/30 bg-amber-300/14 text-amber-100',
    };
  }
  if (action.recommended) {
    return {
      shell:
        'border-emerald-200/20 bg-[radial-gradient(circle_at_top_left,rgba(52,211,153,0.16),transparent_32%),linear-gradient(180deg,rgba(8,35,24,0.82),rgba(5,16,12,0.62))]',
      pill: 'border-emerald-200/28 bg-emerald-300/12 text-emerald-50',
      badge: 'border-emerald-200/24 bg-emerald-300/12 text-emerald-100',
    };
  }
  return {
    shell:
      'border-sky-200/14 bg-[radial-gradient(circle_at_top_left,rgba(125,211,252,0.1),transparent_32%),linear-gradient(180deg,rgba(9,20,32,0.8),rgba(6,10,17,0.62))]',
    pill: 'border-sky-200/18 bg-sky-300/8 text-sky-50/78',
    badge: 'border-white/12 bg-white/6 text-white/70',
  };
}

function formatShantenTransition(action: HintSpecialAction): string {
  const current = typeof action.current_shanten === 'number' ? action.current_shanten : null;
  const next = typeof action.next_shanten === 'number' ? action.next_shanten : null;
  if (current === null && next === null) {
    return '-';
  }
  if (current === -1 || next === -1) {
    return '和牌';
  }
  if (current !== null && next !== null) {
    return `${current} → ${next}`;
  }
  return String(current ?? next);
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
    ...options,
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || '请求失败');
  }
  return data as T;
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function getSnapshotLogEntry(snapshot: ReplaySnapshot): ActionLogEntry | null {
  const lastEntry = snapshot.state.log_tail[snapshot.state.log_tail.length - 1];
  return lastEntry ?? null;
}

const AI_DELAY_ACTION_TYPES = new Set(['DISCARD', 'RIICHI', 'RON', 'TSUMO', 'DRAW_END']);

function isAiSnapshot(snapshot: ReplaySnapshot): boolean {
  const entry = getSnapshotLogEntry(snapshot);
  return typeof entry?.seat === 'number' && entry.seat >= 0 && entry.seat !== snapshot.state.human_seat;
}

function shouldDelayAiSnapshot(snapshot: ReplaySnapshot): boolean {
  if (!isAiSnapshot(snapshot)) {
    return false;
  }
  const entry = getSnapshotLogEntry(snapshot);
  return Boolean(entry && AI_DELAY_ACTION_TYPES.has(entry.type));
}

type CompassSeatPosition = 'north' | 'east' | 'south' | 'west';
type CenterCoreSeatIndicator = {
  position: CompassSeatPosition;
  wind: string;
  isDealer: boolean;
  isActive: boolean;
  isRiichi: boolean;
};

const CENTER_CORE_SEAT_LAYOUT: Record<
  CompassSeatPosition,
  {
    wrapClass: string;
    railClass: string;
    labelClass: string;
  }
> = {
  north: {
    wrapClass: 'left-1/2 top-[14px] -translate-x-1/2',
    railClass: 'h-[14px] w-[78px]',
    labelClass: 'absolute left-1/2 top-[20px] -translate-x-1/2',
  },
  east: {
    wrapClass: 'right-[14px] top-1/2 -translate-y-1/2',
    railClass: 'h-[78px] w-[14px]',
    labelClass: 'absolute right-[20px] top-1/2 -translate-y-1/2',
  },
  south: {
    wrapClass: 'bottom-[14px] left-1/2 -translate-x-1/2',
    railClass: 'h-[14px] w-[78px]',
    labelClass: 'absolute bottom-[20px] left-1/2 -translate-x-1/2',
  },
  west: {
    wrapClass: 'left-[14px] top-1/2 -translate-y-1/2',
    railClass: 'h-[78px] w-[14px]',
    labelClass: 'absolute left-[20px] top-1/2 -translate-y-1/2',
  },
};
const CENTER_CORE_SEAT_ORDER: CompassSeatPosition[] = ['north', 'east', 'south', 'west'];

const COMPASS_SEAT_PLACEMENT: Record<CompassSeatPosition, string> = {
  north: 'left-[58%] top-[78px] -translate-x-1/2',
  east: 'right-[84px] top-[176px]',
  south: 'left-1/2 bottom-[92px] -translate-x-1/2',
  west: 'left-[84px] top-[176px]',
};

const RIICHI_AURA_PLACEMENT: Record<CompassSeatPosition, string> = {
  north: 'left-1/2 top-[118px] h-[120px] w-[290px] -translate-x-1/2',
  east: 'right-[118px] top-1/2 h-[290px] w-[118px] -translate-y-1/2',
  south: 'bottom-[112px] left-1/2 h-[124px] w-[328px] -translate-x-1/2',
  west: 'left-[118px] top-1/2 h-[290px] w-[118px] -translate-y-1/2',
};

const RIICHI_AURA_GLOW: Record<CompassSeatPosition, string> = {
  north:
    'bg-[radial-gradient(circle_at_50%_12%,rgba(255,238,182,0.28),rgba(255,120,190,0.18)_34%,rgba(255,120,190,0)_76%)]',
  east:
    'bg-[radial-gradient(circle_at_88%_50%,rgba(255,238,182,0.28),rgba(255,120,190,0.18)_34%,rgba(255,120,190,0)_76%)]',
  south:
    'bg-[radial-gradient(circle_at_50%_88%,rgba(255,238,182,0.28),rgba(255,120,190,0.18)_34%,rgba(255,120,190,0)_76%)]',
  west:
    'bg-[radial-gradient(circle_at_12%_50%,rgba(255,238,182,0.28),rgba(255,120,190,0.18)_34%,rgba(255,120,190,0)_76%)]',
};

const RIICHI_AURA_STREAK: Record<CompassSeatPosition, string> = {
  north:
    'bg-[linear-gradient(180deg,rgba(255,244,198,0.24),rgba(255,132,196,0.12)_46%,rgba(255,132,196,0)_100%)]',
  east:
    'bg-[linear-gradient(90deg,rgba(255,244,198,0.24),rgba(255,132,196,0.12)_46%,rgba(255,132,196,0)_100%)]',
  south:
    'bg-[linear-gradient(0deg,rgba(255,244,198,0.24),rgba(255,132,196,0.12)_46%,rgba(255,132,196,0)_100%)]',
  west:
    'bg-[linear-gradient(270deg,rgba(255,244,198,0.24),rgba(255,132,196,0.12)_46%,rgba(255,132,196,0)_100%)]',
};

const TableRiichiAura: React.FC<{
  player: PlayerView | null;
  position: CompassSeatPosition;
}> = ({ player, position }) => {
  if (!player?.riichi) {
    return null;
  }

  return (
    <div className={cn('pointer-events-none absolute z-[4]', RIICHI_AURA_PLACEMENT[position])}>
      <div className={cn('absolute inset-0 rounded-[999px] blur-[14px] animate-riichi-aura', RIICHI_AURA_GLOW[position])} />
      <div
        className={cn(
          'absolute inset-[18%] rounded-[999px] opacity-85 blur-[5px] animate-riichi-aura',
          RIICHI_AURA_STREAK[position]
        )}
      />
    </div>
  );
};

const CompassSeatBadge: React.FC<{
  player: PlayerView | null;
  active: boolean;
  position: CompassSeatPosition;
}> = ({
  player,
  active,
  position,
}) => {
  if (!player) {
    return null;
  }

  const isSidePosition = position === 'east' || position === 'west';
  const badgeTone = player.riichi
    ? active
      ? 'mahjong-seat-badge mahjong-seat-badge-riichi mahjong-seat-badge-active animate-riichi-badge'
      : 'mahjong-seat-badge mahjong-seat-badge-riichi animate-riichi-badge'
    : active
      ? 'mahjong-seat-badge mahjong-seat-badge-active'
      : 'mahjong-seat-badge';

  return (
    <div
      className={cn(
        'pointer-events-none absolute z-40 text-center',
        COMPASS_SEAT_PLACEMENT[position],
        isSidePosition ? 'min-w-[134px] rounded-[24px] px-3 py-2.5' : 'min-w-[126px] rounded-[22px] px-3 py-2',
        badgeTone
      )}
    >
      {player.riichi ? (
        <div className="absolute -top-[16px] left-1/2 -translate-x-1/2 rounded-full border border-rose-100/45 bg-[linear-gradient(180deg,rgba(120,27,75,0.96),rgba(74,13,43,0.96))] px-2.5 py-1 text-[10px] font-black tracking-[0.22em] text-rose-50 shadow-[0_10px_20px_rgba(60,8,34,0.32)]">
          立直
        </div>
      ) : null}
      <div className={`flex items-center justify-center gap-1.5 font-semibold text-white/78 ${isSidePosition ? 'text-[11px]' : 'text-[11px]'}`}>
        <span>{WIND_TEXT[player.seat_wind] ?? player.seat_wind}家</span>
        {player.dealer ? (
          <span className="rounded-full bg-amber-300/20 px-2 py-0.5 text-[10px] text-amber-100">庄家</span>
        ) : null}
      </div>
      <div className={`mt-1 font-black text-points-gold drop-shadow-sm ${isSidePosition ? 'text-[15px]' : 'text-[15px]'}`}>
        {formatPoints(player.points)}
      </div>
    </div>
  );
};

const CenterTableCore: React.FC<{
  roundMeta: { wind: string; hand: string; honba: string } | null;
  remainingTiles?: number | null;
  seatIndicators: CenterCoreSeatIndicator[];
}> = ({ roundMeta, remainingTiles, seatIndicators }) => {
  return (
    <div className="absolute left-1/2 top-1/2 z-10 h-[186px] w-[214px] -translate-x-1/2 -translate-y-1/2">
      <div
        className="absolute inset-0 border border-[#8f98ab] bg-[linear-gradient(180deg,rgba(92,102,118,0.98),rgba(43,50,62,0.98)_32%,rgba(16,20,28,0.99)_100%)] shadow-[0_22px_54px_rgba(0,0,0,0.42)]"
        style={{ clipPath: CENTER_CORE_OCTAGON }}
      />
      <div
        className="absolute inset-[3px] border border-black/60 bg-[linear-gradient(180deg,rgba(64,73,87,0.98),rgba(24,29,39,0.99)_36%,rgba(10,13,18,1)_100%)]"
        style={{ clipPath: CENTER_CORE_OCTAGON }}
      />
      <div
        className="absolute inset-[8px] border border-white/8 bg-[linear-gradient(180deg,rgba(35,42,54,0.99),rgba(17,22,30,0.99)_52%,rgba(7,10,15,1)_100%)] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),inset_0_-14px_24px_rgba(0,0,0,0.32)]"
        style={{ clipPath: MECHA_CENTER_CORE_INNER }}
      />
      <div
        className="pointer-events-none absolute inset-[14px] border border-white/5 bg-[radial-gradient(circle_at_50%_28%,rgba(140,228,255,0.06),transparent_28%),radial-gradient(circle_at_50%_76%,rgba(255,198,108,0.06),transparent_26%)]"
        style={{ clipPath: MECHA_CENTER_CORE_INNER }}
      />

      {MECHA_CENTER_CORE_FRAME_STRIPS.map((className) => (
        <div
          key={className}
          className={cn(
            'pointer-events-none absolute rounded-full bg-[linear-gradient(180deg,rgba(255,255,255,0.12),rgba(255,255,255,0.015))] opacity-75',
            className
          )}
        />
      ))}
      {MECHA_CENTER_CORE_GROOVES.map((className) => (
        <div
          key={className}
          className={cn(
            'pointer-events-none absolute rounded-[999px] border border-white/6 bg-[linear-gradient(180deg,rgba(32,38,48,0.96),rgba(12,16,22,0.98))] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
            className
          )}
        />
      ))}
      {MECHA_CENTER_CORE_VENTS.map((className) => (
        <div
          key={className}
          className={cn(
            'pointer-events-none absolute rounded-full bg-[linear-gradient(90deg,rgba(255,255,255,0.16),rgba(255,255,255,0.03))] opacity-70',
            className
          )}
        />
      ))}
      {MECHA_CENTER_CORE_CONNECTORS.map((className) => (
        <div
          key={className}
          className={cn(
            'pointer-events-none absolute rounded-[999px] border border-white/5 bg-[linear-gradient(180deg,rgba(26,32,42,0.95),rgba(10,14,20,0.98))]',
            className
          )}
        />
      ))}
      {MECHA_CENTER_CORE_BOLTS.map((className) => (
        <div
          key={className}
          className={cn(
            'pointer-events-none absolute h-[8px] w-[8px] rounded-full border border-black/60 bg-[radial-gradient(circle_at_32%_32%,rgba(255,255,255,0.42),rgba(70,78,92,0.95)_48%,rgba(10,14,20,0.98)_100%)] shadow-[inset_0_1px_1px_rgba(255,255,255,0.14),0_1px_2px_rgba(0,0,0,0.32)]',
            className
          )}
        />
      ))}
      {MECHA_CENTER_CORE_CORNER_ACCENTS.map((className) => (
        <div key={className} className={cn('pointer-events-none absolute h-[14px] w-[14px] border-white/18 opacity-90', className)} />
      ))}

      <div className="pointer-events-none absolute inset-x-[64px] top-1/2 h-[16px] -translate-y-1/2 rounded-full border border-white/8 bg-[linear-gradient(180deg,rgba(18,24,32,0.98),rgba(5,8,12,1))] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]" />
      <div className="pointer-events-none absolute left-[56px] top-1/2 h-[2px] w-[24px] -translate-y-1/2 rounded-full bg-white/14" />
      <div className="pointer-events-none absolute right-[56px] top-1/2 h-[2px] w-[24px] -translate-y-1/2 rounded-full bg-white/14" />

      {seatIndicators.map((indicator) => {
        const layout = CENTER_CORE_SEAT_LAYOUT[indicator.position];
        const windText = WIND_TEXT[indicator.wind] ?? indicator.wind;
        const railTone = indicator.isActive
          ? 'border-cyan-100/70 bg-[linear-gradient(180deg,rgba(170,243,255,0.94),rgba(74,196,245,0.34))] shadow-[0_0_18px_rgba(118,224,255,0.36),0_0_28px_rgba(118,224,255,0.16),inset_0_1px_0_rgba(255,255,255,0.28)]'
          : indicator.isDealer
            ? 'border-amber-100/60 bg-[linear-gradient(180deg,rgba(255,241,189,0.9),rgba(255,185,76,0.28))] shadow-[0_0_18px_rgba(255,193,86,0.26),inset_0_1px_0_rgba(255,255,255,0.18)]'
            : indicator.isRiichi
              ? 'border-rose-100/32 bg-[linear-gradient(180deg,rgba(153,61,112,0.58),rgba(54,15,35,0.22))] shadow-[0_0_18px_rgba(255,121,196,0.14)]'
              : 'border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.015))] opacity-75';
        const labelTone = indicator.isActive
          ? 'border-cyan-100/70 bg-[linear-gradient(180deg,rgba(34,87,114,0.98),rgba(8,24,36,0.98))] text-cyan-50 shadow-[0_0_14px_rgba(118,224,255,0.2),0_6px_12px_rgba(0,0,0,0.2)]'
          : indicator.isRiichi
            ? 'border-rose-100/30 bg-[linear-gradient(180deg,rgba(77,29,56,0.98),rgba(25,10,19,0.98))] text-rose-50/90 shadow-[0_6px_14px_rgba(0,0,0,0.18)]'
            : 'border-white/8 bg-[linear-gradient(180deg,rgba(24,31,42,0.96),rgba(11,15,21,0.98))] text-white/72 shadow-[0_6px_12px_rgba(0,0,0,0.18)]';

        return (
          <div key={indicator.position} className={cn('pointer-events-none absolute z-[3]', layout.wrapClass)}>
            <div className={cn('rounded-full border', layout.railClass, railTone)} />
            <div className={layout.labelClass}>
              <div className={cn('flex items-center gap-1.5 rounded-full border px-2 py-[3px] text-[9px] font-black tracking-[0.18em]', labelTone)}>
                <span>{windText}</span>
                {indicator.isDealer ? (
                  <span className="rounded-full border border-amber-100/65 bg-[linear-gradient(180deg,rgba(113,76,18,0.98),rgba(59,37,8,0.98))] px-1.5 py-[1px] text-[8px] tracking-[0.12em] text-amber-100 shadow-[0_0_10px_rgba(255,187,56,0.2)]">
                    庄
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}

      <div
        className="absolute inset-x-[42px] top-[34px] h-[44px] overflow-hidden border border-cyan-100/12 bg-[linear-gradient(180deg,rgba(11,21,28,0.98),rgba(3,7,11,1))] px-3 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.08),inset_0_-6px_12px_rgba(0,0,0,0.24)]"
        style={{ clipPath: MECHA_CENTER_CORE_TOP_SCREEN }}
      >
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(174,239,255,0.08),rgba(174,239,255,0)_40%,rgba(0,0,0,0.18)_100%)]" />
        <div className="pointer-events-none absolute inset-0 opacity-[0.16] bg-[linear-gradient(180deg,rgba(255,255,255,0.16)_0,rgba(255,255,255,0.16)_1px,transparent_1px,transparent_4px)]" />
        <div className="pointer-events-none absolute inset-[2px] border border-white/4" style={{ clipPath: MECHA_CENTER_CORE_TOP_SCREEN }} />
        <div className="relative grid grid-cols-2 gap-4">
          <div className="text-left">
            <div className="text-[8px] font-semibold tracking-[0.2em] text-white/36">风场</div>
            <div className="mt-1 whitespace-nowrap text-[13px] font-black tracking-[0.14em] text-cyan-100/92">
              {roundMeta ? `${roundMeta.wind}风场` : '-'}
            </div>
          </div>
          <div className="text-left">
            <div className="text-[8px] font-semibold tracking-[0.2em] text-white/36">局数</div>
            <div className="mt-1 whitespace-nowrap text-[13px] font-black tracking-[0.14em] text-amber-100/92">
              {roundMeta ? `${ROUND_HAND_TEXT[roundMeta.hand] ?? roundMeta.hand}局` : '-'}
            </div>
          </div>
        </div>
      </div>

      <div
        className="absolute inset-x-[56px] bottom-[34px] h-[48px] overflow-hidden border border-emerald-100/10 bg-[linear-gradient(180deg,rgba(8,20,18,0.98),rgba(2,8,6,1))] px-3 py-2 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.06),inset_0_-6px_12px_rgba(0,0,0,0.24)]"
        style={{ clipPath: MECHA_CENTER_CORE_BOTTOM_SCREEN }}
      >
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(173,255,216,0.06),rgba(173,255,216,0)_38%,rgba(0,0,0,0.18)_100%)]" />
        <div className="pointer-events-none absolute inset-0 opacity-[0.14] bg-[linear-gradient(180deg,rgba(255,255,255,0.14)_0,rgba(255,255,255,0.14)_1px,transparent_1px,transparent_4px)]" />
        <div className="pointer-events-none absolute inset-[2px] border border-white/4" style={{ clipPath: MECHA_CENTER_CORE_BOTTOM_SCREEN }} />
        <div className="relative text-[8px] font-semibold tracking-[0.2em] text-white/36">剩余牌</div>
        <div className="relative mt-1 font-mono text-[22px] font-black leading-none tracking-[0.08em] text-emerald-50">
          {remainingTiles ?? '-'}
        </div>
      </div>
    </div>
  );
};

type TableMeldTileSlot = {
  tile: Tile;
  faceDown?: boolean;
  rotated?: boolean;
  stackedTile?: Tile | null;
};

function getCalledTileIndex(meld: BackendMeld, playerSeat: number, playerCount: number): number | null {
  if (!meld.opened || meld.type === 'closed_kan' || meld.type === 'kita') {
    return null;
  }

  if (meld.type === 'chi') {
    return Math.min(2, Math.max(0, meld.tiles.length - 1));
  }

  if (typeof meld.from_seat !== 'number') {
    return Math.min(1, Math.max(0, meld.tiles.length - 1));
  }

  const relativeSeat = (meld.from_seat - playerSeat + playerCount) % playerCount;
  if (relativeSeat === playerCount - 1) {
    return 0;
  }
  if (relativeSeat === 2) {
    return Math.min(1, Math.max(0, meld.tiles.length - 1));
  }
  return Math.max(0, meld.tiles.length - 1);
}

function buildTableMeldSlots(meld: BackendMeld, playerSeat: number, playerCount: number): TableMeldTileSlot[] {
  const tiles = meld.tiles.map((tile) => parseTileLabel(tile)).filter((tile): tile is Tile => tile !== null);
  if (!tiles.length) {
    return [];
  }

  if (meld.type === 'closed_kan' && tiles.length >= 4) {
    return tiles.map((tile, index) => ({
      tile,
      faceDown: index === 0 || index === tiles.length - 1,
    }));
  }

  if (meld.type === 'added_kan' && tiles.length >= 4) {
    const calledIndex = getCalledTileIndex(meld, playerSeat, playerCount);
    const baseTiles = tiles.slice(0, 3);
    const stackIndex = calledIndex === null ? 1 : Math.min(calledIndex, baseTiles.length - 1);

    return baseTiles.map((tile, index) => ({
      tile,
      rotated: index === stackIndex,
      stackedTile: index === stackIndex ? tiles[3] : null,
    }));
  }

  const calledIndex = getCalledTileIndex(meld, playerSeat, playerCount);
  return tiles.map((tile, index) => ({
    tile,
    rotated: index === calledIndex,
  }));
}

const TableMeldTile: React.FC<{
  slot: TableMeldTileSlot;
}> = ({ slot }) => {
  const widthClass = slot.rotated ? 'w-[40px]' : 'w-[30px]';

  return (
    <div className={`relative flex ${widthClass} items-end justify-center`}>
      <MahjongTile
        tile={slot.tile}
        size="sm"
        isFaceDown={slot.faceDown}
        className={slot.rotated ? 'origin-center rotate-90 translate-y-[5px]' : ''}
      />
      {slot.stackedTile ? (
        <MahjongTile
          tile={slot.stackedTile}
          size="sm"
          className="absolute -top-[16px] left-1/2 -translate-x-1/2 scale-[0.84] shadow-lg"
        />
      ) : null}
    </div>
  );
};

function TableMeldStrip({
  melds,
  position,
  playerSeat,
  playerCount,
}: {
  melds: BackendMeld[];
  position: SeatPosition;
  playerSeat: number;
  playerCount: number;
}) {
  if (!melds.length) {
    return null;
  }

  const placement: Record<SeatPosition, string> = {
    bottom: 'bottom-[92px] right-[350px] max-w-[360px]',
    right: 'right-[88px] top-[calc(50%+168px)] w-[300px]',
    top: 'right-[286px] top-[88px] max-w-[320px]',
    left: 'left-[88px] top-[calc(50%+168px)] w-[300px]',
  };

  const layoutClass: Record<SeatPosition, string> = {
    bottom: 'flex flex-wrap justify-end gap-2',
    right: 'flex flex-col-reverse items-end gap-3',
    top: 'flex flex-wrap justify-end gap-2',
    left: 'flex flex-col-reverse items-start gap-3',
  };

  const meldOrientationClass: Record<SeatPosition, string> = {
    bottom: '',
    right: '',
    top: 'rotate-180 origin-center',
    left: '',
  };

  return (
    <div className={`pointer-events-none absolute ${placement[position]} z-40`}>
      <div className={layoutClass[position]}>
        {melds.map((meld, index) => {
          const slots = buildTableMeldSlots(meld, playerSeat, playerCount);

          if (!slots.length) {
            return null;
          }

          return (
            <div
              key={`${position}-${meld.type}-${index}`}
              className={`relative flex min-h-[52px] items-end gap-1 rounded-2xl border border-white/10 bg-black/32 px-2 py-1.5 shadow-[0_14px_26px_rgba(0,0,0,0.24)] backdrop-blur-sm ${meldOrientationClass[position]}`}
            >
              {slots.map((slot, tileIndex) => (
                <TableMeldTile key={`${position}-${meld.type}-${index}-${tileIndex}`} slot={slot} />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MeldStrip({ melds }: { melds: BackendMeld[] }) {
  if (!melds.length) {
    return <div className="text-xs text-white/45">暂无副露</div>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {melds.map((meld, index) => (
        <div
          key={`${meld.type}-${index}`}
          className="flex items-center gap-2 rounded-2xl border border-white/15 bg-black/25 px-2 py-1"
        >
          <Badge variant="outline" className="border-white/15 text-[10px] text-white/75">
            {MELD_TEXT[meld.type] ?? meld.type}
          </Badge>
          <div className="flex gap-1">
            {meld.tiles
              .map((tile) => parseTileLabel(tile))
              .filter((tile): tile is Tile => tile !== null)
              .map((tile, tileIndex) => (
                <MahjongTile key={`${meld.type}-${index}-${tileIndex}`} tile={tile} size="sm" />
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ResultHandBlock({
  player,
  winTileLabel,
  isTsumo,
}: {
  player: PlayerView | null;
  winTileLabel?: string | null;
  isTsumo?: boolean;
}) {
  if (!player) {
    return null;
  }

  const preview = buildResultHandPreview(player.hand, winTileLabel, isTsumo);

  return (
    <div className="mt-3 rounded-2xl border border-white/10 bg-black/15 p-3">
      <div className="text-[11px] font-semibold tracking-[0.16em] text-white/55">和牌牌型</div>
      <div className="mt-3 flex flex-wrap items-end gap-1.5">
        {preview.concealedTiles.length ? (
          preview.concealedTiles.map((tile, tileIndex) => (
            <MahjongTile
              key={`result-hand-${player.seat}-${tileIndex}-${tile.suit}-${tile.value}-${tile.isRed ? 'red' : 'normal'}`}
              tile={tile}
              size="sm"
            />
          ))
        ) : (
          <div className="text-xs text-white/45">暂无手牌数据</div>
        )}

        {preview.winningTile ? (
          <>
            <div className="mx-1 h-8 w-px rounded-full bg-white/12" />
            <MahjongTile
              tile={preview.winningTile}
              size="sm"
              className="border-amber-200 shadow-[0_5px_0_rgba(168,120,34,0.24),0_0_0_1px_rgba(255,237,170,0.35),0_12px_20px_rgba(251,191,36,0.18)]"
            />
          </>
        ) : null}
      </div>

      {player.melds.length ? (
        <div className="mt-3">
          <div className="mb-2 text-[11px] font-semibold tracking-[0.16em] text-white/45">副露</div>
          <MeldStrip melds={player.melds} />
        </div>
      ) : null}
    </div>
  );
}

function HintPanel({
  hint,
  legalActions = [],
}: {
  hint: HintView | null | undefined;
  legalActions?: LegalAction[];
}) {
  const fallbackSpecialActionHints = hint ? [] : buildFallbackSpecialActionHints(legalActions);
  const topDiscards = hint?.top_discards ?? [];
  const specialActionHints =
    hint?.special_actions && hint.special_actions.length ? hint.special_actions : fallbackSpecialActionHints;
  const hasHintContent = Boolean(hint) || specialActionHints.length > 0;

  if (!hasHintContent) {
    return (
      <div className="mahjong-hint-empty px-4 py-5 text-sm text-white/65">
        提示区会结合向听、进张和风险，给出更适合当前巡目的操作建议。
      </div>
    );
  }

  const leadSpecialAction = specialActionHints.find((item) => item.recommended) ?? specialActionHints[0] ?? null;
  const topPick = topDiscards[0] ?? null;
  const topPickTile = topPick ? parseTileLabel(topPick.tile) : null;
  const topPickLabel = topPick ? formatTileLabelZh(topPick.tile) : '-';
  const topPickRoutes = topPick?.routes ?? [];

  return (
    <div className="space-y-4 text-white">
      <div className="mahjong-hint-shell p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
              <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">行动总览</div>
              <div className="mt-3 flex items-end gap-2">
              <div className="text-3xl font-black tracking-[0.08em] text-cyan-50">{hint?.shanten ?? '-'}</div>
              <div className="pb-1 text-sm font-semibold text-white/62">向听</div>
            </div>
          </div>

          {topPick ? (
            <div className="shrink-0 text-right">
              <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">当前推荐</div>
              <div className="mt-2 flex items-center justify-end gap-2">
                {topPickTile ? <MahjongTile tile={topPickTile} size="sm" /> : null}
                <div className="text-base font-bold text-white/92">{topPickLabel}</div>
              </div>
            </div>
          ) : null}
        </div>

        {topPick ? (
          <div className="mt-4 space-y-3">
            <div className="grid gap-2 sm:grid-cols-3">
              <div className="mahjong-hint-summary-chip">
                <span className="text-white/45">进张</span>
                <span className="text-white/88">{topPick.ukeire}</span>
              </div>
              <div className="mahjong-hint-summary-chip">
                <span className="text-white/45">风险</span>
                <span className="text-white/88">{formatHintValue(topPick.risk)}</span>
              </div>
              <div className="mahjong-hint-summary-chip">
                <span className="text-white/45">有效牌种</span>
                <span className="text-white/88">{topPick.waits.length}</span>
              </div>
            </div>

            {topPickRoutes.length ? (
              <div>
                <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">推荐路线</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {topPickRoutes.map((route) => (
                    <span key={`top-route-${route}`} className="mahjong-hint-route">
                      {route}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {leadSpecialAction ? (
          <div className="mt-4 rounded-2xl border border-cyan-200/14 bg-cyan-950/18 px-3 py-3 text-xs text-cyan-50/78">
            <div className="flex items-center justify-between gap-3">
              <span className="font-semibold">特殊操作</span>
              <span className="truncate text-right">
                {getSpecialActionDecisionText(leadSpecialAction)} · {humanizeText(leadSpecialAction.label)}
              </span>
            </div>
            <div className="mt-1 text-white/45">
              EV {formatOptionalHintValue(leadSpecialAction.final_ev)}
              {typeof leadSpecialAction.threshold === 'number'
                ? ` / 阈值 ${formatHintValue(leadSpecialAction.threshold)}`
                : ''}
            </div>
          </div>
        ) : null}
      </div>

      {specialActionHints.length ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3 px-1">
            <div>
              <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">特殊操作分析</div>
              <div className="mt-1 text-xs text-white/52">碰、杠、吃、荣和等操作会单独比较收益和风险。</div>
            </div>
          </div>

          {specialActionHints.map((action) => {
            const tone = getSpecialActionTone(action);
            const actionTile = action.tile ? parseTileLabel(action.tile) : null;
            const routeList = action.routes ?? [];
            const evBreakdown = [
              { label: '速度', value: action.speed_ev },
              { label: '打点', value: action.value_ev },
              { label: '防守', value: action.defense_ev },
              { label: '局况', value: action.table_ev },
              { label: '后续', value: action.post_discard_ev },
              { label: '承诺', value: action.call_commitment_ev ?? undefined },
            ].filter((entry): entry is { label: string; value: number } => typeof entry.value === 'number');

            return (
              <div key={action.id} className={cn('mahjong-hint-card p-4', tone.shell)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className={cn('mahjong-hint-rank', tone.badge)}>{getSpecialActionTypeText(action.type)}</span>
                    {actionTile ? <MahjongTile tile={actionTile} size="sm" /> : null}
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">可选操作</div>
                      <div className="truncate text-base font-bold text-white/92">{humanizeText(action.label)}</div>
                    </div>
                  </div>
                  <span className={cn('mahjong-hint-risk-pill', tone.pill)}>{getSpecialActionDecisionText(action)}</span>
                </div>

                <div className="mt-4 grid grid-cols-3 gap-2">
                  <div className="mahjong-hint-metric">
                    <span className="text-white/45">向听</span>
                    <strong>{formatShantenTransition(action)}</strong>
                  </div>
                  <div className="mahjong-hint-metric">
                    <span className="text-white/45">EV</span>
                    <strong>{formatOptionalHintValue(action.final_ev)}</strong>
                  </div>
                  <div className="mahjong-hint-metric">
                    <span className="text-white/45">阈值</span>
                    <strong>{formatOptionalHintValue(action.threshold)}</strong>
                  </div>
                </div>

                {action.strategy_label || action.best_discard_tile ? (
                  <div className="mt-3 flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-white/62">
                    <span className="font-semibold">{action.strategy_label ? '局况目标' : '鸣后建议'}</span>
                    <span className="truncate text-right">
                      {action.strategy_label ? humanizeText(action.strategy_label) : ''}
                      {action.strategy_label && action.best_discard_tile ? ' · ' : ''}
                      {action.best_discard_tile ? `鸣后建议打 ${formatTileLabelZh(action.best_discard_tile)}` : ''}
                    </span>
                  </div>
                ) : null}

                {action.yaku_label ? (
                  <div
                    className={cn(
                      'mt-3 flex items-center justify-between gap-3 rounded-2xl border px-3 py-2 text-xs',
                      action.has_yaku_path === false
                        ? 'border-rose-200/18 bg-rose-950/20 text-rose-50/78'
                        : action.guaranteed_yaku
                          ? 'border-emerald-200/18 bg-emerald-950/18 text-emerald-50/78'
                          : 'border-amber-200/16 bg-amber-950/16 text-amber-50/76'
                    )}
                  >
                    <span className="font-semibold">和牌路线</span>
                    <span className="truncate text-right">
                      {humanizeText(action.yaku_label)}
                      {typeof action.yaku_confidence === 'number'
                        ? ` · 稳定度 ${Math.round(action.yaku_confidence * 100)}`
                        : ''}
                    </span>
                  </div>
                ) : null}

                {action.call_commitment_label ? (
                  <div
                    className={cn(
                      'mt-3 flex items-center justify-between gap-3 rounded-2xl border px-3 py-2 text-xs',
                      action.call_commitment_blocker
                        ? 'border-rose-200/18 bg-rose-950/20 text-rose-50/78'
                        : 'border-sky-200/16 bg-sky-950/14 text-sky-50/76'
                    )}
                  >
                    <span className="font-semibold">副露承诺</span>
                    <span className="truncate text-right">
                      {humanizeText(action.call_commitment_label)}
                      {action.call_commitment_reason ? ` · ${humanizeText(action.call_commitment_reason)}` : ''}
                    </span>
                  </div>
                ) : null}

                {action.reason ? (
                  <div className="mt-3 rounded-2xl border border-cyan-200/12 bg-cyan-950/14 px-3 py-2 text-xs leading-5 text-cyan-50/72">
                    {humanizeText(action.reason)}
                  </div>
                ) : null}

                {evBreakdown.length ? (
                  <div className="mt-4">
                    <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">EV 拆分</div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {evBreakdown.map((entry) => (
                        <div key={`${action.id}-ev-${entry.label}`} className="mahjong-hint-ev-chip">
                          <span>{entry.label}</span>
                          <strong>{formatHintValue(entry.value)}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {routeList.length ? (
                  <div className="mt-4">
                    <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">操作路线</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {routeList.map((route) => (
                        <span key={`${action.id}-route-${route}`} className="mahjong-hint-route">
                          {humanizeText(route)}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      <div className="space-y-3">
        {topDiscards.map((item, index) => {
          const tone = getHintCardTone(index, item.risk);
          const discardTile = parseTileLabel(item.tile);
          const priorityText = index === 0 ? '首选' : index === 1 ? '次选' : `备选 ${index + 1}`;
          const routeList = item.routes ?? [];
          const riskSources = item.risk_sources ?? [];
          const safetyScore = typeof item.safety_score === 'number' ? Math.round(item.safety_score * 100) : null;
          const waitQuality = typeof item.wait_quality === 'number' ? Math.round(item.wait_quality * 100) : null;
          const pressureScore = typeof item.pressure_score === 'number' ? Math.round(item.pressure_score * 100) : null;
          const commitmentScore = typeof item.commitment_score === 'number' ? Math.round(item.commitment_score * 100) : null;
          const valueRoutes = item.value_routes ?? [];
          const evBreakdown = [
            { label: '速度', value: item.speed_ev },
            { label: '打点', value: item.value_ev },
            { label: '防守', value: item.defense_ev },
            { label: '局况', value: item.table_ev },
            { label: '前瞻', value: item.lookahead_ev },
            { label: '安全', value: item.safety_ev },
            { label: '形状', value: item.shape_ev },
            { label: '预打点', value: item.hand_value_ev },
            { label: '押退', value: item.push_fold_ev },
            { label: '强防', value: item.defense_override_ev },
          ].filter((entry): entry is { label: string; value: number } => typeof entry.value === 'number');

          return (
            <div
              key={`${item.tile}-${item.ukeire}-${item.risk}-${item.score}`}
              className={cn('mahjong-hint-card p-4', tone.shell)}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <span className={cn('mahjong-hint-rank', tone.rank)}>{priorityText}</span>
                  {discardTile ? <MahjongTile tile={discardTile} size="sm" /> : null}
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">建议打出</div>
                    <div className="truncate text-base font-bold text-white/92">{formatTileLabelZh(item.tile)}</div>
                  </div>
                </div>
                <span className={cn('mahjong-hint-risk-pill', tone.risk)}>{getHintRiskLabel(item.risk)}</span>
              </div>

              {item.safety_label ? (
                <div
                  className={cn(
                    'mt-3 flex items-center justify-between gap-3 rounded-2xl border px-3 py-2 text-xs',
                    item.defense_mode
                      ? 'border-cyan-200/22 bg-cyan-950/24 text-cyan-50/82'
                      : 'border-white/10 bg-white/[0.04] text-white/58',
                  )}
                >
                  <span className="font-semibold">{item.defense_mode ? '防守模式' : '安全判断'}</span>
                  <span className="truncate text-right">
                    {item.safety_label}
                    {safetyScore !== null ? ` · ${safetyScore}` : ''}
                  </span>
                </div>
              ) : null}

              {item.strategy_label ? (
                <div className="mt-2 flex items-center justify-between gap-3 rounded-2xl border border-amber-200/14 bg-amber-950/16 px-3 py-2 text-xs text-amber-50/72">
                  <span className="font-semibold">局况目标</span>
                  <span className="truncate text-right">
                    {item.strategy_label}
                    {typeof item.placement === 'number' ? ` · 第 ${item.placement} 位` : ''}
                  </span>
                </div>
              ) : null}

              {item.push_fold_label ? (
                <div
                  className={cn(
                    'mt-2 rounded-2xl border px-3 py-2 text-xs',
                    item.push_fold_mode === 'fold'
                      ? 'border-sky-200/18 bg-sky-950/18 text-sky-50/76'
                      : item.push_fold_mode === 'balanced'
                        ? 'border-lime-200/14 bg-lime-950/14 text-lime-50/72'
                        : 'border-rose-200/14 bg-rose-950/14 text-rose-50/74',
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-semibold">押退判断</span>
                    <span className="truncate text-right">{item.push_fold_label}</span>
                  </div>
                  {pressureScore !== null || commitmentScore !== null ? (
                    <div className="mt-1 truncate text-[11px] opacity-70">
                      {pressureScore !== null ? `威胁 ${pressureScore}` : ''}
                      {pressureScore !== null && commitmentScore !== null ? ' · ' : ''}
                      {commitmentScore !== null ? `胜负度 ${commitmentScore}` : ''}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {item.defense_override_label ? (
                <div className="mt-2 rounded-2xl border border-sky-200/18 bg-sky-950/20 px-3 py-2 text-xs text-sky-50/78">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-semibold">{item.forced_defense ? '强制防守' : '防守修正'}</span>
                    <span className="truncate text-right">
                      {item.defense_override_label}
                      {typeof item.fold_need === 'number' ? ` · 压力差 ${formatHintValue(item.fold_need)}` : ''}
                    </span>
                  </div>
                </div>
              ) : null}

              {item.shape_label ? (
                <div className="mt-2 flex items-center justify-between gap-3 rounded-2xl border border-emerald-200/14 bg-emerald-950/16 px-3 py-2 text-xs text-emerald-50/72">
                  <span className="font-semibold">牌型质量</span>
                  <span className="truncate text-right">
                    {item.shape_label}
                    {waitQuality !== null ? ` · ${waitQuality}` : ''}
                  </span>
                </div>
              ) : null}

              {item.value_label ? (
                <div className="mt-2 rounded-2xl border border-orange-200/14 bg-orange-950/16 px-3 py-2 text-xs text-orange-50/72">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-semibold">预计打点</span>
                    <span className="truncate text-right">
                      {item.value_label}
                      {typeof item.estimated_han === 'number' ? ` · ${formatHintValue(item.estimated_han)}番` : ''}
                      {typeof item.estimated_value === 'number' ? ` · ${item.estimated_value}` : ''}
                    </span>
                  </div>
                  {valueRoutes.length || typeof item.dora_count === 'number' ? (
                    <div className="mt-1 truncate text-[11px] text-orange-50/48">
                      {valueRoutes.length ? valueRoutes.join(' / ') : '基础路线'}
                      {typeof item.dora_count === 'number' ? ` · 宝牌 ${item.dora_count}` : ''}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="mt-4 grid grid-cols-3 gap-2">
                <div className="mahjong-hint-metric">
                  <span className="text-white/45">进张</span>
                  <strong>{item.ukeire}</strong>
                </div>
                <div className="mahjong-hint-metric">
                  <span className="text-white/45">风险</span>
                  <strong>{formatHintValue(item.risk)}</strong>
                </div>
                <div className="mahjong-hint-metric">
                  <span className="text-white/45">综合</span>
                  <strong>{formatHintValue(item.score)}</strong>
                </div>
              </div>

              {evBreakdown.length ? (
                <div className="mt-4">
                  <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">EV 拆分</div>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {evBreakdown.map((entry) => (
                      <div key={`${item.tile}-ev-${entry.label}`} className="mahjong-hint-ev-chip">
                        <span>{entry.label}</span>
                        <strong>{formatHintValue(entry.value)}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {riskSources.length ? (
                <div className="mt-4">
                  <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">危险来源</div>
                  <div className="mt-2 space-y-2">
                    {riskSources.map((source) => (
                      <div
                        key={`${item.tile}-risk-${source.seat}`}
                        className="rounded-2xl border border-rose-200/12 bg-rose-950/20 px-3 py-2 text-xs text-rose-50/78"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="truncate font-semibold">{source.name}</span>
                          <span className="font-mono text-rose-100">{formatHintValue(source.risk)}</span>
                        </div>
                        <div className="mt-1 flex items-center justify-between gap-3 text-[11px] text-rose-50/48">
                          <span className="truncate">{source.routes.join(' / ')}</span>
                          <span>预估 {source.estimated_loss}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {routeList.length ? (
                <div className="mt-4">
                  <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">推荐路线</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {routeList.map((route) => (
                      <span key={`${item.tile}-route-${route}`} className="mahjong-hint-route">
                        {route}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              {item.waits.length ? (
                <div className="mt-4">
                  <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">有效进张</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {item.waits.map((wait) => (
                      <span key={`${item.tile}-${wait}`} className="mahjong-hint-wait">
                        {formatTileLabelZh(wait)}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mt-4 text-xs text-white/52">当前没有额外记录到有效进张。</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

type DockPanelKey = 'setup' | 'stats' | 'history' | 'status' | 'intel' | 'log' | 'replay' | 'hint';

type DockItemConfig = {
  key: DockPanelKey;
  label: string;
  ariaLabel: string;
  icon: React.ReactNode;
  badge?: string | number;
  disabled?: boolean;
};

const DOCK_PANEL_KEYS: DockPanelKey[] = ['setup', 'stats', 'history', 'status', 'intel', 'log', 'replay', 'hint'];

const DOCK_PANEL_META: Record<DockPanelKey, { title: string; subtitle: string }> = {
  setup: { title: '开局设置', subtitle: '新对局、规则、电脑强度与动画节奏。' },
  stats: { title: '玩家统计', subtitle: '查看当前玩家的战绩概览。' },
  history: { title: '历史对局', subtitle: '载入、回看或删除本地存档。' },
  status: { title: '你的状态', subtitle: '当前手顺、副露、牌河和操作状态。' },
  intel: { title: '牌桌情报', subtitle: '观察其他玩家的点数、副露、牌河和 AI 判断。' },
  log: { title: '对局记录', subtitle: '最近摸牌、打牌、鸣牌和结算事件。' },
  replay: { title: '牌谱回看', subtitle: '沿时间轴查看完整对局。' },
  hint: { title: '行动提示', subtitle: 'AI 推荐打法、风险、进张和押退判断。' },
};

function getDockPanelFromHash(): DockPanelKey | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const key = window.location.hash.replace(/^#dock-/, '') as DockPanelKey;
  return DOCK_PANEL_KEYS.includes(key) ? key : null;
}

function updateDockRoute(key: DockPanelKey | null) {
  if (typeof window === 'undefined') {
    return;
  }
  const nextUrl = `${window.location.pathname}${window.location.search}${key ? `#dock-${key}` : ''}`;
  window.history.pushState(null, '', nextUrl);
}

function getDockScale(index: number, hoveredIndex: number | null, active: boolean) {
  if (hoveredIndex === null) {
    return active ? 1.12 : 1;
  }
  const distance = Math.abs(index - hoveredIndex);
  if (distance === 0) return 1.46;
  if (distance === 1) return 1.24;
  if (distance === 2) return 1.1;
  return active ? 1.08 : 1;
}

function DockPanelShell({
  activeKey,
  children,
  onClose,
}: {
  activeKey: DockPanelKey;
  children: React.ReactNode;
  onClose: () => void;
}) {
  const meta = DOCK_PANEL_META[activeKey];

  return (
    <motion.div
      key={activeKey}
      initial={{ opacity: 0, y: 22, scale: 0.96, filter: 'blur(10px)' }}
      animate={{ opacity: 1, y: 0, scale: 1, filter: 'blur(0px)' }}
      exit={{ opacity: 0, y: 18, scale: 0.97, filter: 'blur(8px)' }}
      transition={{ type: 'spring', stiffness: 360, damping: 34, mass: 0.9 }}
      className="fixed inset-x-0 bottom-[108px] z-40 flex justify-center px-3"
      role="dialog"
      aria-label={meta.title}
    >
      <div className="relative w-[min(calc(100vw-1.5rem),1080px)] overflow-hidden rounded-[32px] border border-white/14 bg-[linear-gradient(180deg,rgba(18,31,35,0.88),rgba(5,9,13,0.86))] text-white shadow-[0_26px_90px_rgba(0,0,0,0.46),0_0_0_1px_rgba(255,255,255,0.04)] backdrop-blur-2xl">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_0%,rgba(125,255,214,0.18),transparent_32%),radial-gradient(circle_at_82%_12%,rgba(255,211,105,0.12),transparent_30%),linear-gradient(180deg,rgba(255,255,255,0.08),transparent_32%)]" />
        <div className="relative flex items-start justify-between gap-4 border-b border-white/10 px-5 py-4">
          <div className="min-w-0">
            <div className="text-[11px] font-black tracking-[0.22em] text-cyan-100/58">牌桌 Dock 面板</div>
            <h2 className="mt-1 text-xl font-black tracking-[0.08em] text-white">{meta.title}</h2>
            <p className="mt-1 text-xs leading-5 text-white/58">{meta.subtitle}</p>
          </div>
          <button
            type="button"
            aria-label="关闭面板"
            className="rounded-full border border-white/12 bg-white/8 p-2 text-white/70 transition hover:bg-white/14 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-200"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <div className="relative max-h-[min(70vh,680px)] overflow-y-auto px-5 py-5">{children}</div>
      </div>
    </motion.div>
  );
}

function MacDock({
  items,
  activeKey,
  onSelect,
}: {
  items: DockItemConfig[];
  activeKey: DockPanelKey | null;
  onSelect: (key: DockPanelKey) => void;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <motion.nav
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 320, damping: 28 }}
      className="fixed inset-x-0 bottom-5 z-50 flex justify-center px-3"
      aria-label="牌桌底部 Dock 导航"
      onMouseLeave={() => setHoveredIndex(null)}
    >
      <div className="inline-flex items-end gap-2 rounded-[28px] border border-white/16 bg-[linear-gradient(180deg,rgba(255,255,255,0.18),rgba(255,255,255,0.08)),rgba(7,14,18,0.68)] px-3 py-2.5 shadow-[0_18px_58px_rgba(0,0,0,0.36),inset_0_1px_0_rgba(255,255,255,0.16)] backdrop-blur-2xl">
        {items.map((item, index) => {
          const active = activeKey === item.key;
          const scale = getDockScale(index, hoveredIndex, active);

          return (
            <motion.button
              key={item.key}
              type="button"
              aria-label={item.ariaLabel}
              aria-current={active ? 'page' : undefined}
              disabled={item.disabled}
              className={cn(
                'group relative flex h-12 w-12 items-center justify-center rounded-2xl border text-white shadow-[0_10px_24px_rgba(0,0,0,0.24)] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-200 sm:h-14 sm:w-14',
                active
                  ? 'border-cyan-200/55 bg-[radial-gradient(circle_at_30%_18%,rgba(255,255,255,0.26),transparent_34%),linear-gradient(180deg,rgba(58,217,255,0.35),rgba(15,65,76,0.66))] text-cyan-50'
                  : 'border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.16),rgba(255,255,255,0.05))] text-white/72 hover:text-white',
                item.disabled ? 'cursor-not-allowed opacity-45' : ''
              )}
              style={{ transformOrigin: '50% 100%' }}
              animate={{ scale, y: hoveredIndex === index ? -12 : active ? -5 : 0 }}
              transition={{ type: 'spring', stiffness: 420, damping: 24, mass: 0.55 }}
              whileTap={{ scale: scale * 0.92 }}
              onMouseEnter={() => setHoveredIndex(index)}
              onFocus={() => setHoveredIndex(index)}
              onBlur={() => setHoveredIndex(null)}
              onClick={() => onSelect(item.key)}
            >
              <span className="pointer-events-none absolute inset-0 rounded-2xl bg-[radial-gradient(circle_at_50%_0%,rgba(255,255,255,0.26),transparent_42%)] opacity-70" />
              <span className="relative z-10">{item.icon}</span>
              {item.badge !== undefined ? (
                <span className="absolute -right-1 -top-1 rounded-full border border-black/30 bg-amber-300 px-1.5 py-0.5 text-[10px] font-black leading-none text-slate-950 shadow-[0_4px_12px_rgba(0,0,0,0.26)]">
                  {item.badge}
                </span>
              ) : null}
              <span className="pointer-events-none absolute -top-9 whitespace-nowrap rounded-full border border-white/12 bg-slate-950/84 px-2.5 py-1 text-[11px] font-semibold text-white/88 opacity-0 shadow-lg backdrop-blur-xl transition group-hover:opacity-100 group-focus-visible:opacity-100">
                {item.label}
              </span>
              {active ? (
                <motion.span
                  layoutId="dock-active-dot"
                  className="absolute -bottom-1.5 h-1.5 w-1.5 rounded-full bg-cyan-100 shadow-[0_0_14px_rgba(165,243,252,0.8)]"
                />
              ) : null}
            </motion.button>
          );
        })}
      </div>
    </motion.nav>
  );
}

export const Table: React.FC = () => {
  const [playerName, setPlayerName] = useState('访客');
  const [mode, setMode] = useState<GameMode>('4P');
  const [roundLength, setRoundLength] = useState<RoundLength>('EAST');
  const [ruleProfile, setRuleProfile] = useState<RuleProfile>('RANKED');
  const [enableKoyaku, setEnableKoyaku] = useState(false);
  const [sanmaScoringMode, setSanmaScoringMode] = useState<SanmaScoringMode>('TSUMO_LOSS');
  const [aiLevels, setAiLevels] = useState<number[]>(DEFAULT_AI_LEVELS['4P']);

  const [currentGame, setCurrentGame] = useState<PublicGameView | null>(null);
  const [savedGames, setSavedGames] = useState<SavedGameSummary[]>([]);
  const [stats, setStats] = useState<PlayerStats | null>(null);
  const [replay, setReplay] = useState<ReplayView | null>(null);
  const [replayIndex, setReplayIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busyText, setBusyText] = useState<string | null>(null);
  const [uiPending, setUiPending] = useState(false);
  const [resultModalOpen, setResultModalOpen] = useState(false);
  const [lastResultEventKey, setLastResultEventKey] = useState<string | null>(null);
  const [aiMoveDelay, setAiMoveDelay] = useState(2000);
  const [activeDockPanel, setActiveDockPanel] = useState<DockPanelKey | null>(() => getDockPanelFromHash());
  const playbackTokenRef = useRef(0);

  const activeView = replay ? (replay.snapshots[replayIndex]?.state ?? null) : currentGame;
  const deferredSavedGames = useDeferredValue(savedGames);
  const deferredLogTail = useDeferredValue(activeView?.log_tail ?? []);
  const replaySnapshot = replay?.snapshots[replayIndex] ?? null;
  const replayTotalSteps = replay?.snapshots.length ?? 0;
  const replayHasSteps = replayTotalSteps > 0;
  const replayProgressPercent = replayHasSteps && replayTotalSteps > 1 ? (replayIndex / (replayTotalSteps - 1)) * 100 : 0;
  const replayCurrentEntry = useMemo(() => {
    if (!replaySnapshot) {
      return null;
    }
    const entries = replaySnapshot.state.log_tail ?? [];
    return entries.length ? entries[entries.length - 1] : null;
  }, [replaySnapshot]);
  const replayFrameRoundText = replaySnapshot?.round
    ? humanizeText(replaySnapshot.round)
    : activeView?.round_label
      ? humanizeText(activeView.round_label)
      : '未载入牌谱';
  const replayFrameSummary = replayCurrentEntry
    ? `${getDisplayName(replayCurrentEntry.actor)} · ${getActionTypeText(replayCurrentEntry.type)}`
    : replaySnapshot
      ? `${replayFrameRoundText} · ${getActionTypeText(replaySnapshot.type)}`
      : '尚未进入牌谱回看';
  const replayFrameTileText = replayCurrentEntry?.tile ? formatTileLabelZh(replayCurrentEntry.tile) : '';
  const replayFrameNarrative = replayCurrentEntry
    ? getActionLogNarrative(replayCurrentEntry)
    : replay
      ? '拖动时间轴或使用步进按钮，查看整局变化。'
      : '载入历史对局后，可以沿着时间轴回看整局进程。';
  const replayRoundResult = useMemo(() => {
    return isRecord(activeView?.round_result) ? activeView.round_result : null;
  }, [activeView]);
  const replayRoundHeadline = replayRoundResult?.headline ? humanizeText(String(replayRoundResult.headline)) : null;
  const replayRoundSubtypeText = useMemo(() => {
    return formatResultSubtype(replayRoundResult?.subtype);
  }, [replayRoundResult?.subtype]);
  const replayRoundLoserName =
    typeof replayRoundResult?.loser === 'string' ? getDisplayName(String(replayRoundResult.loser)) : null;
  const replayRoundTenpai = useMemo(() => {
    const tenpai = replayRoundResult?.tenpai;
    if (!Array.isArray(tenpai)) {
      return [];
    }
    return tenpai.map((item) => humanizeText(String(item)));
  }, [replayRoundResult]);

  const humanPlayer = useMemo(() => {
    return activeView?.players.find((player) => player.is_human) ?? null;
  }, [activeView]);

  const bottomPlayer = useMemo(() => getPlayerByPosition(activeView, 'bottom'), [activeView]);
  const topPlayer = useMemo(() => getPlayerByPosition(activeView, 'top'), [activeView]);
  const leftPlayer = useMemo(() => getPlayerByPosition(activeView, 'left'), [activeView]);
  const rightPlayer = useMemo(() => getPlayerByPosition(activeView, 'right'), [activeView]);
  const bottomPlayerInsight = useMemo(() => parsePlayerInsight(bottomPlayer?.last_reason), [bottomPlayer?.last_reason]);
  const hasBottomPlayer = Boolean(activeView && bottomPlayer);
  const isBottomTurn = Boolean(activeView && bottomPlayer && activeView.turn_seat === bottomPlayer.seat);
  const bottomPlayerStatusSummary = bottomPlayer
    ? bottomPlayerInsight.summary ?? humanizeText(bottomPlayer.last_reason || '轮到你时，直接点击手牌即可打出。')
    : '载入或开始新对局后，这里会显示你的当前手顺与操作提示。';
  const bottomPlayerStatusDetail = !bottomPlayer
    ? '开始或载入一局后，这里会同步显示当前轮次、手牌数量和牌河变化。'
    : isBottomTurn
      ? '轮到你行动，直接点选手牌即可打出。'
      : '当前正在等待其他玩家行动，牌桌会自动推进。';
  const bottomPlayerTurnLabel = !bottomPlayer ? '等待开局' : isBottomTurn ? '轮到你出牌' : '等待他家';

  const aiCount = mode === '4P' ? 3 : 2;
  const selectedAiLevels = aiLevels.slice(0, aiCount);

  const discardActionMap = useMemo(() => {
    const map = new Map<number, string>();
    const handTileById = new Map<number, BackendTile>((activeView?.human_hand ?? []).map((tile) => [tile.id, tile]));
    const actionByTileLabel = new Map<string, string>();

    for (const action of activeView?.legal_actions ?? []) {
      if (action.type === 'discard' && typeof action.tile_id === 'number') {
        map.set(action.tile_id, action.id);
        const actionTile = handTileById.get(action.tile_id);
        if (actionTile && !actionByTileLabel.has(actionTile.label)) {
          actionByTileLabel.set(actionTile.label, action.id);
        }
      }
    }

    for (const tile of activeView?.human_hand ?? []) {
      const actionId = actionByTileLabel.get(tile.label);
      if (actionId && !map.has(tile.id)) {
        map.set(tile.id, actionId);
      }
    }

    return map;
  }, [activeView]);

  const specialActions = useMemo(() => {
    const unique = new Map<string, NonNullable<PublicGameView['legal_actions']>[number]>();
    for (const action of activeView?.legal_actions ?? []) {
      if (action.type === 'discard') {
        continue;
      }
      const key =
        action.type === 'riichi'
          ? `${action.type}:${formatTileLabelZh(action.label)}`
          : `${action.type}:${action.tile_id ?? action.label}:${action.id}`;
      if (!unique.has(key)) {
        unique.set(key, action);
      }
    }
    return Array.from(unique.values());
  }, [activeView]);
  const hintBadgeCount =
    (activeView?.hint?.top_discards?.length ?? 0) +
      (activeView?.hint?.special_actions?.length ?? 0) ||
    specialActions.filter((action) => isHintableSpecialActionType(action.type)).length ||
    undefined;

  const doraTiles = useMemo(() => {
    return (activeView?.dora_indicators ?? [])
      .map((tile) => parseTileLabel(tile))
      .filter((tile): tile is Tile => tile !== null);
  }, [activeView]);

  const humanHandTiles = useMemo(() => {
    return activeView ? toVisibleTiles(activeView.human_hand) : [];
  }, [activeView]);
  const revealOpponentHands = activeView?.phase === 'ROUND_END';
  const bottomRiverDiscards = useMemo(() => {
    return bottomPlayer ? toRiverTiles(bottomPlayer.discards) : [];
  }, [bottomPlayer]);
  const leftRiverDiscards = useMemo(() => {
    return leftPlayer ? toRiverTiles(leftPlayer.discards) : [];
  }, [leftPlayer]);
  const topRiverDiscards = useMemo(() => {
    return topPlayer ? toRiverTiles(topPlayer.discards) : [];
  }, [topPlayer]);
  const rightRiverDiscards = useMemo(() => {
    return rightPlayer ? toRiverTiles(rightPlayer.discards) : [];
  }, [rightPlayer]);
  const leftHandTiles = useMemo(() => {
    return leftPlayer ? (revealOpponentHands ? toVisibleTiles(leftPlayer.hand) : toFaceDownTiles(leftPlayer.hand_size)) : [];
  }, [leftPlayer, revealOpponentHands]);
  const topHandTiles = useMemo(() => {
    return topPlayer ? (revealOpponentHands ? toVisibleTiles(topPlayer.hand) : toFaceDownTiles(topPlayer.hand_size)) : [];
  }, [topPlayer, revealOpponentHands]);
  const rightHandTiles = useMemo(() => {
    return rightPlayer ? (revealOpponentHands ? toVisibleTiles(rightPlayer.hand) : toFaceDownTiles(rightPlayer.hand_size)) : [];
  }, [rightPlayer, revealOpponentHands]);

  const roundMeta = useMemo(() => {
    return parseRoundLabel(activeView?.round_label);
  }, [activeView?.round_label]);
  const activeRoundWind = roundMeta?.wind ?? null;
  const dealerCompassPosition = useMemo<CompassSeatPosition | null>(() => {
    if (!activeView) {
      return null;
    }
    if (topPlayer?.seat === activeView.dealer_seat) {
      return 'north';
    }
    if (rightPlayer?.seat === activeView.dealer_seat) {
      return 'east';
    }
    if (bottomPlayer?.seat === activeView.dealer_seat) {
      return 'south';
    }
    if (leftPlayer?.seat === activeView.dealer_seat) {
      return 'west';
    }
    return null;
  }, [activeView, topPlayer, rightPlayer, bottomPlayer, leftPlayer]);
  const centerCoreSeatIndicators = useMemo<CenterCoreSeatIndicator[]>(() => {
    const seats = [
      { position: 'north' as const, player: topPlayer },
      { position: 'east' as const, player: rightPlayer },
      { position: 'south' as const, player: bottomPlayer },
      { position: 'west' as const, player: leftPlayer },
    ];

    return seats.flatMap(({ position, player }) =>
      player
        ? [
            {
              position,
              wind: player.seat_wind,
              isDealer: player.dealer,
              isActive: activeView?.turn_seat === player.seat,
              isRiichi: player.riichi,
            },
          ]
        : []
    );
  }, [activeView?.turn_seat, topPlayer, rightPlayer, bottomPlayer, leftPlayer]);

  const currentRoundResult = useMemo(() => {
    return isRecord(currentGame?.round_result) ? currentGame.round_result : null;
  }, [currentGame]);

  const currentResultSummary = useMemo(() => {
    return isRecord(currentGame?.result_summary) ? currentGame.result_summary : null;
  }, [currentGame]);

  const currentRoundSubtypeText = useMemo(() => {
    return formatResultSubtype(currentRoundResult?.subtype);
  }, [currentRoundResult?.subtype]);

  const leftoverRiichiBonus =
    typeof currentResultSummary?.leftover_riichi_bonus === 'number' ? currentResultSummary.leftover_riichi_bonus : 0;

  const resultPlacements = useMemo(() => {
    const placements = currentResultSummary?.placements;
    if (!Array.isArray(placements)) {
      return [];
    }
    return placements.filter(isRecord);
  }, [currentResultSummary]);

  const resultWinners = useMemo(() => {
    const winners = currentRoundResult?.winners;
    if (!Array.isArray(winners)) {
      return [];
    }
    return winners.filter(isRecord);
  }, [currentRoundResult]);

  const resultTenpai = useMemo(() => {
    const tenpai = currentRoundResult?.tenpai;
    if (!Array.isArray(tenpai)) {
      return [];
    }
    return tenpai.map((item) => humanizeText(String(item)));
  }, [currentRoundResult]);

  const resultScoreChanges = useMemo(() => {
    const scoreChanges = currentRoundResult?.score_changes;
    if (!Array.isArray(scoreChanges) || !currentGame) {
      return [];
    }
    return currentGame.players.map((player, index) => ({
      seat: player.seat,
      name: getDisplayName(player.name),
      delta: typeof scoreChanges[index] === 'number' ? scoreChanges[index] : 0,
      points: player.points,
    }));
  }, [currentRoundResult, currentGame]);

  const nextRoundAction = useMemo(() => {
    if (!currentGame || replay) {
      return null;
    }
    return currentGame.legal_actions.find((action) => action.type === 'next_round') ?? null;
  }, [currentGame, replay]);

  const resultEventKey = useMemo(() => {
    if (replay || !currentGame) {
      return null;
    }
    if (currentResultSummary?.finished_at) {
      return `game:${currentGame.game_id}:${String(currentResultSummary.finished_at)}`;
    }
    if (currentRoundResult?.headline) {
      return `round:${currentGame.game_id}:${currentGame.updated_at ?? ''}:${String(currentRoundResult.headline)}`;
    }
    return null;
  }, [currentGame, currentRoundResult, currentResultSummary, replay]);

  const refreshSavedGames = async () => {
    const response = await api<{ items: SavedGameSummary[] }>('/api/games');
    startTransition(() => {
      setSavedGames(response.items ?? []);
    });
  };

  const refreshStats = async (targetPlayerName?: string) => {
    const nextPlayerName = (targetPlayerName ?? humanPlayer?.name ?? playerName).trim() || '访客';
    const response = await api<PlayerStats>(`/api/stats/${encodeURIComponent(nextPlayerName)}`);
    startTransition(() => {
      setStats(response);
    });
  };

  useEffect(() => {
    void (async () => {
      try {
        setBusyText('正在同步存档...');
        await Promise.all([refreshSavedGames(), refreshStats(playerName)]);
      } catch (err) {
        setError(err instanceof Error ? err.message : '初始化失败');
      } finally {
        setBusyText(null);
      }
    })();
  }, []);

  useEffect(() => {
    if (!resultEventKey || resultEventKey === lastResultEventKey) {
      return;
    }
    setLastResultEventKey(resultEventKey);
    setResultModalOpen(true);
  }, [lastResultEventKey, resultEventKey]);

  useEffect(() => {
    return () => {
      playbackTokenRef.current += 1;
    };
  }, []);

  useEffect(() => {
    const syncDockRoute = () => {
      setActiveDockPanel(getDockPanelFromHash());
    };
    window.addEventListener('hashchange', syncDockRoute);
    window.addEventListener('popstate', syncDockRoute);
    return () => {
      window.removeEventListener('hashchange', syncDockRoute);
      window.removeEventListener('popstate', syncDockRoute);
    };
  }, []);

  const handleDockSelect = useCallback(
    (key: DockPanelKey) => {
      const nextKey = activeDockPanel === key ? null : key;
      startTransition(() => {
        setActiveDockPanel(nextKey);
      });
      updateDockRoute(nextKey);
    },
    [activeDockPanel]
  );

  const handleCloseDockPanel = useCallback(() => {
    startTransition(() => {
      setActiveDockPanel(null);
    });
    updateDockRoute(null);
  }, []);

  const setLoadingState = (text: string | null, pending: boolean) => {
    setBusyText(text);
    setUiPending(pending);
  };

  const handleModeChange = (nextMode: GameMode) => {
    setMode(nextMode);
    if (nextMode === '4P') {
      setSanmaScoringMode('TSUMO_LOSS');
    } else if (ruleProfile === 'RANKED') {
      setSanmaScoringMode('TSUMO_LOSS');
    }
    setAiLevels((current) => {
      if (nextMode === '3P') {
        return current.slice(0, 2);
      }
      return [current[0] ?? 1, current[1] ?? 2, current[2] ?? 3];
    });
  };

  const handleRuleProfileChange = (nextProfile: RuleProfile) => {
    setRuleProfile(nextProfile);
    if (nextProfile === 'RANKED') {
      setEnableKoyaku(false);
      setSanmaScoringMode('TSUMO_LOSS');
      return;
    }
    if (nextProfile === 'KOYAKU') {
      setEnableKoyaku(true);
    }
  };

  const handleAiLevelChange = (index: number, value: number) => {
    setAiLevels((current) => {
      const next = [...current];
      next[index] = value;
      return next;
    });
  };

  const withTask = async <T,>(text: string, task: () => Promise<T>) => {
    try {
      setError(null);
      setLoadingState(text, true);
      return await task();
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求失败');
      throw err;
    } finally {
      setLoadingState(null, false);
    }
  };

  const syncAfterGameUpdate = async (
    game: PublicGameView,
    nextPlayer?: string,
    options: { playbackFromStep?: number | null } = {}
  ) => {
    const playbackToken = playbackTokenRef.current + 1;
    playbackTokenRef.current = playbackToken;
    const playbackFromStep = typeof options.playbackFromStep === 'number' ? options.playbackFromStep : null;
    const applyGameState = (nextGame: PublicGameView) => {
      startTransition(() => {
        setCurrentGame(nextGame);
      });
    };

    if (playbackFromStep !== null && game.replay_steps > playbackFromStep) {
      try {
        const replayResponse = await api<ReplayView>(`/api/games/${game.game_id}/replay`);
        const nextSnapshots = replayResponse.snapshots.slice(playbackFromStep);

        if (nextSnapshots.length === 0) {
          applyGameState(game);
        }

        for (const snapshot of nextSnapshots) {
          if (playbackTokenRef.current !== playbackToken) {
            return;
          }

          const lastEntry = getSnapshotLogEntry(snapshot);
          if (shouldDelayAiSnapshot(snapshot) && aiMoveDelay > 0) {
            setBusyText(`${getDisplayName(lastEntry?.actor ?? 'AI')} 思考中...`);
            await wait(aiMoveDelay);
            if (playbackTokenRef.current !== playbackToken) {
              return;
            }
          }

          applyGameState(snapshot.state);
        }

        setBusyText('正在同步牌局...');
        if (playbackTokenRef.current !== playbackToken) {
          return;
        }
        applyGameState(game);
      } catch {
        applyGameState(game);
      }
    } else {
      applyGameState(game);
    }

    await Promise.all([refreshSavedGames(), refreshStats(nextPlayer ?? game.players.find((player) => player.is_human)?.name)]);
  };

  const handleCreateGame = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await withTask('正在创建新对局...', async () => {
      const response = await api<PublicGameView>('/api/games', {
        method: 'POST',
        body: JSON.stringify({
          player_name: playerName.trim() || '访客',
          mode,
          round_length: roundLength,
          rule_profile: ruleProfile,
          ai_levels: selectedAiLevels,
          enable_koyaku: enableKoyaku,
          sanma_scoring_mode: sanmaScoringMode,
        }),
      });
      startTransition(() => {
        setReplay(null);
        setReplayIndex(0);
      });
      await syncAfterGameUpdate(response, playerName, { playbackFromStep: 0 });
      return response;
    });
  };

  const handleLoadGame = async (gameId: string) => {
    await withTask('正在载入对局...', async () => {
      playbackTokenRef.current += 1;
      const response = await api<PublicGameView>(`/api/games/${gameId}`);
      startTransition(() => {
        setReplay(null);
        setReplayIndex(0);
        setPlayerName(response.players.find((player) => player.is_human)?.name ?? '访客');
      });
      await syncAfterGameUpdate(response, response.players.find((player) => player.is_human)?.name);
      return response;
    });
  };

  const handleDeleteGame = async (gameId: string, gamePlayerName: string) => {
    if (!window.confirm('确认删除这条历史对局吗？删除后将无法恢复。')) {
      return;
    }

    await withTask('正在删除对局...', async () => {
      playbackTokenRef.current += 1;
      await api<{ ok: boolean }>(`/api/games/${gameId}`, {
        method: 'DELETE',
      });

      startTransition(() => {
        if (currentGame?.game_id === gameId) {
          setCurrentGame(null);
          setReplay(null);
          setReplayIndex(0);
          setResultModalOpen(false);
          setLastResultEventKey(null);
        }
      });

      await Promise.all([refreshSavedGames(), refreshStats(gamePlayerName)]);
      return true;
    });
  };

  const handleAction = async (actionId: string) => {
    const playbackFromStep = currentGame?.replay_steps ?? 0;
    if (!currentGame || replay) return;
    await withTask('正在同步牌局...', async () => {
      const response = await api<PublicGameView>(`/api/games/${currentGame.game_id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ action_id: actionId }),
      });
      await syncAfterGameUpdate(response, undefined, { playbackFromStep });
      return response;
    });
  };

  const handleLoadReplay = async () => {
    if (!currentGame) return;
    await withTask('正在读取回放...', async () => {
      playbackTokenRef.current += 1;
      const response = await api<ReplayView>(`/api/games/${currentGame.game_id}/replay`);
      startTransition(() => {
        setReplay(response);
        setReplayIndex(Math.max(0, response.snapshots.length - 1));
      });
      return response;
    });
  };

  const handleDiscardByIndex = useCallback(
    async (index: number) => {
      if (!activeView || replay || uiPending) return;
      if (activeView.phase !== 'DISCARD' || activeView.turn_seat !== activeView.human_seat) return;
      const targetTile = activeView.human_hand[index];
      if (!targetTile) return;
      const actionId = discardActionMap.get(targetTile.id);
      if (!actionId) return;
      await handleAction(actionId);
    },
    [activeView, discardActionMap, replay, uiPending]
  );

  const dockItems: DockItemConfig[] = [
    {
      key: 'setup',
      label: '开局',
      ariaLabel: '打开开局设置面板',
      icon: <Settings2 className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />,
    },
    {
      key: 'stats',
      label: '统计',
      ariaLabel: '打开玩家统计面板',
      icon: <BarChart3 className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />,
      badge: stats?.games_played || undefined,
    },
    {
      key: 'history',
      label: '历史',
      ariaLabel: '打开历史对局面板',
      icon: <History className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />,
      badge: deferredSavedGames.length || undefined,
    },
    {
      key: 'status',
      label: '状态',
      ariaLabel: '打开你的状态面板',
      icon: <UserRound className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />,
    },
    {
      key: 'intel',
      label: '情报',
      ariaLabel: '打开牌桌情报面板',
      icon: <Radar className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />,
    },
    {
      key: 'log',
      label: '记录',
      ariaLabel: '打开对局记录面板',
      icon: <ScrollText className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />,
      badge: deferredLogTail.length || undefined,
    },
    {
      key: 'replay',
      label: '回放',
      ariaLabel: '打开牌谱回看面板',
      icon: <Clapperboard className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />,
      badge: replay ? replayTotalSteps : undefined,
    },
    {
      key: 'hint',
      label: '提示',
      ariaLabel: '打开行动提示面板',
      icon: <Lightbulb className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />,
      badge: hintBadgeCount,
    },
  ];

  const dockPanelContent = activeDockPanel
    ? (() => {
        switch (activeDockPanel) {
          case 'setup':
            return (
              <form className="grid gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]" onSubmit={handleCreateGame}>
                <div className="space-y-3">
                  <label className="block text-sm">
                    <div className="mb-1 text-white/75">玩家名</div>
                    <input
                      className="mahjong-console-input"
                      maxLength={32}
                      value={playerName}
                      onChange={(event) => setPlayerName(event.target.value)}
                      placeholder="访客"
                    />
                  </label>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block text-sm">
                      <div className="mb-1 text-white/75">模式</div>
                      <select className="mahjong-console-input" value={mode} onChange={(event) => handleModeChange(event.target.value as GameMode)}>
                        <option value="4P">四麻</option>
                        <option value="3P">三麻</option>
                      </select>
                    </label>
                    <label className="block text-sm">
                      <div className="mb-1 text-white/75">场次</div>
                      <select className="mahjong-console-input" value={roundLength} onChange={(event) => setRoundLength(event.target.value as RoundLength)}>
                        <option value="EAST">东风场</option>
                        <option value="HANCHAN">半庄战</option>
                      </select>
                    </label>
                  </div>

                  <label className="block text-sm">
                    <div className="mb-1 text-white/75">规则档位</div>
                    <select className="mahjong-console-input" value={ruleProfile} onChange={(event) => handleRuleProfileChange(event.target.value as RuleProfile)}>
                      <option value="RANKED">{RULE_PROFILE_TEXT.RANKED}</option>
                      <option value="FRIEND">{RULE_PROFILE_TEXT.FRIEND}</option>
                      <option value="KOYAKU">{RULE_PROFILE_TEXT.KOYAKU}</option>
                    </select>
                  </label>

                  {mode === '3P' ? (
                    <label className="block text-sm">
                      <div className="mb-1 text-white/75">三麻结算方式</div>
                      <select
                        className="mahjong-console-input"
                        value={sanmaScoringMode}
                        disabled={ruleProfile === 'RANKED'}
                        onChange={(event) => setSanmaScoringMode(event.target.value as SanmaScoringMode)}
                      >
                        <option value="TSUMO_LOSS">{SANMA_SCORING_TEXT.TSUMO_LOSS}</option>
                        <option value="NORTH_BISECTION">{SANMA_SCORING_TEXT.NORTH_BISECTION}</option>
                      </select>
                    </label>
                  ) : null}
                </div>

                <div className="space-y-3">
                  <div className="mahjong-console-section p-3 text-sm text-white">
                    <div className="mb-2 text-white/75">规则预设</div>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        disabled={ruleProfile !== 'FRIEND'}
                        className={cn(
                          'rounded-2xl border px-3 py-2 text-sm font-semibold transition',
                          !enableKoyaku
                            ? 'border-cyan-300/80 bg-cyan-300/20 text-cyan-100'
                            : 'border-white/10 bg-black/20 text-white/75 hover:border-white/20 hover:text-white',
                          ruleProfile !== 'FRIEND' ? 'cursor-not-allowed opacity-60 hover:border-white/10 hover:text-white/75' : ''
                        )}
                        onClick={() => setEnableKoyaku(false)}
                      >
                        雀魂在线规则
                      </button>
                      <button
                        type="button"
                        disabled={ruleProfile !== 'FRIEND'}
                        className={cn(
                          'rounded-2xl border px-3 py-2 text-sm font-semibold transition',
                          enableKoyaku
                            ? 'border-amber-300/80 bg-amber-300/20 text-amber-100'
                            : 'border-white/10 bg-black/20 text-white/75 hover:border-white/20 hover:text-white',
                          ruleProfile !== 'FRIEND' ? 'cursor-not-allowed opacity-60 hover:border-white/10 hover:text-white/75' : ''
                        )}
                        onClick={() => setEnableKoyaku(true)}
                      >
                        开启古役
                      </button>
                    </div>
                    <div className="mt-2 text-xs leading-5 text-white/55">默认按雀魂在线常规规则结算；友人场可手动开启古役。</div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    {Array.from({ length: aiCount }, (_, index) => (
                      <label key={index} className="block text-sm">
                        <div className="mb-1 text-white/75">电脑 {index + 1} 强度</div>
                        <select
                          className="mahjong-console-input"
                          value={selectedAiLevels[index] ?? DEFAULT_AI_LEVELS[mode][index]}
                          onChange={(event) => handleAiLevelChange(index, Number(event.target.value))}
                        >
                          <option value="1">{AI_LEVEL_OPTION_TEXT[1]}</option>
                          <option value="2">{AI_LEVEL_OPTION_TEXT[2]}</option>
                          <option value="3">{AI_LEVEL_OPTION_TEXT[3]}</option>
                        </select>
                      </label>
                    ))}
                  </div>

                  <label className="block text-sm">
                    <div className="mb-1 text-white/75">电脑出牌节奏</div>
                    <select className="mahjong-console-input" value={aiMoveDelay} onChange={(event) => setAiMoveDelay(Number(event.target.value))}>
                      {AI_MOVE_DELAY_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <button type="submit" className="mahjong-console-primary w-full px-5 py-3 text-sm font-black tracking-[0.2em] transition-all active:translate-y-1 active:shadow-none">
                    开始新对局
                  </button>
                </div>
              </form>
            );

          case 'stats':
            return (
              <div className="space-y-4">
                <div className="flex items-center justify-end">
                  <Button variant="outline" className="mahjong-console-ghost" onClick={() => void refreshStats()}>
                    刷新
                  </Button>
                </div>
                {stats && stats.games_played ? (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <div className="mahjong-console-stat p-3">
                      <div className="text-xs text-white/60">对局数</div>
                      <div className="mt-1 text-2xl font-black">{stats.games_played}</div>
                    </div>
                    <div className="mahjong-console-stat p-3">
                      <div className="text-xs text-white/60">一位次数</div>
                      <div className="mt-1 text-2xl font-black">{stats.wins}</div>
                    </div>
                    <div className="mahjong-console-stat p-3">
                      <div className="text-xs text-white/60">平均顺位</div>
                      <div className="mt-1 text-2xl font-black">{stats.avg_placement ?? '-'}</div>
                    </div>
                    <div className="mahjong-console-stat p-3">
                      <div className="text-xs text-white/60">最高分</div>
                      <div className="mt-1 text-2xl font-black">{stats.best_score ?? '-'}</div>
                    </div>
                  </div>
                ) : (
                  <div className="mahjong-console-empty px-4 py-6 text-sm text-white/60">暂无数据</div>
                )}
              </div>
            );

          case 'history':
            return (
              <div className="space-y-4">
                <div className="flex items-center justify-end">
                  <Button variant="outline" className="mahjong-console-ghost" onClick={() => void refreshSavedGames()}>
                    刷新
                  </Button>
                </div>
                <div className="grid max-h-[520px] gap-3 overflow-auto pr-1 md:grid-cols-2">
                  {deferredSavedGames.length ? (
                    deferredSavedGames.map((item) => (
                      <div key={item.game_id} className="mahjong-console-stat p-3">
                        <div className="font-semibold">{getDisplayName(item.player_name)}</div>
                        <div className="mt-1 text-xs text-white/65">
                          {MODE_TEXT[item.mode]} · {ROUND_LENGTH_TEXT[item.round_length]}
                          {item.rule_profile ? ` · ${RULE_PROFILE_TEXT[item.rule_profile]}` : ''}
                          {item.mode === '3P' ? ` · ${SANMA_SCORING_TEXT[item.sanma_scoring_mode ?? 'TSUMO_LOSS']}` : ''}
                          {' · '}
                          {formatRoundLabel(item.round_label)}
                        </div>
                        <div className="mt-1 text-xs text-white/55">{item.points.map((point) => formatPoints(point)).join(' / ')}</div>
                        <div className="mt-3 flex items-center justify-between gap-3">
                          <span className="text-xs text-white/55">{getStatusText(item.status)}</span>
                          <div className="flex items-center gap-2">
                            <Button size="sm" variant="outline" className="mahjong-console-ghost" onClick={() => void handleLoadGame(item.game_id)}>
                              载入
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="border-rose-300/20 bg-rose-500/10 text-rose-100 hover:bg-rose-500/20"
                              onClick={() => void handleDeleteGame(item.game_id, item.player_name)}
                            >
                              删除
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="mahjong-console-empty px-4 py-6 text-sm text-white/60 md:col-span-2">暂无存档。</div>
                  )}
                </div>
              </div>
            );

          case 'status':
            return (
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
                <div className="mahjong-status-shell p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">当前操作</div>
                      <div className="mt-3 text-base font-bold leading-7 text-white/92">{bottomPlayerStatusSummary}</div>
                      <div className="mt-2 text-xs leading-6 text-white/62">{bottomPlayerStatusDetail}</div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">当前席位</div>
                      <div className="mt-2 text-sm font-black tracking-[0.12em] text-cyan-50">
                        {bottomPlayer ? `${WIND_TEXT[bottomPlayer.seat_wind] ?? bottomPlayer.seat_wind}家` : '-'}
                      </div>
                      <div className="mt-2">
                        <span className={cn('mahjong-status-turn-pill', hasBottomPlayer && isBottomTurn ? 'mahjong-status-turn-pill--active' : '')}>
                          {bottomPlayerTurnLabel}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-2 sm:grid-cols-3">
                    <div className="mahjong-status-summary-chip">
                      <span className="text-white/45">当前点数</span>
                      <strong>{formatPoints(bottomPlayer?.points)}</strong>
                    </div>
                    <div className="mahjong-status-summary-chip">
                      <span className="text-white/45">手牌张数</span>
                      <strong>{humanHandTiles.length}</strong>
                    </div>
                    <div className="mahjong-status-summary-chip">
                      <span className="text-white/45">牌河张数</span>
                      <strong>{bottomPlayer?.discards.length ?? 0}</strong>
                    </div>
                  </div>
                </div>

                <div className="grid gap-4">
                  <div className="mahjong-status-section p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div className="text-sm font-semibold text-white/84">你的副露</div>
                      <span className="text-[11px] font-semibold tracking-[0.14em] text-white/45">{bottomPlayer?.melds.length ?? 0} 组</span>
                    </div>
                    <MeldStrip melds={bottomPlayer?.melds ?? []} />
                  </div>
                  <div className="mahjong-status-section p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div className="text-sm font-semibold text-white/84">你的牌河</div>
                      <span className="text-[11px] font-semibold tracking-[0.14em] text-white/45">{bottomPlayer?.discards.length ?? 0} 张</span>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-black/15 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                      <River discards={bottomPlayer ? toRiverTiles(bottomPlayer.discards) : []} orientation="bottom" />
                    </div>
                  </div>
                </div>
              </div>
            );

          case 'intel':
            return (
              <div className="grid gap-3 lg:grid-cols-3">
                {[rightPlayer, topPlayer, leftPlayer]
                  .filter((player): player is PlayerView => player !== null)
                  .map((player) => {
                    const insight = parsePlayerInsight(player.last_reason);
                    return (
                      <div key={player.seat} className="rounded-2xl border border-white/10 bg-black/20 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="font-semibold">{getDisplayName(player.name)}</div>
                            <div className="mt-1 text-xs text-white/60">
                              {WIND_TEXT[player.seat_wind] ?? player.seat_wind}家 · {formatPoints(player.points)} 点
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Badge variant="outline" className="border-white/15 text-white/80">
                              {formatAiLevelLabel(player.ai_level)}
                            </Badge>
                            {player.dealer ? <Badge variant="outline" className="border-amber-200/30 text-amber-100">庄家</Badge> : null}
                            {player.riichi ? <Badge variant="outline" className="border-pink-300/30 text-pink-100">立直</Badge> : null}
                          </div>
                        </div>
                        <div className="mt-3 rounded-2xl border border-white/10 bg-black/15 px-3 py-3">
                          <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">当前判断</div>
                          <div className="mt-1 text-sm text-white/82">{insight.summary ?? '等待行动中。'}</div>
                          {insight.detail ? <div className="mt-2 text-xs leading-5 text-white/58">{insight.detail}</div> : null}
                        </div>
                        <div className="mt-3 grid gap-3">
                          <div>
                            <div className="mb-2 text-xs font-semibold text-white/70">副露</div>
                            <MeldStrip melds={player.melds} />
                          </div>
                          <div>
                            <div className="mb-2 text-xs font-semibold text-white/70">牌河</div>
                            <div className="rounded-2xl border border-white/10 bg-black/15 p-3">
                              <River discards={toRiverTiles(player.discards)} orientation="bottom" />
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
              </div>
            );

          case 'log':
            return (
              <div className="space-y-4">
                <div className="flex justify-end">
                  <Button variant="outline" className="mahjong-console-ghost" disabled={!currentGame} onClick={() => void handleLoadReplay()}>
                    载入牌谱
                  </Button>
                </div>
                <div className="grid max-h-[520px] gap-3 overflow-auto pr-1 lg:grid-cols-2">
                  {deferredLogTail.length ? (
                    deferredLogTail.map((entry) => {
                      const tone = getActionLogTone(entry.type);
                      const tileLabel = entry.tile ? formatTileLabelZh(entry.tile) : '';
                      const narrative = getActionLogNarrative(entry);
                      return (
                        <div key={entry.seq} className={cn('mahjong-log-entry border p-3.5 pl-5', tone.shell)}>
                          <span aria-hidden className={cn('absolute bottom-3 left-2 top-3 w-1 rounded-full', tone.accent)} />
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2 text-[11px] tracking-[0.18em] text-white/42">
                                <span className="font-black text-white/52">#{String(entry.seq).padStart(3, '0')}</span>
                                <span className="text-white/58">{getDisplayName(entry.actor)}</span>
                              </div>
                            </div>
                            <span className={cn('shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-black tracking-[0.16em] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]', tone.badge)}>
                              {getActionTypeText(entry.type)}
                            </span>
                          </div>
                          <div className="mt-3 flex flex-wrap items-center gap-2.5">
                            {tileLabel ? <span className={cn('mahjong-log-tile-chip', tone.tile)}>{tileLabel}</span> : null}
                            <span className={cn('text-sm leading-6', tone.detail)}>{narrative}</span>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="mahjong-console-empty px-4 py-6 text-sm text-white/60 lg:col-span-2">对局中的摸牌、打牌和鸣牌记录会按顺序显示在这里。</div>
                  )}
                </div>
              </div>
            );

          case 'replay':
            return (
              <div className="space-y-4">
                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    className="mahjong-console-ghost"
                    disabled={!replay}
                    onClick={() => {
                      startTransition(() => {
                        setReplay(null);
                        setReplayIndex(0);
                      });
                    }}
                  >
                    回到实时牌桌
                  </Button>
                </div>
                <div className="mahjong-replay-shell p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="mahjong-replay-pill">{replay ? '牌谱回看中' : '实时牌桌'}</span>
                        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-semibold tracking-[0.16em] text-white/58">
                          {replayFrameRoundText}
                        </span>
                      </div>
                      <div className="mt-3 text-sm font-semibold text-white/88">{replayFrameSummary}</div>
                      <div className="mt-2 flex flex-wrap items-center gap-2.5">
                        {replayFrameTileText && replay ? <span className="mahjong-log-tile-chip border-cyan-200/20 bg-[linear-gradient(180deg,rgba(56,189,248,0.18),rgba(10,36,57,0.74))] text-cyan-50">{replayFrameTileText}</span> : null}
                        <span className="text-xs leading-6 text-white/62">{replayFrameNarrative}</span>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">回看进度</div>
                      <div className="mt-1 text-2xl font-black tracking-[0.08em] text-cyan-50">{replay ? `${replayIndex + 1}/${replayTotalSteps}` : '--/--'}</div>
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="mahjong-replay-track">
                      <div className="mahjong-replay-track-fill" style={{ width: `${replayProgressPercent}%` }} />
                      <input
                        type="range"
                        min={0}
                        max={Math.max(0, replayTotalSteps - 1)}
                        value={replayIndex}
                        disabled={!replay}
                        onChange={(event) => setReplayIndex(Number(event.target.value))}
                        className="mahjong-replay-range"
                      />
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Button variant="outline" className="mahjong-console-ghost mahjong-replay-step" disabled={!replay || replayIndex <= 0} onClick={() => setReplayIndex(0)}>
                      回到开局
                    </Button>
                    <Button variant="outline" className="mahjong-console-ghost mahjong-replay-step" disabled={!replay || replayIndex <= 0} onClick={() => setReplayIndex((current) => Math.max(0, current - 1))}>
                      上一步
                    </Button>
                    <Button variant="outline" className="mahjong-console-ghost mahjong-replay-step" disabled={!replay || replayIndex >= replayTotalSteps - 1} onClick={() => setReplayIndex((current) => Math.min(replayTotalSteps - 1, current + 1))}>
                      下一步
                    </Button>
                    <Button variant="outline" className="mahjong-console-ghost mahjong-replay-step" disabled={!replay || replayIndex >= replayTotalSteps - 1} onClick={() => setReplayIndex(Math.max(0, replayTotalSteps - 1))}>
                      回到末手
                    </Button>
                  </div>
                </div>

                {replayRoundHeadline ? (
                  <div className="mahjong-replay-result-card p-4">
                    <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">这一局结果</div>
                    <div className="mt-2 text-base font-bold leading-7 text-white/92">{replayRoundHeadline}</div>
                  </div>
                ) : null}
              </div>
            );

          case 'hint':
            return (
              <div className="mahjong-console-section p-4">
                <HintPanel hint={activeView?.hint} legalActions={activeView?.legal_actions} />
              </div>
            );
        }
      })()
    : null;

  return (
    <div className="mahjong-page">
      {!activeView ? <WaterBackground /> : null}

      <div className="relative z-10 flex min-h-screen flex-col gap-5 p-4 pb-28 lg:p-5 lg:pb-32">
        <aside className="hidden">
          <Card className="mahjong-console-card mahjong-console-card-hero rounded-[30px] p-5 text-white lg:p-6">
            <div className="mb-4">
              <div className="mahjong-brand-kicker">本地牌桌 · 单机对战服务</div>
              <h1 className="mt-2 text-3xl font-black tracking-[0.08em]">单人立直麻将</h1>
              <p className="mt-2 text-sm text-white/70">在浏览器里直接开打，把单机对局、牌谱回看和电脑陪打都收进同一张牌桌。</p>
              <div className="mt-5 flex flex-wrap gap-2">
                <span className="mahjong-seat-meta border-cyan-200/18 bg-cyan-300/12 text-cyan-50">浏览器牌桌</span>
                <span className="mahjong-seat-meta border-emerald-200/18 bg-emerald-300/12 text-emerald-50">雀魂在线规则</span>
                <span className="mahjong-seat-meta border-amber-200/18 bg-amber-300/12 text-amber-50">电脑强度 L1 / L2 / L3</span>
              </div>
            </div>

            <form className="space-y-3" onSubmit={handleCreateGame}>
              <label className="block text-sm">
                <div className="mb-1 text-white/75">玩家名</div>
                <input
                  className="mahjong-console-input"
                  maxLength={32}
                  value={playerName}
                  onChange={(event) => setPlayerName(event.target.value)}
                  placeholder="访客"
                />
              </label>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm">
                  <div className="mb-1 text-white/75">模式</div>
                  <select
                    className="mahjong-console-input"
                    value={mode}
                    onChange={(event) => handleModeChange(event.target.value as GameMode)}
                  >
                    <option value="4P">四麻</option>
                    <option value="3P">三麻</option>
                  </select>
                </label>

                <label className="block text-sm">
                  <div className="mb-1 text-white/75">场次</div>
                  <select
                    className="mahjong-console-input"
                    value={roundLength}
                    onChange={(event) => setRoundLength(event.target.value as RoundLength)}
                  >
                    <option value="EAST">东风场</option>
                    <option value="HANCHAN">半庄战</option>
                  </select>
                </label>
              </div>

              <label className="block text-sm">
                <div className="mb-1 text-white/75">规则档位</div>
                <select
                  className="mahjong-console-input"
                  value={ruleProfile}
                  onChange={(event) => handleRuleProfileChange(event.target.value as RuleProfile)}
                >
                  <option value="RANKED">{RULE_PROFILE_TEXT.RANKED}</option>
                  <option value="FRIEND">{RULE_PROFILE_TEXT.FRIEND}</option>
                  <option value="KOYAKU">{RULE_PROFILE_TEXT.KOYAKU}</option>
                </select>
                <div className="mt-2 text-xs text-white/55">
                  段位默认会锁定雀魂在线默认规则；友人场允许自定义三麻计分；古役房会自动开启古役。
                </div>
              </label>

              <div className="mahjong-console-section p-3 text-sm text-white">
                <div className="mb-2 text-white/75">规则预设</div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    disabled={ruleProfile !== 'FRIEND'}
                    className={cn(
                      'rounded-2xl border px-3 py-2 text-sm font-semibold transition',
                      !enableKoyaku
                        ? 'border-cyan-300/80 bg-cyan-300/20 text-cyan-100'
                        : 'border-white/10 bg-black/20 text-white/75 hover:border-white/20 hover:text-white',
                      ruleProfile !== 'FRIEND' ? 'cursor-not-allowed opacity-60 hover:border-white/10 hover:text-white/75' : ''
                    )}
                    onClick={() => setEnableKoyaku(false)}
                  >
                    雀魂在线规则
                  </button>
                  <button
                    type="button"
                    disabled={ruleProfile !== 'FRIEND'}
                    className={cn(
                      'rounded-2xl border px-3 py-2 text-sm font-semibold transition',
                      enableKoyaku
                        ? 'border-amber-300/80 bg-amber-300/20 text-amber-100'
                        : 'border-white/10 bg-black/20 text-white/75 hover:border-white/20 hover:text-white',
                      ruleProfile !== 'FRIEND' ? 'cursor-not-allowed opacity-60 hover:border-white/10 hover:text-white/75' : ''
                    )}
                    onClick={() => setEnableKoyaku(true)}
                  >
                    开启古役
                  </button>
                </div>
                <div className="mt-2 text-xs text-white/55">
                  默认按雀魂在线常规规则结算。开启后会额外启用当前系统已对齐的古役算番。
                </div>
                <div className="mt-1 text-xs text-white/40">当前已接入：人和、大车轮 / 大数邻 / 大竹林、大七星等古役。</div>
              </div>

              {mode === '3P' ? (
                <label className="block text-sm">
                  <div className="mb-1 text-white/75">三麻结算方式</div>
                  <select
                    className="mahjong-console-input"
                    value={sanmaScoringMode}
                    disabled={ruleProfile === 'RANKED'}
                    onChange={(event) => setSanmaScoringMode(event.target.value as SanmaScoringMode)}
                  >
                    <option value="TSUMO_LOSS">{SANMA_SCORING_TEXT.TSUMO_LOSS}</option>
                    <option value="NORTH_BISECTION">{SANMA_SCORING_TEXT.NORTH_BISECTION}</option>
                  </select>
                  <div className="mt-2 text-xs text-white/55">
                    段位场默认使用自摸损。切到北家点数折半分摊后，会按雀魂友人场规则把缺失的北家支付平均分给其余两家。
                  </div>
                </label>
              ) : null}

              <div className="grid gap-3">
                {Array.from({ length: aiCount }, (_, index) => (
                  <label key={index} className="block text-sm">
                    <div className="mb-1 text-white/75">电脑 {index + 1} 强度</div>
                    <select
                      className="mahjong-console-input"
                      value={selectedAiLevels[index] ?? DEFAULT_AI_LEVELS[mode][index]}
                      onChange={(event) => handleAiLevelChange(index, Number(event.target.value))}
                    >
                      <option value="1">{AI_LEVEL_OPTION_TEXT[1]}</option>
                      <option value="2">{AI_LEVEL_OPTION_TEXT[2]}</option>
                      <option value="3">{AI_LEVEL_OPTION_TEXT[3]}</option>
                    </select>
                  </label>
                ))}
              </div>

              <label className="block text-sm">
                <div className="mb-1 text-white/75">电脑出牌节奏</div>
                <select
                  className="mahjong-console-input"
                  value={aiMoveDelay}
                  onChange={(event) => setAiMoveDelay(Number(event.target.value))}
                >
                  {AI_MOVE_DELAY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <button
                type="submit"
                className="mahjong-console-primary w-full px-5 py-3 text-sm font-black tracking-[0.2em] transition-all active:translate-y-1 active:shadow-none"
              >
                开始新对局
              </button>
            </form>
          </Card>

          <Card className="mahjong-console-card rounded-[30px] p-5 text-white lg:p-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-bold">玩家统计</h2>
              <Button variant="outline" className="mahjong-console-ghost" onClick={() => void refreshStats()}>
                刷新
              </Button>
            </div>

            {stats && stats.games_played ? (
              <div className="grid grid-cols-2 gap-3">
                <div className="mahjong-console-stat p-3">
                  <div className="text-xs text-white/60">对局数</div>
                  <div className="mt-1 text-2xl font-black">{stats.games_played}</div>
                </div>
                <div className="mahjong-console-stat p-3">
                  <div className="text-xs text-white/60">一位次数</div>
                  <div className="mt-1 text-2xl font-black">{stats.wins}</div>
                </div>
                <div className="mahjong-console-stat p-3">
                  <div className="text-xs text-white/60">平均顺位</div>
                  <div className="mt-1 text-2xl font-black">{stats.avg_placement ?? '-'}</div>
                </div>
                <div className="mahjong-console-stat p-3">
                  <div className="text-xs text-white/60">最高分</div>
                  <div className="mt-1 text-2xl font-black">{stats.best_score ?? '-'}</div>
                </div>
              </div>
            ) : (
              <div className="mahjong-console-empty px-4 py-6 text-sm text-white/60">
                暂无数据
              </div>
            )}
          </Card>

          <Card className="mahjong-console-card rounded-[30px] p-5 text-white lg:p-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-bold">历史对局</h2>
              <Button variant="outline" className="mahjong-console-ghost" onClick={() => void refreshSavedGames()}>
                刷新
              </Button>
            </div>

            <div className="max-h-[320px] space-y-3 overflow-auto pr-1">
              {deferredSavedGames.length ? (
                deferredSavedGames.map((item) => (
                  <div key={item.game_id} className="mahjong-console-stat p-3">
                    <div className="font-semibold">{getDisplayName(item.player_name)}</div>
                    <div className="mt-1 text-xs text-white/65">
                      {MODE_TEXT[item.mode]} · {ROUND_LENGTH_TEXT[item.round_length]}
                      {item.rule_profile ? ` · ${RULE_PROFILE_TEXT[item.rule_profile]}` : ''}
                      {item.mode === '3P' ? ` · ${SANMA_SCORING_TEXT[item.sanma_scoring_mode ?? 'TSUMO_LOSS']}` : ''}
                      {' · '}
                      {formatRoundLabel(item.round_label)}
                    </div>
                    <div className="mt-1 text-xs text-white/55">{item.points.map((point) => formatPoints(point)).join(' / ')}</div>
                    <div className="mt-3 flex items-center justify-between gap-3">
                      <span className="text-xs text-white/55">{getStatusText(item.status)}</span>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="mahjong-console-ghost"
                          onClick={() => void handleLoadGame(item.game_id)}
                        >
                          载入
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="border-rose-300/20 bg-rose-500/10 text-rose-100 hover:bg-rose-500/20"
                          onClick={() => void handleDeleteGame(item.game_id, item.player_name)}
                        >
                          删除
                        </Button>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="mahjong-console-empty px-4 py-6 text-sm text-white/60">
                  暂无存档。
                </div>
              )}
            </div>
          </Card>
        </aside>

        <div className="order-1 flex flex-col gap-5">
        <main>
          <Card className="mahjong-console-card h-full rounded-[34px] p-0 text-white">
            <div className="flex h-full flex-col gap-4 p-3 xl:p-4">
              {error ? (
                <div className="rounded-2xl border border-red-300/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                  {error}
                </div>
              ) : null}

              <div className="overflow-x-auto px-1 pb-2">
                <div className="relative mx-auto aspect-[39/20] w-[min(100%,1720px)] min-w-[1320px] rounded-[42px] border-4 border-ui-border bg-[radial-gradient(circle,_rgba(76,233,142,0.95)_0%,_rgba(18,82,45,0.96)_72%,_rgba(10,40,24,0.98)_100%)] shadow-[0_30px_80px_rgba(0,0,0,0.35)]">
                  <div className="pointer-events-none absolute inset-[4px] overflow-hidden rounded-[36px]">
                    <WaterBackground variant="table" className="opacity-90 mix-blend-screen" />
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_46%,rgba(222,255,235,0.28),rgba(123,235,181,0.14)_28%,rgba(14,71,39,0.05)_56%,rgba(0,0,0,0)_78%),radial-gradient(circle_at_top,rgba(255,255,255,0.16),transparent_28%),linear-gradient(180deg,rgba(4,28,16,0.2),transparent_16%,transparent_80%,rgba(2,18,10,0.3)),linear-gradient(90deg,rgba(2,18,10,0.46),transparent_14%,transparent_86%,rgba(2,18,10,0.46))]" />
                    <div className="absolute inset-0 bg-[linear-gradient(115deg,rgba(255,255,255,0.04),transparent_22%,transparent_76%,rgba(255,255,255,0.04))]" />
                  </div>

                  <div className="mahjong-dora-box absolute left-6 top-6 z-30 w-[236px] rounded-[30px] p-4">
                    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_18%,rgba(255,232,154,0.14),transparent_28%),linear-gradient(135deg,rgba(255,255,255,0.08),transparent_28%,transparent_72%,rgba(255,255,255,0.04))]" />
                    <div className="absolute right-4 top-4 rounded-full border border-amber-200/12 bg-amber-300/10 px-2.5 py-1 text-[10px] font-semibold tracking-[0.18em] text-amber-100/70">
                      {doraTiles.length}/5
                    </div>
                    <div className="relative z-10">
                      <div className="mb-2 text-sm font-bold text-white/85">宝牌指示牌</div>
                    </div>
                    <div className="relative z-10 mt-3 flex gap-1.5 rounded-[22px] border border-black/20 bg-[linear-gradient(180deg,rgba(0,0,0,0.18),rgba(255,255,255,0.05))] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06),inset_0_-10px_18px_rgba(0,0,0,0.18)]">
                      {doraTiles.map((tile, index) => (
                        <div key={`dora-slot-${index}`} className="mahjong-dora-slot">
                          <MahjongTile tile={tile} size="sm" className="shadow-[0_8px_14px_rgba(0,0,0,0.18)]" />
                        </div>
                      ))}
                      {Array.from({ length: Math.max(0, 5 - doraTiles.length) }, (_, index) => (
                        <div key={`hidden-dora-slot-${index}`} className="mahjong-dora-slot">
                          <MahjongTile tile={EMPTY_TILE} size="sm" isFaceDown className="shadow-[0_8px_14px_rgba(0,0,0,0.18)]" />
                        </div>
                      ))}
                    </div>
                  </div>

                  <CompassSeatBadge player={topPlayer} active={activeView?.turn_seat === topPlayer?.seat} position="north" />
                  <CompassSeatBadge player={rightPlayer} active={activeView?.turn_seat === rightPlayer?.seat} position="east" />
                  <CompassSeatBadge player={bottomPlayer} active={activeView?.turn_seat === bottomPlayer?.seat} position="south" />
                  <CompassSeatBadge player={leftPlayer} active={activeView?.turn_seat === leftPlayer?.seat} position="west" />

                  <TableRiichiAura player={topPlayer} position="north" />
                  <TableRiichiAura player={rightPlayer} position="east" />
                  <TableRiichiAura player={bottomPlayer} position="south" />
                  <TableRiichiAura player={leftPlayer} position="west" />

                  <CenterTableCore
                    roundMeta={roundMeta}
                    remainingTiles={activeView?.remaining_tiles}
                    seatIndicators={centerCoreSeatIndicators}
                  />
                  <div className="hidden absolute left-1/2 top-1/2 z-10 h-[176px] w-[204px] -translate-x-1/2 -translate-y-1/2">
                    <div
                      className="absolute inset-0 border border-[#95a7bd] bg-[linear-gradient(180deg,rgba(124,139,158,0.98),rgba(69,81,97,0.98)_36%,rgba(22,29,40,0.99)_100%)] shadow-[0_24px_48px_rgba(0,0,0,0.4)]"
                      style={{ clipPath: CENTER_CORE_OCTAGON }}
                    />
                    <div
                      className="absolute inset-[3px] border border-black/45 bg-[linear-gradient(180deg,rgba(86,97,113,0.84),rgba(41,50,62,0.96)_28%,rgba(17,24,34,0.98)_100%)]"
                      style={{ clipPath: CENTER_CORE_OCTAGON }}
                    />
                    <div
                      className="absolute inset-[7px] border border-white/8 bg-[linear-gradient(180deg,rgba(50,60,75,0.98),rgba(24,31,42,0.98)_54%,rgba(10,16,24,0.99)_100%)] shadow-[inset_0_1px_0_rgba(255,255,255,0.1),inset_0_-10px_18px_rgba(0,0,0,0.18)]"
                      style={{ clipPath: CENTER_CORE_OCTAGON }}
                    />
                    <div
                      className="pointer-events-none absolute inset-[13px] border border-white/5 opacity-75"
                      style={{ clipPath: CENTER_CORE_OCTAGON }}
                    />
                    <div
                      className="pointer-events-none absolute inset-[20px] bg-[radial-gradient(circle_at_50%_32%,rgba(158,233,255,0.08),transparent_38%),radial-gradient(circle_at_50%_72%,rgba(255,214,120,0.07),transparent_34%)] opacity-90"
                      style={{ clipPath: CENTER_CORE_OCTAGON }}
                    />
                    {CENTER_CORE_FRAME_STRIPS.map((className) => (
                      <div
                        key={className}
                        className={cn(
                          'pointer-events-none absolute rounded-full bg-[linear-gradient(180deg,rgba(255,255,255,0.12),rgba(255,255,255,0.015))] opacity-70',
                          className
                        )}
                      />
                    ))}
                    {CENTER_CORE_BOLTS.map((className) => (
                      <div
                        key={className}
                        className={cn(
                          'pointer-events-none absolute h-[7px] w-[7px] rounded-full border border-black/55 bg-[radial-gradient(circle_at_32%_32%,rgba(255,255,255,0.42),rgba(74,82,98,0.94)_48%,rgba(10,14,20,0.98)_100%)] shadow-[inset_0_1px_1px_rgba(255,255,255,0.12),0_1px_2px_rgba(0,0,0,0.28)]',
                          className
                        )}
                      />
                    ))}
                    {CENTER_CORE_CORNER_ACCENTS.map((className) => (
                      <div
                        key={className}
                        className={cn('pointer-events-none absolute h-[14px] w-[14px] border-white/16 opacity-85', className)}
                      />
                    ))}
                    {CENTER_CORE_SIDE_GROOVES.map((className) => (
                      <div
                        key={className}
                        className={cn(
                          'pointer-events-none absolute rounded-full bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.01))] opacity-70',
                          className
                        )}
                      />
                    ))}
                    {(['north', 'east', 'south', 'west'] as const).map((position) => {
                      const isDealer = dealerCompassPosition === position;
                      return (
                        <div
                          key={`dealer-lamp-${position}`}
                          className={cn('pointer-events-none absolute z-[2]', CENTER_CORE_DEALER_LAMP_PLACEMENT[position])}
                        >
                          <div
                            className={cn(
                              'rounded-full border border-amber-100/14 bg-[linear-gradient(180deg,rgba(255,241,196,0.06),rgba(62,46,13,0.08))] opacity-55 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
                              CENTER_CORE_DEALER_LAMP_SIZE[position],
                              isDealer &&
                                'border-amber-100/70 bg-[linear-gradient(180deg,rgba(255,243,182,0.98),rgba(255,189,74,0.46))] opacity-100 shadow-[0_0_16px_rgba(255,209,102,0.42),0_0_24px_rgba(255,184,56,0.22),inset_0_1px_0_rgba(255,255,255,0.34)]'
                            )}
                          />
                          {isDealer ? (
                            <div
                              className={cn(
                                'absolute rounded-full border border-amber-100/55 bg-[linear-gradient(180deg,rgba(97,66,15,0.98),rgba(48,32,6,0.98))] px-1.5 py-[1px] text-[8px] font-black tracking-[0.16em] text-amber-100 shadow-[0_0_12px_rgba(255,187,56,0.22)]',
                                CENTER_CORE_DEALER_BADGE_PLACEMENT[position]
                              )}
                            >
                              庄
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                    {CENTER_CORE_DIRECTIONS.map((marker) => {
                      const isActive = activeRoundWind === marker.wind;
                      return (
                        <div
                          key={marker.wind}
                          className={cn('pointer-events-none absolute flex items-center justify-center gap-1.5', marker.wrapClass)}
                        >
                          <div
                            className={cn(
                              'rounded-full border border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.015))] opacity-65 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
                              marker.railClass,
                              isActive &&
                                'border-cyan-100/60 bg-[linear-gradient(180deg,rgba(162,244,255,0.84),rgba(79,205,248,0.22))] opacity-100 shadow-[0_0_18px_rgba(118,224,255,0.4),0_0_26px_rgba(118,224,255,0.18),inset_0_1px_0_rgba(255,255,255,0.28)]'
                            )}
                          />
                          <div
                            className={cn(
                              'rounded-full border px-1.5 py-[2px] text-[9px] font-black tracking-[0.12em] text-white/36 shadow-[0_4px_10px_rgba(0,0,0,0.18)]',
                              isActive
                                ? 'border-cyan-100/60 bg-[linear-gradient(180deg,rgba(47,107,132,0.98),rgba(12,36,49,0.98))] text-cyan-50 shadow-[0_0_14px_rgba(118,224,255,0.22),0_4px_10px_rgba(0,0,0,0.22)]'
                                : 'border-white/8 bg-[linear-gradient(180deg,rgba(31,41,52,0.94),rgba(14,20,28,0.98))]'
                            )}
                          >
                            {marker.wind}
                          </div>
                        </div>
                      );
                    })}
                    <div className="pointer-events-none absolute inset-x-[28px] top-[88px] h-[1px] bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,0.16)_18%,rgba(255,255,255,0.06)_50%,rgba(255,255,255,0.16)_82%,rgba(255,255,255,0))]" />
                    <div className="pointer-events-none absolute inset-x-[36px] top-[94px] h-[1px] bg-[linear-gradient(90deg,rgba(0,0,0,0),rgba(0,0,0,0.42)_18%,rgba(0,0,0,0.08)_50%,rgba(0,0,0,0.42)_82%,rgba(0,0,0,0))]" />
                    <div className="pointer-events-none absolute left-[26px] top-[14px] h-[3px] w-[34px] rounded-full bg-cyan-100/35 shadow-[0_0_10px_rgba(162,244,255,0.25)]" />
                    <div className="pointer-events-none absolute right-[26px] top-[14px] h-[3px] w-[34px] rounded-full bg-amber-100/30 shadow-[0_0_10px_rgba(255,231,163,0.2)]" />
                    <div className="pointer-events-none absolute left-[24px] bottom-[16px] h-[2px] w-[26px] rounded-full bg-white/12" />
                    <div className="pointer-events-none absolute right-[24px] bottom-[16px] h-[2px] w-[26px] rounded-full bg-white/12" />

                    <div
                      className="absolute inset-x-[28px] top-[26px] h-[56px] overflow-hidden border border-cyan-100/14 bg-[linear-gradient(180deg,rgba(15,28,34,0.97),rgba(5,11,15,0.99))] px-3 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.07),inset_0_-6px_12px_rgba(0,0,0,0.22),0_8px_16px_rgba(0,0,0,0.18)]"
                      style={{ clipPath: CENTER_CORE_SCREEN }}
                    >
                      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(164,238,255,0.06),rgba(164,238,255,0)_42%,rgba(0,0,0,0.18)_100%)]" />
                      <div className="pointer-events-none absolute inset-0 opacity-[0.15] bg-[linear-gradient(180deg,rgba(255,255,255,0.16)_0,rgba(255,255,255,0.16)_1px,transparent_1px,transparent_4px)]" />
                      <div className="pointer-events-none absolute inset-[2px] border border-white/4" style={{ clipPath: CENTER_CORE_SCREEN }} />
                      <div className="relative grid grid-cols-2 gap-3">
                        <div className="text-left">
                          <div className="text-[8px] font-semibold tracking-[0.2em] text-white/38">风场</div>
                          <div className="mt-1 whitespace-nowrap text-[13px] font-black tracking-[0.14em] text-cyan-100/92">
                            {roundMeta ? `${roundMeta.wind}风场` : '-'}
                          </div>
                        </div>
                          <div className="text-left">
                            <div className="text-[8px] font-semibold tracking-[0.2em] text-white/38">局数</div>
                            <div className="mt-1 whitespace-nowrap text-[13px] font-black tracking-[0.14em] text-amber-100/92">
                              {roundMeta ? `${ROUND_HAND_TEXT[roundMeta.hand] ?? roundMeta.hand}局` : '-'}
                            </div>
                          </div>
                      </div>
                    </div>

                    <div
                      className="absolute inset-x-[42px] bottom-[28px] h-[58px] overflow-hidden border border-emerald-100/12 bg-[linear-gradient(180deg,rgba(10,26,22,0.97),rgba(4,12,9,0.99))] px-3 py-2 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.06),inset_0_-6px_12px_rgba(0,0,0,0.2),0_8px_16px_rgba(0,0,0,0.16)]"
                      style={{ clipPath: CENTER_CORE_SCREEN }}
                    >
                      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(174,255,218,0.06),rgba(174,255,218,0)_42%,rgba(0,0,0,0.18)_100%)]" />
                      <div className="pointer-events-none absolute inset-0 opacity-[0.13] bg-[linear-gradient(180deg,rgba(255,255,255,0.14)_0,rgba(255,255,255,0.14)_1px,transparent_1px,transparent_4px)]" />
                      <div className="pointer-events-none absolute inset-[2px] border border-white/4" style={{ clipPath: CENTER_CORE_SCREEN }} />
                        <div className="relative text-[8px] font-semibold tracking-[0.2em] text-white/38">剩余牌</div>
                        <div className="relative mt-1 font-mono text-[23px] font-black leading-none tracking-[0.08em] text-emerald-50">
                          {activeView?.remaining_tiles ?? '-'}
                        </div>
                    </div>
                  </div>

                  <div className="absolute bottom-[182px] left-1/2 z-[14] -translate-x-1/2">
                    <River discards={bottomRiverDiscards} orientation="bottom" />
                  </div>
                  <div className="absolute left-[calc(50%-292px)] top-1/2 z-[14] -translate-x-1/2 -translate-y-1/2 rotate-90">
                    <River discards={leftRiverDiscards} orientation="left" />
                  </div>
                  <div className="absolute left-1/2 top-[178px] z-[14] -translate-x-1/2 rotate-180">
                    <River discards={topRiverDiscards} orientation="top" />
                  </div>
                  <div className="absolute left-[calc(50%+292px)] top-1/2 z-[14] -translate-x-1/2 -translate-y-1/2 -rotate-90">
                    <River discards={rightRiverDiscards} orientation="right" />
                  </div>

                  <div className="absolute bottom-[10px] left-1/2 z-[5] -translate-x-1/2">
                    <Hand tiles={humanHandTiles} isCurrentPlayer onTileClick={handleDiscardByIndex} />
                  </div>
                  <TableMeldStrip
                    melds={bottomPlayer?.melds ?? []}
                    position="bottom"
                    playerSeat={bottomPlayer?.seat ?? activeView?.human_seat ?? 0}
                    playerCount={activeView?.players.length ?? 4}
                  />
                  <div className="absolute left-[0px] top-1/2 z-[5] -translate-y-1/2">
                    <Hand tiles={leftHandTiles} orientation="left" revealTiles={revealOpponentHands} />
                  </div>
                  <TableMeldStrip
                    melds={leftPlayer?.melds ?? []}
                    position="left"
                    playerSeat={leftPlayer?.seat ?? 0}
                    playerCount={activeView?.players.length ?? 4}
                  />
                  <div className="absolute left-[58%] top-[4px] z-[5] -translate-x-1/2 rounded-[28px] border border-white/8 bg-black/16 opacity-90 shadow-[0_10px_24px_rgba(0,0,0,0.18)] backdrop-blur-sm">
                    <Hand tiles={topHandTiles} orientation="top" revealTiles={revealOpponentHands} />
                  </div>
                  <TableMeldStrip
                    melds={topPlayer?.melds ?? []}
                    position="top"
                    playerSeat={topPlayer?.seat ?? 0}
                    playerCount={activeView?.players.length ?? 4}
                  />
                  <div className="absolute right-[0px] top-1/2 z-[5] -translate-y-1/2">
                    <Hand tiles={rightHandTiles} orientation="right" revealTiles={revealOpponentHands} />
                  </div>
                  <TableMeldStrip
                    melds={rightPlayer?.melds ?? []}
                    position="right"
                    playerSeat={rightPlayer?.seat ?? 0}
                    playerCount={activeView?.players.length ?? 4}
                  />

                  <div className="absolute bottom-[34px] right-[30px] z-30 flex w-[150px] flex-col gap-3">
                    {specialActions.map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        disabled={Boolean(replay)}
                        className={`${getActionButtonClass(action.type)} w-full`}
                        onClick={() => void handleAction(action.id)}
                      >
                        {humanizeText(action.label)}
                      </button>
                    ))}
                  </div>

                  {false ? (
                    <div className="absolute right-[32px] top-[32px] z-20 w-[250px] rounded-[26px] border border-white/15 bg-black/35 p-4 shadow-lg backdrop-blur-md">
                    <div className="text-sm font-bold text-white/80">当前弃牌</div>
                    <div className="mt-2 text-base font-semibold">
                      {activeView?.last_discard
                        ? `${getDisplayName(activeView.players[activeView.last_discard.seat]?.name ?? '')} · ${formatTileLabelZh(activeView.last_discard.tile)}`
                        : '-'}
                    </div>
                    <div className="mt-3 text-xs text-white/60">
                      {busyText ? busyText : replay ? `回放第 ${replayIndex + 1} / ${replay.snapshots.length} 帧` : '实时局面'}
                    </div>
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="hidden">
                <Card className="mahjong-console-card rounded-[30px] p-5 text-white lg:p-6">
                  <div className="mb-3 flex items-center justify-between">
                    <h2 className="text-lg font-bold">你的状态</h2>
                    {bottomPlayer ? (
                      <div className="flex flex-wrap gap-2">
                        <Badge variant="outline" className="border-white/15 text-white/80">
                          {WIND_TEXT[bottomPlayer.seat_wind] ?? bottomPlayer.seat_wind}家
                        </Badge>
                        {bottomPlayer.dealer ? (
                          <Badge variant="outline" className="border-amber-200/30 text-amber-100">
                            庄家
                          </Badge>
                        ) : null}
                        {bottomPlayer.riichi ? (
                          <Badge variant="outline" className="border-pink-300/30 text-pink-100">
                            立直
                          </Badge>
                        ) : null}
                        {bottomPlayer.nuki_count ? (
                          <Badge variant="outline" className="border-cyan-300/30 text-cyan-100">
                            拔北 {bottomPlayer.nuki_count}
                          </Badge>
                        ) : null}
                      </div>
                    ) : null}
                  </div>

                  <div className="mahjong-status-shell p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">当前操作</div>
                        <div className="mt-3 text-base font-bold leading-7 text-white/92">{bottomPlayerStatusSummary}</div>
                        <div className="mt-2 text-xs leading-6 text-white/62">{bottomPlayerStatusDetail}</div>
                      </div>

                      <div className="shrink-0 text-right">
                        <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">当前席位</div>
                        <div className="mt-2 text-sm font-black tracking-[0.12em] text-cyan-50">
                          {bottomPlayer ? `${WIND_TEXT[bottomPlayer.seat_wind] ?? bottomPlayer.seat_wind}家` : '-'}
                        </div>
                        <div className="mt-2">
                          <span
                            className={cn(
                              'mahjong-status-turn-pill',
                              hasBottomPlayer && isBottomTurn ? 'mahjong-status-turn-pill--active' : ''
                            )}
                          >
                            {bottomPlayerTurnLabel}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-2 sm:grid-cols-3">
                      <div className="mahjong-status-summary-chip">
                        <span className="text-white/45">当前点数</span>
                        <strong>{formatPoints(bottomPlayer?.points)}</strong>
                      </div>
                      <div className="mahjong-status-summary-chip">
                        <span className="text-white/45">手牌张数</span>
                        <strong>{humanHandTiles.length}</strong>
                      </div>
                      <div className="mahjong-status-summary-chip">
                        <span className="text-white/45">牌河张数</span>
                        <strong>{bottomPlayer?.discards.length ?? 0}</strong>
                      </div>
                    </div>

                    {bottomPlayerInsight.metrics.length ? (
                      <div className="mt-4 flex flex-wrap gap-2">
                        {bottomPlayerInsight.metrics.map((item) => (
                          <span
                            key={`bottom-status-${item.label}-${item.value}`}
                            className="rounded-full border border-cyan-300/15 bg-cyan-400/10 px-2.5 py-1 text-[11px] font-semibold text-cyan-100"
                          >
                            {item.label} {item.value}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>

                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    <div className="mahjong-status-section p-4">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-white/84">你的副露</div>
                        <span className="text-[11px] font-semibold tracking-[0.14em] text-white/45">
                          {bottomPlayer?.melds.length ?? 0} 组
                        </span>
                      </div>
                      <MeldStrip melds={bottomPlayer?.melds ?? []} />
                    </div>
                    <div className="mahjong-status-section p-4">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-white/84">你的牌河</div>
                        <span className="text-[11px] font-semibold tracking-[0.14em] text-white/45">
                          {bottomPlayer?.discards.length ?? 0} 张
                        </span>
                      </div>
                      <div className="rounded-2xl border border-white/10 bg-black/15 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                        <River discards={bottomPlayer ? toRiverTiles(bottomPlayer.discards) : []} orientation="bottom" />
                      </div>
                    </div>
                  </div>
                </Card>

                <Card className="mahjong-console-card rounded-[30px] p-5 text-white lg:p-6">
                  <div className="mb-3 flex items-center justify-between">
                    <h2 className="text-lg font-bold">牌桌情报</h2>
                    <div className="text-xs text-white/55">观察副露、牌河与当前判断</div>
                  </div>
                  <div className="space-y-3">
                    {[rightPlayer, topPlayer, leftPlayer]
                      .filter((player): player is PlayerView => player !== null)
                      .map((player) => {
                        const insight = parsePlayerInsight(player.last_reason);
                        return (
                          <div key={player.seat} className="rounded-2xl border border-white/10 bg-black/20 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div>
                                <div className="font-semibold">{getDisplayName(player.name)}</div>
                                <div className="mt-1 text-xs text-white/60">
                                  {WIND_TEXT[player.seat_wind] ?? player.seat_wind}家 · {formatPoints(player.points)} 点
                                </div>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                <Badge variant="outline" className="border-white/15 text-white/80">
                                  {formatAiLevelLabel(player.ai_level)}
                                </Badge>
                                {player.dealer ? (
                                  <Badge variant="outline" className="border-amber-200/30 text-amber-100">
                                    庄家
                                  </Badge>
                                ) : null}
                                {player.riichi ? (
                                  <Badge variant="outline" className="border-pink-300/30 text-pink-100">
                                    立直
                                  </Badge>
                                ) : null}
                                {player.nuki_count ? (
                                  <Badge variant="outline" className="border-cyan-300/30 text-cyan-100">
                                    拔北 {player.nuki_count}
                                  </Badge>
                                ) : null}
                              </div>
                            </div>

                            <div className="mt-3 rounded-2xl border border-white/10 bg-black/15 px-3 py-3">
                              <div className="text-[11px] font-semibold tracking-[0.16em] text-white/45">当前判断</div>
                              <div className="mt-1 text-sm text-white/82">{insight.summary ?? '等待行动中。'}</div>
                              {insight.metrics.length ? (
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {insight.metrics.map((item) => (
                                    <span
                                      key={`${player.seat}-${item.label}-${item.value}`}
                                      className="rounded-full border border-cyan-300/15 bg-cyan-400/10 px-2.5 py-1 text-[11px] font-semibold text-cyan-100"
                                    >
                                      {item.label} {item.value}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                              {insight.detail ? (
                                <div className="mt-2 text-xs leading-5 text-white/58">{insight.detail}</div>
                              ) : null}
                            </div>

                            <div className="mt-3 grid gap-3 lg:grid-cols-2">
                              <div>
                                <div className="mb-2 text-xs font-semibold text-white/70">副露</div>
                                <MeldStrip melds={player.melds} />
                              </div>
                              <div>
                                <div className="mb-2 text-xs font-semibold text-white/70">牌河</div>
                                <div className="rounded-2xl border border-white/10 bg-black/15 p-3">
                                  <River discards={toRiverTiles(player.discards)} orientation="bottom" />
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                  </div>
                </Card>
              </div>
            </div>
          </Card>
        </main>

        <aside className="hidden">
          <Card className="mahjong-console-card rounded-[30px] p-5 text-white lg:p-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-bold">对局记录</h2>
              <Button
                variant="outline"
                className="mahjong-console-ghost"
                disabled={!currentGame}
                onClick={() => void handleLoadReplay()}
              >
                载入牌谱
              </Button>
            </div>

            <div className="max-h-[420px] space-y-3 overflow-auto pr-1">
              {deferredLogTail.length ? (
                deferredLogTail.map((entry) => {
                  const tone = getActionLogTone(entry.type);
                  const tileLabel = entry.tile ? formatTileLabelZh(entry.tile) : '';
                  const narrative = getActionLogNarrative(entry);

                  return (
                    <div key={entry.seq} className={cn('mahjong-log-entry border p-3.5 pl-5', tone.shell)}>
                      <span aria-hidden className={cn('absolute bottom-3 top-3 left-2 w-1 rounded-full', tone.accent)} />

                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2 text-[11px] tracking-[0.18em] text-white/42">
                            <span className="font-black text-white/52">#{String(entry.seq).padStart(3, '0')}</span>
                            <span className="text-white/58">{getDisplayName(entry.actor)}</span>
                          </div>
                        </div>
                        <span
                          className={cn(
                            'shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-black tracking-[0.16em] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]',
                            tone.badge,
                          )}
                        >
                          {getActionTypeText(entry.type)}
                        </span>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2.5">
                        {tileLabel ? <span className={cn('mahjong-log-tile-chip', tone.tile)}>{tileLabel}</span> : null}
                        <span className={cn('text-sm leading-6', tone.detail)}>{narrative}</span>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="mahjong-console-empty px-4 py-6 text-sm text-white/60">
                  对局中的摸牌、打牌和鸣牌记录会按顺序显示在这里。
                </div>
              )}
            </div>
          </Card>

          <Card className="mahjong-console-card rounded-[30px] p-5 text-white lg:p-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-bold">牌谱回看</h2>
              <Button
                variant="outline"
                className="mahjong-console-ghost"
                disabled={!replay}
                onClick={() => {
                  startTransition(() => {
                    setReplay(null);
                    setReplayIndex(0);
                  });
                }}
              >
                回到实时牌桌
              </Button>
            </div>

            <div className="mahjong-replay-shell mt-1 p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="mahjong-replay-pill">{replay ? '牌谱回看中' : '实时牌桌'}</span>
                    <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-semibold tracking-[0.16em] text-white/58">
                      {replayFrameRoundText}
                    </span>
                  </div>
                  <div className="mt-3 text-sm font-semibold text-white/88">{replayFrameSummary}</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2.5">
                    {replayFrameTileText && replay ? (
                      <span className="mahjong-log-tile-chip border-cyan-200/20 bg-[linear-gradient(180deg,rgba(56,189,248,0.18),rgba(10,36,57,0.74))] text-cyan-50">
                        {replayFrameTileText}
                      </span>
                    ) : null}
                    <span className="text-xs leading-6 text-white/62">{replayFrameNarrative}</span>
                  </div>
                </div>

                <div className="shrink-0 text-right">
                  <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">回看进度</div>
                  <div className="mt-1 text-2xl font-black tracking-[0.08em] text-cyan-50">
                    {replay ? `${replayIndex + 1}/${replayTotalSteps}` : '--/--'}
                  </div>
                </div>
              </div>

              <div className="mt-4">
                <div className="mahjong-replay-track">
                  <div className="mahjong-replay-track-fill" style={{ width: `${replayProgressPercent}%` }} />
                  <input
                    type="range"
                    min={0}
                    max={Math.max(0, replayTotalSteps - 1)}
                    value={replayIndex}
                    disabled={!replay}
                    onChange={(event) => setReplayIndex(Number(event.target.value))}
                    className="mahjong-replay-range"
                  />
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] font-semibold tracking-[0.16em] text-white/42">
                  <span>开局</span>
                  <span>{replay ? `第 ${replaySnapshot?.seq ?? replayIndex + 1} 手` : '等待载入'}</span>
                  <span>末手</span>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Button
                  variant="outline"
                  className="mahjong-console-ghost mahjong-replay-step"
                  disabled={!replay || replayIndex <= 0}
                  onClick={() => setReplayIndex(0)}
                >
                  回到开局
                </Button>
                <Button
                  variant="outline"
                  className="mahjong-console-ghost mahjong-replay-step"
                  disabled={!replay || replayIndex <= 0}
                  onClick={() => setReplayIndex((current) => Math.max(0, current - 1))}
                >
                  上一步
                </Button>
                <Button
                  variant="outline"
                  className="mahjong-console-ghost mahjong-replay-step"
                  disabled={!replay || replayIndex >= replayTotalSteps - 1}
                  onClick={() => setReplayIndex((current) => Math.min(replayTotalSteps - 1, current + 1))}
                >
                  下一步
                </Button>
                <Button
                  variant="outline"
                  className="mahjong-console-ghost mahjong-replay-step"
                  disabled={!replay || replayIndex >= replayTotalSteps - 1}
                  onClick={() => setReplayIndex(Math.max(0, replayTotalSteps - 1))}
                >
                  回到末手
                </Button>
              </div>
            </div>

            {replayRoundHeadline ? (
              <div className="mahjong-replay-result-card mt-4 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">这一局结果</div>
                    <div className="mt-2 text-base font-bold leading-7 text-white/92">{replayRoundHeadline}</div>
                  </div>
                  {replayRoundSubtypeText ? (
                    <Badge className="border border-amber-300/25 bg-amber-400/10 px-3 py-1 text-[11px] font-semibold tracking-[0.18em] text-amber-100">
                      {replayRoundSubtypeText}
                    </Badge>
                  ) : null}
                </div>

                {(replayRoundLoserName || replayRoundTenpai.length || activeView?.round_label) ? (
                  <div className="mahjong-replay-result-grid mt-4">
                    {activeView?.round_label ? (
                      <div className="mahjong-replay-result-chip">
                        <span className="text-white/45">局面</span>
                        <span className="text-white/82">{humanizeText(activeView.round_label)}</span>
                      </div>
                    ) : null}
                    {replayRoundLoserName ? (
                      <div className="mahjong-replay-result-chip">
                        <span className="text-white/45">放铳者</span>
                        <span className="text-white/82">{replayRoundLoserName}</span>
                      </div>
                    ) : null}
                    {replayRoundTenpai.length ? (
                      <div className="mahjong-replay-result-chip sm:col-span-2">
                        <span className="text-white/45">流局听牌</span>
                        <span className="text-white/82">{replayRoundTenpai.join('、')}</span>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            {resultPlacements.length ? (
              <div className="mahjong-replay-result-card mt-4 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold tracking-[0.18em] text-white/45">整场顺位</div>
                    <div className="mt-2 text-sm text-white/72">这一场对局的最终名次已经锁定。</div>
                  </div>
                  <span className="mahjong-replay-pill">终局</span>
                </div>
                <div className="mt-4 space-y-2.5">
                  {resultPlacements.map((item) => (
                    <div
                      key={`${String(item.seat)}-${String(item.placement)}`}
                      className={cn(
                        'mahjong-replay-rank-row',
                        Number(item.placement) === 1
                          ? 'border-amber-300/24 bg-[radial-gradient(circle_at_left,rgba(251,191,36,0.16),transparent_26%),linear-gradient(180deg,rgba(44,30,10,0.76),rgba(18,12,8,0.58))]'
                          : Number(item.placement) === 2
                            ? 'border-cyan-300/18 bg-[radial-gradient(circle_at_left,rgba(103,232,249,0.12),transparent_26%),linear-gradient(180deg,rgba(10,24,34,0.76),rgba(6,12,18,0.58))]'
                            : Number(item.placement) === 3
                              ? 'border-rose-300/18 bg-[radial-gradient(circle_at_left,rgba(251,113,133,0.12),transparent_26%),linear-gradient(180deg,rgba(36,16,18,0.76),rgba(16,8,10,0.58))]'
                              : 'border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.015)),rgba(0,0,0,0.18)]',
                      )}
                    >
                      <span
                        className={cn(
                          'mahjong-replay-rank-badge',
                          Number(item.placement) === 1
                            ? 'border-amber-300/35 bg-amber-300/16 text-amber-100'
                            : Number(item.placement) === 2
                              ? 'border-cyan-300/25 bg-cyan-400/12 text-cyan-100'
                              : Number(item.placement) === 3
                                ? 'border-rose-300/25 bg-rose-400/12 text-rose-100'
                                : 'border-white/14 bg-white/6 text-white/70',
                        )}
                      >
                        第 {String(item.placement)} 名
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold text-white/90">{getDisplayName(String(item.name))}</div>
                      </div>
                      <div className="mahjong-replay-rank-score">{formatPoints(Number(item.points))}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mahjong-console-section mt-4 px-4 py-3 text-sm text-white/60">
              {busyText ?? (uiPending ? '正在整理牌桌信息...' : '你可以随时载入历史对局，回看整局进程。')}
            </div>
          </Card>

          <Card className="mahjong-console-card rounded-[30px] p-5 text-white lg:p-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-bold">行动提示</h2>
              <div className="text-xs text-white/55">已移出牌桌，避免遮挡视线</div>
            </div>
            <div className="mahjong-console-section p-4">
              <HintPanel hint={activeView?.hint} legalActions={activeView?.legal_actions} />
            </div>
          </Card>
        </aside>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {activeDockPanel && dockPanelContent ? (
          <DockPanelShell activeKey={activeDockPanel} onClose={handleCloseDockPanel}>
            {dockPanelContent}
          </DockPanelShell>
        ) : null}
      </AnimatePresence>
      <MacDock items={dockItems} activeKey={activeDockPanel} onSelect={handleDockSelect} />

      {resultModalOpen && !replay && currentGame ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/72 p-4 backdrop-blur-md">
          <div className="mahjong-result-shell flex max-h-[calc(100vh-2rem)] w-full max-w-3xl flex-col overflow-hidden rounded-[34px] text-white">
            <div className="mahjong-result-header border-b border-white/10 px-6 py-5">
              <div className="text-xs uppercase tracking-[0.24em] text-cyan-200/75">
                {resultPlacements.length ? '终局结算' : '本局结算'}
              </div>
              <h2 className="mt-2 text-3xl font-black tracking-[0.08em]">
                {humanizeText(
                  String(currentRoundResult?.headline ?? (resultPlacements.length ? '本场对局已结束。' : '本局结算'))
                )}
              </h2>
              <p className="mt-2 text-sm text-white/65">
                {resultPlacements.length ? '最终顺位已经确定。' : '查看完本局收支后，就可以继续下一局。'}
              </p>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
              <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <div className="space-y-4">
                {currentRoundResult ? (
                  <div className="mahjong-result-card p-4">
                    <div className="text-sm font-semibold text-white/85">和牌详情</div>

                    {currentRoundSubtypeText ? (
                      <div className="mt-3">
                        <Badge className="border border-amber-300/25 bg-amber-400/10 px-3 py-1 text-[11px] font-semibold tracking-[0.18em] text-amber-100">
                          {currentRoundSubtypeText}
                        </Badge>
                      </div>
                    ) : null}

                    {resultWinners.length ? (
                      <div className="mt-3 space-y-3">
                        {resultWinners.map((winner, index) => {
                          const liabilitySummary = formatLiabilitySummary(winner.liability);
                          const parsedYaku = Array.isArray(winner.yaku)
                            ? winner.yaku.map((item) => parseYakuDetail(item)).filter((item): item is ParsedYakuDetail => item !== null)
                            : [];
                          const regularYaku = parsedYaku.filter((item) => item.category !== 'bonus');
                          const bonusYaku = parsedYaku.filter((item) => item.category === 'bonus');
                          const winnerLevelText = localizeYakuLevel(
                            typeof winner.yaku_level === 'string' ? winner.yaku_level : null,
                            winner.yaku
                          );
                          const winnerIsYakuman = Boolean(winnerLevelText?.includes('役满'));
                          const fuDetails = Array.isArray(winner.fu_details)
                            ? winner.fu_details.filter(
                                (item): item is { fu: number; reason: string } =>
                                  isRecord(item) && typeof item.fu === 'number' && typeof item.reason === 'string'
                              )
                            : [];
                          const paymentDetails = Array.isArray(winner.payments)
                            ? winner.payments.filter(
                                (item): item is { from_seat?: number | null; from_name: string; amount: number; kind: string } =>
                                  isRecord(item) &&
                                  typeof item.from_name === 'string' &&
                                  typeof item.amount === 'number' &&
                                  typeof item.kind === 'string'
                              )
                            : [];
                          const winnerPlayer =
                            currentGame.players.find((player) => player.seat === Number(winner.seat)) ?? null;

                          return (
                            <div
                              key={`${String(winner.seat)}-${index}`}
                              className={cn(
                                'rounded-2xl border p-3',
                                winnerIsYakuman
                                  ? 'border-fuchsia-300/30 bg-[linear-gradient(180deg,rgba(79,18,63,0.34),rgba(20,10,28,0.82))] shadow-[0_0_0_1px_rgba(244,114,182,0.08),0_18px_40px_rgba(120,20,80,0.18)]'
                                  : 'mahjong-result-card'
                              )}
                            >
                              <div className="flex flex-wrap items-center justify-between gap-3">
                                <div className="flex flex-wrap items-center gap-2">
                                  <div className="font-semibold">{getDisplayName(String(winner.name ?? '-'))}</div>
                                  {winnerLevelText ? (
                                    <span
                                      className={cn(
                                        'rounded-full px-3 py-1 text-[11px] font-semibold tracking-[0.16em]',
                                        winnerIsYakuman
                                          ? 'border border-fuchsia-200/30 bg-fuchsia-400/15 text-fuchsia-100'
                                          : 'border border-white/10 bg-white/5 text-white/70'
                                      )}
                                    >
                                      {winnerLevelText}
                                    </span>
                                  ) : null}
                                </div>
                                <div className="text-sm text-amber-100">
                                  {typeof winner.amount === 'number' ? formatScoreDelta(winner.amount) : '-'}
                                </div>
                              </div>

                              {(winner.han || winner.fu) ? (
                                <div className="mt-2 text-xs font-semibold tracking-[0.12em] text-white/70">
                                  {winner.han ? `${String(winner.han)} 番` : ''}
                                  {winner.han && winner.fu ? ' · ' : ''}
                                  {winner.fu ? `${String(winner.fu)} 符` : ''}
                                </div>
                              ) : null}

                              <ResultHandBlock
                                player={winnerPlayer}
                                winTileLabel={typeof winner.win_tile_label === 'string' ? winner.win_tile_label : null}
                                isTsumo={Boolean(winner.is_tsumo)}
                              />

                              {parsedYaku.length ? (
                                <div className="mt-3">
                                  {regularYaku.length ? (
                                    <div>
                                      <div className="mb-2 text-[11px] font-semibold tracking-[0.16em] text-white/45">
                                        役种明细
                                      </div>
                                      <div className="flex flex-wrap gap-2">
                                        {regularYaku.map((item, yakuIndex) => (
                                          <span
                                            key={`${String(winner.seat)}-${index}-regular-${yakuIndex}-${item.rawName}`}
                                            className={cn(
                                              'mahjong-result-chip leading-5',
                                              item.category === 'yakuman'
                                                ? 'border border-fuchsia-200/30 bg-fuchsia-400/15 text-fuchsia-100'
                                                : 'border border-cyan-300/15 bg-cyan-400/10 text-cyan-100'
                                            )}
                                          >
                                            {formatYakuLabel(`${item.rawName}${item.han ? ` ${item.han} han` : ''}`)}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null}

                                  {bonusYaku.length ? (
                                    <div className={regularYaku.length ? 'mt-3' : ''}>
                                      <div className="mb-2 text-[11px] font-semibold tracking-[0.16em] text-amber-100/70">
                                        宝牌加成
                                      </div>
                                      <div className="flex flex-wrap gap-2">
                                        {bonusYaku.map((item, yakuIndex) => (
                                          <span
                                            key={`${String(winner.seat)}-${index}-bonus-${yakuIndex}-${item.rawName}`}
                                            className="mahjong-result-chip border border-amber-300/20 bg-amber-400/10 leading-5 text-amber-100"
                                          >
                                            {formatYakuLabel(`${item.rawName}${item.han ? ` ${item.han} han` : ''}`)}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null}

                                  {!winnerIsYakuman && fuDetails.length ? (
                                    <div className={regularYaku.length || bonusYaku.length ? 'mt-3' : ''}>
                                      <div className="mb-2 text-[11px] font-semibold tracking-[0.16em] text-emerald-100/70">
                                        符数来源
                                      </div>
                                      <div className="flex flex-wrap gap-2">
                                        {fuDetails.map((item, fuIndex) => (
                                          <span
                                            key={`${String(winner.seat)}-${index}-fu-${fuIndex}-${item.reason}-${item.fu}`}
                                            className="mahjong-result-chip border border-emerald-300/20 bg-emerald-400/10 leading-5 text-emerald-100"
                                          >
                                            {formatFuReason(item.reason, item.fu)} {item.fu} 符
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null}

                                  {paymentDetails.length ? (
                                    <div
                                      className={
                                        regularYaku.length || bonusYaku.length || (!winnerIsYakuman && fuDetails.length) ? 'mt-3' : ''
                                      }
                                    >
                                      <div className="mb-2 text-[11px] font-semibold tracking-[0.16em] text-sky-100/70">
                                        支付明细
                                      </div>
                                      <div className="space-y-2">
                                        {paymentDetails.map((item, paymentIndex) => (
                                          <div
                                            key={`${String(winner.seat)}-${index}-payment-${paymentIndex}-${item.kind}-${item.from_name}-${item.amount}`}
                                            className="mahjong-console-section flex items-center justify-between px-3 py-2 text-xs"
                                          >
                                            <div className="text-sky-50">
                                              {getDisplayName(item.from_name)} · {formatPaymentKind(item.kind)}
                                            </div>
                                            <div className="font-semibold text-sky-100">+{formatPoints(item.amount)}</div>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null}
                                </div>
                              ) : null}

                              {liabilitySummary ? (
                                <div className="mt-2 rounded-2xl border border-amber-300/20 bg-amber-400/10 px-3 py-2 text-xs leading-5 text-amber-100">
                                  {liabilitySummary}
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    ) : null}

                    {typeof currentRoundResult.loser === 'string' ? (
                      <div className="mt-3 text-sm text-white/65">放铳者：{getDisplayName(String(currentRoundResult.loser))}</div>
                    ) : null}

                    {resultTenpai.length ? (
                      <div className="mt-3 text-sm text-white/65">流局听牌：{resultTenpai.join('、')}</div>
                    ) : null}
                  </div>
                ) : null}

                {resultScoreChanges.length ? (
                  <div className="mahjong-result-card p-4">
                    <div className="text-sm font-semibold text-white/85">点数增减</div>
                    <div className="mt-3 space-y-2">
                      {resultScoreChanges.map((item) => (
                        <div key={item.seat} className="mahjong-console-section flex items-center justify-between px-3 py-2 text-sm">
                          <div>{item.name}</div>
                          <div className={item.delta > 0 ? 'text-emerald-200' : item.delta < 0 ? 'text-rose-200' : 'text-white/65'}>
                            {formatScoreDelta(item.delta)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="space-y-4">
                <div className="mahjong-result-card p-4">
                  <div className="text-sm font-semibold text-white/85">当前顺位</div>
                  <div className="mt-3 space-y-2">
                    {(resultPlacements.length
                      ? resultPlacements
                      : [...(currentGame.players ?? [])]
                          .sort((left, right) => right.points - left.points || left.seat - right.seat)
                          .map((player, index) => ({
                            placement: index + 1,
                            seat: player.seat,
                            name: player.name,
                            points: player.points,
                          }))
                    ).map((item) => (
                      <div key={`${String(item.seat)}-${String(item.placement)}`} className="mahjong-console-section flex items-center justify-between px-3 py-2 text-sm">
                        <div>
                          第 {String(item.placement)} 名 · {getDisplayName(String(item.name))}
                        </div>
                        <div className="text-points-gold">{formatPoints(Number(item.points))}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {leftoverRiichiBonus > 0 ? (
                  <div className="rounded-[24px] border border-amber-300/15 bg-amber-400/10 p-4 text-sm text-amber-100">
                    终局余供：{formatPoints(leftoverRiichiBonus)}，已结转给第一名。
                  </div>
                ) : null}

                <div className="mahjong-result-card p-4 text-sm text-white/65">
                  {resultPlacements.length
                    ? '整场对局结束后，你仍可从历史对局里回看完整牌谱。'
                    : '如果想继续对局，直接点击“开始下一局”即可进入下一手。'}
                </div>
              </div>
            </div>
            </div>

            <div className="shrink-0 border-t border-white/10 bg-[linear-gradient(180deg,rgba(8,16,26,0.94),rgba(8,16,26,0.98))] px-6 py-5">
              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <Button
                variant="outline"
                className="mahjong-console-ghost"
                onClick={() => setResultModalOpen(false)}
              >
                收起结算
              </Button>

              {nextRoundAction && !resultPlacements.length ? (
                <button
                  type="button"
                  className="mahjong-console-primary px-5 py-3 text-sm font-black tracking-[0.18em] transition-all active:translate-y-1 active:shadow-none"
                  onClick={() => {
                    void (async () => {
                      await handleAction(nextRoundAction.id);
                      setResultModalOpen(false);
                    })();
                  }}
                >
                  开始下一局
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
      ) : null}
    </div>
  );
};

