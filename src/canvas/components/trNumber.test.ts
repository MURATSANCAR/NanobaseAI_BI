import { describe, expect, it } from 'vitest';
import { parseTrNumber } from './trNumber';

describe('Türkçe sayı', () => {
  it('binlik noktayı ondalık sanmaz', () => {
    expect(parseTrNumber('7.500')).toBe(7500);
    expect(parseTrNumber('125.000')).toBe(125000);
    expect(parseTrNumber('1.250.000')).toBe(1250000);
    expect(parseTrNumber('-2.000')).toBe(-2000);
  });
  it('virgül ondalıktır', () => {
    expect(parseTrNumber('12.500,50')).toBe(12500.5);
    expect(parseTrNumber('7,5')).toBe(7.5);
    expect(parseTrNumber('0,25')).toBe(0.25);
  });
  it('öteki yazımlar olduğu gibi', () => {
    expect(parseTrNumber('7500')).toBe(7500);
    expect(parseTrNumber('7.5')).toBe(7.5);
    expect(parseTrNumber('12.50')).toBe(12.5);
    expect(parseTrNumber('0.125')).toBe(0.125);
    expect(parseTrNumber(' 1 500 ₺ ')).toBe(1500);
    expect(parseTrNumber('%12')).toBe(12);
    expect(parseTrNumber('3.500 TL')).toBe(3500);
  });
  it('boş ve bozuk girdi null', () => {
    expect(parseTrNumber('')).toBeNull();
    expect(parseTrNumber('  ')).toBeNull();
    expect(parseTrNumber('abc')).toBeNull();
    expect(parseTrNumber(null)).toBeNull();
  });
});
