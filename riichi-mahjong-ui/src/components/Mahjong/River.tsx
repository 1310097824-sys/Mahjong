/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { Tile } from '@/src/types/mahjong';
import { MahjongTile } from './MahjongTile';
import { cn } from '@/lib/utils';

export interface RiverDiscardView {
  tile: Tile;
  riichi: boolean;
  called: boolean;
  key: string;
}

interface RiverProps {
  discards: RiverDiscardView[];
  orientation?: 'bottom' | 'top' | 'left' | 'right';
}

const RIVER_COLUMNS = 6;
const MINIMUM_SLOTS = 18;

export const River = React.memo(function River({ discards, orientation = 'bottom' }: RiverProps) {
  const slotCount = Math.max(
    MINIMUM_SLOTS,
    Math.ceil(Math.max(discards.length, 1) / RIVER_COLUMNS) * RIVER_COLUMNS
  );
  const slots = Array.from({ length: slotCount }, (_, index) => discards[index] ?? null);

  return (
    <div className="grid grid-cols-6 gap-x-[3px] gap-y-[4px] rounded-[16px] px-[4px] py-[4px]">
      {slots.map((discard, slotIndex) => (
        <div
          key={discard?.key ?? `${orientation}-slot-${slotIndex}`}
          className="relative flex h-[44px] w-[42px] items-center justify-center overflow-visible"
        >
          {discard ? (
            <>
              {discard.riichi ? (
                <>
                  <div className="pointer-events-none absolute inset-x-[2px] top-1/2 h-[18px] -translate-y-1/2 rounded-full border border-cyan-100/10 bg-[linear-gradient(90deg,rgba(118,224,255,0.06),rgba(255,245,196,0.18)_50%,rgba(118,224,255,0.06))] animate-riichi-aura" />
                  <div className="pointer-events-none absolute inset-x-[8px] bottom-[4px] h-[6px] rounded-full bg-cyan-100/18 blur-[4px] animate-riichi-tile" />
                  <div className="pointer-events-none absolute inset-x-[9px] top-[4px] h-[2px] rounded-full bg-[linear-gradient(90deg,rgba(255,244,196,0),rgba(255,244,196,0.86)_50%,rgba(255,244,196,0))] animate-riichi-tile" />
                </>
              ) : null}
              <MahjongTile
                tile={discard.tile}
                size="sm"
                isDiscarded
                isRiichi={discard.riichi}
                className={cn(
                  discard.riichi &&
                    'relative z-10 animate-riichi-tile shadow-[0_6px_0_rgba(168,120,34,0.22),0_0_0_1px_rgba(255,245,196,0.42),0_10px_18px_rgba(59,197,255,0.12)]'
                )}
              />
            </>
          ) : (
            <div className="h-[40px] w-[30px] opacity-0" aria-hidden="true" />
          )}
        </div>
      ))}
    </div>
  );
});
