import { describe, expect, it } from 'vitest';
import { fmtDay } from './parts';

describe('fmtDay', () => {
  it('yalnız gün olan tarihi yerel gün olarak yazar, saat eklemez', () => {
    const y = new Date().getFullYear();
    const s = fmtDay(`${y}-10-07`);
    expect(s).toContain('07');
    expect(s).not.toMatch(/\d{2}:\d{2}/);
    expect(s).not.toContain(String(y));
  });

  it('başka yılın tarihinde yılı yazar; boş değerde tire', () => {
    expect(fmtDay('2020-01-31')).toContain('2020');
    expect(fmtDay(null)).toBe('—');
  });
});
