import { describe, expect, it } from 'vitest';
import { markScrollTop } from './proofScroll';

// Panel 600 px enindeki sayfa ~846 px boy; görünür kap 400 px.
const FRAME_H = 846;
const VIEW_H = 400;

describe('markScrollTop', () => {
  it('sayfanın altındaki işareti kabın ortasına getirir (ekrandaki şikâyet: işaret altta, kesik)', () => {
    const box = [120, 900, 700, 940] as const; // y merkezi 920/1000
    const top = markScrollTop(box, 0, FRAME_H, VIEW_H, FRAME_H);
    // merkez 778 px; ortalamak 578 ister, en fazla kaydırma 446 → sona dayanır, işaret yine görünür
    expect(top).toBe(FRAME_H - VIEW_H);
    const markTop = (FRAME_H * box[1]) / 1000 - top;
    const markBottom = (FRAME_H * box[3]) / 1000 - top;
    expect(markTop).toBeGreaterThanOrEqual(0);
    expect(markBottom).toBeLessThanOrEqual(VIEW_H);
  });

  it('ortadaki işareti tam ortalar', () => {
    const box = [100, 480, 900, 520] as const;
    const top = markScrollTop(box, 0, FRAME_H, VIEW_H, FRAME_H);
    expect(top).toBe(Math.round(FRAME_H * 0.5 - VIEW_H / 2));
  });

  it('sayfa başındaki işarette kaydırmaz (eksiye gitmez)', () => {
    expect(markScrollTop([0, 20, 500, 60], 0, FRAME_H, VIEW_H, FRAME_H)).toBe(0);
  });

  it('sayfa kaba sığıyorsa kaydırma sıfırdır', () => {
    expect(markScrollTop([0, 950, 500, 990], 0, 380, VIEW_H, 380)).toBe(0);
  });

  it('çerçevenin kaptaki üst payını hesaba katar', () => {
    const box = [0, 500, 100, 500] as const;
    expect(markScrollTop(box, 10, 1000, 200, 1010)).toBe(410);
  });
});
