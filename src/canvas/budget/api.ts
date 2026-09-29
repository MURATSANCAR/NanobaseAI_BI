import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';
import { normalizeTrNumber } from '../components/trNumber';

/** M46 Bütçe ekranının köprü uçları: /api/v1/budget/*. */

export type Scenario = 'muhafazakar' | 'temel' | 'iyimser';
export type PlanStatus = 'taslak' | 'onayda' | 'onayli' | 'arsiv';
export type Segment = 'yeni' | 'backlist';
export type TrackState = 'iyi' | 'izle' | 'sapma' | 'baslamadi';
export type DeptState = 'normal' | 'yaklasti' | 'asim' | 'baslamadi';

export type BudgetParams = {
  hacim: Record<Scenario, number>;
  fiyat: number;
  fiyatKaynak?: string;
  gider: number;
  giderKaynak?: string;
  marjDegisim: number;
  esik: number;
  uyariKapsam?: number;
  tahmin: boolean;
  pencere?: string;
};

export type PlanTotals = {
  segments: Partial<Record<Segment, { kitap: number; adet: number; ciro: number; brutKar: number }>>;
  program: { ekBaslik: number; adet: number; ciro: number; brutKar: number };
  adet: number;
  ciro: number;
  brutKar: number;
  marj: number | null;
  gider: number;
  kitap: number;
};

export type Plan = {
  id: string;
  year: number;
  scenario: Scenario;
  scenarioLabel: string;
  version: number;
  status: PlanStatus;
  statusLabel: string;
  title: string;
  note: string | null;
  params: BudgetParams;
  basis: {
    pencere: string;
    veriSonu: string | null;
    tahmin?: {
      kullanildi: boolean;
      baslangic?: string | null;
      /** Senaryonun tabanı hangi tahmin kantili (muhafazakâr p10, temel p50, iyimser p90; kantil yoksa p50). */
      kantil?: 'p10' | 'p50' | 'p90' | null;
      /** Tahminli backlist kitaplarının 12 aylık bandı (adet). `aralik` false ise p10/p90 yok. */
      bant?: { kitap: number; p10: number | null; p50: number; p90: number | null; aralik: boolean } | null;
    };
    sirketMarj?: number | null;
    dagilim?: { adet: number[]; ciro: number[] };
  };
  revisionOf: string | null;
  revisionReason: string | null;
  createdBy: string;
  createdAt: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
  submittedBy: string | null;
  submittedAt: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
  decisionNote: string | null;
  totals: PlanTotals;
  archived?: string | null;
};

export type BookTrack = {
  beklenenAdet: number;
  beklenenCiro: number;
  gercekAdet: number;
  gercekCiro: number;
  gercekMarj: number | null;
  oranAdet: number | null;
  oranCiro: number | null;
  durum: TrackState;
};

export type BookTarget = {
  stokKodu: string;
  ad: string | null;
  segment: Segment;
  segmentLabel: string;
  yayinevi: string | null;
  kitaplik: string | null;
  ilkYayin: string | null;
  adet: number;
  ciro: number;
  marj: number | null;
  brutKar: number | null;
  oneri: Record<string, unknown> & { adet?: number; ciro?: number; marj?: number | null; yontem?: string };
  elle: boolean;
  note: string | null;
  editedBy: string | null;
  editedAt: string | null;
  izleme?: BookTrack;
};

export type BookPage = {
  items: BookTarget[];
  total: number;
  page: number;
  pageSize: number;
  yayinevleri: string[];
  izleme: { asof: string | null; esik?: number; gecenPay?: number };
  /** Sorgu bilgisi (her rakamın SQL'i ve hesabı): `<SqlInfo k={…kaynaklar} alan="…" />`. */
  kaynaklar?: Kaynaklar;
};

export type ProgramLine = {
  yayinevi: string;
  baslik: number;
  bilinen: number;
  ekBaslik: number;
  baslikAdet: number;
  baslikCiro: number;
  marj: number | null;
  adet: number;
  ciro: number;
  oneri: Record<string, unknown>;
  elle: boolean;
  note: string | null;
};

export type DeptLine = {
  merkezKodu: string;
  merkezAdi: string | null;
  hesap: string;
  hesapAdi: string | null;
  aylar: number[];
  yillik: number;
  oneri: { taban?: number[]; gider?: number; aylar?: number[] };
  elle: boolean;
  note: string | null;
  izleme?: { butceDonem: number; gercek: number; gercekAylar: number[]; kullanim: number | null; buAyKullanim: number | null; durum: DeptState };
};

export type GroupTrack = {
  ad?: string;
  kitap?: number;
  hedefCiro: number;
  hedefAdet: number;
  beklenenCiro: number;
  beklenenAdet: number;
  gercekCiro: number;
  gercekAdet: number;
  oran: number | null;
  durum: TrackState;
};

