import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** Fiyatlama ve maliyet (M9) köprü uçları: /api/v1/pricing/*. */

export type Stage = 'tahmini' | 'kesin';
export type ApproverRole = 'mali' | 'satis' | 'pazarlama' | 'yonetim';
export type AnalysisStatus = 'taslak' | 'onayda' | 'onaylandi' | 'reddedildi' | 'arsiv';
export type FixedKey = 'avans' | 'ceviri' | 'grafik' | 'redaksiyon' | 'pazarlama' | 'diger';

export type Channel = { channel: string; gross: number; net: number; qty: number; rows: number; discount: number; share: number };
export type PaperItem = { code: string; name: string; gsm: number | null; kind: 'ic' | 'kapak'; kg: number; amount: number; perKg: number; last: string | null };
export type PaperTable = {
  items: PaperItem[];
  innerPerKg: number | null;
  innerByGsm: Record<string, number>;
  coverPerKg: number | null;
  bandrol: { code: string; name: string; unit: number; qty: number; last: string | null } | null;
};

export type Defaults = {
  targetMargin: number;
  variableRate: number;
  overheadRate: number;
  sellThrough: number;
  qtys: number[];
  channelMix: Record<string, number> | null;
  updatedBy: string | null;
  updatedAt: string | null;
};

export type Overview = { kaynaklar?: Kaynaklar;
  status: { updatedAt?: number; failedAt?: number; error?: string | null; refreshing: boolean; durationMs?: number; dataEnd?: string };
  measured: {
    dataEnd: string;
    asOf: string;
    copies: Array<{ firm: string; from: string; to: string; last: string }>;
    channels: Channel[];
    paper: PaperTable;
    distribution: { freight: number; net: number; rate: number | null; from: string; to: string };
    discount: number | null;
    books: number;
    printedBooks: number;
    printInvoices: number;
    warnings: string[];
  } | null;
  defaults: Defaults;
  counts: Partial<Record<AnalysisStatus, number>>;
  toApprove: number;
  me: { user: string; canWrite: boolean; approve: Record<ApproverRole, boolean> };
  stages: Record<Stage, string>;
  approvers: Record<ApproverRole, string>;
  required: Record<Stage, ApproverRole[]>;
  fixedLabels: Record<FixedKey, string>;
};

export type BookHit = { code: string; name: string | null; author: string | null; publisher: string | null; price: number | null; pages: number | null; prints: number };

export type Royalty = { rate: number; basis: 'kapak' | 'net'; basisLabel: string | null; on: 'satis' | 'baski' | 'tek'; kindLabel: string | null; advance: number; currency: string };

export type LogoPrint = { date: string | null; invoice: string | null; printer: string | null; qty: number; cost: number; unit: number };
export type CrmPrint = {
  id: string | null; no: number | null; year: number | null; date: string | null; qty: number | null; price: number | null; suggestedQty: number | null;
  pages: number | null; binding: string | null; type: string | null; gsm: number | null; colors: number | null; printer: string | null;
};
export type YearSales = { year: string; qty: number; net: number; gross: number; cogs: number; costedQty: number; soldQty: number; avgNet: number | null; unitCost: number | null };

export type Comparable = {
  code: string; name: string; pages: number | null; binding: string | null; printDate: string | null; printQty: number;
  printUnit: number; printer: string | null; price: number | null; unitCost: number | null; publisher: string | null; library: string | null;
};
export type Comparables = { kaynaklar?: Kaynaklar;
  since: string; until: string; pages: number | null; binding: string | null; band: number; count: number; rows: Comparable[];
  price: { p25: number | null; median: number | null; p75: number | null; n: number };
  pricePerPage: number | null;
  printCurvePerPage: { a: number; b: number; n: number; shape: string; r2?: number | null } | null;
  unitCost: { p25: number | null; median: number | null; p75: number | null };
};

export type PaperCost = {
  perCopy: number | null; parts: { inner: number | null; cover: number | null; bandrol: number | null };
  innerKg: number; coverKg: number; perKg: number | null; coverPerKg: number | null; gsm: number; trim: [number, number];
  waste: number; trimAssumed: boolean; gsmAssumed: boolean; missing: string[];
};

