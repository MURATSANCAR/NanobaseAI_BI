import { describe, expect, it } from 'vitest';
import { fieldHits, modelTone, sinifTone, tlSigned } from './api';

describe('pazar yeri satış modeli ve mutabakat biçimleri', () => {
  it('model rozeti: belirsiz uyarı, güçlü onay, zayıf nötr', () => {
    expect(modelTone('belirsiz', null)).toBe('warn');
    expect(modelTone('toptan', 'guclu')).toBe('ok');
    expect(modelTone('konsinye', 'zayif')).toBe('muted');
  });

  it('mutabakat sınıfı rengi', () => {
    expect(sinifTone('eslesti')).toBe('ok');
    expect(sinifTone('tutar-farki')).toBe('warn');
    expect(sinifTone('eksik-fatura')).toBe('err');
    expect(sinifTone('fazla-fatura')).toBe('err');
    expect(sinifTone('bekliyor')).toBe('violet');
    expect(sinifTone('iptal')).toBe('muted');
  });

  it('eşleşen belge alanları büyükten küçüğe, türüyle', () => {
    expect(fieldHits({ 'siparis:docode': 2, 'belge:ficheno': 5, 'siparis:genexp1': 1 })).toEqual([
      { alan: 'FICHENO', tur: 'kesinti belgesi', sayi: 5 },
      { alan: 'DOCODE', tur: 'sipariş', sayi: 2 },
      { alan: 'GENEXP1', tur: 'sipariş', sayi: 1 },
    ]);
    expect(fieldHits(null)).toEqual([]);
  });

  it('işaretli tutar', () => {
    expect(tlSigned(-57)).toBe('−57,00 ₺');
    expect(tlSigned(1234.5)).toBe('1.234,50 ₺');
    expect(tlSigned(null)).toBe('—');
  });
});