export type Tracking = {
  year: number;
  plan: Plan | null;
  asof?: string | null;
  esik?: number;
  gecenPay?: number;
  /** Kitap uyarısının kapsamı: hedef cirosunun bu payını oluşturan kitaplar. */
  uyariKapsam?: { pay: number; kitap: number; sapma: number };
  kitapHedefleri?: GroupTrack;
  sirket?: GroupTrack;
  program?: { hedefCiro: number; beklenenCiro: number };
  hedefDisi?: { ciro: number; adet: number; kitap: number };
  durumlar?: Record<TrackState, number>;
  segmentler?: GroupTrack[];
  yayinevleri?: GroupTrack[];
  aylar?: Array<{ ay: number; hedef: number; gercek: number | null; gecen: number }>;
  gider?: { butce: number; butceDonem: number; gercek: number; kullanim: number | null; asim: number; yaklasti: number };
  /** Tahmini yıl sonu kapanışı (kitap hedefleri, ciro): gerçekleşen + kalan günlerin tahmin bandı. Tahmin yoksa null. */
  yilSonu?: YearEnd | null;
  kaynaklar?: Kaynaklar;
};

export type YearEnd = {
  kitap: number;
  hedefCiro: number;
  gercekCiro: number;
  kapsamPay: number | null;
  p10: number | null;
  p50: number;
  p90: number | null;
  aralik: boolean;
  not: string | null;
  oranP50: number | null;
  baslangic: string | null;
  eksikAylar: number[];
  asof: string;
};

export type Deviation = {
  id: string;
  year: number;
  planId: string;
  kind: 'satis' | 'gider' | 'revizyon';
  scope: 'kitap' | 'yayinevi' | 'segment' | 'toplam' | 'merkez';
  key: string;
  label: string | null;
  ratio: number | null;
  expected: number | null;
  actual: number | null;
  gap: number | null;
  detail: Record<string, unknown>;
  modules: string[];
  status: 'acik' | 'kapandi' | 'bilgi';
  firstAt: string | null;
  lastAt: string | null;
  closedAt: string | null;
  notifiedAt: string | null;
};

export type RefreshStatus = {
  running: boolean;
  step: string | null;
  startedAt: number | null;
  finishedAt?: number;
  error: string | null;
  dataEnd: string | null;
  dataEndAt: string | null;
  books: { rows?: number; crm?: number; crmError?: string | null; _at?: string };
  years: Record<string, { rows?: number; ciro?: number; at?: string; gider?: { rows?: number; tutar?: number; at?: string } }>;
};

export type BudgetMeta = {
  scenarios: Record<Scenario, string>;
  statuses: Record<PlanStatus, string>;
  segments: Record<Segment, string>;
  months: string[];
  threshold: number;
  earlyWarning: number;
  years: number[];
  defaultYear: number | null;
  data: RefreshStatus;
  me: { username: string; display: string; canEdit: boolean; canApprove: boolean };
};

export type Defaults = BudgetParams & { tahminVar: boolean; tahminBaslangic?: string | null; kaynaklar?: Kaynaklar };

export type Compare = {
  year: number;
  items: Plan[];
  taban: { pencere: string; ciro: number; adet: number; gider: number } | null;
  kaynaklar?: Kaynaklar;
};

