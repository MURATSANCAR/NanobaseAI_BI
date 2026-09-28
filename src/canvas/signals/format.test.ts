import { describe, expect, it } from 'vitest';
import { activeLabels, claimKey, shouldAskModel, todayText, topicHow, urgentCount } from './format';
import type { TodayItem } from './api';

const item = (oncelik: 1 | 2 | 3): TodayItem => ({ kaynak: 'x', baslik: 'b', sayi: 1, link: '/', oncelik, oncelikAdi: '', detay: null });

describe('okur sesi, not sinyali ve Bugün yardımcıları', () => {
  it('iade anahtarı köprüdekiyle aynı biçimde', () => {
    expect(claimKey('T1', '978000')).toBe('T1:978000');
  });

  it('«Zeki AI» yalnız modelin seçtiği etikette', () => {
    expect(topicHow({ yontem: 'zeki' })).toBe('Zeki AI');
    expect(topicHow({ yontem: 'emin-degil' })).toBe('Zeki AI emin değil');
    expect(topicHow({ yontem: 'kural' })).toBe('kurala göre');
    expect(topicHow({ yontem: 'iade-nedeni' })).toBe('kurala göre');
  });

  it('sıfır ve «yok» etiketi gösterilmez', () => {
    expect(activeLabels({ tahsilat: 2, sikayet: 0, siparis: 1, iade: 0, kapanis: 0, yok: 5 })).toEqual(['tahsilat', 'siparis']);
  });

  it('Bugün: acil sayısı, özet seçimi ve model isteği', () => {
    expect(urgentCount([item(1), item(2), item(1)])).toBe(2);
    expect(urgentCount(undefined)).toBe(0);
    const base = { kuralOzeti: 'Kural.', modelVar: true, items: [item(1)] };
    expect(todayText({ ...base, ozet: null })).toEqual({ text: 'Kural.', byModel: false });
    expect(todayText({ ...base, ozet: { metin: 'Model.', dusen: 0, zaman: '', guncel: true } })).toEqual({ text: 'Model.', byModel: true });
    expect(todayText({ ...base, ozet: { metin: 'Eski.', dusen: 0, zaman: '', guncel: false } }).byModel).toBe(false);
    expect(shouldAskModel({ ...base, ozet: null })).toBe(true);
    expect(shouldAskModel({ ...base, ozet: { metin: 'M', dusen: 0, zaman: '', guncel: true } })).toBe(false);
    expect(shouldAskModel({ ...base, modelVar: false, ozet: null })).toBe(false);
    expect(shouldAskModel({ ...base, items: [], ozet: null })).toBe(false);
  });
});
