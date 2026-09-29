import { ENGINE_BASE } from '../../../engine';
import type { Kaynaklar } from '../../../components/sqlInfo';
import { call, qs } from '../api';

/** Sözleşme karşılaştırma: köprü uçları /api/v1/editorial/contracts/compare/* (model yok, CRM'e yazma yok). */

export type Status = 'olagan' | 'yuksek' | 'dusuk' | 'nadir' | 'nadir-madde' | 'eksik' | 'emsal-az' | 'yok';
export type TextStatus = 'ozgun' | 'az' | 'kalip';
export type View = { okunduAn: string | null; yenileniyor: boolean };

export type Facet = { kod: number; ad: string | null; sayi: number };
export type Meta = {
  ayarlar: { emsal: number; esikYuzde: number; yil: number; metinBenzerlik: number; kalip: number };
  durumlar: Record<Status, string>;
  metinDurumlari: Record<TextStatus, string>;
  gruplar: Record<string, string>;
  facets: { tip: Facet[]; odeme: Facet[]; bolum: Facet[]; para: Facet[]; yillar: number[]; maddeler: Array<{ key: string; label: string; grup: string }> };
  belgeTurleri: Record<string, string>;
  belgeDurumlari: Record<string, string>;
  gorunum: View;
  can: { upload: boolean };
  kaynaklar?: Kaynaklar;
};

export type ScanItem = {
  id: string;
  no: string;
  kopya: number;
  kitap: string;
  yazar: string;
  yil: number | null;
  tip: string | null;
  odeme: string | null;
  para: string | null;
  bolum: string | null;
  durum: string | null;
  emsal: number;
  gevsetilen: string[];
  yeterli: boolean;
  sapmalar: Array<{ key: string; label: string; status: Status; statusLabel: string; valueLabel: string }>;
  ozgunNotlar: Array<{ key: string; label: string }>;
};
export type Scan = {
  items: ScanItem[];
  total: number;
  page: number;
  pageSize: number;
  ozet: { sozlesme: number; anlasma: number; sapan: number; ozgun: number; emsalYetersiz: number };
  maddeler: Array<{ key: string; label: string; sayi: number }>;
  gorunum: View;
  ayar: { yil: number };
  kaynaklar?: Kaynaklar;
};
export type ScanQuery = {
  q?: string;
  tip?: number;
  odeme?: number;
  bolum?: number;
  yilDen?: number;
  yilE?: number;
  only?: 'sapan' | 'ozgun' | 'hepsi-sapma' | 'hepsi';
  madde?: string;
  aktif?: boolean;
  enAz?: number;
  page?: number;
  yil?: number;
};

export type Top = { deger: unknown; sayi: number; pay: number | null; ad: string };
export type ClauseRow = {
  key: string;
  label: string;
  kind: 'oran' | 'tutar' | 'sayi' | 'metin-sayi' | 'secim' | 'bayrak';
  value: unknown;
  valueLabel: string;
  status: Status;
  statusLabel: string;
  reason: string | null;
  n: number;
  dolu?: number;
  doluPay?: number | null;
  ayni?: number;
  ayniPay?: number | null;
  konum?: number | null;
  medyan?: number | null;
  p10?: number | null;
  p90?: number | null;
  enAz?: number | null;
  enCok?: number | null;
  medyanAd?: string;
  p10Ad?: string;
  p90Ad?: string;
  enAzAd?: string;
  enCokAd?: string;
  enSik?: Top[];
};
export type TextRow = {
  key: string;
  label: string;
  text: string;
  status: TextStatus;
  statusLabel: string;
  birebir: number;
  benzer: number;
  toplam: number;
  ornekler: Array<{ id: string; no: string; alan: string; alanAd: string; metin: string; benzerlik: number }>;
};
export type Criteria = {
  boyutlar: Array<{ id: string; ad: string; deger: string | null }>;
  donem: { ad: string; deger: string };
  gevsetilen: string[];
  bilinmeyen: string[];
  emsal: number;
  sozlesme: number;
  yeterli: boolean;
  yil: number;
};
export type Detail = {
  subject: {
    kaynak: 'crm' | 'portal' | 'belge';
    key: string;
    no: string;
    baslik: string;
    yazar: string;
    tip: string | null;
    odeme: string | null;
    para: string | null;
    bolum: string | null;
    yil: number | null;
    bas: string | null;
    bit: string | null;
    durum: string | null;
    kopyalar: Array<{ id: string; no: string }>;
    anlasma: Array<{ id: string; no: string }>;
  };
  criteria: Criteria;
  groups: Array<{ id: string; label: string; clauses: ClauseRow[] }>;
  texts: TextRow[];
  sayim: { sapan: number; uyumlu: number; emsalAz: number; ozgunNot: number };
  peers: Array<{ id: string; no: string; kitap: string; yazar: string; yil: number | null; kopya: number }>;
  history: {
    taraflar: string[];
    items: Array<{ id: string; no: string; kitap: string; bas: string | null; bit: string | null; yil: number | null; kopya: number; odeme: string | null; oran: string; avans: string; tekOdeme: string }>;
    onceki: { id: string; no: string; bas: string | null } | null;
    degisen: Array<{ key: string; label: string; old: unknown; new: unknown }>;
  };
  warnings: string[];
  gorunum: View;
  ayar: { yil: number; emsal: number; esikYuzde: number };
  kaynaklar?: Kaynaklar;
};
export type Found = { items: Array<{ id: string; no: string; kitap: string; yazar: string; yil: number | null; kopya: number; odeme: string | null }>; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar };

