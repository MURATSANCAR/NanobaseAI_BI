import { describe, expect, it } from 'vitest';
import { dayName, monthName, pct, signedPct, stockoutText, trackTone } from './api';

describe('ilk baskı biçimleri', () => {
  it('ay ve gün adları Türkçe, boşta tire', () => {
    expect(monthName('2026-10')).toBe('Ekim 2026');
    expect(monthName('2027-01-15')).toBe('Ocak 2027');
    expect(monthName(null)).toBe('—');
    expect(dayName('2026-08-17')).toBe('17 Ağustos 2026');
  });

  it('yüzde ve işaretli yüzde', () => {
    expect(pct(0.482)).toBe('%48');
    expect(pct(null)).toBe('—');
    expect(signedPct(0.124)).toBe('+%12');
    expect(signedPct(-0.08)).toBe('−%8');
  });

  it('tükenme cümlesi olasılığı söyler, yoksa hesaplanamadı der', () => {
    expect(stockoutText(0.25)).toContain('%25');
    expect(stockoutText(null)).toContain('hesaplanamadı');
  });

  it('takip tonu: kötümserin altı kırmızı, bazın altı sarı', () => {
    expect(trackTone({ alert: true, deviation: -0.6 })).toBe('err');
    expect(trackTone({ alert: false, deviation: -0.1 })).toBe('warn');
    expect(trackTone({ alert: false, deviation: 0.2 })).toBe('ok');
    expect(trackTone({ alert: false, deviation: null })).toBe('ok');
  });
});
