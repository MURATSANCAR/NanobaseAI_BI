import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';

/** M39 Pazar araştırması ve rekabet: köprü uçları /api/v1/pazar/*. Portal CRM'e ve Logo'ya yazmaz; dış tarama yok. */

export type Job = { running: boolean; step: string | null; startedAt: string | null; finishedAt: string | null; error: string | null; result?: unknown };
export type Jobs = { kaynak: Job; eslesme: Job; cikarim: string[] };

export type Meta = {
  me: { username: string; display: string; canUpload: boolean; canFigure: boolean; canMap: boolean; canWrite: boolean; canApprove: boolean; canExport: boolean };
  settings: { staleDays: number; newDays: number; compPageTol: number; compPriceTol: number; compModel: number; fileMaxMb: number; twoEyes: boolean; ownYears: number };
  categorySource: 'kitaplik' | 'agac' | null;
  categoryNote: string | null;
  olcu: Record<string, string>;
  mapStatus: Record<MapStatus, string>;
  figureStatus: Record<FigureStatus, string>;
  briefStatus: Record<BriefStatus, string>;
  reportStatus: Record<string, string>;
  dimensions: Record<Dimension, string>;
  modelVar: boolean;
  jobs: Jobs;
  sellIn: string;
};

export type Freshness = {
  records: number;
  firstCreated: string | null;
  lastCreated: string | null;
  lastModified: string | null;
  lastChange: string | null;
  ageDays: number | null;
  staleDays: number;
  stale: boolean;
  byYear: Array<{ yil: string; kayit: number }>;
  crmLinks: number;
  snapshotAt: string | null;
  ownSalesAt: string | null;
  dataEnd: string | null;
  note: string;
};

export type Category = { id: string; ad: string; ustId: string | null; yol: string; kaynak: 'kitaplik' | 'agac' };

export type Dimension = 'kategori' | 'yayinevi' | 'kanal';
export type OwnRow = {
  anahtar: string;
  ad: string;
  ytdCiro: number;
  oncekiYtdCiro: number;
  ciroBuyume: number | null;
  ytdAdet: number;
  oncekiYtdAdet: number;
  adetBuyume: number | null;
  yilCiro: number;
  oncekiYilCiro: number;
  pay: number | null;
};
export type OwnMarket = {
  boyut: Dimension;
  boyutAd?: string;
  yil: number | null;
  years: number[];
  rows: OwnRow[];
  dataEnd: string | null;
  period?: { yil: number; baslangic: string; bitis: string | null };
  total: (Omit<OwnRow, 'anahtar' | 'ad' | 'pay'>) | null;
  missingPrev?: boolean;
  note: string;
  empty?: string;
};

export type Stats = {
  kitap: number;
  fiyatli: number;
  medyan: number | null;
  q1: number | null;
  q3: number | null;
  min: number | null;
  max: number | null;
  sayfaMedyan: number | null;
  sayfaBasiMedyan: number | null;
  yeni: number | null;
  cilt: Array<{ ad: string; kitap: number }>;
};
export type MatrixRow = Stats & { yayinevi: string; own: boolean; total?: boolean; watched: boolean };
export type Matrix = {
  kategori: { id: string; yol: string | null } | null;
  includeSuggested: boolean;
  sayfa: { min: number | null; max: number | null };
  rakipOzet: Stats & { yayinevi: number };
  timas: MatrixRow[];
  rows: MatrixRow[];
  timasKonum: number | null;
  eslenmemis: number | null;
  newDays: number;
  note: string;
};

export type Competitor = {
  crmId: string;
  ad: string;
  yayinevi: string | null;
  yazarlar: string | null;
  isbn: string | null;
  fiyat: number | null;
  sayfa: number | null;
  cilt: string | null;
  kagit: string | null;
  baski: number | null;
  dil: string | null;
  kategoriHam: string | null;
  kategoriId: string | null;
  kategoriYol: string | null;
  satisDurumu: string | null;
  satisAdediHam: number | null;
  satisAdedi2Ham: string | null;
  olusturma: string | null;
  degisme: string | null;
  emsalBagi: boolean;
};
export type Paged<T> = { items: T[]; total: number; page: number; pageSize: number };

