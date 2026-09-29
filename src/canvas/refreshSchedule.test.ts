import { describe, expect, it } from 'vitest';
import { REFRESH_NOTE, msUntilNextRefresh } from './refreshSchedule';

// İstanbul UTC+3 (yaz saati yok): 07:00 İstanbul = 04:00 UTC.
const at = (h: number, m: number, s = 0) => Date.UTC(2026, 8, 29, h - 3, m, s);
const min = (ms: number) => ms / 60_000;

describe('ekran verisi her gün 07:00 ve 12:00 (İstanbul) yenilenir', () => {
  it('bir sonraki yenileme, tazeleme saatini 5 ve 20 dakika geçe', () => {
    expect(min(msUntilNextRefresh(at(6, 0)))).toBe(65);      // 07:05
    expect(min(msUntilNextRefresh(at(7, 5)))).toBe(15);      // 07:20
    expect(min(msUntilNextRefresh(at(9, 0)))).toBe(185);     // 12:05
    expect(min(msUntilNextRefresh(at(12, 10)))).toBe(10);    // 12:20
  });
  it('öğleden sonra bir sonraki yenileme ertesi sabah 07:05', () => {
    expect(min(msUntilNextRefresh(at(12, 20)))).toBe(18 * 60 + 45);
    expect(min(msUntilNextRefresh(at(23, 0)))).toBe(8 * 60 + 5);
  });
  it('5 dakikalık aralık yok', () => {
    expect(msUntilNextRefresh(at(8, 0))).toBeGreaterThan(5 * 60_000);
  });
  it('ekrandaki not saatleri yazar', () => {
    expect(REFRESH_NOTE).toBe("Her gün 07:00 ve 12:00'de yenilenir");
  });
});
