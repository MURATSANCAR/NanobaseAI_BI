import { describe, expect, it } from 'vitest';
import { distTotal, qs, segmentTone, thresholdsOk, weightSum, worsened } from './api';

describe('bayi riski biçimleri', () => {
  it('segment tonu: harf her zaman yazılır, renk yardımcı', () => {
    expect(segmentTone('A')).toBe('ok');
    expect(segmentTone('B')).toBe('muted');
    expect(segmentTone('C')).toBe('warn');
    expect(segmentTone('D')).toBe('err');
    expect(segmentTone(null)).toBe('muted');
  });

  it('segment düşüşü yalnız A → D yönünde', () => {
    expect(worsened('C', 'B')).toBe(true);
    expect(worsened('B', 'C')).toBe(false);
    expect(worsened('B', null)).toBe(false);
  });

  it('kural formu: ağırlık toplamı ve artan eşik', () => {
    expect(weightSum({ gecikme: 35, cek: 20, iade: 15, limit: 10, duzensizlik: 10, tahsilat_suresi: 10 })).toBe(100);
    expect(weightSum({ gecikme: Number.NaN, cek: 20 })).toBe(20);
    expect(thresholdsOk({ A: 20, B: 40, C: 60 })).toBe(true);
    expect(thresholdsOk({ A: 40, B: 40, C: 60 })).toBe(false);
    expect(thresholdsOk({ A: 20, B: 40, C: 120 })).toBe(false);
  });

  it('dağılım toplamı gruplar birlikte', () => {
    const d = { standart: { A: 1, B: 2, C: 3, D: 4 }, anahtar: { A: 1, B: 0, C: 0, D: 1 } };
    expect(distTotal(d)).toBe(12);
    expect(distTotal(d, 'D')).toBe(5);
    expect(distTotal(null)).toBe(0);
  });

  it('sorgu dizesi boş değerleri atar', () => {
    expect(qs({ segment: 'C,D', q: '', page: 1, bmt: undefined })).toBe('?segment=C%2CD&page=1');
    expect(qs({})).toBe('');
  });
});
