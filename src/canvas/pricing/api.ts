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

export type Spec = { code?: string | null; pages?: number | null; trim?: string | null; gsm?: number | null; binding?: string | null; vat?: number | null };

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

export type MarketPrice = { id: string; analysisId: string | null; crmBookId: string | null; title: string; publisher: string | null; channel: string | null;
  price: number; pages: number | null; url: string | null; seenOn: string | null; createdBy: string; createdAt: string };

export type ActualRow = {
  code: string; name: string; publisher: string | null; printed: number; printCost: number; printUnit: number | null; lastPrintUnit: number | null;
  lastPrintDate: string | null; sold: number; net: number; avgNet: number | null; unitCost: number | null; cogs: number; profit: number | null;
  margin: number | null; costCoverage: number | null; discount: number | null; price: number | null; costToPrice: number | null;
};
export type Actuals = { kaynaklar?: Kaynaklar; rows: ActualRow[]; count: number; net: number; printCost: number; printed: number; sold: number; margin: number | null;
  sinceYear: number | null; dataEnd: string; offset: number; limit: number };

export type BacklistRow = {
  code: string; name: string; publisher: string | null; price: number; vat: number; pages: number | null; lastPrintDate: string | null; lastPrintQty: number;
  printUnit: number; paperUnit: number | null; unit: number; ratio: number; sold2y: number; avgNet: number | null; proposed: number; increase: number;
};
export type Backlist = { kaynaklar?: Kaynaklar; rows: BacklistRow[]; count: number; target: number | null; measuredTarget: number | null; freshBooks: number; candidates: number; since: string; dataEnd: string };

export type Proposal = { kaynaklar?: Kaynaklar; id: string; title: string; status: AnalysisStatus; statusLabel: string; count: number; params: { target?: number; measuredTarget?: number; dataEnd?: string };
  createdBy: string; createdAt: string; decidedBy: string | null; decidedAt: string | null; decisionNote: string | null;
  items?: Array<{ code: string; name: string; price: number; proposed: number; increase: number; ratio: number; unit: number; sold2y: number; lastPrintDate: string | null }> };

export type Sources = { kaynaklar?: Kaynaklar; sources: Array<{ id: string; connection: 'logo' | 'crm'; title: string; description: string; sql: string; runs: number; stats: { rows: number; ms: number } | null }>;
  copies: Array<{ firm: string; from: string; to: string; last: string }> | null; dataEnd: string | null; asOf: string | null };

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
  backlist: (p: { target?: number | null; minSold?: number }) => send<Backlist>('GET', `/backlist${qs(p)}`),
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
  addMarket: (b: Record<string, unknown>) => send<{ id: string }>('POST', '/market', b),
  deleteMarket: (id: string) => send<{ ok: boolean }>('DELETE', `/market/${enc(id)}`),
  saveDefaults: (b: Partial<Defaults>) => send<Defaults>('PUT', '/defaults', b),
  proposals: () => send<{ items: Proposal[]; kaynaklar?: Kaynaklar }>('GET', '/proposals'),
  proposal: (id: string) => send<Proposal>('GET', `/proposals/${enc(id)}`),
  createProposal: (b: { title: string; codes: string[]; target?: number | null; minSold?: number }) => send<Proposal>('POST', '/proposals', b),
  decideProposal: (id: string, b: { decision: 'onay' | 'ret'; note: string }) => send<Proposal>('POST', `/proposals/${enc(id)}/decide`, b),
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
