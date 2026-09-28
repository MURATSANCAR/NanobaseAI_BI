import { send } from '../engine';

/** Fark ayrıştırma («Neden?») ve «ne değişti» uçları. Rakamlar köprüdeki SQL'den gelir; ekran hesaplamaz. */

export type Compare = 'gecen-yil' | 'onceki-donem';

export type ReasonItem = {
  anahtar: string;
  ad: string;
  simdi: number;
  onceki: number;
  fark: number;
  yon: 'artis' | 'azalis';
  /** Kalemin farkı / net fark (karşı yönlü kalemler varsa %100'ü aşabilir). */
  pay: number | null;
  /** |fark| / Σ|fark| — çubuğun genişliği. */
  payMutlak: number | null;
  yeni: boolean;
  kayip: boolean;
};

export type ReasonDim = {
  id: string;
  ad: string;
  /** Boyutun karşılaştırma tabanı başka ise (bütçe sapmasında «geçen yılın aynı aylarına göre»). */
  karsi?: string;
  simdi: number;
  onceki: number;
  fark: number;
  oran: number | null;
  kalemler: ReasonItem[];
  kalemSayisi: number;
};

export type Narrative = { metin: string; kaynak: 'zeki' | 'kural'; neden: string | null };

export type ReasonOk = {
  ok: true;
  olcu: { ad: string; birim: string };
  donem: { etiket: string; bas?: string; bit?: string };
  karsi: { tur: string; ad: string; etiket: string };
  kirpildi: boolean;
  veriSonu?: string | null;
  toplam: { simdi: number; onceki: number; fark: number; oran: number | null };
  boyutlar: ReasonDim[];
  notlar?: string[];
  anlatim?: Narrative;
  /** Çalıştırılan tam SQL'ler (sorgu bilgisi). */
  kaynak?: { sql?: Array<{ ad: string; sql: string }>; tablolar?: string[] };
};

export type Reason = ReasonOk | { ok: false; neden: string };

export type ChangeNote = { maddeler: string[]; kaynak: 'zeki' | 'kural'; neden: string | null };

/** Kartın saklanan farkı (kodla bulunmuş). */
export type CardChange = ChangeNote & {
  ilk?: boolean;
  degisti?: boolean;
  zaman?: string;
  degisenSatir?: number;
  anlatildi?: boolean;
};

const enc = encodeURIComponent;

export const reasonApi = {
  /** Sohbet cevabı (`queryId`) ya da pano kartı / uyarı sorusu (`question`). */
  forAnswer: (b: { queryId?: string; question?: string; karsi: Compare }) =>
    send<Reason>('POST', '/api/v1/fark/ayristir', b, 300_000),
  budget: (id: string) => send<Reason>('POST', `/api/v1/budget/deviations/${enc(id)}/neden`, {}, 180_000),
  finance: (id: string) => send<Reason>('POST', `/api/v1/finance/budget/deviations/${enc(id)}/neden`, {}, 180_000),
  cardChange: (id: string) => send<ChangeNote>('POST', `/api/v1/board/cards/${enc(id)}/change-note`, {}, 120_000),
};

/** «1.234 ₺» / «1.234 adet»: birim yoksa yalnız sayı. */
export function amount(v: number | null | undefined, unit: string): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const s = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 }).format(Math.round(v));
  return unit ? `${s} ${unit}` : s;
}

export function signed(v: number, unit: string): string {
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${amount(Math.abs(v), unit)}`;
}

export function share(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return `%${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(Math.abs(v) * 100)}`;
}
