/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { Tile } from '@/src/types/mahjong';
import { MahjongTile } from './MahjongTile';

interface HandProps {
  tiles: Tile[];
  onTileClick?: (index: number) => void;
  isCurrentPlayer?: boolean;
  orientation?: 'bottom' | 'top' | 'left' | 'right';
  revealTiles?: boolean;
}

export const Hand = React.memo(function Hand({
  tiles,
  onTileClick,
  isCurrentPlayer = false,
  orientation = 'bottom',
  revealTiles = false,
}: HandProps) {
  return (
    <div
      className="flex flex-row gap-1 p-4"
      style={{
        transform: orientation === 'top' ? 'rotate(180deg)' : 
                   orientation === 'left' ? 'rotate(90deg)' : 
                   orientation === 'right' ? 'rotate(-90deg)' : 'none'
      }}
    >
      {tiles.map((tile, index) => (
        <MahjongTile
          key={`${tile.suit}-${tile.value}-${index}`}
          tile={tile}
          isFaceDown={!isCurrentPlayer && !revealTiles}
          onClick={() => isCurrentPlayer && onTileClick?.(index)}
          className={index === tiles.length - 1 && tiles.length % 3 === 2 ? 'ml-4' : ''}
        />
      ))}
    </div>
  );
});