export type Suggested = { kaynaklar?: Kaynaklar;
  printPerCopy: number | null; printService: number | null; printSetup: number | null; paper: PaperCost | null;
  royaltyRate: number | null; royaltyBase: 'kapak' | 'net'; royaltyOn: 'satis' | 'baski'; advance: number | null;
  advanceForeign: { amount: number; currency: string } | null; vat: number; discount: number | null; variableRate: number | null;
  sellThrough: number; targetMargin: number; origin: Record<string, string>; comparables: Comparables;
};

export type Spec = { code?: string | null; pages?: number | null; trim?: string | null; gsm?: number | null; binding?: string | null; vat?: number | null;
  /** Kitap hesabının maliyet alanları (basım Excel'iyle aynı; analizle birlikte saklanır). */
  form?: FormInputs };

export type BookDetail = { kaynaklar?: Kaynaklar;
  book: { id: string | null; name: string | null; code: string; pages: number | null; trim: string | null; price: number | null; vat: number | null;
    author: string | null; publisher: string | null; library: string | null; firstPub: string | null; royalty: Royalty | null };
  prints: LogoPrint[];
  crmPrints: CrmPrint[];
  salesByYear: YearSales[];
  total: { qty: number; net: number; cogs: number; avgNet: number | null; unitCost: number | null; profit: number | null; discount: number | null; costCoverage: number | null };
  spec: Spec;
  suggested: Suggested;
  freelance: { items: Array<{ role: string; status: string; amount: number; package: string; key: FixedKey }>; byKey: Partial<Record<FixedKey, number>> };
  analyses: AnalysisHead[];
  market: MarketPrice[];
  /** Üretim ekranında (M12) bu kitabın baskı kartlarına girilen matbaa teklifleri. */
  quotes: PrinterQuote[];
};

export type PrinterQuote = {
  id: string; cardId: string; printer: string; unitPrice: number | null; totalPrice: number | null; deliveryDay: string | null;
  note: string | null; byName: string; at: string | null; printNo: number | null; printQty: number | null;
};

export type Inputs = {
  printPerCopy?: number | null; printSetup?: number | null; overheadRate?: number | null;
  fixed?: Partial<Record<FixedKey, number>>;
  royaltyRate?: number | null; royaltyBase?: 'kapak' | 'net'; royaltyOn?: 'satis' | 'baski';
  vat?: number | null; discount?: number | null; variableRate?: number | null; sellThrough?: number | null;
  targetMargin?: number | null; qtys?: number[]; price?: number | null; chosenQty?: number | null;
};

export type Scenario = {
  qty: number; printUnit: number; printTotal: number; fixedTotal: number; unitCost: number; totalCost: number; parts: Record<string, number>;
  price?: number; netUnit?: number; royaltyUnit?: number; variableUnit?: number; sold?: number; revenue?: number; royaltyTotal?: number;
  profit?: number; margin?: number | null; breakeven?: number | null; breakevenShare?: number | null; costToPrice?: number;
};

export type CalcResult = { kaynaklar?: Kaynaklar;
  scenarios: Scenario[];
  floors: Array<{ qty: number; price: number | null; raw?: number; reason: string | null }>;
  recommendation: { floor: number | null; floorReason: string | null; band: [number | null, number | null]; median: number | null; price: number | null; notes: string[] };
  channels: Array<{ channel: string; discount: number; share: number; netUnit: number; royaltyUnit: number; variableUnit: number; unitCost: number; contribution: number; margin: number | null }>;
  summary: { price: number | null; qty: number; unitCost: number; totalCost: number; breakeven: number | null | undefined; margin: number | null | undefined;
    profit: number | null | undefined; recommended: number | null; floor: number | null; band: [number | null, number | null]; targetMargin: number };
  comparables: Comparables | null;
  marketCount: number;
  dataEnd?: string | null;
};

export type Approval = { id: string; version: number; role: ApproverRole; roleLabel: string; decision: 'onay' | 'ret'; note: string | null; by: string; at: string };

