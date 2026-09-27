import { describe, expect, it } from 'vitest';
import { clock, resolve } from './overlay';

describe('önizlemede dinle: ses eşlemesinin okunması', () => {
  it('SMIL saat değerini saniyeye çevirir', () => {
    expect(clock('0:00:01.234')).toBeCloseTo(1.234);
    expect(clock('1:02:03.500')).toBeCloseTo(3723.5);
    expect(clock('00:12.5')).toBeCloseTo(12.5);
    expect(Number.isNaN(clock('abc'))).toBe(true);
    expect(Number.isNaN(clock(null))).toBe(true);
  });

  it('göreli yolu e-kitap içi yola çözer', () => {
    expect(resolve('smil/s005.smil', '../text/s005.xhtml')).toBe('text/s005.xhtml');
    expect(resolve('smil/s005.smil', '../audio/p_1a2b3c4d.mp3')).toBe('audio/p_1a2b3c4d.mp3');
    expect(resolve('smil/bolum-001.smil', './x.mp3')).toBe('smil/x.mp3');
  });
});
