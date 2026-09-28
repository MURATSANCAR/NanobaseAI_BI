import { describe, expect, it } from 'vitest';
import { BOARD, STATE_TONE, daysLeft, fmtDay } from './api';

describe('M19 talep yardımcıları', () => {
  it('termine kalan gün İstanbul gününe göre (bugün 0, geçmiş eksi, termin yoksa null)', () => {
    const now = new Date('2026-09-28T22:30:00+03:00');
    expect(daysLeft('2026-09-28', now)).toBe(0);
    expect(daysLeft('2026-09-30', now)).toBe(2);
    expect(daysLeft('2026-09-25', now)).toBe(-3);
    expect(daysLeft(null, now)).toBeNull();
  });

  it('gün biçimi ve pano sütunları', () => {
    expect(fmtDay(null)).toBe('—');
    expect(fmtDay('2026-11-24')).toMatch(/24/);
    expect(BOARD).toEqual(['talep', 'uretimde', 'tasarim-onayi', 'mesaj-onayi', 'onayli']);
    expect(Object.keys(STATE_TONE)).toHaveLength(7);
  });
});
