import { describe, expect, it } from 'vitest';
import { amount, share, signed } from './api';

describe('«Neden?» biçimleri', () => {
  it('tutar birimiyle, birim yoksa yalnız sayı; boş değer tire', () => {
    expect(amount(1234567.4, '₺')).toBe('1.234.567 ₺');
    expect(amount(12, 'adet')).toBe('12 adet');
    expect(amount(12, '')).toBe('12');
    expect(amount(null, '₺')).toBe('—');
  });

  it('fark işaretli (eksi işareti tipografik), pay mutlak yüzde', () => {
    expect(signed(40, '₺')).toBe('+40 ₺');
    expect(signed(-50, '₺')).toBe('−50 ₺');
    expect(signed(0, '')).toBe('0');
    expect(share(0.1234)).toBe('%12,3');
    expect(share(-0.5)).toBe('%50');
    expect(share(null)).toBe('—');
  });
});
