/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {
  Blank,
  Chun,
  Haku,
  Hatsu,
  Man1,
  Man2,
  Man3,
  Man4,
  Man5,
  Man5Dora,
  Man6,
  Man7,
  Man8,
  Man9,
  Nan,
  Pei,
  Pin1,
  Pin2,
  Pin3,
  Pin4,
  Pin5,
  Pin5Dora,
  Pin6,
  Pin7,
  Pin8,
  Pin9,
  Shaa,
  Sou1,
  Sou2,
  Sou3,
  Sou4,
  Sou5,
  Sou5Dora,
  Sou6,
  Sou7,
  Sou8,
  Sou9,
  Ton,
} from 'react-riichi-mahjong-tiles';

import { cn } from '@/lib/utils';
import { Tile } from '@/src/types/mahjong';

interface MahjongTileProps {
  tile: Tile;
  size?: 'sm' | 'md' | 'lg';
  isFaceDown?: boolean;
  isDiscarded?: boolean;
  isRiichi?: boolean;
  onClick?: () => void;
  className?: string;
}

type RiichiTileComponent = React.ComponentType<React.SVGProps<SVGSVGElement>>;

type TileShellPreset = {
  shell: string;
  facePanel: string;
  faceSvg: string;
  backInset: string;
  backEmblem: string;
};

const TILE_PRESETS: Record<NonNullable<MahjongTileProps['size']>, TileShellPreset> = {
  sm: {
    shell: 'h-[40px] w-[30px] rounded-[8px] border-r-[2px] border-b-[5px]',
    facePanel: 'm-[2px] rounded-[6px]',
    faceSvg: 'h-[30px] w-[22px]',
    backInset: 'inset-[3px] rounded-[6px]',
    backEmblem: 'h-3.5 w-3.5',
  },
  md: {
    shell: 'h-[56px] w-[40px] rounded-[10px] border-r-[2px] border-b-[6px]',
    facePanel: 'm-[3px] rounded-[8px]',
    faceSvg: 'h-[43px] w-[31px]',
    backInset: 'inset-[4px] rounded-[8px]',
    backEmblem: 'h-4.5 w-4.5',
  },
  lg: {
    shell: 'h-[70px] w-[50px] rounded-[12px] border-r-[3px] border-b-[7px]',
    facePanel: 'm-[4px] rounded-[9px]',
    faceSvg: 'h-[54px] w-[38px]',
    backInset: 'inset-[5px] rounded-[10px]',
    backEmblem: 'h-5.5 w-5.5',
  },
};

const SUITED_TILE_COMPONENTS: Record<'m' | 'p' | 's', Record<number, RiichiTileComponent>> = {
  m: {
    1: Man1,
    2: Man2,
    3: Man3,
    4: Man4,
    5: Man5,
    6: Man6,
    7: Man7,
    8: Man8,
    9: Man9,
  },
  p: {
    1: Pin1,
    2: Pin2,
    3: Pin3,
    4: Pin4,
    5: Pin5,
    6: Pin6,
    7: Pin7,
    8: Pin8,
    9: Pin9,
  },
  s: {
    1: Sou1,
    2: Sou2,
    3: Sou3,
    4: Sou4,
    5: Sou5,
    6: Sou6,
    7: Sou7,
    8: Sou8,
    9: Sou9,
  },
};

const RED_FIVE_COMPONENTS: Record<'m' | 'p' | 's', RiichiTileComponent> = {
  m: Man5Dora,
  p: Pin5Dora,
  s: Sou5Dora,
};

const HONOR_TILE_COMPONENTS: Record<number, RiichiTileComponent> = {
  1: Ton,
  2: Nan,
  3: Shaa,
  4: Pei,
  5: Haku,
  6: Hatsu,
  7: Chun,
};

function getTileComponent(tile: Tile): RiichiTileComponent {
  if (tile.suit === 'z') {
    return HONOR_TILE_COMPONENTS[tile.value] ?? Blank;
  }

  if (tile.isRed && tile.value === 5) {
    return RED_FIVE_COMPONENTS[tile.suit] ?? Blank;
  }

  return SUITED_TILE_COMPONENTS[tile.suit]?.[tile.value] ?? Blank;
}

