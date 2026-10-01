import { describe, expect, it } from 'vitest';
import { sortStep } from './sortKeys';

describe('Baskı önerisi çok kolonlu sıralama', () => {
  it('düz tıklama tek kolon: azalan → artan → kaldır', () => {
    let s = sortStep([], 3, false);
    expect(s).toEqual([{ index: 3, dir: -1 }]);
    s = sortStep(s, 3, false);
    expect(s).toEqual([{ index: 3, dir: 1 }]);
    expect(sortStep(s, 3, false)).toEqual([]);
  });
  it('Shift ile ek anahtar sona eklenir, öncekiler korunur', () => {
    const s = sortStep(sortStep([], 3, false), 5, true);
    expect(s).toEqual([
      { index: 3, dir: -1 },
      { index: 5, dir: -1 },
    ]);
    expect(sortStep(s, 5, true)).toEqual([
      { index: 3, dir: -1 },
      { index: 5, dir: 1 },
    ]);
    expect(sortStep(sortStep(s, 5, true), 5, true)).toEqual([{ index: 3, dir: -1 }]);
  });
  it('çok anahtarlıyken düz tıklama o kolona tek başına sıralar', () => {
    const s = [
      { index: 3, dir: -1 as const },
      { index: 5, dir: 1 as const },
    ];
    expect(sortStep(s, 5, false)).toEqual([{ index: 5, dir: -1 }]);
    expect(sortStep(s, 7, false)).toEqual([{ index: 7, dir: -1 }]);
  });
});
