import type { NewPrints } from '../editorial/production/api';

/** Kampüs «Matbaadan yeni çıkanlar» kartının saf yardımcıları (vitest: newPrints.test.ts). */

export type NewPrint = NewPrints['items'][number];

/** Kart kapalıyken gösterilen satır sayısı. Tavan değil: kalanlar «Tümünü göster» ile açılır, sayı başlıkta yazar. */
export const FOLDED_ROWS = 6;

export function printLabel(p: Pick<NewPrint, 'firstPrint' | 'printNo'>): string {
  if (p.firstPrint) return 'İlk baskı';
  return p.printNo ? `${p.printNo}. baskı` : 'Baskı tekrarı';
}

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', timeZone: 'Europe/Istanbul' });

/** "2026-09-25" → "25 Eyl" (gün, İstanbul takvimiyle; saat yok). */
export function dayLabel(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return iso;
  return dayFmt.format(new Date(Date.UTC(y, m - 1, d, 12)));
}

/** Gösterilecek satırlar: kart kapalıyken ilk FOLDED_ROWS, açıkken hepsi. */
export function visibleRows<T>(items: T[], expanded: boolean): T[] {
  return expanded ? items : items.slice(0, FOLDED_ROWS);
}

/** Bölüm yalnız gerçek veri varsa görünür: okuma hazır değilse, hata varsa ya da pencerede baskı yoksa gizli. */
export function shouldShow(data: NewPrints | undefined, failed: boolean): data is NewPrints {
  return !failed && !!data && data.ready && data.items.length > 0;
}
