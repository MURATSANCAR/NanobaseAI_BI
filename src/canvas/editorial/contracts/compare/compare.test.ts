import { describe, expect, it } from 'vitest';
import type { ClauseRow } from './api';
import { band, clauseTitle, isDeviation, pct, periodOptions, statusTone, visibleClauses, visibleDiff } from './compare';

const row = (o: Partial<ClauseRow>): ClauseRow => ({
  key: 'k', label: 'L', kind: 'oran', value: 10, valueLabel: '%10', status: 'olagan', statusLabel: '', reason: null, n: 50, ...o,
});

describe('sözleşme karşılaştırma yardımcıları', () => {
  it('sapma durumları ve renkleri', () => {
    expect(isDeviation('yuksek') && isDeviation('eksik') && !isDeviation('olagan') && !isDeviation('emsal-az')).toBe(true);
    expect([statusTone('yuksek'), statusTone('eksik'), statusTone('olagan'), statusTone('emsal-az')]).toEqual(['err', 'warn', 'ok', 'muted']);
  });

  it('yüzde Türkçe yazılır, boşsa tire', () => {
    expect(pct(0.183)).toBe('%18,3');
    expect(pct(null)).toBe('—');
  });

  it('dağılım şeridi: değer aralık içinde ve dışında', () => {
    const b = band({ value: 10, enAz: 0, enCok: 20, p10: 2, p90: 18, medyan: 8 })!;
    expect([b.lo, b.hi, b.med, b.value, b.outside]).toEqual([0.1, 0.9, 0.4, 0.5, null]);
    const out = band({ value: 40, enAz: 0, enCok: 20, p10: 2, p90: 18, medyan: 8 })!;
    expect(out.value).toBe(1);
    expect(out.outside).toBe('ust');
    expect(band({ value: 5, enAz: null, enCok: null, p10: null, p90: null, medyan: null })).toBeNull();
    expect(band({ value: 5, enAz: 5, enCok: 5, p10: 5, p90: 5, medyan: 5 })!.value).toBe(0.5);
  });

  it('yalnız farklar süzgeci', () => {
    const rows = [row({ status: 'olagan' }), row({ status: 'yuksek' }), row({ status: 'emsal-az' })];
    expect(visibleClauses(rows, true).map((r) => r.status)).toEqual(['yuksek']);
    expect(visibleClauses(rows, false)).toHaveLength(3);
    expect(visibleDiff([{ durum: 'ayni' }, { durum: 'eklenmis' }], true)).toEqual([{ durum: 'eklenmis' }]);
  });

  it('madde başlığı', () => {
    expect(clauseTitle({ no: '5', baslik: 'Telif', metin: 'x' })).toBe('Madde 5 · Telif');
    expect(clauseTitle({ no: null, baslik: 'Giriş', metin: 'x' })).toBe('Giriş');
    expect(clauseTitle({ no: null, baslik: null, metin: 'bir iki üç dört beş altı yedi sekiz dokuz' })).toBe('bir iki üç dört beş altı yedi sekiz…');
  });

  it('dönem seçenekleri ayar değerini içerir', () => {
    expect(periodOptions(5).map((o) => o.value)).toEqual([3, 5, 10, -1]);
    expect(periodOptions(7).map((o) => o.value)).toEqual([3, 5, 7, 10, -1]);
    expect(periodOptions(-1).at(-1)?.label).toBe('Bütün yıllar');
  });
});