export type MapStatus = 'yeni' | 'oneri' | 'belirsiz' | 'onaylandi' | 'reddedildi';
export type MapRow = {
  ham: string;
  kayit: number;
  durum: MapStatus;
  durumAd: string;
  oneriId: string | null;
  oneriYol: string | null;
  kategoriId: string | null;
  kategoriYol: string | null;
  olasilik: number | null;
  marj: number | null;
  yontem: string | null;
  oneren: string | null;
  onaylayan: string | null;
  kararAt: string | null;
  not: string | null;
  ornekler?: string[];
};
export type MapList = Paged<MapRow> & {
  counts: Partial<Record<MapStatus, number>>;
  coverage: { records: number; approved: number; noMatch: number };
  categories: Category[];
  statusLabels: Record<MapStatus, string>;
  job: Job;
};

export type Comparable = {
  tur: 'rakip' | 'timas';
  id: string;
  ad: string;
  yazar: string | null;
  yayinevi: string | null;
  kategoriId: string | null;
  kategoriHam: string | null;
  kategoriYol: string | null;
  sayfa: number | null;
  fiyat: number | null;
  crmEmsal: boolean;
  skor: number;
  stokKodu?: string | null;
  satis?: { adet: number; ciro: number } | null;
  ilkYayin?: string | null;
  zeki?: { sinif: string | null; olasilik: number | null; puan: number };
  gerekce: string[];
};
export type Comparables = {
  query: { q: string; crmKitapId: string | null; kategoriId: string | null; kategoriYol: string | null; sayfa: number | null; fiyat: number | null; base: { ad: string; stokKodu: string | null } | null };
  rakip: Comparable[];
  timas: Comparable[];
  counts: { havuz: number; sozcukEslesen: number; zekiOkudu: number; zekiBenzemiyor: number; crmEmsal: number };
  salesYear: number | null;
  stopped: string | null;
  note: string;
};
export type OwnBookHit = { crmId: string; ad: string; yazar: string | null; stokKodu: string | null; marka: string | null };

export type Report = {
  id: string;
  kaynak: string;
  yil: number | null;
  baslik: string;
  dosyaAdi: string;
  mime: string;
  boyut: number;
  sayfaSayisi: number | null;
  durum: 'yuklendi' | 'cikariliyor' | 'cikarildi' | 'hata';
  durumAd: string;
  ilerleme: { sayfa?: number; toplam?: number; rakam?: number; atilan?: number; metinsiz?: number; metinsizSayfa?: number; hata?: string } | null;
  yukleyen: string;
  yuklendiAt: string | null;
  rakam?: Partial<Record<FigureStatus, number>>;
};
export type FigureStatus = 'oneri' | 'onaylandi' | 'duzeltildi' | 'reddedildi';
export type Figure = {
  id: string;
  raporId: string;
  gosterge: string;
  deger: number;
  degerMetin: string | null;
  degerOneri: number | null;
  birim: string | null;
  donem: string | null;
  sayfa: string;
  alinti: string | null;
  olcu: string;
  olcuAd: string;
  kategoriId: string | null;
  kategoriYol: string | null;
  yontem: 'zeki' | 'elle';
  durum: FigureStatus;
  durumAd: string;
  onaylayan: string | null;
  kararAt: string | null;
  not: string | null;
  rapor?: string;
  raporKaynak?: string;
  raporYil?: number | null;
};

export type BriefStatus = 'taslak' | 'onay_bekliyor' | 'onaylandi';
export type Source = { id: string; tur: 'ic' | 'dis' | 'rakip' | 'tazelik'; baslik: string; deger: number; birim: string; donem: string; kaynak: string; ref: string | null; degerMetin: string };
export type Brief = {
  id: string;
  donem: string;
  donemAd: string;
  taslak: string;
  kaynaklar: Source[];
  reddedilen: Array<{ bolum: string; metin: string; neden: string }>;
  disarida: number;
  durum: BriefStatus;
  durumAd: string;
  yazan: string;
  yazildiAt: string | null;
  guncelleyen: string | null;
  guncellendiAt: string | null;
  gonderen: string | null;
  gonderildiAt: string | null;
  onaylayan: string | null;
  onaylandiAt: string | null;
  dykGonderildiAt: string | null;
  kararNotu: string | null;
  sorunlar: Array<{ satir: number; metin: string; neden: string }>;
};
export type BriefListItem = Omit<Brief, 'taslak' | 'kaynaklar' | 'reddedilen'>;

