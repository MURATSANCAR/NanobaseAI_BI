import { ENGINE_BASE, ENGINE_ENABLED, EngineForbiddenError, freshHeaders } from '../engine';
import type { Kaynaklar } from '../components/sqlInfo';

/** M10 İlk baskı ve satış tahmini: köprünün /api/v1/management/first-print/* uçları. */

export type Tier = 'yuksek' | 'orta' | 'dusuk';

export type BookInfo = {
  code: string;
  name: string;
  publisher: string | null;
  library: string | null;
  series: string | null;
  authors: string | null;
  audience: string | null;
  genre: string | null;
  pages: number | null;
  price: number | null;
  firstPub: string | null;
  status: string | null;
  launch: string | null;
  salesTarget: number | null;
};

export type UpcomingRow = BookInfo & {
  launchUsed: string;
  tier: Tier;
  base6: number;
  low6: number;
  high6: number;
  base12: number | null;
  revenue12: number | null;
  print: number;
  stockout6: number | null;
  analogs: number;
  emsal: number;
};

export type TrackForecast = {
  base: number;
  low: number;
  high: number;
  pess: number;
  expectedSoFar: number;
  pessSoFar: number;
  revised: number | null;
};

/** Çıkmış kitabın ilk 12 ayı için stok ve yeniden baskı (elde kalan = depo stoku − bekleyen sipariş). */
export type Reprint = {
  stock: number;
  orders: number;
  available: number;
  asOf: string | null;
  sold: number;
  observed: number;
  revised12: number;
  remaining: Record<'0.2' | '0.5' | '0.8', number>;
  runOut: string | null;
  runOutName: string | null;
  monthsLeft: number | null;
  status: 'yok' | 'acil' | 'gerekli' | 'yeterli';
  need: Record<'0.2' | '0.5' | '0.8', number>;
  units: number;
  unitsHigh: number;
  window: string;
  plan: Array<{ month: string; label: string; units: number; cum: number; left: number }>;
  lastPrint: { count: number | null; units: number | null; date: string | null } | null;
  typicalError: number | null;
};

export const REPRINT_LABEL: Record<Reprint['status'], string> = {
  yok: 'Stok yok',
  acil: 'Yeniden baskı acil',
  gerekli: 'Yeniden baskı gerekli',
  yeterli: 'Stok yeterli',
};

export function reprintTone(r: Pick<Reprint, 'status'>): 'err' | 'warn' | 'ok' {
  return r.status === 'yeterli' ? 'ok' : r.status === 'gerekli' ? 'warn' : 'err';
}

/** Tek cümle: ne zaman biter, 12. aya kadar kaç adet daha gerekir. */
export function reprintSentence(r: Reprint): string {
  if (r.status === 'yeterli') return `Elde kalan ${fmtUnits(r.available)} adet, ${r.window} sonuna kadarki beklenen satışı karşılıyor.`;
  const when = r.status === 'yok' ? 'Satılabilir stok kalmadı' : `Stok ${r.runOutName} içinde tükenir`;
  return `${when}; ${r.window} sonuna kadar yaklaşık ${fmtUnits(r.need['0.5'])} adet daha satılması bekleniyor.`;
}

export type TrackingRow = BookInfo & {
  months: Array<{ month: string; label: string; units: number }>;
  actual: number;
  observed: number;
  forecast: Record<string, TrackForecast>;
  deviation: number | null;
  alert: boolean;
  reprint?: Reprint | null;
};

export type Metrics = {
  n: number;
  mdape: number;
  wape: number;
  within25: number;
  within50: number;
  within2x: number;
  bias: number;
};

export type Backtest = {
  horizon: number;
  from: string;
  to: string;
  model: Metrics | null;
  naive: Metrics | null;
  emsal: Metrics | null;
  coverage80: number | null;
  stockout: Record<string, number | null>;
  byYear: Record<string, Metrics | null>;
  byTier?: Partial<Record<Tier, Partial<Metrics> & { coverage80: number | null }>>;
  samples: Array<{ code: string; name: string; launch: string; forecast: number; low: number; high: number; actual: number; tier: Tier }>;
  revise?: Record<string, Metrics | null>;
};