export type DocStatus = 'bekliyor' | 'okunuyor' | 'hazir' | 'hata';
export type Doc = {
  ref: string;
  kind: 'crm' | 'belge' | 'sablon' | 'yukleme';
  kindLabel: string;
  title: string;
  filename: string | null;
  bytes: number | null;
  contractNo: string | null;
  status: DocStatus;
  statusLabel: string;
  error: string | null;
  maddeSayisi: number | null;
  okuma: { sayfa?: number; not?: string | null } | null;
  createdBy: string | null;
  createdAt: string | null;
  finishedAt: string | null;
  okunabilir?: boolean;
};
export type Clause = { sira: number; no: string | null; baslik: string | null; metin: string; sayfa: string | null };
export type Op = { op: 'eq' | 'ins' | 'del' | 'fill'; text: string; alan?: string };
export type DiffRow = {
  durum: 'ayni' | 'degismis' | 'yeri-degismis' | 'eklenmis' | 'cikarilmis';
  benzerlik: number;
  a: Clause | null;
  b: Clause | null;
  fark?: Op[];
  sayilar?: { a: string[]; b: string[] };
};
export type DocDiff = {
  maddeler: DiffRow[];
  sayim: Record<DiffRow['durum'], number>;
  a: Doc;
  b: Doc;
  kaynaklar?: Kaynaklar;
};
export type CorpusRow = {
  durum: 'ayni' | 'benzer' | 'arsivde-yok';
  a: Clause;
  ayniBelge: number;
  benzerBelge: number;
  enYakin?: { belge: { ref: string; title: string; kindLabel: string; contractNo: string | null }; madde: Clause; benzerlik: number };
  fark?: Op[];
};
export type Corpus = { maddeler: CorpusRow[]; sayim: Record<CorpusRow['durum'], number>; belgeSayisi: number; a: Doc; kaynaklar?: Kaynaklar };

const B = '/compare';
const enc = encodeURIComponent;

export const compareApi = {
  meta: () => call<Meta>(`${B}/meta`, { timeout: 180_000 }),
  refresh: () => call<{ ok: boolean; yenileniyor: boolean }>(`${B}/refresh`, { method: 'POST', body: {} }),
  scan: (p: ScanQuery) =>
    call<Scan>(`${B}/scan${qs({ ...p, aktif: p.aktif || undefined } as Record<string, string | number | boolean | undefined>)}`, { timeout: 180_000 }),
  search: (q: string, page = 0) => call<Found>(`${B}/search${qs({ q, page })}`),
  contract: (key: string, yil?: number) => call<Detail>(`${B}/contract/${enc(key)}${qs({ yil })}`, { timeout: 180_000 }),
  documents: () => call<{ items: Doc[]; crmHata: string | null; can: { upload: boolean }; kaynaklar?: Kaynaklar }>(`${B}/documents`),
  read: (ref: string) => call<Doc | { ref: string; status: DocStatus }>(`${B}/documents/read`, { method: 'POST', body: { ref } }),
  readAll: () => call<{ ok: boolean; kuyruk: number | null; suruyor: boolean }>(`${B}/documents/read-all`, { method: 'POST', body: {} }),
  upload: (file: File) => call<Doc>(`${B}/documents${qs({ filename: file.name })}`, { method: 'PUT', raw: file, timeout: 300_000 }),
  remove: (ref: string) => call<{ ok: boolean }>(`${B}/documents${qs({ ref })}`, { method: 'DELETE' }),
  fileUrl: (ref: string) => `${ENGINE_BASE}/api/v1/editorial/contracts${B}/documents/file${qs({ ref })}`,
  diff: (a: string, b: string) => call<DocDiff>(`${B}/documents/diff`, { method: 'POST', body: { a, b } }),
  corpus: (a: string) => call<Corpus>(`${B}/documents/corpus`, { method: 'POST', body: { a }, timeout: 180_000 }),
};
