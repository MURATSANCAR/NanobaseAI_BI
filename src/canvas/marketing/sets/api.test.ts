import { describe, expect, it } from 'vitest';
import { addItem, canEditSet, pctToRatio, qs } from './api';

describe('M53 set yardımcıları', () => {
  it('aynı kitap eklenince adet artar, yeni kitap sona eklenir', () => {
    const a = addItem([], 'K1');
    expect(a).toEqual([{ stok: 'K1', adet: 1 }]);
    expect(addItem(a, 'K1', 2)).toEqual([{ stok: 'K1', adet: 3 }]);
    expect(addItem(a, 'K2')).toEqual([{ stok: 'K1', adet: 1 }, { stok: 'K2', adet: 1 }]);
  });

  it('yüzde metni orana çevrilir; aralık dışı ve boş null', () => {
    expect(pctToRatio('20')).toBe(0.2);
    expect(pctToRatio('%12,5')).toBe(0.125);
    expect(pctToRatio('')).toBeNull();
    expect(pctToRatio('120')).toBeNull();
    expect(pctToRatio('abc')).toBeNull();
  });

  it('yalnız öneri ve taslak düzenlenir', () => {
    expect(canEditSet('taslak')).toBe(true);
    expect(canEditSet('oneri')).toBe(true);
    expect(canEditSet('onayda')).toBe(false);
    expect(canEditSet('satista')).toBe(false);
  });

  it('boş süzgeç sorguya girmez', () => {
    expect(qs({ q: '', durum: 'satista', page: 0, yas: null })).toBe('?durum=satista&page=0');
  });
});
