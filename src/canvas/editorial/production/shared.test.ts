import { describe, expect, it } from 'vitest';
import { defaultPublication, nextPoint, pointState, worstDelay } from './shared';
import type { Delay } from './api';

const card = {
  actual: { dosya: { day: '2026-09-01', source: 'crm' as const } },
  plan: { dosya: '2026-08-30', matbaa: null, baski: '2026-09-20', depo: '2026-10-05' },
  delays: [{ milestone: 'baski', label: 'Baskı çıkışı', due: '2026-09-20', days: 8, level: 'yonetici' } as Delay],
};

describe('üretim kartı dönüm noktaları', () => {
  it('gerçekleşen, geciken, planlanan ve planı olmayanı ayırır', () => {
    expect(pointState(card, 'dosya')).toBe('done');
    expect(pointState(card, 'baski')).toBe('late');
    expect(pointState(card, 'depo')).toBe('planned');
    expect(pointState(card, 'matbaa')).toBe('none');
  });
  it('sıradaki adım gerçekleşmemiş ilk adımdır', () => {
    expect(nextPoint(card)).toEqual({ key: 'matbaa', label: 'Matbaa belirlendi', due: null });
    expect(nextPoint({ actual: { dosya: card.actual.dosya, matbaa: card.actual.dosya, baski: card.actual.dosya, depo: card.actual.dosya }, plan: {} })).toBeNull();
  });
  it('en büyük gecikmeyi seçer', () => {
    const a = { ...card.delays[0], days: 2, level: 'sorumlu' as const };
    expect(worstDelay([a, card.delays[0]])?.days).toBe(8);
    expect(worstDelay([])).toBeNull();
  });
  it('varsayılan yayın tarihi iki ay sonrasının ilk günü', () => {
    expect(defaultPublication(new Date(Date.UTC(2026, 8, 28)))).toBe('2026-11-01');
    expect(defaultPublication(new Date(Date.UTC(2026, 11, 3)))).toBe('2027-02-01');
  });
});
