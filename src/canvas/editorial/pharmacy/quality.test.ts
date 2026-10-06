import { describe, expect, it } from 'vitest';
import { QUALITY_FILTERS, pagesText, qualityPill } from './labels';

describe('okuma kalitesi rozeti', () => {
  it('durumu ekran diliyle verir', () => {
    expect(qualityPill(null)).toBeNull();
    expect(qualityPill({ status: 'CLEAN', label: 'Temiz', open: 0 })).toEqual({ tone: 'ok', text: 'Temiz' });
    expect(qualityPill({ status: 'FIXED', label: 'Düzeltildi', open: 0 })).toEqual({ tone: 'ok', text: 'Düzeltildi' });
    expect(qualityPill({ status: 'REVIEW', label: 'Gözden geçir', open: 3 })).toEqual({ tone: 'warn', text: 'Gözden geçir · 3' });
    expect(qualityPill({ status: 'REREAD', label: 'Yeniden okunacak', open: 1 })?.text).toBe('Yeniden okunacak');
  });

  it('süzgeçler üç durum', () => {
    expect(QUALITY_FILTERS.map((f) => f.key)).toEqual(['temiz', 'duzeltildi', 'gozden']);
  });

  it('sayfaları kısaltır', () => {
    expect(pagesText(null)).toBeNull();
    expect(pagesText([4, 7])).toBe('s. 4, 7');
    expect(pagesText([1, 2, 3, 4, 5, 6, 7, 8])).toBe('s. 1, 2, 3, 4, 5, 6 … (+2)');
  });
});