export type AnalysisHead = {
  id: string; title: string; stage: Stage; stageLabel: string; status: AnalysisStatus; statusLabel: string; version: number;
  crmBookId: string | null; stockCode: string | null; chosenPrice: number | null; chosenQty: number | null; note: string | null;
  createdBy: string; createdAt: string; updatedBy: string | null; updatedAt: string | null; submittedBy: string | null; submittedAt: string | null;
  required: Array<{ role: ApproverRole; label: string }>; approvals: Approval[]; summary?: CalcResult['summary'] | null;
};
export type Analysis = AnalysisHead & { kaynaklar?: Kaynaklar; specs: Spec & { title?: string }; inputs: Inputs; result: CalcResult | null; history: Approval[]; market: MarketPrice[] };

/** Dağıtımcı kataloğundaki (Başarı) TİMAŞ dışı başlıkların fiyat özeti; köprü `pricing/dagitim.py`. */
export type DistStats = {
  n: number; p25: number | null; median: number | null; p75: number | null;
  perPage: { median: number | null; n: number };
  /** D&R satış fiyatı ÷ D&R liste fiyatı ortancası (sitelerden silinmemiş ürünler). */
  dr: { ratioMedian: number | null; n: number };
};
export type DistCategory = { kategori: string; ust: string; alt: string | null; n: number; puan?: number };
export type Distributor = {
  kaynaklar?: Kaynaklar;
  hazir: boolean;
  kod: string | null;
  kaynak: { basari: string | null; dr: string | null; basariEtiket: string; drEtiket: string };
  not: string;
  mesaj?: string | null;
  /** «Dağıtımcı kataloğundan (n başlık, GG.AA.YYYY)». */
  etiket: string | null;
  kume: number;
  kategori: {
    secili: string | null; yol: 'secim' | 'kendi' | 'ad' | 'yok'; aciklama: string; kitaplik: string | null;
    kendi: { barkod: string; kategori: string; sayfa: number | null; kapak: string | null; fiyat: number | null; son: string | null } | null;
    adaylar: DistCategory[];
  } | null;
  suzgec: {
    sayfa: number | null; sayfaAralik: [number, number] | null; sayfaUygulandi: boolean; kapak: string | null; kapakSinifi: string | null;
    kapakUygulandi: boolean; notlar: string[];
  } | null;
  tum: DistStats | null;
  sonYillar: (DistStats & { yillar: number[] }) | null;
};

export type MarketPrice = { id: string; analysisId: string | null; crmBookId: string | null; title: string; publisher: string | null; channel: string | null;
  price: number; pages: number | null; url: string | null; seenOn: string | null; createdBy: string; createdAt: string };

export type ActualRow = {
  code: string; name: string; publisher: string | null; printed: number; printCost: number; printUnit: number | null; lastPrintUnit: number | null;
  lastPrintDate: string | null; sold: number; net: number; avgNet: number | null; unitCost: number | null; cogs: number; profit: number | null;
  margin: number | null; costCoverage: number | null; discount: number | null; price: number | null; costToPrice: number | null;
};
export type Actuals = { kaynaklar?: Kaynaklar; rows: ActualRow[]; count: number; net: number; printCost: number; printed: number; sold: number; margin: number | null;
  sinceYear: number | null; dataEnd: string; offset: number; limit: number };

