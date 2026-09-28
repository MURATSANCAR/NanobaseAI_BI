import { describe, expect, it } from 'vitest';
import { change, fmtDay, fmtMinutes, guessQuery, qs } from './api';

describe('müşteri bağlamı araması', () => {
  it('tek kutudan yazılanın türünü anlar', () => {
    expect(guessQuery('okur@example.com')).toEqual({ email: 'okur@example.com' });
    expect(guessQuery('0532 111 22 33')).toEqual({ phone: '0532 111 22 33' });
    expect(guessQuery('+90 (532) 111-22-33')).toEqual({ phone: '+90 (532) 111-22-33' });
    expect(guessQuery('120.01.005')).toEqual({ code: '120.01.005' });
    expect(guessQuery('TS-240915')).toEqual({ order: 'TS-240915' });
    expect(guessQuery('  ')).toBeNull();
  });
});

describe('biçim', () => {
  it('süre, tarih ve değişim', () => {
    expect(fmtMinutes(45)).toBe('45 dk');
    expect(fmtMinutes(180)).toBe('3 sa');
    expect(fmtMinutes(null)).toBe('—');
    expect(fmtDay('2026-08-17')).toBe('17.08.2026');
    expect(change(15, 10)).toBeCloseTo(0.5);
    expect(change(3, 0)).toBeNull();
    expect(qs({ a: 'x', b: '', c: undefined, d: 0 })).toBe('?a=x&d=0');
  });
});
