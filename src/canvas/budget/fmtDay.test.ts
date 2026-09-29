import { describe, expect, it } from 'vitest';
import { fmtDay } from './api';

describe('fmtDay (bütçe/ortak)', () => {
  it('gün biçimi', () => expect(fmtDay('2026-09-25')).toBe('25 Eylül 2026'));
  it('ay biçimi çökmez, ay adıyla yazılır', () => expect(fmtDay('2026-08')).toBe('Ağustos 2026'));
  it('boş ve çözülemeyen değer', () => {
    expect(fmtDay(null)).toBe('—');
    expect(fmtDay('bilinmiyor')).toBe('bilinmiyor');
    expect(fmtDay('2026-13-01')).toBe('2026-13-01');
  });
});