/** Eski kitap karşılaştırması: CRM'deki güncel fiyat ↔ «Kitap hesabı»nın aynı zinciriyle bizim fiyatımız (köprü `pricing/karsilastir.py`). */
export type CompareStatus = 'zam' | 'yuksek' | 'esit' | 'hesaplanamadi';
export type CompareRow = {
  code: string; name: string; author: string | null; publisher: string | null; library: string | null; firstPub: string | null;
  firstPrint: string | null; lastPrint: string | null; pages: number | null; price: number; new: boolean; sold2y: number; net2y: number;
  status: CompareStatus; reason?: string; ours?: number | null; floor?: number | null; median?: number | null; band?: [number | null, number | null];
  unitCost?: number | null; qty?: number | null; margin?: number | null; targetMargin?: number | null; comparables?: number | null;
  diff?: number; diffPct?: number;
};
export type CompareSort = 'diffPct' | 'diffPctAsc' | 'sold' | 'name';
export type Compare = { kaynaklar?: Kaynaklar;
  /** Güncel girdilerle hesap hazır mı; değilse arka planda sürüyor (`stale`: gösterilen önceki hesap). */
  ready: boolean; stale: boolean; error: string | null; startedAt: number | null;
  kur: { USD: number; EUR: number } | null; kurKaynak: 'logo' | 'elle'; logoKur: Partial<Record<'USD' | 'EUR', { rate: number; date: string | null }>>;
  dataEnd: string | null; since: string | null; targetMargin: number | null; seconds: number | null; offset: number; limit: number;
  rows?: CompareRow[]; count?: number; total?: number; counts?: Record<CompareStatus, number>; avgDiffPct?: number | null; newHidden?: number;
};
export type CompareQuery = { q?: string; status?: CompareStatus | ''; new?: boolean; minSold?: number | null; sort?: CompareSort; offset?: number; limit?: number };

export type Proposal = { kaynaklar?: Kaynaklar; id: string; title: string; status: AnalysisStatus; statusLabel: string; count: number; params: {
    /** Eski teklifler (maliyet/fiyat oranı yöntemi). */ target?: number; measuredTarget?: number; dataEnd?: string;
    /** «Kitap hesabı» yöntemi. */ method?: 'kitap-hesabi'; targetMargin?: number; kur?: { USD: number; EUR: number } | null; kurKaynak?: 'logo' | 'elle' };
  createdBy: string; createdAt: string; decidedBy: string | null; decidedAt: string | null; decisionNote: string | null;
  items?: Array<{ code: string; name: string; price: number; proposed: number; increase: number; unit: number; qty?: number; margin?: number | null; sold2y: number; lastPrintDate: string | null }> };

export type Sources = { kaynaklar?: Kaynaklar; sources: Array<{ id: string; connection: 'logo' | 'crm'; title: string; description: string; sql: string; runs: number; stats: { rows: number; ms: number } | null }>;
  copies: Array<{ firm: string; from: string; to: string; last: string }> | null; dataEnd: string | null; asOf: string | null };

// ---- maliyet formu (basım Excel'iyle aynı hesap; köprü pricing/form.py)
export type FormPart = { kagit?: string | null; en?: number | null; boy?: number | null; gr?: number | null; verim?: number | null; fire?: number | null;
  renk?: number | null; iscilik?: boolean; sayfa?: number | null;
  /** Kitaba özel elle kâğıt fiyatı (₺/kg; tabaka malzemede ₺/adet). Boşsa Logo alışı. */
  kgFiyat?: number | null };
