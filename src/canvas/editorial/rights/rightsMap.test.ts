import { describe, expect, it } from 'vitest';
import type { MapFields } from '../royalty/api';
import { dropItem, isEmptyMap, mapSummary, usesModel } from './rightsMapText';

const F: MapFields = {
  format: [{ deger: 'e-kitap', ad: 'E-kitap', alinti: 'e-kitap olarak', kaynak: 'kural' }],
  dil: [{ deger: 'Türkçe', alinti: 'Türkçe dilinde', kaynak: 'kural' }],
  ulke: [{ deger: 'Almanya', alinti: 'Almanya için', kaynak: 'zeki' }],
  bitis: { deger: '2030-12-31', tarih: '2030-12-31', alinti: '31.12.2030 tarihine kadar', kaynak: 'kural' },
  munhasirlik: { deger: 'munhasir-degil', ad: 'Münhasır değil', alinti: 'münhasır değildir', kaynak: 'kural' },
};

describe('hak haritası metni', () => {
  it('özet sırası format → dil → ülke → bitiş → münhasırlık, adlar ve yerel tarih', () => {
    expect(mapSummary(F)).toBe('E-kitap · Türkçe · Almanya · 31.12.2030 · Münhasır değil');
  });

  it('boş harita ve model kullanımı', () => {
    expect(isEmptyMap({ format: [], dil: [], ulke: [], bitis: null, munhasirlik: null })).toBe(true);
    expect(usesModel(F)).toBe(true);
    expect(usesModel(dropItem(F, 'ulke', 0))).toBe(false);
  });

  it('değer çıkarma: liste alanında öğe, tek değerli alanda alan boşalır', () => {
    expect(dropItem(F, 'dil', 0).dil).toEqual([]);
    expect(dropItem(F, 'bitis', 0).bitis).toBeNull();
    expect(F.dil).toHaveLength(1);
  });
});