export const MahjongTile = React.memo(function MahjongTile({
  tile,
  size = 'md',
  isFaceDown = false,
  isDiscarded = false,
  isRiichi = false,
  onClick,
  className,
}: MahjongTileProps) {
  const preset = TILE_PRESETS[size];
  const TileFace = getTileComponent(tile);

  if (isFaceDown) {
    return (
      <div
        className={cn(
          'relative overflow-hidden border-[#c58d1f] bg-[linear-gradient(180deg,#f7c739_0%,#eea80f_64%,#d78407_100%)] shadow-[0_5px_0_rgba(144,96,13,0.34),0_10px_18px_rgba(0,0,0,0.16)] transition-transform hover:-translate-y-2',
          preset.shell,
          className
        )}
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-[34%] bg-white/16" />
        <div
          className={cn(
            'pointer-events-none absolute border border-white/18 bg-[linear-gradient(180deg,rgba(255,246,212,0.18),rgba(151,91,0,0.08))] shadow-[inset_0_1px_0_rgba(255,255,255,0.18),inset_0_-1px_0_rgba(126,77,0,0.14)]',
            preset.backInset
          )}
        />
        <div className="pointer-events-none absolute inset-x-[24%] top-[22%] h-[1px] bg-white/18" />
        <div className="pointer-events-none absolute inset-x-[24%] bottom-[22%] h-[1px] bg-[#9e6612]/26" />
        <div className="pointer-events-none absolute inset-y-[24%] left-[22%] w-[1px] bg-white/14" />
        <div className="pointer-events-none absolute inset-y-[24%] right-[22%] w-[1px] bg-[#9e6612]/20" />
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div
            className={cn(
              'relative rotate-45 rounded-[5px] border border-white/22 bg-[radial-gradient(circle,rgba(255,249,222,0.42),rgba(236,177,52,0.26)_52%,rgba(158,95,8,0.18)_100%)] shadow-[0_1px_0_rgba(255,255,255,0.12)]',
              preset.backEmblem
            )}
          >
            <div className="absolute inset-[23%] rounded-[3px] border border-[#fff4d1]/42" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={onClick}
      className={cn(
        'relative overflow-hidden border-[#d0a448] bg-tile-ivory shadow-[0_6px_0_rgba(168,120,34,0.3),0_12px_18px_rgba(0,0,0,0.18)] transition-all hover:-translate-y-2 hover:shadow-[0_8px_0_rgba(168,120,34,0.26),0_16px_24px_rgba(0,0,0,0.22)] active:translate-y-0 active:border-b-[3px]',
        preset.shell,
        onClick ? 'cursor-pointer' : 'cursor-default',
        isRiichi &&
          'rotate-90 border-[#dfbd67] shadow-[0_6px_0_rgba(168,120,34,0.24),0_0_0_1px_rgba(255,243,200,0.42),0_12px_18px_rgba(0,0,0,0.16)]',
        isDiscarded && 'opacity-90',
        className
      )}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[28%] bg-white/26" />
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-[22%] bg-[linear-gradient(180deg,transparent,rgba(216,189,128,0.2))]" />
      <div className="pointer-events-none absolute inset-[2px] rounded-[inherit] border border-[#f8edd2]/90" />
      {isRiichi ? (
        <>
          <div className="pointer-events-none absolute inset-[1px] rounded-[inherit] border border-amber-100/55" />
          <div className="pointer-events-none absolute inset-x-[6px] bottom-[5px] h-[4px] rounded-full bg-[radial-gradient(circle,rgba(255,247,212,0.75),rgba(121,216,255,0.18)_72%,rgba(121,216,255,0)_100%)] blur-[3px]" />
        </>
      ) : null}

      <div
        className={cn(
          'relative flex h-[calc(100%-4px)] items-center justify-center overflow-hidden bg-[linear-gradient(180deg,#fffdfa_0%,#f8efda_72%,#f1e2c1_100%)] shadow-[inset_0_1px_0_rgba(255,255,255,0.82),inset_0_-1px_0_rgba(199,169,112,0.22)]',
          preset.facePanel
        )}
      >
        <TileFace
          className={cn(
            'drop-shadow-[0_1px_1px_rgba(0,0,0,0.12)]',
            preset.faceSvg
          )}
          aria-hidden="true"
          focusable="false"
        />
      </div>
    </div>
  );
});
