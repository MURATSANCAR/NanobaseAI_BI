import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** Uç cevabındaki sorgu bilgisi (`<SqlInfo k={…kaynaklar} alan="…" />`). */
export type WithK = { kaynaklar?: Kaynaklar };

/** M29 İlk dağılım ekranının köprü uçları: /api/v1/distribution/*. */

export type PlanStatus = 'taslak' | 'onayda' | 'onayli' | 'arsiv';
export type BookState = 'yok' | 'taslak' | 'onayda' | 'onayli' | 'sevkte';
export type AlertKind = 'plan_yok' | 'sevk_gecikti' | 'hic_satmadi' | 'tukendi';

export type DistMeta = {
  statuses: Record<PlanStatus, string>;
  bookStates: Record<BookState, string>;
  alertKinds: Record<AlertKind, string>;
  regions: string[];
  params: { pencere: number; takipHafta: number; listeGun: number; rezervPay: number; benzer: number; sevkGun: number; satisGun: number };
  veriSonu: string | null;
  depoSonu: string | null;
  asof: string | null;
  me: { username: string; display: string; canPlan: boolean; canApprove: boolean; canAll: boolean; canExport: boolean };
};

export type Book = {
  stokKodu: string;
  ad: string | null;
  yayinevi: string | null;
  depoGiris: string | null;
  baskiAdedi: number | null;
  baskiNo: number | null;
  ilkBaski: boolean | null;
  kaynak: 'logo' | 'm12' | 'logo+m12';
  stok: number | null;
  durum: BookState;
  durumEtiket: string;
  plan: { id: string; surum: number; durum: PlanStatus; toplam: number; rezerv: number } | null;
};

export type TrackSummary = {
  planId: string;
  stokKodu: string;
  ad: string | null;
  surum: number;
  onay: string | null;
  hafta: number;
  takipHafta: number;
  plan: number;
  sevk: number;
  fatura: number;
  iade: number;
  net: number;
  sevkOrani: number | null;
  iadeOrani: number | null;
  musteri: number;
  planDisi: { musteri: number; sevk: number };
  degerlendirmeGunu: string;
  veriBitti: boolean;
  bolgeler?: Array<{ bolge: string; plan: number; sevk: number; fatura: number; iade: number; net: number }>;
  haftalar?: Array<{ hafta: number; sevk: number; fatura: number; iade: number }>;
  cariler?: Array<Line & { takip: Track }>;
};

export type BooksResponse = {
  asof: string | null;
  veriSonu: string | null;
  depoSonu: string | null;
  uyarilar: string[];
  pencereGun: number;
  items: Book[];
  izlenen: TrackSummary[];
};

export type Cell = { bolge: string; kanal: string; adet: number; onerilen: number; musteri: number; satir: number };
export type Matrix = {
  bolgeler: Array<{ bolge: string; adet: number; pay: number }>;
  kanallar: Array<{ kanal: string; adet: number; pay: number }>;
  hucreler: Cell[];
  toplam: number;
};

export type Comp = {
  stokKodu: string;
  ad: string | null;
  yazar: string | null;
  yayinevi: string | null;
  pencere: [string, string] | null;
  puan: number | null;
  benzerlik: number | null;
  modelKarar: 'benzer' | 'az' | 'degil' | null;
  gerekce: string | null;
  secildi: boolean;
  agirlik: number | null;
  satis: number | null;
  iade: number | null;
  net: number | null;
  netCiro: number | null;
  musteri: number | null;
  kanallar: Record<string, number>;
  crmDagilimAdet: number | null;
  crmDagilimSiparis: number | null;
};

export type Plan = {
  /** Sorgu bilgisi (plan ucu doldurur). */
  kaynaklar?: Kaynaklar;
  id: string;
  stokKodu: string;
  ad: string | null;
  surum: number;
  durum: PlanStatus;
  durumEtiket: string;
  depoGiris: string | null;
  baskiAdedi: number | null;
  stok: number | null;
  toplam: number;
  onerilenToplam: number;
  rezerv: number;
  hedef: { var?: boolean; yillikAdet?: number; ikiAyAdet?: number; planBaslik?: string; planId?: string; aylar?: number[] };
  basis: {
    yontem?: 'emsal' | 'kitap-karti' | 'kendi' | 'yok';
    toplamKaynak?: 'hedef' | 'benzer' | 'yok';
    benzerOrtanca?: number | null;
    istenen?: number;
    dagitilabilir?: number | null;
    stokKaynak?: 'logo' | 'baski' | null;
    pencereGun?: number;
    rezervPay?: number;
    modelAyiklama?: boolean;
    benzerSayisi?: number;
    veriSonu?: string;
    uyarilar?: string[];
  };
  gerekce: string | null;
  gerekceKaynak: 'model' | 'kural' | null;
  note: string | null;
  revisionOf: string | null;
  revisionReason: string | null;
  createdBy: string;
  createdAt: string | null;
  submittedBy: string | null;
  submittedAt: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
  decisionNote: string | null;
  matris: Matrix;
  benzerler: Comp[];
  satirSayisi: number;
  musteri: number;
  elleSatir: number;
  guncelStok: { adet: number | null; tur: 'stok' | 'baski' | 'yok' };
  asim: boolean;
  kapsam: 'kendi' | 'hepsi';
  veriSonu: string | null;
  archived?: string | null;
};

