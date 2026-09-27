import { describe, expect, it } from 'vitest';
import { daysAgo, fmtAge, fmtShort, parseTr, scoreTone } from './api';

describe('saha biçimleri', () => {
  it('kısa tutar telefon kartına sığar', () => {
    expect(fmtShort(42_350)).toBe('42 bin ₺');
    expect(fmtShort(1_260_000)).toBe('1,3 Mn ₺');
    expect(fmtShort(850)).toBe('850 ₺');
    expect(fmtShort(null)).toBe('—');
  });

  it('onay bekleme yaşı saat, sonra gün', () => {
    expect(fmtAge(5.2)).toBe('5 sa');
    expect(fmtAge(0.2)).toBe('1 sa');
    expect(fmtAge(73)).toBe('3 gün');
    expect(fmtAge(null)).toBe('—');
  });

  it('puan tonu: 60+ acil, 30+ öncelikli', () => {
    expect(scoreTone(75)).toBe('err');
    expect(scoreTone(30)).toBe('warn');
    expect(scoreTone(12)).toBe('muted');
    expect(scoreTone(null)).toBe('muted');
  });

  it('Türkçe sayı girişi', () => {
    expect(parseTr('20.000,50')).toBe(20000.5);
    expect(parseTr(' ')).toBeNull();
    expect(Number.isNaN(parseTr('yirmi') as number)).toBe(true);
  });

  it('kaç gün önce (gün farkı, saat yok sayılır)', () => {
    expect(daysAgo('2026-07-19', '2026-09-28')).toBe(71);
    expect(daysAgo('2026-09-28T14:05', '2026-09-28')).toBe(0);
    expect(daysAgo(null, '2026-09-28')).toBeNull();
  });
});
