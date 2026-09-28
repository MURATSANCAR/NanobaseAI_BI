import { describe, expect, it } from 'vitest';
import { donemLabel, fmtGrowth, fmtPct, lastMonth, qs } from './api';
import { permissionItemFor } from '../nav/navModel';

describe('pazar biçimleri', () => {
  it('geçen ay ve dönem adı', () => {
    expect(lastMonth(new Date(2026, 0, 15))).toBe('2025-12');
    expect(lastMonth(new Date(2026, 8, 28))).toBe('2026-08');
    expect(donemLabel('2026-08')).toBe('Ağustos 2026');
    expect(donemLabel('2026-13')).toBe('2026-13');
  });

  it('büyüme ve pay', () => {
    expect(fmtGrowth(0.3)).toBe('+%30');
    expect(fmtGrowth(-0.125)).toBe('−%12,5');
    expect(fmtGrowth(null)).toBe('—');
    expect(fmtPct(0.5, 0)).toBe('%50');
  });

  it('sorgu: boş ve yanlış değerler gönderilmez', () => {
    expect(qs({ kategori: '', oneri: false, izlenen: true, sayfaMin: 200 })).toBe('?izlenen=true&sayfaMin=200');
    expect(qs({})).toBe('');
  });

  it('alt ekranlar kendi menü sayfasının yetkisiyle açılır', () => {
    expect(permissionItemFor('/pazar-arastirma')?.id).toBe('pazar-arastirma');
    expect(permissionItemFor('/pazar-arastirma/ozet/2026-08')?.id).toBe('pazar-arastirma');
    expect(permissionItemFor('/pazar-arastirma/rakipler')?.id).toBe('pazar-rakipler');
    expect(permissionItemFor('/pazar-arastirma/emsal')?.id).toBe('pazar-rakipler');
    expect(permissionItemFor('/pazar-arastirma/kategori-esleme')?.id).toBe('pazar-rakipler');
    expect(permissionItemFor('/pazar-arastirma/raporlar/abc')?.id).toBe('pazar-raporlar');
  });
});