export type Track = { sevk: number; fatura: number; iade: number };

export type Line = {
  no: number;
  cariKodu: string | null;
  crmId: string | null;
  unvan: string | null;
  il: string | null;
  bolge: string;
  kanal: string;
  bmt: string | null;
  bmtHesap: string | null;
  dagilimCarisi: boolean;
  pay: number;
  gecmisNet: number | null;
  gecmisIadeOrani: number | null;
  onerilen: number;
  adet: number;
  elle: boolean;
  gerekce: string | null;
  editedBy: string | null;
  editedAt: string | null;
  takip?: Track;
};

export type LinePage = { items: Line[]; total: number; page: number; pageSize: number };

export type RegionBook = {
  planId: string;
  stokKodu: string;
  ad: string | null;
  onay: string | null;
  depoGiris: string | null;
  adet: number;
  musteri: number;
  sevk: number;
  cariler: Array<{ cariKodu: string | null; unvan: string | null; il: string | null; adet: number; bmt: string | null } & Track>;
};

export type DistAlert = {
  id: string;
  planId: string | null;
  stokKodu: string | null;
  tur: AlertKind;
  turEtiket: string;
  etiket: string | null;
  detay: Record<string, unknown>;
  durum: 'acik' | 'kapandi' | 'bilgi';
  ilk: string | null;
  son: string | null;
};

const B = '/api/v1/distribution';

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401) throw new EngineAuthError();
  const j = res.ok ? null : ((await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null);
  const msg = j ? (typeof j.detail === 'string' ? j.detail : j.detail?.message) : undefined;
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  if (!res.ok) throw new Error(msg || httpErrorText(res.status));
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export const distApi = {
  meta: () => send<DistMeta>('GET', '/meta'),
  books: (p: { durum?: string; q?: string } = {}) => send<BooksResponse & WithK>('GET', `/books${qs(p)}`),
  refreshBooks: () => send<{ kitap: number; logo: number; m12: number; uyarilar: string[] }>('POST', '/books/refresh', {}, 300_000),
  plansOf: (stok: string) => send<{ items: Plan[] } & WithK>('GET', `/plans${qs({ stok })}`),
  generate: (stokKodu: string) => send<Plan>('POST', '/plans/generate', { stokKodu }, 300_000),
  plan: (id: string) => send<Plan & WithK>('GET', `/plans/${enc(id)}`),
  lines: (id: string, p: { q?: string; bolge?: string; kanal?: string; yalniz?: string; page?: number }) =>
    send<LinePage & WithK>('GET', `/plans/${enc(id)}/lines${qs(p)}`),
  updatePlan: (id: string, b: { rezerv?: number; note?: string }) => send<Plan>('PATCH', `/plans/${enc(id)}`, b),
  updateLine: (id: string, no: number, b: { adet?: number; gerekce?: string }) => send<Line>('PATCH', `/plans/${enc(id)}/lines/${no}`, b),
  updateCell: (id: string, b: { bolge: string; kanal: string; adet: number; gerekce?: string }) => send<Plan>('PATCH', `/plans/${enc(id)}/cells`, b),
  deletePlan: (id: string) => send<{ ok: boolean }>('DELETE', `/plans/${enc(id)}`),
  submit: (id: string) => send<Plan>('POST', `/plans/${enc(id)}/submit`, {}),
  withdraw: (id: string) => send<Plan>('POST', `/plans/${enc(id)}/withdraw`, {}),
  approve: (id: string, note?: string) => send<Plan>('POST', `/plans/${enc(id)}/approve`, { note }),
  reject: (id: string, note: string) => send<Plan>('POST', `/plans/${enc(id)}/reject`, { note }),
  revise: (id: string, reason: string) => send<Plan>('POST', `/plans/${enc(id)}/revise`, { reason }),
  track: (id: string) => send<{ satir: number }>('POST', `/plans/${enc(id)}/track`, {}, 300_000),
  tracking: (stok: string, hafta?: number) => send<{ items: TrackSummary[]; veriSonu: string | null; takipHafta: number } & WithK>('GET', `/tracking${qs({ stok, hafta })}`),
  myRegion: (herkes = false) => send<{ items: RegionBook[]; kapsam: 'kendi' | 'hepsi'; veriSonu: string | null } & WithK>('GET', `/my-region${qs({ herkes })}`),
  alerts: (p: { durum?: string; tur?: string; page?: number } = {}) =>
    send<{ items: DistAlert[]; total: number; page: number; pageSize: number; sayilar: Partial<Record<AlertKind, number>> } & WithK>('GET', `/alerts${qs(p)}`),
  exportUrl: (id: string) => `${ENGINE_BASE}${B}/plans/${enc(id)}/export.xlsx`,
};

export const STATUS_TONE: Record<PlanStatus, 'ok' | 'warn' | 'muted' | 'violet'> = { taslak: 'muted', onayda: 'warn', onayli: 'ok', arsiv: 'muted' };
export const BOOK_TONE: Record<BookState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  yok: 'err', taslak: 'muted', onayda: 'warn', onayli: 'ok', sevkte: 'violet',
};
