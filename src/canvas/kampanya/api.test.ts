import { describe, expect, it } from 'vitest';
import { isoPlus, parseMoney, pctToRatio, qs, span, worst } from './api';

describe('M35 kampanya yardımcıları', () => {
  it('yüzde metni orana çevrilir; 1 ve altı oran sayılır; aralık dışı null', () => {
    expect(pctToRatio('30')).toBe(0.3);
    expect(pctToRatio('%12,5')).toBe(0.125);
    expect(pctToRatio('0,25')).toBe(0.25);
    expect(pctToRatio('')).toBeNull();
    expect(pctToRatio('120')).toBeNull();
    expect(pctToRatio('abc')).toBeNull();
  });

  it('tutar metni sayıya çevrilir; sıfır ve boş null', () => {
    expect(parseMoney('45,50')).toBe(45.5);
    expect(parseMoney('1.250,00 ₺')).toBe(1250);
    expect(parseMoney('45.5')).toBe(45.5);
    expect(parseMoney('0')).toBeNull();
    expect(parseMoney('')).toBeNull();
  });

  it('en ağır kontrol seviyesi satırın rengidir', () => {
    expect(worst([])).toBeNull();
    expect(worst([{ kod: 'a', seviye: 'bilgi', mesaj: '' }])).toBe('bilgi');
    expect(worst([{ kod: 'a', seviye: 'sari', mesaj: '' }, { kod: 'b', seviye: 'kirmizi', mesaj: '' }])).toBe('kirmizi');
  });

  it('takvim şeridi aralığı pencereye kırpılır; dışarıdaki null', () => {
    expect(span('2026-10-01', '2026-10-10', '2026-10-01', '2026-10-10')).toEqual([0, 100]);
    const [l, w] = span('2026-10-01', '2026-10-10', '2026-09-20', '2026-10-05')!;
    expect(l).toBe(0);
    expect(w).toBeCloseTo(50);
    expect(span('2026-10-01', '2026-10-10', '2026-11-01', '2026-11-02')).toBeNull();
  });

  it('gün ekleme ve boş süzgeç', () => {
    expect(isoPlus(1, new Date(2026, 11, 31))).toBe('2027-01-01');
    expect(qs({ q: '', durum: 'taslak', page: 0, kanal: null })).toBe('?durum=taslak&page=0');
  });
});