export type RuleStats = { n?: number; stockout6?: number | null; stockout12?: number | null; leftover12?: number | null; medianPrint?: number | null };

/** Geçmiş sınama: ilk baskı her kural kadar yapılsaydı (12 ayı gözlenmiş kitaplar). */
export type PrintRules = {
  rules: Array<RuleStats & { id: string; label: string }>;
  theirs: RuleStats | null;
  recommended: string;
};

export type Summary = {
  status: {
    updatedAt?: number | null;
    refreshing?: boolean;
    error?: string | null;
    nextRefreshAt?: number | null;
    durationMs?: number | null;
    refreshStartedAt?: number | null;
    hasData?: boolean;
  };
  ready: boolean;
  meta: {
    asOf?: string;
    dataEnd?: string | null;
    lastFullMonth?: string;
    counts?: { books: number; launches: number; withEmsal: number };
    levelNote?: string | null;
    warnings?: string[];
  };
  backtest: ({ '6'?: Backtest; '12'?: Backtest; print?: PrintRules }) | null;
  upcoming: UpcomingRow[];
  tracking: TrackingRow[];
  formulas: Array<{ name: string; text: string }>;
  notes: string[];
  /** Son okumada çalışan metin; henüz okunmadıysa yok (şablon gösterilmez). */
  sources: Array<{ id: string; connection: 'logo' | 'crm'; title: string; description: string; sql: string | null; rows: number | null }>;
  can: { decide: boolean; approve: boolean };
  kaynaklar?: Kaynaklar;
};

export type Analog = {
  code: string;
  name: string;
  authors: string | null;
  publisher: string | null;
  library: string | null;
  launch: string;
  score: number;
  reasons: string[];
  sales: number;
  adjusted: number;
  factor: number;
};

export type CurvePoint = {
  month: string;
  label: string;
  share: number;
  low: number;
  base: number;
  high: number;
  pess: number;
  opt: number;
};

export type Horizon = {
  tier: Tier;
  scenarios: Array<{ id: 'kotumser' | 'baz' | 'iyimser'; label: string; units: number; revenue: number | null }>;
  band: { low: number; high: number };
  raw: number;
  /** Yazar geçmişi çarpanından önceki baz (yalnız emsallerden). */
  emsalBase?: number | null;
  curve: CurvePoint[];
  unitRevenue: number | null;
  discount: number | null;
  analogs: Analog[];
  channels: Array<{ channel: string; share: number; units: number }>;
};

/** Yazarın önceki kitapları: emsal tahmini bu düzeye kitap sayısı ve tutarlılık oranında yaklaştırılır. */
export type AuthorHistory = {
  authors: string | null;
  count: number;
  level6: number;
  base6: number;
  weight: number;
  factor: number;
  spread: number;
  books: Array<{ code: string; name: string; authors: string | null; launch: string; sales6: number; sales12: number | null; weight: number }>;
};

export type Forecast = {
  book: BookInfo;
  launch: string;
  launchName: string;
  cutoff: string;
  horizons: Record<string, Horizon>;
  recommendation: {
    units: number;
    rule: string;
    basis: string;
    minimum: number | null;
    stockout6: number | null;
    options: Array<{ rule: string; label: string; units: number; stockout6: number | null; history: RuleStats | null }>;
  };
  reasons: string[];
  author?: AuthorHistory | null;
  mode: 'upcoming' | 'launched' | 'free';
  actual?: Array<{ month: string; label: string; units: number; cum: number }>;
  revised?: Record<string, number | null>;
  reprint?: Reprint | null;
  emsalCrm?: string[];
  emsalOverride?: boolean;
  kaynaklar?: Kaynaklar;
};

export type BookHit = { code: string; name: string; authors: string | null; publisher: string | null; firstPub: string | null; launched: boolean };