export type FormInputs = {
  yayinevi?: string | null; kitap?: string; yazar?: string; sayfa?: number | null; adet?: number | null; ebat?: string | null;
  fiyat?: number | null; simdikiFiyat?: number | null; ozelIskonto?: number | null; matbaaAyar?: number | null;
  kur?: { USD?: number | null; EUR?: number | null } | null;
  ic: FormPart; renkli: FormPart;
  kapak: FormPart & { bolen?: number | null; selofan: { var: boolean; tur: string; ciftYuz?: boolean; bolen?: number | null };
    lak: { var: boolean; tur: string | null }; yaldiz: boolean; gofre: boolean; gren: number; klise: { adet: number | null; ebat: string | null } };
  ekler: Record<'yanKagit' | 'somiz' | 'ayrac' | 'mukavva' | 'ciltBezi' | 'digerKagit', FormPart> & {
    kenarBoyama: number | null; vakum: boolean; icSelofan: { var: boolean; tur: string } };
  cilt: { tur: string; birim: number | null };
  diger: { kapakUcreti: number | null; kapakBolen: number | null; kapakEtiket: string | null; nakliye: number | null; mizanpaj: number | null; diger: number | null;
    /** Dijital formun diğer giderleri (Excel J20–J28). */
    yanKagit?: number | null; nakliyeAdet?: number | null; hediye?: number | null; zayiat?: number | null; reklam?: number | null };
  telif: number | null; dolayli: number | null;
  /** Baskı türü: «ofset» (varsayılan) ya da «dijital» (TBK dijital Excel'i; alanları `dijital` ve `diger`'in dijital kalemleri). */
  baski?: 'ofset' | 'dijital';
  dijital?: DigitalInputs;
};
export type DigitalInputs = {
  icKagit: string | null; icBirim?: number | null; renkliSayfa: number | null; renkliKagit: string | null; renkliBirim?: number | null;
  kapakKagit: string | null; kapakGr: number | null; kapakBirim?: number | null; pay: number | null;
  ekler: { ayracAtma: boolean; ayracRenk: number | null; gofre: boolean; kulakli: boolean; kapakRenk: number | null; selofan: boolean; lokalLak: boolean };
};
export type DigitalTariff = {
  guncelleme: string | null; kagitlar: string[]; kapakKagitlari: string[];
  tablo: Array<{ ebat: string; fiyat: Record<string, number> }>;
  pay: number; dolayli: number; dolayliYayinevi?: Record<string, number>; fire: { kapak: number }; kapak: { en: number; boy: number; verim: number };
  kalemler: Record<string, { m: number; n?: number; label: string }>; publishers: Record<string, number>; kapakGramajlari: number[];
};
export type ExtraKey = keyof Omit<FormInputs['ekler'], 'kenarBoyama' | 'vakum' | 'icSelofan'>;
export type TariffPaper = { name: string; base: number; cur: 'USD' | 'EUR'; unit: 'ton' | 'adet' };
export type TariffPrice = { label: string | null; m: number; n: number; eski?: Array<number | null> };
export type Tariff = {
  kur: { USD: number; EUR: number };
  /** «logo»: Logo'daki son döviz faturalarının kuru (o dövizle fatura yoksa yukarıdaki kur); «elle»: hep yukarıdaki kur. */
  kurKaynak: 'logo' | 'elle';
  vade: { oran: number; ay: number }; papers: TariffPaper[]; prices: Record<string, TariffPrice>;
  trims: Array<{ ebat: string; taslama: number | null; kapakTakma: number | null; mukavvaVerim: number | null; icVerim: number | null; icEn: number | null; icBoy: number | null }>;
  cliche: Record<string, { pieces: number; price: number }>; publishers: Record<string, number>; fire: Record<string, number>;
  dolayli: number; kapakBolen: number; updatedBy: string | null; updatedAt: string | null; isDefault: boolean;
  dijital?: DigitalTariff;
};
export type FormSetup = { kaynaklar?: Kaynaklar;
  tariff: Tariff; bindings: string[]; laminates: string[]; varnishes: string[];
  extras: Record<ExtraKey, { row: number; label: string; kind: 'kg' | 'tabaka' }>;
  logoKur: Partial<Record<'USD' | 'EUR', { rate: number; date: string | null }>>; paper: PaperTable | null; dataEnd: string | null; canWrite: boolean;
  inputs: FormInputs; origin: Record<string, string>; paperSource: 'logo' | 'tarife';
  book?: { code: string; name: string | null; author: string | null; publisher: string | null; price: number | null; pages: number | null; trim: string | null;
    lastPrint: LogoPrint | null; logoUnitCost: number | null };
};
export type FormLine = { key: string; group: 'kagit' | 'matbaa' | 'telif' | 'diger'; name: string; excel: string; total: number; perCopy: number;
  material?: string; sheets?: number; kg?: number; unitPrice?: number; unit?: string; priceSource?: 'logo' | 'tarife' | 'elle'; plates?: number; formula?: string };
export type FormPrice = { name: string; unit: 'kg' | 'adet'; tarife: number; used: number; source: 'logo' | 'tarife' | 'elle'; tarifeText: string; gsm: number | null;
  logo?: { perKg: number; kg: number; cards: number; sameGsm: boolean; last: string | null; names: string[] } | null };
