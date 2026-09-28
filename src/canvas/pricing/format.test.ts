import { describe, expect, it } from 'vitest';
import { editNum, editPct, mn, parseNum, parsePct, pct, tl2 } from './api';
import { parseQtys } from './parts';

describe('fiyatlama sayı girişi', () => {
  it('Türkçe yazımı okur, boşu null sayar', () => {
    expect(parseNum('1.250,50')).toBe(1250.5);
    expect(parseNum('4.000')).toBe(4000);
    expect(parseNum('12,5 ₺')).toBe(12.5);
    expect(parseNum('')).toBeNull();
    expect(parseNum('abc')).toBeNull();
    expect(parseNum(editNum(1250.5))).toBe(1250.5);
  });
  it('yüzde kutusu oranla gidip gelir', () => {
    expect(editPct(0.155)).toBe('15,5');
    expect(parsePct('15,5')).toBeCloseTo(0.155);
    expect(parsePct('%10')).toBeCloseTo(0.1);
    expect(parsePct('')).toBeNull();
  });
  it('baskı adedi listesi sıralı ve tekil', () => {
    expect(parseQtys('3000, 1000; 2.000 1000 x')).toEqual([1000, 2000, 3000]);
    expect(parseQtys('')).toEqual([]);
  });
  it('biçimler', () => {
    expect(pct(0.1534)).toBe('%15,3');
    expect(pct(null)).toBe('—');
    expect(tl2(5.399)).toBe('5,40 ₺');
    expect(mn(12_345_678)).toBe('12,3 Mn ₺');
  });
});