const B = '/api/v1/budget';

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
  if (res.status === 403) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export const budgetApi = {
  meta: () => send<BudgetMeta>('GET', '/meta'),
  status: () => send<RefreshStatus>('GET', '/status'),
  refresh: () => send<RefreshStatus & { started: boolean }>('POST', '/refresh', {}),
  plans: (year?: number) => send<{ items: Plan[]; years: number[]; kaynaklar?: Kaynaklar }>('GET', `/plans${qs({ year })}`),
  defaults: (year: number) => send<Defaults>('GET', `/defaults${qs({ year })}`),
  generate: (year: number, scenarios: Scenario[], params: Partial<BudgetParams>) =>
    send<{ items: Plan[] }>('POST', '/plans/generate', { year, scenarios, params }, 300_000),
  plan: (id: string) => send<Plan>('GET', `/plans/${enc(id)}`),
  updatePlan: (id: string, b: { title?: string; note?: string }) => send<Plan>('PATCH', `/plans/${enc(id)}`, b),
  deletePlan: (id: string) => send<{ ok: boolean }>('DELETE', `/plans/${enc(id)}`),
  recompute: (id: string, params: Partial<BudgetParams>) => send<Plan>('POST', `/plans/${enc(id)}/recompute`, { params }, 300_000),
  submit: (id: string) => send<Plan>('POST', `/plans/${enc(id)}/submit`, {}),
  withdraw: (id: string) => send<Plan>('POST', `/plans/${enc(id)}/withdraw`, {}),
  approve: (id: string, note?: string) => send<Plan>('POST', `/plans/${enc(id)}/approve`, { note }),
  reject: (id: string, note: string) => send<Plan>('POST', `/plans/${enc(id)}/reject`, { note }),
  revise: (id: string, reason: string) => send<Plan>('POST', `/plans/${enc(id)}/revise`, { reason }),
  books: (id: string, p: { segment?: string; q?: string; yayinevi?: string; sort?: string; page?: number; durum?: string }) =>
    send<BookPage>('GET', `/plans/${enc(id)}/books${qs(p)}`),
  addBook: (id: string, b: { stokKodu: string; adet: number; ciro: number; marj?: number | null; note?: string }) =>
    send<BookTarget>('POST', `/plans/${enc(id)}/books`, b),
  updateBook: (id: string, code: string, b: { adet?: number; ciro?: number; marj?: number | null; note?: string }) =>
    send<BookTarget>('PATCH', `/plans/${enc(id)}/books/${enc(code)}`, b),
  deleteBook: (id: string, code: string) => send<{ ok: boolean }>('DELETE', `/plans/${enc(id)}/books/${enc(code)}`),
  program: (id: string) => send<{ items: ProgramLine[]; kaynaklar?: Kaynaklar }>('GET', `/plans/${enc(id)}/program`),
  updateProgram: (id: string, yayinevi: string, b: { ekBaslik?: number; baslikAdet?: number; baslikCiro?: number; marj?: number | null }) =>
    send<ProgramLine>('PATCH', `/plans/${enc(id)}/program/${enc(yayinevi)}`, b),
  departments: (id: string) => send<{ items: DeptLine[]; asof: string | null; kaynaklar?: Kaynaklar }>('GET', `/plans/${enc(id)}/departments`),
  updateDept: (id: string, center: string, hesap: string, b: { yillik?: number; aylar?: number[] }) =>
    send<DeptLine>('PATCH', `/plans/${enc(id)}/departments/${enc(center)}/${enc(hesap)}`, b),
  compare: (year: number) => send<Compare>('GET', `/compare${qs({ year })}`),
  tracking: (year: number, plan?: string) => send<Tracking>('GET', `/tracking${qs({ year, plan })}`, undefined, 180_000),
  deviations: (year: number, p: { status?: string; kind?: string; page?: number } = {}) =>
    send<{ items: Deviation[]; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar }>('GET', `/deviations${qs({ year, ...p })}`),
  exportUrl: (id: string) => `${ENGINE_BASE}${B}/plans/${enc(id)}/export.csv`,
};

/* ------------------------------------------------------------------ biçim */

const money0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const pct1 = new Intl.NumberFormat('tr-TR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
const pct0 = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 0 });

export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money0.format(v)} ₺`);
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtPct = (v: number | null | undefined, digits: 0 | 1 = 1) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : (digits ? pct1 : pct0).format(v);

/** 848.110.178 → «848,1 Mn ₺» (KPI kutuları için). */
export function fmtShort(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  const f = (x: number, u: string) => `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(x)} ${u}`;
  if (a >= 1e9) return f(v / 1e9, 'Mr');
  if (a >= 1e6) return f(v / 1e6, 'Mn');
  if (a >= 1e3) return f(v / 1e3, 'B');
  return money0.format(v);
}

/** «1.234,5» ya da «1234.5» → sayı; boşsa null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, '').replace(/₺|%/g, '');
  if (!t) return null;
  const norm = normalizeTrNumber(t);
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

export const TRACK: Record<TrackState, { label: string; pill: string; bar: string }> = {
  iyi: { label: 'Hedefte', pill: 'bg-emerald-50 text-emerald-700', bar: 'bg-emerald-500' },
  izle: { label: 'İzlenmeli', pill: 'bg-amber-50 text-amber-800', bar: 'bg-amber-400' },
  sapma: { label: 'Sapma', pill: 'bg-red-50 text-red-700', bar: 'bg-red-500' },
  baslamadi: { label: 'Başlamadı', pill: 'bg-slate-100 text-canvas-muted', bar: 'bg-slate-300' },
};

export const DEPT: Record<DeptState, { label: string; pill: string }> = {
  normal: { label: 'Bütçe içinde', pill: 'bg-emerald-50 text-emerald-700' },
  yaklasti: { label: 'Sınıra yakın', pill: 'bg-amber-50 text-amber-800' },
  asim: { label: 'Aşıldı', pill: 'bg-red-50 text-red-700' },
  baslamadi: { label: 'Dönem başlamadı', pill: 'bg-slate-100 text-canvas-muted' },
};

export const STATUS_TONE: Record<PlanStatus, 'ok' | 'warn' | 'muted' | 'violet'> = {
  taslak: 'muted',
  onayda: 'warn',
  onayli: 'ok',
  arsiv: 'muted',
};

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return dayFmt.format(new Date(Date.UTC(y, m - 1, d)));
}
