import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { FOLDED_ROWS, dayLabel, printLabel, shouldShow, visibleRows } from './newPrints';

const item = (i: number) => ({ cardId: `c${i}`, bookId: null, title: `Kitap ${i}`, printNo: 1, firstPrint: true, day: '2026-09-25', depot: null });

describe('Kampüs «Matbaadan yeni çıkanlar»', () => {
  it('baskı etiketi ve gün', () => {
    expect(printLabel({ firstPrint: true, printNo: 1 })).toBe('İlk baskı');
    expect(printLabel({ firstPrint: false, printNo: 3 })).toBe('3. baskı');
    expect(printLabel({ firstPrint: false, printNo: null })).toBe('Baskı tekrarı');
    expect(dayLabel('2026-09-25')).toMatch(/^25 Eyl/);
    expect(dayLabel('bozuk')).toBe('bozuk');
  });

  it('veri yoksa bölüm gizli; tavan yok, kalanlar açılır', () => {
    expect(shouldShow(undefined, false)).toBe(false);
    expect(shouldShow({ items: [item(1)], days: 30, ready: false, asOf: null }, false)).toBe(false);
    expect(shouldShow({ items: [], days: 30, ready: true, asOf: null }, false)).toBe(false);
    expect(shouldShow({ items: [item(1)], days: 30, ready: true, asOf: null }, true)).toBe(false);
    expect(shouldShow({ items: [item(1)], days: 30, ready: true, asOf: null }, false)).toBe(true);
    const many = Array.from({ length: FOLDED_ROWS + 4 }, (_, i) => item(i));
    expect(visibleRows(many, false)).toHaveLength(FOLDED_ROWS);
    expect(visibleRows(many, true)).toHaveLength(FOLDED_ROWS + 4);
  });

  it('Kampüs sayfasında sabit örnek kitap kalmadı', () => {
    const src = readFileSync(new URL('./KampusPage.tsx', import.meta.url), 'utf-8');
    expect(src).not.toMatch(/book[12]Img|Gecenin Sessiz Yankısı|İpek Yolunun Muhafızları|6 Yeni Baskı/);
    expect(src).toContain('<NewPrintsCard');
  });
});

describe('Modelsiz özellikler «Zeki AI» adını taşımaz', () => {
  // Kural/veri hesabıyla çalışan düğme ve başlıklar (2026-09-28 AI fırsatları, hemen-düzelt 3). Gerçek model ya da
  // tahmin motoru çıktısı (ör. bütçedeki «ZEKİ AI satış tahmini») bu listede değildir.
  const files: Array<[string, RegExp]> = [
    ['../categories/TreeEditor.tsx', /Zeki AI önerisi \(veriden\)|Zeki AI veriden/],
    ['../budget/BudgetScreen.tsx', /ZEKİ AI önerisi/],
    ['../budget/GenerateSheet.tsx', /ZEKİ AI bütçe önerisi/],
    ['../budget/TargetsTab.tsx', /'ZEKİ AI önerisi'/],
    ['../budget/parts.tsx', /ZEKİ AI üç senaryoyla/],
    ['../first-print/BacktestTab.tsx', /ZEKİ AI emsal/],
    ['../events/FairBooks.tsx', /Zeki AI önerisi/],
  ];
  it.each(files)('%s', (path, bad) => {
    const src = readFileSync(new URL(path, import.meta.url), 'utf-8');
    expect(src).not.toMatch(bad);
  });
});
