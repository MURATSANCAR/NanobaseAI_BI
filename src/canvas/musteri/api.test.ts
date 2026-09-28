import { describe, expect, it } from 'vitest';
import { barHeights, fmtChange, fmtMonth, levelTone, qs } from './api';

describe('müşteri ilişkileri biçimleri', () => {
  it('değişim işaretli yüzde', () => {
    expect(fmtChange(0.12)).toBe('+%12');
    expect(fmtChange(-0.345)).toBe('−%35');
    expect(fmtChange(0)).toBe('%0');
    expect(fmtChange(null)).toBe('—');
  });

  it('risk düzeyinin tonu', () => {
    expect(levelTone('kayip')).toBe('err');
    expect(levelTone('yuksek')).toBe('err');
    expect(levelTone('orta')).toBe('warn');
    expect(levelTone('dusuk')).toBe('muted');
    expect(levelTone(null)).toBe('muted');
  });

  it('aylık çubuk yüksekliği; negatif ay sıfır', () => {
    expect(barHeights([50, 100, -20, 0])).toEqual([0.5, 1, 0, 0]);
    expect(barHeights([])).toEqual([]);
    expect(barHeights([-5])).toEqual([0]);
  });

  it('ay adı kısa', () => {
    expect(fmtMonth('2026-08')).toBe('Ağu 26');
    expect(fmtMonth('2025-01')).toBe('Oca 25');
  });

  it('boş süzgeç adrese girmez', () => {
    expect(qs({ kanal: 'KITAPCI', bolge: '', p: 2, q: undefined })).toBe('?kanal=KITAPCI&p=2');
    expect(qs({})).toBe('');
  });
});
