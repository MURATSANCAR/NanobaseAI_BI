import { send } from '../../engine';
import type { Kaynaklar } from '../../components/sqlInfo';
import type { QuoteRef } from '../QuoteEvidence';

/** Öneri 12 — başvuru ön okuması: köprünün `/api/v1/editorial/applications/{id}/preread` uçları ve taslağın editör
 *  raporu formuna aktarılması (saf; vitest). Puan ve kabul/red önerisi hiçbir zaman taslaktan gelmez. */

export type Pick_ = { deger: string | null; ad?: string; olasilik?: number | null; emin: boolean; neden?: string; kanit?: QuoteRef[]; adaylar?: string[] };
export type PrereadResult = {
  alanlar: {
    tur: Pick_ | null;
    kitle: Pick_ | null;
    yas: { alt: number | null; ust: number | null; ad: string | null; neden?: string; kanit: QuoteRef[] } | null;
    konu: { deger: string; kanit: QuoteRef[]; aday: number } | null;
    ozet: { cumleler: Array<{ cumle: string; kanit: QuoteRef }>; aday: number; secim: 'hepsi' | 'zeki' | 'esit-aralik' } | null;
    temalar: Array<{ deger: string; kanit: QuoteRef[] }>;
    ilke: Array<{ kategori: string; ad: string; kanit: QuoteRef }>;
  };
  benzer: { items: Array<{ sira: number; kitapId: string; stokKodu: string | null; ad: string; yazar: string | null; kitaplik: string | null; gerekce: string[] }>; not: string | null; kaynak: string | null };
  atilan: number;
  pencere: { sayi: number; butce: number; ortusme: number; okunamayan: string[] };
  okuma: { sayfa: number; ocrSayfa: string[]; okunamayan: string[]; not: string | null };
  kaynak: 'zeki';
  dosya?: { id: string; ad: string; tur: string | null; round: number };
  taslak: Draft;
};
export type Draft = {
  topic: string | null;
  genre: string | null;
  ageGroup: string | null;
  overlapNote: string | null;
  redline: string | null;
  redlineNote: string | null;
  report: string | null;
};
export type Preread = {
  id: string;
  appId: string;
  fileId: string;
  round: number;
  filename: string;
  status: 'hazirlaniyor' | 'hazir' | 'hata';
  statusLabel: string;
  done: number;
  total: number;
  error: string | null;
  createdBy: string;
  createdAt: string;
  finishedAt: string | null;
  result: PrereadResult | null;
};
export type PrereadFile = { id: string; filename: string; kindLabel: string | null; round: number; current: boolean; readable: boolean; why: string | null };
export type PrereadResponse = { preread: Preread | null; previous?: Preread; files: PrereadFile[]; model: boolean; kaynaklar?: Kaynaklar };

const A = '/api/v1/editorial/applications';
const enc = encodeURIComponent;

export const prereadApi = {
  get: (appId: string) => send<PrereadResponse>('GET', `${A}/${enc(appId)}/preread`, undefined, 30_000),
  start: (appId: string, fileId?: string) =>
    send<{ preread: Preread; already: boolean }>('POST', `${A}/${enc(appId)}/preread`, { fileId }, 60_000),
};

// ------------------------------------------------------------------------------------------------ taslak → form (saf)

/** Taslağın dolduracağı form alanları (puan ve öneri bu listede yok). */
export const DRAFT_KEYS = ['topic', 'genre', 'ageGroup', 'overlapNote', 'redline', 'redlineNote', 'report'] as const;
export type DraftKey = (typeof DRAFT_KEYS)[number];
type Formish = Record<DraftKey, string>;

/** Uzun metin alanlarında editörün yazdığı silinmez: taslak altına eklenir. Tek satırlık alanlar değiştirilir. */
const APPEND: DraftKey[] = ['overlapNote', 'redlineNote', 'report'];

/**
 * Taslağı forma uygular. `keys` verilirse yalnız o alanlar (editör tek tek «aktar» dedi), verilmezse yalnız boş
 * alanlar doldurulur. Yayın ilkeleri seçimi editörün seçtiği bir değerin üstüne hiçbir zaman yazılmaz.
 * Dönen: yeni form ve gerçekten değişen alanlar.
 */
export function mergeDraft<F extends Formish>(form: F, d: Draft, keys?: DraftKey[]): { form: F; changed: DraftKey[] } {
  const next = { ...form };
  const changed: DraftKey[] = [];
  for (const k of keys ?? DRAFT_KEYS) {
    const v = d[k];
    if (v == null || v === '') continue;
    const cur = (next[k] ?? '').trim();
    if (k === 'redline') {
      if (cur) continue;
    } else if (!keys && cur) {
      continue;
    }
    let val = v;
    if (APPEND.includes(k) && cur) {
      if (cur.includes(v.trim())) continue;
      val = `${cur}\n\n${v}`;
    }
    if (val !== next[k]) {
      (next as Formish)[k] = val;
      changed.push(k);
    }
  }
  return { form: next, changed };
}
