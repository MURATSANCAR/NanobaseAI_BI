import { describe, expect, it } from 'vitest';
import { GIFT_NEXT, STAGE_FLOW, fmtMonth, fmtMoney, parseAmount, qs, shiftMonth } from './api';

describe('kurumsal ilişkiler biçimleri', () => {
  it('ay adı ve ay kaydırma yıl sınırını geçer', () => {
    expect(fmtMonth('2026-09')).toBe('Eylül 2026');
    expect(shiftMonth('2026-12', 1)).toBe('2027-01');
    expect(shiftMonth('2026-01', -1)).toBe('2025-12');
  });

  it('Türkçe tutar yazımı', () => {
    expect(parseAmount('125.000,50')).toBe(125000.5);
    expect(parseAmount('150000')).toBe(150000);
    expect(parseAmount('  ')).toBeNull();
    expect(parseAmount('abc')).toBeNull();
    expect(fmtMoney(null)).toBe('—');
  });

  it('sorgu parçası boş değerleri atar', () => {
    expect(qs({ q: '', scope: 'zamani', archived: false, page: 0 })).toBe('?scope=zamani&page=0');
    expect(qs({})).toBe('');
  });

  it('hediye durum geçişleri sunucudakiyle aynı; aşama akışı rapor ile biter', () => {
    expect(GIFT_NEXT.oneri).toEqual(['iptal']);
    expect(GIFT_NEXT.onayli).toContain('sevk');
    expect(GIFT_NEXT.donus).toEqual([]);
    expect(STAGE_FLOW[0]).toBe('fikir');
    expect(STAGE_FLOW[STAGE_FLOW.length - 1]).toBe('rapor');
  });
});