export type Overview = {
  freshness: Freshness;
  snapshot: { at?: string; competitors?: number; ownBooks?: number; categorySource?: string; categoryNote?: string | null; errors?: Record<string, string> } | null;
  ownBooks: number;
  publishers: number;
  mapping: { counts: Partial<Record<MapStatus, number>>; coverage: { records: number; approved: number; noMatch: number } };
  own: OwnMarket;
  figures: Figure[];
  pendingFigures: number;
  brief: Brief | null;
  pendingBrief: { id: string; donem: string; donemAd: string; durum: BriefStatus; durumAd: string; yazan: string } | null;
  watchlist: number;
  disTarama: string;
  note: string;
  jobs: Jobs;
};

export type Watch = { id: string; yayinevi: string; kategoriId: string | null; kategoriYol: string | null; ekleyen: string; eklendiAt: string | null };

const B = '/api/v1/pazar';

async function fail(res: Response): Promise<never> {
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  throw new Error(msg || httpErrorText(res.status));
}

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

export const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export type MatrixFilter = { kategori?: string; oneri?: boolean; sayfaMin?: number | ''; sayfaMax?: number | ''; yayinevi?: string; izlenen?: boolean };

export const pazarApi = {
  meta: () => send<Meta>('GET', '/meta'),
  overview: () => send<Overview>('GET', '/overview'),
  freshness: () => send<Freshness>('GET', '/freshness'),
  status: () => send<Jobs>('GET', '/status'),
  refresh: () => send<Jobs & { started: boolean }>('POST', '/refresh', {}),
  categories: () => send<{ items: Category[]; source: string | null; note: string | null }>('GET', '/categories'),
  publishers: () => send<{ items: Array<{ ad: string; kitap: number }> }>('GET', '/publishers'),
  competitors: (f: { yayinevi?: string; kategori?: string; q?: string; durum?: string; page?: number }) => send<Paged<Competitor>>('GET', `/competitors${qs(f)}`),
  matrix: (f: MatrixFilter) => send<Matrix>('GET', `/matrix${qs(f)}`, undefined, 180_000),
  matrixCsvUrl: (f: MatrixFilter) => `${ENGINE_BASE}${B}/matrix/export.csv${qs(f)}`,
  ownMarket: (boyut: Dimension, yil?: number) => send<OwnMarket>('GET', `/own-market${qs({ boyut, yil })}`),
  ownBooks: (q: string) => send<{ items: OwnBookHit[]; limit: number; note: string | null }>('GET', `/own-books${qs({ q })}`),
  categoryMap: (f: { durum?: string; q?: string; page?: number }) => send<MapList>('GET', `/category-map${qs(f)}`),
  decideMap: (items: Array<{ ham: string; karar: 'onayla' | 'duzelt' | 'reddet'; kategoriId?: string | null; not?: string }>) =>
    send<{ decided: Array<{ ham: string; durum: MapStatus; kategoriId: string | null; kategoriYol: string | null }>; errors: Array<{ ham: string; neden: string }> }>('POST', '/category-map/decision', { items }),
  suggestMap: (hams?: string[]) => send<{ started: boolean; queued: number; job: Job }>('POST', '/category-map/suggest', { hams }),
  comparables: (body: { q?: string; crmKitapId?: string; kategoriId?: string; sayfa?: number; fiyat?: number }) =>
    send<Comparables>('POST', '/comparables', body, 600_000),
  watchlist: () => send<{ items: Watch[] }>('GET', '/watchlist'),
  addWatch: (yayinevi: string, kategoriId?: string | null) => send<Watch>('POST', '/watchlist', { yayinevi, kategoriId: kategoriId || null }),
  deleteWatch: (id: string) => send<{ ok: boolean }>('DELETE', `/watchlist/${enc(id)}`),
  reports: () => send<{ items: Report[]; statusLabels: Record<string, string>; figureStatus: Record<FigureStatus, string>; olcu: Record<string, string> }>('GET', '/reports'),
  report: (id: string) => send<Report>('GET', `/reports/${enc(id)}`),
  reportFileUrl: (id: string) => `${ENGINE_BASE}${B}/reports/${enc(id)}/file`,
  uploadReport: async (file: File, meta: { kaynak: string; yil?: string; baslik?: string }): Promise<Report> => {
    if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
    const res = await fetch(`${ENGINE_BASE}${B}/reports${qs({ ...meta, filename: file.name })}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
      signal: AbortSignal.timeout(600_000),
    });
    if (!res.ok) return fail(res);
    return (await res.json()) as Report;
  },
  deleteReport: (id: string) => send<{ ok: boolean }>('DELETE', `/reports/${enc(id)}`),
  extract: (id: string) => send<Report>('POST', `/reports/${enc(id)}/extract`, {}),
  figures: (id: string) => send<{ report: Report; items: Figure[]; olcu: Record<string, string>; statusLabels: Record<FigureStatus, string>; categories: Category[] }>('GET', `/reports/${enc(id)}/figures`),
  addFigure: (id: string, body: { gosterge: string; deger: string; birim?: string; donem?: string; sayfa: string; olcu?: string; kategoriId?: string | null; alinti?: string }) =>
    send<Figure>('POST', `/reports/${enc(id)}/figures`, body),
  decideFigure: (id: string, body: { karar: FigureStatus; deger?: string | number; olcu?: string; kategoriId?: string | null; birim?: string; donem?: string; gosterge?: string; not?: string }) =>
    send<Figure>('POST', `/figures/${enc(id)}/decision`, body),
  briefs: () => send<{ items: BriefListItem[]; statusLabels: Record<BriefStatus, string> }>('GET', '/briefs'),
  briefByPeriod: (donem: string) => send<{ brief: Brief | null; donem: string }>('GET', `/briefs/by-period/${enc(donem)}`),
  briefSources: () => send<{ kaynaklar: Source[]; disarida: number; dis: number }>('GET', '/briefs/sources'),
  draftBrief: (donem: string) => send<Brief>('POST', `/briefs/draft${qs({ donem })}`, {}, 600_000),
  updateBrief: (id: string, taslak: string) => send<Brief>('PATCH', `/briefs/${enc(id)}`, { taslak }),
  submitBrief: (id: string) => send<Brief>('POST', `/briefs/${enc(id)}/submit`, {}),
  approveBrief: (id: string, not?: string) => send<Brief>('POST', `/briefs/${enc(id)}/approve`, { not }),
  rejectBrief: (id: string, not: string) => send<Brief>('POST', `/briefs/${enc(id)}/reject`, { not }),
};

/* ------------------------------------------------------------------ biçim */

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const dec2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 });
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtTl = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${dec2.format(v)} ₺`);
export const fmtTlShort = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${compact.format(v)} ₺`);
export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? '—' : `%${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: digits }).format(v * 100)}`;
export const fmtGrowth = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v >= 0 ? '+' : '−'}${fmtPct(Math.abs(v))}`);
export const fmtNum = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 4 }).format(v);

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Europe/Istanbul' });
export const fmtDay = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return Number.isNaN(d.getTime()) ? iso : dayFmt.format(d);
};

/** Geçen ay (YYYY-AA): aylık özetin varsayılan dönemi. */
export function lastMonth(now = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
export const donemLabel = (donem: string) => {
  const [y, m] = donem.split('-');
  const i = Number(m) - 1;
  return i >= 0 && i < 12 ? `${MONTHS[i]} ${y}` : donem;
};

export const STATUS_TONE: Record<string, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  yeni: 'muted',
  oneri: 'violet',
  belirsiz: 'warn',
  onaylandi: 'ok',
  reddedildi: 'err',
  duzeltildi: 'ok',
  taslak: 'muted',
  onay_bekliyor: 'warn',
  yuklendi: 'muted',
  cikariliyor: 'violet',
  cikarildi: 'ok',
  hata: 'err',
};
