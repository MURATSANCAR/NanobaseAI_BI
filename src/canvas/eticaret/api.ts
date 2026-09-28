import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** Her rakam ucunun cevabında sorgu bilgisi (`<SqlInfo k={d.kaynaklar} …/>`). */
export type WithK = { kaynaklar?: Kaynaklar };

/** M34 E-ticaret ve platform yönetimi ekranlarının köprü uçları: /api/v1/eticaret/*. Portal hiçbir sisteme yazmaz. */

export type DiffKind = 'hak' | 'fiyat' | 'stok' | 'aktiflik' | 'barkod' | 'ad' | 'eksik_kart';
export type DiffState = 'acik' | 'sonra' | 'bilincli' | 'duzeltildi' | 'kapandi';
export type MarkState = Exclude<DiffState, 'kapandi'>;

export type Me = { username: string; display: string; admin: boolean; canMark: boolean; canPropose: boolean; canApprove: boolean; canExport: boolean };
export type RefreshState = { running: boolean; startedAt: string | null; finishedAt: string | null; error: string | null; step: string | null };

export type Meta = {
  turler: Record<DiffKind, string>;
  durumlar: Record<DiffState, string>;
  isaretler: MarkState[];
  alanlar: Record<string, string>;
  nedenler: string[];
  gonderim: false;
  ayarlar: {
    channels: string[]; priceRef: 'crm' | 'logo'; priceTol: number; stockMin: number; required: string[]; kinds: DiffKind[];
    alertKinds: DiffKind[]; snoozeDays: number; salesMonths: number; funnelMinViews: number; funnelLowRatio: number;
    stockoutDays: number; bildirim: boolean; haftalik: boolean;
  };
  durum: RefreshState;
  me: Me;
};

export type Diff = {
  id: string;
  productKey: string;
  tur: DiffKind;
  turAdi: string;
  ad: string | null;
  stokKodu: string | null;
  crm: string | null;
  logo: string | null;
  site: string | null;
  aciklama: string | null;
  etki: number;
  ilkGoruldu: string | null;
  sonGoruldu: string | null;
  durum: DiffState;
  durumAdi: string;
  erteleBitis: string | null;
  neden: { oneri: string; olasilik: number | null } | null;
  sahip: string | null;
  not: string | null;
  isaretleyen: string | null;
  isaretlendi: string | null;
  kapatan: string | null;
  kapandi: string | null;
  dogrulandi: boolean;
};

export type LogRow = { zaman: string | null; kullanici: string; eylem: string; not: string | null; tur?: DiffKind | null; turAdi?: string };

export type Item = {
  productKey: string; stokKodu: string | null; crmKitapId: string | null; tsoftUrunId: string | null; ad: string | null;
  adSite: string | null; sitede: boolean; siteAktif: boolean; crmVar: boolean; crmTsoftAktif: boolean; crmEtkin: boolean;
  stokLogo: number | null; stokSite: number | null; fiyatCrm: number | null; fiyatLogo: number | null; fiyatSite: number | null;
  fiyatSiteIndirimli: number | null; doluluk: number | null; eksik: Array<{ alan: string; ad: string }>; goruntulenme: number;
  siteSatis: number; yorum: number; donusum: number | null; logoAdet: number | null; logoCiro: number | null; hak: string | null;
  yayinDurumu: string | null; yayinBayragi: string | null; url: string | null; logoKesim: string | null; okundu: string | null;
  olasiNedenler?: string[];
};

export type Proposal = {
  id: string; productId: string; status: 'hazir' | 'onaylandi' | 'reddedildi'; fields: Record<string, string>;
  before: Record<string, string>; scoreBefore: number | null; scoreAfter: number | null; source: string; createdBy: string | null;
  createdAt: string | null; decidedBy: string | null; decidedAt: string | null; note: string | null; result: string | null;
  productKey?: string; ad?: string | null;
};

export type RunInfo = { basladi: string | null; bitti: string | null; baslatan: string | null; hata: string | null; ozet: Record<string, unknown> & {
  kaynaklar?: Record<string, Record<string, unknown>>;
} };

export type Overview = {
  gostergeler: { siteAktif: number; crmTsoftAktif: number; acikFark: number; eksikKart: number; satistaOlmamali: number };
  turSayilari: Record<DiffKind, number>;
  durumSayilari: Record<DiffState, number>;
  haftalik: { kapanan: number; ortalamaKapanmaGun: number | null };
  bugun: { items: Diff[]; total: number };
  sonOkuma: RunInfo | null;
  logoKesim: string | null;
  durum: RefreshState;
  gonderim: false;
  kaynaklar?: Kaynaklar;
};

export type DiffList = { items: Diff[]; total: number; page: number; pageSize: number; turSayilari: Record<DiffKind, number>; kaynaklar?: Kaynaklar };

export type Funnel = {
  items: Item[]; total: number; page: number; pageSize: number; ortancaDonusum: number | null;
  dusukEsik: { enAzGoruntulenme: number; oran: number; donusum: number | null };
  toplam: { goruntulenme: number; satis: number; yorum: number }; not: string;
  kaynaklar?: Kaynaklar;
};

