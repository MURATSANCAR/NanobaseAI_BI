const nf0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1, minimumFractionDigits: 1 });

/** ₺ kısa gösterim: 922.418.666 → "₺922,4M" */
export function tl(n: number | null | undefined, opts: { compact?: boolean } = { compact: true }): string {
  if (n == null || Number.isNaN(n)) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '−' : '';
  if (opts.compact) {
    if (abs >= 1e9) return `${sign}₺${nf1.format(abs / 1e9)}Mr`;
    if (abs >= 1e6) return `${sign}₺${nf1.format(abs / 1e6)}M`;
    if (abs >= 1e3) return `${sign}₺${nf0.format(abs / 1e3)}B`;
  }
  return `${sign}₺${nf0.format(abs)}`;
}

export function num(n: number | null | undefined): string {
  return n == null ? '—' : nf0.format(n);
}

export function pct(ratio: number | null | undefined, digits = 1): string {
  if (ratio == null || Number.isNaN(ratio)) return '—';
  return `%${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(ratio * 100)}`;
}

export const MONTHS_TR = ['OCA', 'ŞUB', 'MAR', 'NİS', 'MAY', 'HAZ', 'TEM', 'AĞU', 'EYL', 'EKİ', 'KAS', 'ARA'];
export const MONTHS_TR_LONG = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];

/** "2026-08-17" → { year: 2026, month: 8 } (kesit tarihi yoksa null) */
export function ymOf(iso: string | null | undefined): { year: number; month: number } | null {
  if (!iso || iso.length < 7) return null;
  const y = Number(iso.slice(0, 4));
  const m = Number(iso.slice(5, 7));
  return Number.isFinite(y) && m >= 1 && m <= 12 ? { year: y, month: m } : null;
}

/** Rakamın yaşı: "şimdi", "12 sn önce", "4 dk önce". Kokpit kendi kendine yenilendiği için ekranda
 *  "canlı" yazması yetmez — okuyan, baktığı sayının ne zaman hesaplandığını görebilmeli. */
export function agoTr(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '—';
  if (sec < 5) return 'şimdi';
  if (sec < 60) return `${Math.round(sec)} sn önce`;
  if (sec < 3600) return `${Math.round(sec / 60)} dk önce`;
  if (sec < 86_400) return `${Math.round(sec / 3600)} sa önce`;
  return `${Math.round(sec / 86_400)} gün önce`;
}

export function dateTr(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.${y}`;
}
