import { ENGINE_BASE } from '../../../engine';
import type { Kaynaklar } from '../../../components/sqlInfo';
import { call, qs } from '../api';

/** Sözleşme karşılaştırma: köprü uçları /api/v1/editorial/contracts/compare/* (model yok, CRM'e yazma yok). */

export type Status = 'olagan' | 'yuksek' | 'dusuk' | 'nadir' | 'nadir-madde' | 'eksik' | 'emsal-az' | 'kur-yok' | 'yok';
export type ReviewStatus = 'uygun' | 'istisna' | 'crm-duzelt' | 'hukuk';
/** Bulgunun incelemesi: `stale` = CRM'deki değer inceleme anından sonra değişti; `open` = bulgu hâlâ açık iş. */
export type Review = {
  status: ReviewStatus;
  statusLabel: string;
  stale: boolean;
  open: boolean;
  note?: string | null;
  owner?: string | null;
  by?: string | null;
  at?: string | null;
};
export type PositionResult = {
  id: number;
  clause: string;
  rule: string;
  level: 'kirmizi' | 'uyari';
  levelLabel?: string;
  reason: string | null;
  ok: boolean;
  value: string;
  inceleme?: Review | null;
};
export type Position = {
  id: number;
  clause: string;
  scope: { tip: number | null; odeme: number | null; para: number | null };
  op: 'min' | 'max' | 'eq' | 'in' | 'zorunlu' | 'yasak';
  opLabel: string;
  value: unknown;
  level: 'kirmizi' | 'uyari';
  levelLabel: string;
  reason: string | null;
  state: 'oneri' | 'onayli';
  stateLabel: string;
  text: string;
  createdBy: string;
  approvedBy: string | null;
  approvedAt: string | null;
  updatedBy: string;
  updatedAt: string | null;
};
export type PositionClause = { key: string; label: string; kind: string; group?: string; options?: Array<{ kod: number; ad: string }> | null };
export type FormalCheck = { id: string; label: string; ok: boolean; detail: string | null; law: string; inceleme?: Review | null };
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
  incelemeDurumlari: Record<ReviewStatus, string>;
  sekilDenetimleri: Record<string, { ad: string; dayanak: string }>;
  kur: { ay: number; okunan: number; okunuyor: boolean };
  olcutler: Record<string, string>;
  varsayilanOlcut: string[];
  satisVar: boolean;
  satisDilimleri: Record<string, string>;
  maddeTurleri: Record<string, string>;
  heicVar: boolean;
  pozisyonIslemleri: Record<string, string>;
  pozisyonDuzeyleri: Record<string, string>;
  can: { upload: boolean; review: boolean; export: boolean; position: boolean };
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
  agreement: string;
  sapmalar: Array<{ key: string; label: string; status: Status; statusLabel: string; valueLabel: string; inceleme: Review | null }>;
  ozgunNotlar: Array<{ key: string; label: string; inceleme: Review | null }>;
  sekilEksik: Array<{ id: string; label: string; inceleme: Review | null }>;
  pozisyon: Array<{ id: number; rule: string; level: 'kirmizi' | 'uyari'; value: string; inceleme: Review | null }>;
  acikBulgu: number;
};
export type Scan = {
  items: ScanItem[];
  total: number;
  page: number;
  pageSize: number;
  ozet: { sozlesme: number; anlasma: number; sapan: number; ozgun: number; sekil: number; pozisyon: number; emsalYetersiz: number };
  maddeler: Array<{ key: string; label: string; sayi: number }>;
  sekilSayim: Array<{ id: string; label: string; sayi: number }>;
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
  only?: 'sapan' | 'ozgun' | 'sekil' | 'pozisyon' | 'hepsi-sapma' | 'hepsi';
  acik?: boolean;
  /** Ek kıyas ölçütleri, virgülle («ajans,satis»); boş dize = hiçbiri, yok = Yönetim varsayılanı. */
  olcut?: string;
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
  /** Tutar maddesinde kıyasın birimi (TL sözleşmede başlangıç ayı kuruyla USD) ve değeri. */
  kiyas?: number | null;
  kiyasBirim?: string | null;
  inceleme?: Review | null;
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
  sinif?: { kod: string; ad: string; durum: string | null };
  inceleme?: Review | null;
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
  kur?: string | null;
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
    olcutler: Array<{ id: string; ad: string; deger: string | null }>;
  };
  olaylar: Array<{ tarih: string; olay: string; no: string | null }>;
  criteria: Criteria;
  groups: Array<{ id: string; label: string; clauses: ClauseRow[] }>;
  texts: TextRow[];
  sekil: FormalCheck[];
  pozisyon: PositionResult[];
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
  ayar: { yil: number; emsal: number; esikYuzde: number; olcut: string[] };
  can: { review: boolean };
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
export type Clause = {
  sira: number;
  no: string | null;
  baslik: string | null;
  metin: string;
  sayfa: string | null;
  tur?: string | null;
  turAd?: string | null;
  turKaynak?: 'kural' | 'zeki' | null;
  olasilik?: number | null;
};
export type TypeInfo = { a: string[]; b: string[]; yalnizA: string[]; yalnizB: string[] };
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
  turler: TypeInfo;
  turAdlari: Record<string, string>;
  pozisyon: PositionResult[];
  maskeli: boolean;
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
export type Corpus = {
  maddeler: CorpusRow[];
  sayim: Record<CorpusRow['durum'], number>;
  belgeSayisi: number;
  a: Doc;
  eksikTurler: Array<{ tur: string; ad: string; belge: number }>;
  turler: string[];
  turAdlari: Record<string, string>;
  pozisyon: PositionResult[];
  maskeli: boolean;
  kaynaklar?: Kaynaklar;
};

