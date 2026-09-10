/** Türkçe biçimlendirme yardımcıları — kanvas rakamları hep tabular basar. */

const nf = (d: number) => new Intl.NumberFormat('tr-TR', { minimumFractionDigits: d, maximumFractionDigits: d });

export const num = (v: number | null | undefined, d = 0) => (v == null || !Number.isFinite(v) ? '—' : nf(d).format(v));

export const pct = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `%${nf(d).format(v)}`);

export function money(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1e9) return `${nf(2).format(v / 1e9)} Mr`;
  if (a >= 1e6) return `${nf(1).format(v / 1e6)} Mn`;
  if (a >= 1e3) return nf(0).format(v);
  return nf(0).format(v);
}

/** ISO damgasını "11.09.2026 09:00" biçimine çevirir; saat yoksa yalnız tarih. */
export function dateTime(iso: string | undefined | null): string {
  if (!iso) return '—';
  const s = iso.slice(0, 19).replace('T', ' ');
  const [d, tm] = s.split(' ');
  const parts = d?.split('-');
  if (!parts || parts.length !== 3) return s;
  const day = `${parts[2]}.${parts[1]}.${parts[0]}`;
  return tm ? `${day} ${tm.slice(0, 5)}` : day;
}

/** "3 saat sonra" / "2 gün önce" gibi göreli ifade. */
export function relative(iso: string | undefined | null, now = Date.now()): string {
  if (!iso) return '—';
  const t = Date.parse(iso.length <= 19 && !iso.endsWith('Z') ? `${iso}Z` : iso);
  if (!Number.isFinite(t)) return '—';
  const diff = t - now;
  const abs = Math.abs(diff);
  const min = Math.round(abs / 60_000);
  const hour = Math.round(abs / 3_600_000);
  const day = Math.round(abs / 86_400_000);
  const body = min < 60 ? `${min} dk` : hour < 48 ? `${hour} saat` : `${day} gün`;
  return diff >= 0 ? `${body} sonra` : `${body} önce`;
}

export const recurrenceLabel = (r: string | undefined): string =>
  r === 'daily' ? 'Her gün' : r === 'weekly' ? 'Her hafta' : 'Tek seferlik';

export const conditionLabel = (c: string | undefined): string =>
  ({ lt: '<', lte: '≤', gt: '>', gte: '≥', eq: '=', neq: '≠' })[(c || 'gt') as string] ?? '>';

export const scheduleStatus = (s: string | undefined): { label: string; tone: 'ok' | 'warn' | 'fail' | 'muted' } => {
  const v = (s || '').toLowerCase();
  if (v === 'pending') return { label: 'Etkin', tone: 'ok' };
  if (v === 'paused') return { label: 'Duraklatıldı', tone: 'warn' };
  if (v === 'failed') return { label: 'Başarısız', tone: 'fail' };
  if (v === 'sent' || v === 'completed') return { label: 'Gönderildi', tone: 'muted' };
  return { label: s || '—', tone: 'muted' };
};
