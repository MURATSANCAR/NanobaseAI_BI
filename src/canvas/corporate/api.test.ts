import { describe, expect, it } from 'vitest';
import { daysUntil, dueText, fmtMonth, fmtPct, fmtShort, growth, marginText, parseNum, toItems } from './api';

describe('kurumsal satış biçimleri', () => {
  it('yüzde, kısa tutar ve ay adı', () => {
    expect(fmtPct(0.3)).toBe('%30');
    expect(fmtPct(0.305)).toBe('%30,5');
    expect(fmtPct(null)).toBe('—');
    expect(fmtShort(848_110_178)).toBe('848,1 Mn ₺');
    expect(fmtMonth('2026-12')).toBe('Aralık 2026');
  });

  it('Türkçe sayı yazımı ve büyüme', () => {
    expect(parseNum('1.250,5')).toBe(1250.5);
    expect(parseNum('')).toBeNull();
    expect(growth(120, 100)).toBeCloseTo(0.2);
    expect(growth(10, 0)).toBeNull();
  });

  it('karar tarihine kalan gün', () => {
    const now = new Date(2026, 8, 28);
    expect(daysUntil('2026-10-01', now)).toBe(3);
    expect(dueText('2026-09-28', now)).toBe('bugün');
    expect(dueText('2026-09-25', now)).toBe('3 gün geçti');
    expect(dueText(null, now)).toBeNull();
  });

  it('marj bilinmiyorsa uydurulmaz, kısmi maliyet kapsamı yazılır', () => {
    expect(marginText({ marj: null, maliyetKapsami: 0 })).toBe('Maliyet bilinmiyor');
    expect(marginText({ marj: 0.25, maliyetKapsami: 1 })).toBe('%25');
    expect(marginText({ marj: 0.25, maliyetKapsami: 0.5 })).toContain('%50');
  });

  it('teklif satırı sunucuya yüzde indirimle, elle fiyat yalnız elle girildiyse gider', () => {
    expect(
      toItems([
        { stok: 'A', adet: 3, indirim: 0.305, fiyatKaynak: 'logo', listeFiyati: 100 },
        { stok: 'B', adet: 1, indirim: 0, fiyatKaynak: 'elle', listeFiyati: 75 },
      ]),
    ).toEqual([
      { stok: 'A', adet: 3, indirim: 30.5 },
      { stok: 'B', adet: 1, indirim: 0, listeFiyati: 75 },
    ]);
  });
});