const B = '/compare';
const enc = encodeURIComponent;

export const compareApi = {
  meta: () => call<Meta>(`${B}/meta`, { timeout: 180_000 }),
  refresh: () => call<{ ok: boolean; yenileniyor: boolean }>(`${B}/refresh`, { method: 'POST', body: {} }),
  scan: (p: ScanQuery) =>
    call<Scan>(`${B}/scan${qs({ ...p, aktif: p.aktif || undefined, olcut: p.olcut === '' ? '-' : p.olcut } as Record<string, string | number | boolean | undefined>)}`, { timeout: 180_000 }),
  search: (q: string, page = 0) => call<Found>(`${B}/search${qs({ q, page })}`),
  scanCsvUrl: (p: ScanQuery) =>
    `${ENGINE_BASE}/api/v1/editorial/contracts${B}/scan.csv${qs({ ...p, page: undefined, aktif: p.aktif || undefined, acik: p.acik || undefined, olcut: p.olcut === '' ? '-' : p.olcut } as Record<string, string | number | boolean | undefined>)}`,
  terms: (terms: unknown) => call<Omit<Detail, 'peers'>>(`${B}/terms`, { method: 'POST', body: { terms }, timeout: 120_000 }),
  reviewSave: (b: { key: string; clause: string; status: ReviewStatus; note?: string; owner?: string }) =>
    call<Review>(`${B}/reviews`, { method: 'POST', body: b }),
  reviewDelete: (key: string, clause: string) => call<{ ok: boolean }>(`${B}/reviews${qs({ key, clause })}`, { method: 'DELETE' }),
  contract: (key: string, yil?: number, olcut?: string) =>
    call<Detail>(`${B}/contract/${enc(key)}${qs({ yil, olcut: olcut === '' ? '-' : olcut })}`, { timeout: 180_000 }),
  documents: () =>
    call<{ items: Doc[]; crmHata: string | null; saklamaGun: number; heicVar: boolean; can: { upload: boolean; export: boolean }; kaynaklar?: Kaynaklar }>(`${B}/documents`),
  link: (ref: string, no: string) => call<Doc>(`${B}/documents/link`, { method: 'POST', body: { ref, no } }),
  reportUrl: (key: string, yil?: number, olcut?: string) =>
    `${ENGINE_BASE}/api/v1/editorial/contracts${B}/contract/${enc(key)}/report.docx${qs({ yil, olcut: olcut === '' ? '-' : olcut })}`,
  diffDocxUrl: (a: string, b: string, hepsi = false) => `${ENGINE_BASE}/api/v1/editorial/contracts${B}/documents/diff.docx${qs({ a, b, hepsi })}`,
  positions: () =>
    call<{ items: Position[]; clauses: PositionClause[]; ops: Record<string, string>; levels: Record<string, string>; states: Record<string, string>; facets: Meta['facets']; can: { position: boolean }; kaynaklar?: Kaynaklar }>(`${B}/positions`),
  positionSave: (b: Partial<Omit<Position, 'scope'>> & { scope?: Partial<Position['scope']> }) => call<Position>(`${B}/positions`, { method: 'POST', body: b }),
  positionApprove: (id: number) => call<Position>(`${B}/positions/${id}/approve`, { method: 'POST', body: {} }),
  positionDelete: (id: number) => call<{ ok: boolean }>(`${B}/positions/${id}`, { method: 'DELETE' }),
  positionSuggest: (tip?: number, odeme?: number) => call<{ eklenen: number; atlanan: number }>(`${B}/positions/suggest`, { method: 'POST', body: { tip, odeme }, timeout: 120_000 }),
  read: (ref: string) => call<Doc | { ref: string; status: DocStatus }>(`${B}/documents/read`, { method: 'POST', body: { ref } }),
  readAll: () => call<{ ok: boolean; kuyruk: number | null; suruyor: boolean }>(`${B}/documents/read-all`, { method: 'POST', body: {} }),
  upload: (file: File) => call<Doc>(`${B}/documents${qs({ filename: file.name })}`, { method: 'PUT', raw: file, timeout: 300_000 }),
  remove: (ref: string) => call<{ ok: boolean }>(`${B}/documents${qs({ ref })}`, { method: 'DELETE' }),
  fileUrl: (ref: string) => `${ENGINE_BASE}/api/v1/editorial/contracts${B}/documents/file${qs({ ref })}`,
  diff: (a: string, b: string, maskesiz = false) => call<DocDiff>(`${B}/documents/diff`, { method: 'POST', body: { a, b, maskesiz } }),
  corpus: (a: string, maskesiz = false) => call<Corpus>(`${B}/documents/corpus`, { method: 'POST', body: { a, maskesiz }, timeout: 180_000 }),
};
