import { describe, expect, it } from 'vitest';
import { cellShade, fmtChange, fmtRatio, paramText, qs } from './api';

describe('e-ticaret müşteri biçimleri', () => {
  it('değişim ve oran Türkçe biçimde; payda yoksa tire', () => {
    expect(fmtChange(0.042)).toBe('+%4,2');
    expect(fmtChange(-0.03)).toBe('−%3,0');
    expect(fmtChange(null)).toBe('—');
    expect(fmtRatio(0.125)).toBe('%12,5');
    expect(fmtRatio(0.5, 0)).toBe('%50');
    expect(fmtRatio(undefined)).toBe('—');
  });

  it('matris yoğunluğu en kalabalık hücreye göre; boş hücre renksiz', () => {
    expect(cellShade(0, 10)).toBe(0);
    expect(cellShade(10, 10)).toBe(1);
    expect(cellShade(1, 1000)).toBe(0.08);
    expect(cellShade(5, 0)).toBe(0);
  });

  it('tetik parametre metni ve sorgu parçası', () => {
    expect(paramText('geri-kazanim', { minGun: 90, maxGun: 365, minSiparis: 1 })).toBe('Son sipariş 90–365 gün önce · en az 1 sipariş');
    expect(paramText('yeni-kitap', { barkod: '9786050000011', duzey: 'alt', minAdet: 2 })).toBe('Barkod 9786050000011 · alt kategori · en az 2 kitap');
    expect(qs({ segment: '', page: 0, sort: 'son', kisisel: false })).toBe('?page=0&sort=son');
  });
});