export type FreeInput = {
  name: string;
  authors?: string;
  publisher?: string;
  library?: string;
  series?: string;
  audience?: string;
  genre?: string;
  pages?: number | null;
  price?: number | null;
  launch: string;
  emsal?: string[];
};

export type Decision = {
  id: string;
  code: string | null;
  title: string;
  launch: string | null;
  units: number;
  scenario: string;
  recommended: number | null;
  note: string | null;
  status: 'bekliyor' | 'onaylandi' | 'geri_cekildi';
  createdBy: string;
  createdAt: string;
  approvals: { satis: { by: string; at: string } | null; uretim: { by: string; at: string } | null };
  closedBy: string | null;
  closedAt: string | null;
};

/** Dağıtımcı kataloğunda benzer kitaplar (kitap kartında bağlam bilgisi; tahmine girmez). */
export type MarketCounts = {
  baslik: number;
  bilinen: number;
  bilinmeyen: number;
  ilk: number;
  ikinci: number;
  ucVeUstu: number;
  ikinciyeUlasan: number | null;
  ucuncuyeUlasan: number | null;
};

export type MarketTitle = {
  barkod: string;
  ad: string | null;
  yazar: string | null;
  yayinevi: string | null;
  basimYili: number | null;
  baski: number;
  fiyat: number | null;
  sayfa: number | null;
};

export type Market = {
  durum: 'hazir' | 'okunmadi' | 'kategori_yok';
  kaynak: { ad: string; tarih: string | null; kaynakZamani: string | null; ilkGoruntu: string | null };
  kosul: { sayfa: number | null; sayfaAlt: number | null; sayfaUst: number | null; sayfaPay: number; timasHaric: boolean };
  kategori: {
    secili: string | null;
    yontem: 'secim' | 'kitap_kaydi' | 'tur_eslesmesi' | null;
    yontemEtiket: string | null;
    adaylar: string[];
    tur: string | null;
    hata?: string;
  };
  notlar: { baglam: string; baski: string; cikis: string; ilkYil: string };
  kume?: { baslik: number; fiyatli: number; fiyatMedyan: number | null };
  baskilar?: MarketCounts & { yillar: number[]; yilBazinda: Array<MarketCounts & { yil: number }> };
  enCokBasilan?: MarketTitle[];
  cikis?: { toplam: number | null; pencere: { bas: string; son: string } | null; not: string };
  ilkYilHizi?: { deger: number | null; not: string };
  kaynaklar?: Kaynaklar;
};

export type MarketCategory = { kategori: string; ust: string; alt: string; baslik: number };

const P = '/api/v1/management/first-print';

export class NotReadyError extends Error {}

async function call<T>(path: string, method: 'GET' | 'POST' = 'GET', body?: unknown, timeoutMs = 60_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${P}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } | string } | null;
    const detail = j?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message;
    if (res.status === 401) throw new Error('Oturumunuz kapanmış; sayfayı yenileyip yeniden giriş yapın.');
    if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işlem için yetkiniz yok.');
    if (res.status === 503 && typeof detail === 'object' && detail?.code === 'NOT_READY') throw new NotReadyError(msg);
    throw new Error(msg || 'Sunucu yanıt vermedi.');
  }
  return (await res.json()) as T;
}

const qs = (p: Record<string, string | undefined>) => {
  const s = new URLSearchParams(Object.entries(p).filter((e): e is [string, string] => !!e[1])).toString();
  return s ? `?${s}` : '';
};

