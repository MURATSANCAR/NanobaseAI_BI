import type { ClauseRow, DiffRow, Status, TextStatus } from './api';

/** Sözleşme karşılaştırma ekranının saf yardımcıları (test: compare.test.ts). */

export type Tone = 'ok' | 'warn' | 'err' | 'muted' | 'violet';

export const DEVIATING: readonly Status[] = ['yuksek', 'dusuk', 'nadir', 'nadir-madde', 'eksik'];

export const isDeviation = (s: Status) => DEVIATING.includes(s);

/** Durumun rengi: yüksek/düşük ve nadir değer kırmızı-turuncu, eksik madde turuncu, karar yoksa gri. */
export function statusTone(s: Status): Tone {
  if (s === 'yuksek' || s === 'dusuk' || s === 'nadir') return 'err';
  if (s === 'nadir-madde' || s === 'eksik') return 'warn';
  if (s === 'olagan') return 'ok';
  return 'muted';
}

export function textTone(s: TextStatus): Tone {
  return s === 'ozgun' ? 'violet' : s === 'az' ? 'warn' : 'muted';
}

export const DIFF_LABEL: Record<DiffRow['durum'], string> = {
  ayni: 'Aynı',
  degismis: 'Değişmiş',
  'yeri-degismis': 'Yeri değişmiş',
  eklenmis: 'Yalnız bu belgede',
  cikarilmis: 'Yalnız karşılaştırılanda',
};
export const diffTone = (d: DiffRow['durum']): Tone =>
  d === 'ayni' ? 'ok' : d === 'degismis' ? 'err' : d === 'yeri-degismis' ? 'violet' : 'warn';

export const CORPUS_LABEL = { ayni: 'Arşivde aynısı var', benzer: 'Arşivde benzeri var', 'arsivde-yok': 'Arşivde yok' } as const;
export const corpusTone = (d: keyof typeof CORPUS_LABEL): Tone => (d === 'ayni' ? 'ok' : d === 'benzer' ? 'warn' : 'violet');

const pctFmt = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
/** 0,183 → «%18,3»; boşsa tire. */
export const pct = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? '—' : `%${pctFmt.format(v * 100)}`);

/**
 * Sayısal maddenin dağılım şeridi: emsallerin en azı–en çoğu 0–1 aralığına yerleşir; %10–%90 bandı, medyan çizgisi
 * ve bu sözleşmenin değeri. Değer aralık dışındaysa uca yapışır (`outside` işaretlenir). Dağılım yoksa null.
 */
export function band(c: Pick<ClauseRow, 'value' | 'enAz' | 'enCok' | 'p10' | 'p90' | 'medyan'>): {
  lo: number;
  hi: number;
  med: number | null;
  value: number | null;
  outside: 'alt' | 'ust' | null;
} | null {
  const min = c.enAz;
  const max = c.enCok;
  if (min == null || max == null) return null;
  const v = typeof c.value === 'number' ? c.value : null;
  const a = Math.min(min, v ?? min);
  const b = Math.max(max, v ?? max);
  const span = b - a;
  const at = (x: number | null | undefined) => (x == null ? null : span <= 0 ? 0.5 : (x - a) / span);
  return {
    lo: at(c.p10) ?? 0,
    hi: at(c.p90) ?? 1,
    med: at(c.medyan),
    value: at(v),
    outside: v == null ? null : v < min ? 'alt' : v > max ? 'ust' : null,
  };
}

/** Madde listesinde «yalnız farklar» süzgeci: sapan maddeler + değeri olan ama karar verilemeyenler hariç. */
export function visibleClauses(rows: ClauseRow[], onlyDiff: boolean): ClauseRow[] {
  return onlyDiff ? rows.filter((c) => isDeviation(c.status)) : rows;
}

/** Belge farkında «yalnız farklar»: aynı maddeler gizlenir. */
export function visibleDiff<T extends { durum: string }>(rows: T[], onlyDiff: boolean): T[] {
  return onlyDiff ? rows.filter((r) => r.durum !== 'ayni') : rows;
}

/** Madde başlığı: «Madde 5 · Telif» / «Giriş» / ilk kelimeler. */
export function clauseTitle(c: { no: string | null; baslik: string | null; metin: string } | null): string {
  if (!c) return '—';
  const head = [c.no ? `Madde ${c.no}` : null, c.baslik].filter(Boolean).join(' · ');
  if (head) return head;
  const words = c.metin.split(/\s+/).slice(0, 8).join(' ');
  return words.length < c.metin.length ? `${words}…` : words;
}

/** Emsal dönemi seçenekleri (yıl; -1 = bütün yıllar). Yönetim ayarındaki değer listede yoksa eklenir. */
export function periodOptions(current: number): Array<{ value: number; label: string }> {
  const base = [3, 5, 10, -1];
  const all = base.includes(current) ? base : [...base.slice(0, -1), current, -1].sort((x, y) => (x === -1 ? 1 : y === -1 ? -1 : x - y));
  return all.map((v) => ({ value: v, label: v < 0 ? 'Bütün yıllar' : `Son ${v} yıl` }));
}