export type FormSummary = {
  forma: number; kagitAdet: number; matbaaAdet: number; telifAdet: number; kitapMaliyeti: number; kitapMaliyetiToplam: number; matbaaToplam: number;
  digerToplam: number; toplam: number; dolayliOran: number; dolayli: number; genelToplam: number; birimMaliyet: number; iskonto: number; kapakFiyati: number;
  satisFiyati: number; karAdet: number; toplamKar: number; karYuzde: number | null; adet: number; sayfa: number; kapakPayi: number; sayfaBasi: number;
  baski?: 'dijital'; ekPay?: number; kapakTabaka?: number;
};
export type FormResult = { kaynaklar?: Kaynaklar;
  lines: FormLine[]; summary: FormSummary; warnings: string[]; paperSource: 'logo' | 'tarife' | 'dijital'; prices: FormPrice[]; kur: { USD: number; EUR: number }; vade: number | null;
  baski?: 'dijital'; tabloTarihi?: string | null;
  fire: { ic: number; icPay: number };
  analysis: { printService: number; paperPerCopy: number; printSetup: number; overheadRate: number; royaltyRate: number; royaltyBase: 'kapak'; royaltyOn: 'baski';
    chosenQty: number; price: number | null; fixed: { grafik: number; diger: number }; note: string } | null;
  dataEnd: string | null;
};

const BASE = '/api/v1/pricing';

/** Özet sorgusunun anahtarı: yazan her işlem bunu tazeler. */
export const overviewKey = ['pricing', 'overview'] as const;

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 60_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${BASE}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '');
  return p.length ? `?${p.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&')}` : '';
};
const enc = encodeURIComponent;
const compareParams = (p: CompareQuery) => ({ ...p, new: p.new ? 'true' : undefined, minSold: p.minSold || undefined });

export const pricingApi = {
  overview: () => send<Overview>('GET', '/overview'),
  refresh: () => send<{ started: boolean }>('POST', '/refresh'),
  sources: () => send<Sources>('GET', '/sources'),
  books: (q: string) => send<{ items: BookHit[]; total: number }>('GET', `/books${qs({ q })}`),
  book: (code: string) => send<BookDetail>('GET', `/books/${enc(code)}`),
  suggest: (spec: Spec) => send<Suggested>('POST', '/suggest', spec),
  calc: (body: { inputs: Inputs; spec: Spec; marketPrices?: number[] }) => send<CalcResult>('POST', '/calc', body),
  actuals: (p: { q?: string; since?: number | null; sort?: string; offset?: number; limit?: number }) =>
    send<Actuals>('GET', `/actuals${qs(p)}`),
  compare: (p: CompareQuery) => send<Compare>('GET', `/compare${qs(compareParams(p))}`),
  /** Süzgece uyan bütün satırlar (sayfa yok); Excel eşi `xlsxUrl` ile. */
  compareCsvUrl: (p: CompareQuery) => `${ENGINE_BASE}${BASE}/compare.csv${qs(compareParams({ ...p, offset: undefined, limit: undefined }))}`,
  analyses: (p: { status?: string; q?: string } = {}) =>
    send<{ items: AnalysisHead[]; total: number; counts: Record<string, number>; kaynaklar?: Kaynaklar }>('GET', `/analyses${qs(p)}`),
  analysis: (id: string) => send<Analysis>('GET', `/analyses/${enc(id)}`),
  create: (b: Record<string, unknown>) => send<Analysis>('POST', '/analyses', b),
  update: (id: string, b: Record<string, unknown>) => send<Analysis>('PATCH', `/analyses/${enc(id)}`, b),
  submit: (id: string) => send<Analysis>('POST', `/analyses/${enc(id)}/submit`),
  withdraw: (id: string) => send<Analysis>('POST', `/analyses/${enc(id)}/withdraw`),
  archive: (id: string) => send<Analysis>('POST', `/analyses/${enc(id)}/archive`),
  decide: (id: string, b: { role: ApproverRole; decision: 'onay' | 'ret'; note: string; version: number }) =>
    send<Analysis>('POST', `/analyses/${enc(id)}/decide`, b),
  distributor: (p: { code?: string | null; kategori?: string | null; pages?: number | null; kapak?: string | null }) =>
    send<Distributor>('GET', `/distributor${qs(p)}`),
  distributorCategories: () =>
    send<{ tarih: string | null; items: DistCategory[]; not: string; kaynaklar?: Kaynaklar }>('GET', '/distributor/categories'),
  addMarket: (b: Record<string, unknown>) => send<{ id: string }>('POST', '/market', b),
  deleteMarket: (id: string) => send<{ ok: boolean }>('DELETE', `/market/${enc(id)}`),
  saveDefaults: (b: Partial<Defaults>) => send<Defaults>('PUT', '/defaults', b),
  proposals: () => send<{ items: Proposal[]; kaynaklar?: Kaynaklar }>('GET', '/proposals'),
  proposal: (id: string) => send<Proposal>('GET', `/proposals/${enc(id)}`),
  createProposal: (b: { title: string; codes: string[] }) => send<Proposal>('POST', '/proposals', b),
  decideProposal: (id: string, b: { decision: 'onay' | 'ret'; note: string }) => send<Proposal>('POST', `/proposals/${enc(id)}/decide`, b),
  formSetup: (kitap?: string | null) => send<FormSetup>('GET', `/form/setup${qs({ kitap })}`),
  formCalc: (b: { inputs: FormInputs }) => send<FormResult>('POST', '/form/calc', b),
  saveTariff: (b: Omit<Partial<Tariff>, 'dijital'> & { reset?: boolean; dijital?: Partial<DigitalTariff> }) => send<Tariff>('PUT', '/form/tariff', b),
};