export const firstPrintApi = {
  summary: () => call<Summary>('/summary'),
  books: (q: string) => call<{ items: BookHit[]; total: number }>(`/books${qs({ q })}`),
  options: () => call<{ publisher: string[]; library: string[]; series: string[]; audience: string[]; lastFullMonth: string }>('/options'),
  forecast: (code: string, launch?: string, emsal?: string[]) =>
    call<Forecast>(`/forecast/${encodeURIComponent(code)}${qs({ launch, emsal: emsal ? emsal.join(',') : undefined })}`),
  free: (body: FreeInput) => call<Forecast>('/forecast', 'POST', body),
  decisions: (code?: string) => call<{ items: Decision[]; kaynaklar?: Kaynaklar }>(`/decisions${qs({ code })}`),
  decide: (body: { code: string | null; title: string; launch: string; units: number; scenario: string; recommended: number; note?: string; forecast?: unknown }) =>
    call<Decision>('/decisions', 'POST', body),
  approve: (id: string, role: 'satis' | 'uretim') => call<Decision>(`/decisions/${id}/approve`, 'POST', { role }),
  withdraw: (id: string) => call<Decision>(`/decisions/${id}/withdraw`, 'POST'),
  market: (p: { code?: string; pages?: number | null; genre?: string | null; kategori?: string }) =>
    call<Market>(`/market${qs({ code: p.code, pages: p.pages ? String(p.pages) : undefined, genre: p.genre || undefined, kategori: p.kategori || undefined })}`),
  marketCategories: () => call<{ tarih: string | null; items: MarketCategory[] }>('/market/categories'),
};

// ---- biçim

export const nf = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const money = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 });
const compactMoney = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', notation: 'compact', maximumFractionDigits: 1 });

export const fmtUnits = (n: number | null | undefined) => (n === null || n === undefined ? '—' : nf.format(n));
export const fmtMoney = (n: number | null | undefined, compact = false) =>
  n === null || n === undefined ? '—' : (compact ? compactMoney : money).format(n);
/** 0,482 → «%48»; boşsa tire. */
export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined || !Number.isFinite(x) ? '—' : `%${(x * 100).toLocaleString('tr-TR', { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
/** İşaretli yüzde: +%12 / −%8. */
export const signedPct = (x: number | null | undefined) =>
  x === null || x === undefined || !Number.isFinite(x) ? '—' : `${x >= 0 ? '+' : '−'}%${Math.round(Math.abs(x) * 100).toLocaleString('tr-TR')}`;

const AY = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
/** '2026-10' → 'Ekim 2026'. */
export function monthName(ym: string | null | undefined): string {
  if (!ym || !/^\d{4}-\d{2}/.test(ym)) return '—';
  return `${AY[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;
}
/** '2026-08-17' → '17 Ağustos 2026'. */
export function dayName(d: string | null | undefined): string {
  if (!d || !/^\d{4}-\d{2}-\d{2}/.test(d)) return '—';
  return `${Number(d.slice(8, 10))} ${AY[Number(d.slice(5, 7)) - 1]} ${d.slice(0, 4)}`;
}

export const TIER: Record<Tier, { label: string; hint: string; tone: 'ok' | 'warn' | 'err' }> = {
  yuksek: { label: 'Yüksek', hint: 'En az üç güçlü emsal (CRM emsali, aynı yazar ya da aynı dizi)', tone: 'ok' },
  orta: { label: 'Orta', hint: 'Bir ya da iki güçlü emsal', tone: 'warn' },
  dusuk: { label: 'Düşük', hint: 'Güçlü emsal yok; tahmin yalnız genel benzerlikten. Geçmişte bu düzeyde aralık da sık tutmadı', tone: 'err' },
};

/** Tahmin → yapılacak baskı adedi seçiminde gösterilecek risk cümlesi. */
export function stockoutText(p: number | null | undefined): string {
  if (p === null || p === undefined) return 'Tükenme olasılığı hesaplanamadı.';
  return `Geçmişte bu tahmin düzeyindeki kitapların ${pct(p)}'ü ilk 6 ayda bu adedi aştı.`;
}

/** Takip listesindeki sapmanın tonu: kötümserin altı uyarı, bazın altı dikkat. */
export function trackTone(row: Pick<TrackingRow, 'alert' | 'deviation'>): 'err' | 'warn' | 'ok' {
  if (row.alert) return 'err';
  if (row.deviation !== null && row.deviation < 0) return 'warn';
  return 'ok';
}
