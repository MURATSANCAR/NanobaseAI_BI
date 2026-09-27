import { describe, expect, it } from 'vitest';
import { editNum, parseNum, pctText } from './shared';

describe('serbest çalışan sayı girişi', () => {
  it('Türkçe yazımı (binlik nokta, ondalık virgül) okur', () => {
    expect(parseNum('1.250,50')).toBe(1250.5);
    expect(parseNum('1250,5')).toBe(1250.5);
    expect(parseNum(' 4.000 ₺ ')).toBe(4000);
    expect(parseNum('12.500.000')).toBe(12500000);
  });
  it('virgülsüz yazımda noktayı ondalık sayar (düzenleme kutusuna gelen değer bozulmaz)', () => {
    expect(parseNum('1250.5')).toBe(1250.5);
    expect(parseNum(editNum(1250.5))).toBe(1250.5);
    expect(parseNum(12)).toBe(12);
  });
  it('boş ve bozuk girişi NaN sayar (sunucu hatayı söyler)', () => {
    expect(parseNum('')).toBeNaN();
    expect(parseNum(null)).toBeNaN();
    expect(parseNum('abc')).toBeNaN();
  });
  it('oranı yüzde yazar', () => {
    expect(pctText(0.874)).toBe('%87');
    expect(pctText(null)).toBe('—');
  });
});