// ---- biçimler
const money0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const money2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const n0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const pct1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });

const ok = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);
/** Kuruşlu tutar (birim maliyet gibi küçük sayılar). */
export const tl2 = (v: number | null | undefined) => (ok(v) ? `${money2.format(v)} ₺` : '—');
/** Yuvarlak tutar (toplamlar). */
export const tl0 = (v: number | null | undefined) => (ok(v) ? `${money0.format(v)} ₺` : '—');
export const num = (v: number | null | undefined) => (ok(v) ? n0.format(v) : '—');
/** 0,153 → %15,3 */
export const pct = (v: number | null | undefined) => (ok(v) ? `%${pct1.format(v * 100)}` : '—');
/** Milyon ₺ kısa yazımı: 12.345.678 → 12,3 Mn ₺ */
export const mn = (v: number | null | undefined) =>
  ok(v) ? (Math.abs(v) >= 1_000_000 ? `${pct1.format(v / 1_000_000)} Mn ₺` : tl0(v)) : '—';

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
export const day = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : dayFmt.format(d);
};

/** Kullanıcının yazdığı sayı: virgül varsa Türkçe yazım (1.250,50); «4.000» gibi üçlü gruplar binlik. Boşsa null. */
export const parseNum = (raw: string | number | null | undefined): number | null => {
  const s = String(raw ?? '').trim().replace(/\s|₺|%/g, '');
  if (!s) return null;
  const v = s.includes(',') ? Number(s.replace(/\./g, '').replace(',', '.')) : Number(/^\d{1,3}(\.\d{3})+$/.test(s) ? s.replace(/\./g, '') : s);
  return Number.isFinite(v) ? v : null;
};
/** Sayıyı düzenleme kutusuna Türkçe ondalıkla koyar. */
export const editNum = (v: number | null | undefined, digits = 2) =>
  ok(v) ? String(Math.round(v * 10 ** digits) / 10 ** digits).replace('.', ',') : '';
/** Oran (0,15) ↔ yüzde kutusu (15). */
export const editPct = (v: number | null | undefined) => (ok(v) ? editNum(v * 100, 2) : '');
export const parsePct = (raw: string) => {
  const v = parseNum(raw);
  return v == null ? null : v / 100;
};

export const STATUS_TONE: Record<AnalysisStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  taslak: 'muted',
  onayda: 'warn',
  onaylandi: 'ok',
  reddedildi: 'err',
  arsiv: 'muted',
};