export type Account = {
  kod: string; unvan: string | null; kanal: string | null; satis: number; iade: number; net: number; satisAdet: number; iadeAdet: number;
  iadeOrani: number | null; oncekiNet: number; oncekiIadeOrani: number | null; degisim: number | null; aylik: number[];
};
export type Markets = {
  yil: number; donem: { bas: string; son: string; oncekiBas: string; oncekiSon: string }; cariler: Account[];
  toplam: { satis: number; iade: number; net: number; oncekiNet: number; satisAdet: number; iadeAdet: number; iadeOrani: number | null; degisim: number | null };
  kesim: string | null; kanallar: string[]; yillar: number[];
  kaynaklar?: Kaynaklar;
};
export type MarketBook = {
  stok: string; ad: string | null; satisAdet: number; iadeAdet: number; ciro: number; son: string | null; net: number;
  iadeOrani: number | null; stokLogo: number | null; kalanGun: number | null; tukenmeRiski: boolean; productKey: string | null; siteAktif: boolean;
};

const B = '/api/v1/eticaret';
const enc = encodeURIComponent;

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

export type DiffFilter = { tur?: string; durum?: string; q?: string; sahip?: string };

export const ecomApi = {
  meta: () => send<Meta>('GET', '/meta'),
  overview: () => send<Overview>('GET', '/overview'),
  status: () => send<RefreshState>('GET', '/status'),
  refresh: () => send<RefreshState & { started: boolean }>('POST', '/refresh'),
  diffs: (f: DiffFilter & { page?: number }) => send<DiffList>('GET', `/diffs${qs(f)}`),
  diff: (id: string) => send<Diff & { gunluk: LogRow[] } & WithK>('GET', `/diffs/${enc(id)}`),
  mark: (id: string, b: { durum: MarkState; note?: string; sahip?: string | null }) => send<Diff & { gunluk: LogRow[] }>('POST', `/diffs/${enc(id)}/mark`, b),
  markBulk: (b: { ids: string[]; durum: MarkState; note?: string; sahip?: string | null }) =>
    send<{ items: Diff[]; atlanan: Array<{ id: string; neden: string }> }>('POST', '/diffs/mark-bulk', b),
  diffsCsvUrl: (f: DiffFilter) => `${ENGINE_BASE}${B}/diffs/export.csv${qs(f)}`,
  item: (key: string) => send<{ kitap: Item; farklar: Diff[]; gunluk: LogRow[]; oneriler: Proposal[] } & WithK>('GET', `/items/${enc(key)}`),
  propose: (key: string) => send<Proposal>('POST', `/items/${enc(key)}/propose`, {}, 300_000),
  proposals: (durum = 'hazir') => send<{ items: Proposal[]; canApprove: boolean } & WithK>('GET', `/proposals${qs({ durum })}`),
  decide: (id: string, b: { action: 'approve' | 'reject'; note?: string; fields?: Record<string, string> }) =>
    send<Proposal>('POST', `/proposals/${enc(id)}/decide`, b),
  funnel: (p: { dusuk?: boolean; q?: string; sort?: string; page?: number }) => send<Funnel>('GET', `/funnel${qs(p)}`),
  markets: (yil?: number, yenile = false) => send<Markets>('GET', `/marketplaces${qs({ yil, yenile })}`, undefined, 600_000),
  stockRisk: (yil?: number) =>
    send<{ items: MarketBook[]; yil: number; kesim: string | null; esikGun: number; satisAyi: number } & WithK>('GET', `/marketplaces/stock-risk${qs({ yil })}`, undefined, 600_000),
  marketBooks: (code: string, yil?: number) =>
    send<{ kod: string; yil: number; donem: { bas: string; son: string }; kesim: string | null; items: MarketBook[]; total: number } & WithK>(
      'GET', `/marketplaces/${enc(code)}/books${qs({ yil })}`, undefined, 600_000),
  contentPackUrl: (keys: string[], bicim: 'xlsx' | 'csv' = 'xlsx') => `${ENGINE_BASE}${B}/export/content-pack${qs({ keys: keys.join(','), bicim })}`,
};

/** İçerik paketi yalnız barkodlu (EAN) kitaplar içindir; «crm:» / «tsoft:» anahtarlı satırlar pakete giremez. */
export const isEan = (key: string | null | undefined) => !!key && /^\d{8,14}$/.test(key);

/* ------------------------------------------------------------------ biçim */

const money2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const pct1 = new Intl.NumberFormat('tr-TR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
const dtFmt = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money2.format(v)} ₺`);
export const fmtMoney0 = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money0.format(v)} ₺`);
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : pct1.format(v));
export function fmtDay(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v.length <= 10 ? `${v}T00:00:00` : v);
  return Number.isNaN(d.getTime()) ? v : dayFmt.format(d);
}
export const fmtWhen = (v: string | null | undefined) => (v ? dtFmt.format(new Date(v)) : '—');

export const KIND_TONE: Record<DiffKind, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  hak: 'err',
  fiyat: 'warn',
  stok: 'warn',
  aktiflik: 'violet',
  barkod: 'violet',
  ad: 'muted',
  eksik_kart: 'muted',
};

export const STATE_TONE: Record<DiffState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  acik: 'err',
  sonra: 'warn',
  bilincli: 'muted',
  duzeltildi: 'violet',
  kapandi: 'ok',
};

export const LOG_LABEL: Record<string, string> = {
  acildi: 'Açıldı',
  yeniden_acildi: 'Yeniden açıldı',
  isaret: 'İşaret',
  kapandi: 'Kapandı',
  dogrulandi: 'Doğrulandı',
  sahip: 'Sahip',
};
