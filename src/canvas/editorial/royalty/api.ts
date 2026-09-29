import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders, type CrmLicense, type CrmRight } from '../../engine';
import { httpErrorText } from '../../httpError';
import type { Kaynaklar } from '../../components/sqlInfo';

/** Köprü cevabındaki sorgu bilgisi (her rakamın sorgusu ve hesabı). */
type K = { kaynaklar?: Kaynaklar };

/** M54 Telif dönemi ve haklar: köprü uçları /api/v1/royalty/* ve /api/v1/rights/*. */

export type RunStatus = 'taslak' | 'hesaplaniyor' | 'hesaplandi' | 'onayda' | 'onaylaniyor' | 'onayli' | 'iptal';
export type LineStatus = 'hesaplandi' | 'istisna' | 'haric';
export type Money4 = { gross: number; advance: number; withholding: number; net: number; count?: number };
export type RunSummary = {
  lines?: number;
  counts?: Record<LineStatus, number>;
  reasons?: Record<string, number>;
  totals?: Record<string, Money4>;
  missingYears?: number[];
  fx?: Record<string, { rate: number; on: string; source: string } | null>;
  withholdingPct?: number | null;
  dataIncomplete?: boolean;
  crmScope?: number;
  portalOnly?: number;
};
export type Run = {
  id: string;
  no: string;
  periodStart: string;
  periodEnd: string;
  label: string;
  status: RunStatus;
  statusLabel: string;
  dataEnd: string | null;
  scope: { statuses?: number[]; paymentCodes?: number[]; crmCount?: number; lines?: number; firstSalesYear?: number };
  summary: RunSummary;
  options: { fx?: Record<string, number> };
  progress: { step?: string; done?: number; total?: number; at?: string };
  error: string | null;
  note: string | null;
  preparedBy: string | null;
  submittedBy: string | null;
  approvedBy: string | null;
  createdBy: string;
  createdAt: string;
  computedAt: string | null;
  submittedAt: string | null;
  approvedAt: string | null;
  updatedAt: string;
  version: number;
  kaynaklar?: Kaynaklar;
};
export type Exception = { code: string; label: string; acceptable: boolean; fix: string; detail: string | null };
export type Stamp = { by: string; at: string; reason?: string };
export type Decision = {
  haric?: Stamp | null;
  kabul?: (Stamp & { codes: string[] }) | null;
  auto?: string | null;
  autoReason?: string | null;
  autoUndone?: Stamp | null;
};
export type LineParty = { key: string; name: string; role: string; share: number | null; type: string };
export type CalcLine = {
  book: string;
  stockCode: string;
  format: string;
  source: string;
  party: string;
  share: number;
  quantity: number;
  returns: number;
  base: number;
  rate: number;
  tiers: Array<{ quantity: number; rate: number }> | null;
  royalty: number;
  royaltyCurrency?: number;
};
export type Calc = {
  periodStart: string;
  periodEnd: string;
  currency: string;
  contractCurrency: string;
  fx: { currency: string; rate: number; on: string; source: string } | null;
  quantity: number;
  base: number;
  grossTry: number;
  gross: number;
  carryIn: number;
  advance: number | null;
  advanceUsedBefore: number;
  advanceOffset: number;
  advanceRemaining: number | null;
  withholdingPct: number | null;
  withholding: number;
  net: number;
  carryOut: number;
  lines: CalcLine[];
  warnings: string[];
  dataEnd: string | null;
  advanceBasis?: { contractAdvance: number; opening: number; openingOn: string; openingBy?: string; effective: number };
};
export type Line = {
  id: number;
  contractKey: string;
  crmId: string | null;
  contractId: string | null;
  no: string;
  title: string;
  status: LineStatus;
  statusLabel: string;
  exceptionCode: string | null;
  exceptions: Exception[];
  decision: Decision;
  parties: LineParty[];
  gross: number | null;
  advanceOffset: number | null;
  withholding: number | null;
  net: number | null;
  currency: string;
  fxRate: number | null;
  fxOn: string | null;
  statementId: string | null;
  approvalError: string | null;
  calc?: Calc | null;
  kaynaklar?: Kaynaklar;
};
export type Page<T> = { items: T[]; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar };
export type Caps = {
  run: boolean;
  approve: boolean;
  notify: boolean;
  payments: boolean;
  advance: boolean;
  renewal: boolean;
  rightsEdit: boolean;
  license: boolean;
  export: boolean;
};
export type Meta = {
  can: Caps;
  me: { username: string; display: string };
  runStatuses: Record<RunStatus, string>;
  lineStatuses: Record<LineStatus, string>;
  exceptions: Record<string, { label: string; acceptable: boolean; fix: string }>;
  autoExclude: Record<string, string>;
  renewalDecisions: Record<string, string>;
  currencies: Record<string, string>;
  defaultPeriod: { start: string; end: string };
  periodMonths: number;
  withholdingPct: number | null;
  renewalDays: number[];
  riskYears: number;
  scope: { statuses: number[]; paymentCodes: number[] };
};
export type Party = {
  key: string;
  name: string;
  type: string | null;
  email: string | null;
  hasEmail: boolean;
  totals: Record<string, Money4>;
  contracts: number;
  status: 'hazir' | 'gonderildi' | 'hata';
  channel: string | null;
  note: string | null;
  sentBy: string | null;
  sentAt: string | null;
  docHash: string | null;
};
export type PaymentRow = {
  party: string;
  type: string | null;
  contractNo: string;
  contract: string;
  currency: string;
  share: number;
  gross: number;
  advance: number;
  withholdingPct: number | null;
  withholding: number;
  net: number;
  dueOn: string | null;
  paymentStatus: string | null;
};
export type Opening = { amount: number; currency: string; asOf: string; by: string; reason: string; at: string; source: string };
export type AdvanceItem = {
  contractKey: string;
  no: string;
  title: string;
  currency: string;
  advance: number;
  recoupable: boolean;
  opening: Opening | null;
  openingMissing: boolean;
  remaining: number | null;
  periodGross: number;
  yearsToRecoup: number | null;
  risk: boolean;
  parties: string[];
  lineStatus: LineStatus;
  lineId: number;
};
export type AdvanceHistory = { amount: number | null; currency: string; asOf: string; reason: string; by: string; at: string; active: boolean };
export type Renewal = {
  contractKey: string;
  no: string | null;
  kind: string;
  paymentType: string | null;
  start: string | null;
  end: string | null;
  daysLeft: number | null;
  renewEvery: number | null;
  renewStart: string | null;
  renewEnd: string | null;
  destroyMonths: number | null;
  reportPeriod: unknown;
  unpublishedTermination: string | null;
  advance: number | null;
  currency: string;
  author: string | null;
  translator: string | null;
  illustrator: string | null;
  book: string | null;
  stockCode: string | null;
  decision: string;
  decisionLabel: string;
  reason: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
  staleDecision: boolean;
  suggestion: { decision: string | null; probability: number | null; text: string | null; inputs: Record<string, unknown>; at: string } | null;
};

// ------------------------------------------------------------------ haklar

export type RightState = { key: string; label: string; state: 'var' | 'yok' | 'incele' | 'sozlesme-yok' | 'koruma-disi'; why: string };
export type RightsContract = {
  id: string;
  no: string | null;
  kind: 'alis' | 'satis';
  statusLabel: string | null;
  start: string | null;
  end: string | null;
  rights_note: string | null;
  rights: Record<string, boolean>;
  originalLanguage: string | null;
  soldCountry: string | null;
  grantor: string | null;
  author: string | null;
  translator: string | null;
  illustrator: string | null;
  parties: string[];
  inForce: boolean;
  rightsMap?: RightsMap | null;
  /** CRM'in 12 hakkı; boş alan `granted: null` (girilmemiş) — `rights` eski eşlemede boşu «yok» sayar. */
  crmRights?: CrmRight[];
  license?: CrmLicense;
};
/** Yapılandırılmış hak haritası (öneri 18): her değer metinden birebir alıntıyla; alıntısız alan boş. */
export type MapItem = { deger: string; alinti: string; kaynak: 'zeki' | 'kural' | 'insan'; ad?: string; tarih?: string | null };
export type MapFields = { dil: MapItem[]; ulke: MapItem[]; format: MapItem[]; bitis: MapItem | null; munhasirlik: MapItem | null };
export type RightsMap = {
  id: number;
  contractKey: string;
  no: string | null;
  book: string | null;
  fields: MapFields;
  source: 'zeki' | 'kural' | 'insan';
  dropped: number;
  reason: string | null;
  status: 'oneri' | 'onayli' | 'reddedildi';
  statusLabel: string;
  approvedBy: string | null;
  approvedAt: string | null;
  at: string;
};
/** Kapak e-postası taslağı: gönderim yok, kopyalanır. */
export type CoverEmail = { konu: string; metin: string; kaynak: 'zeki' | 'kural'; neden: string | null; alici: string | null; hakSahibi: string; not: string };
/** Koşu özeti: olgular SQL'den; `sql` çalıştırılan sorgular. */
export type RunNote = { metin: string; kaynak: 'zeki' | 'kural'; neden: string | null; at: string; olgular: Record<string, unknown>; sql: string[]; saklanan: boolean };
export type Grant = {
  id: number;
  bookId: string;
  stockCode: string | null;
  kind: string;
  kindLabel: string;
  language: string | null;
  country: string | null;
  start: string | null;
  end: string | null;
  source: string;
  contractKey: string | null;
  note: string | null;
  by: string;
  at: string;
};
export type License = {
  id: number;
  bookId: string | null;
  book: string;
  buyer: string;
  language: string | null;
  country: string | null;
  advance: number | null;
  rate: number | null;
  currency: string | null;
  start: string | null;
  end: string | null;
  status: string;
  statusLabel: string;
  collection: string | null;
  collectionLabel: string | null;
  collected: number | null;
  authorSharePct: number | null;
  authorShare: number | null;
  crmContractId: string | null;
  note: string | null;
  by: string;
  at: string;
  updatedBy: string | null;
  updatedAt: string | null;
};
export type BookCard = {
  book: { id: string; title: string; stockCode: string | null; ebookCode: string | null; isbn: string | null };
  summary: RightState[];
  contracts: RightsContract[];
  grants: Grant[];
  licenses: License[];
  can: Caps;
  kaynaklar?: Kaynaklar;
};
export type RightsMeta = {
  can: Caps;
  grantKinds: Record<string, string>;
  licenseStatuses: Record<string, string>;
  collectionStatuses: Record<string, string>;
  noteClasses: Record<string, string>;
  currencies: Record<string, string>;
  rights: Record<string, string>;
  mapFields?: Record<string, string>;
  mapFormats?: Record<string, string>;
  mapExclusivity?: Record<string, string>;
};
export type Note = {
  id: number;
  contractKey: string;
  no: string | null;
  book: string | null;
  text: string;
  class: string | null;
  classLabel: string | null;
  probability: number | null;
  margin: number | null;
  method: string | null;
  status: 'oneri' | 'incele' | 'onayli';
  approvedBy: string | null;
  approvedAt: string | null;
  at: string;
  map?: RightsMap | null;
};
export type NotesJob = { running: boolean; done: number; total: number; failed?: number; error: string | null; at: string | null };

async function call<T>(path: string, init: { method?: string; body?: unknown; timeout?: number } = {}): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const method = init.method ?? 'GET';
  const res = await fetch(`${ENGINE_BASE}/api/v1${path}`, {
    method,
    credentials: 'include',
    headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : method === 'GET' ? freshHeaders() : undefined,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    signal: AbortSignal.timeout(init.timeout ?? 120_000),
  });
  if (res.status === 401) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } | string } | null;
    const detail = j?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message;
    if (res.status === 403 && (typeof detail !== 'object' || detail?.code === 'FORBIDDEN')) throw new EngineForbiddenError(msg);
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | boolean | undefined>) => {
  const s = Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== '' && v !== false)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&');
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;
const R = '/royalty';

export const royaltyApi = {
  meta: () => call<Meta>(`${R}/meta`),
  runs: () => call<{ items: Run[]; can: Caps }>(`${R}/runs`),
  run: (id: string) => call<Run & { can: Caps }>(`${R}/runs/${enc(id)}`),
  create: (b: { periodStart: string; periodEnd: string; note?: string; fx?: Record<string, number | null> }) =>
    call<Run>(`${R}/runs`, { method: 'POST', body: b }),
  options: (id: string, b: { fx?: Record<string, number | null>; note?: string }) => call<Run>(`${R}/runs/${enc(id)}`, { method: 'PATCH', body: b }),
  compute: (id: string) => call<Run>(`${R}/runs/${enc(id)}/compute`, { method: 'POST', body: {} }),
  lines: (id: string, p: { status?: string; code?: string; q?: string; page?: number }) => call<Page<Line>>(`${R}/runs/${enc(id)}/lines${qs(p)}`),
  line: (id: string, lineId: number) => call<Line>(`${R}/runs/${enc(id)}/lines/${lineId}`),
  decide: (id: string, lineId: number, b: { action: 'haric' | 'geri-al' | 'kabul'; reason?: string }) =>
    call<Line>(`${R}/runs/${enc(id)}/lines/${lineId}`, { method: 'PATCH', body: b }),
  submit: (id: string, b: { note?: string; acceptDataEnd?: boolean }) => call<Run>(`${R}/runs/${enc(id)}/submit`, { method: 'POST', body: b }),
  withdraw: (id: string) => call<Run>(`${R}/runs/${enc(id)}/withdraw`, { method: 'POST', body: {} }),
  reject: (id: string, note: string) => call<Run>(`${R}/runs/${enc(id)}/reject`, { method: 'POST', body: { note } }),
  approve: (id: string) => call<Run>(`${R}/runs/${enc(id)}/approve`, { method: 'POST', body: {} }),
  cancel: (id: string, note: string) => call<Run>(`${R}/runs/${enc(id)}/cancel`, { method: 'POST', body: { note } }),
  parties: (id: string, p: { q?: string; status?: string; page?: number }) =>
    call<Page<Party> & { ready: boolean; sent: number; all: number }>(`${R}/runs/${enc(id)}/parties${qs(p)}`),
  markSent: (id: string, b: { keys: string[]; channel?: string; note?: string; undo?: boolean }) =>
    call<{ updated: number }>(`${R}/runs/${enc(id)}/parties/mark-sent`, { method: 'POST', body: b }),
  payments: (id: string) => call<{ items: PaymentRow[]; totals: Record<string, Money4 & { payees: number }>; run: { id: string; no: string; label: string } } & K>(`${R}/runs/${enc(id)}/payments`),
  advances: (p: { q?: string; only?: string }) =>
    call<{ run: Run | null; items: AdvanceItem[]; totals: Record<string, { advance: number; remaining: number; missing: number; risk: number }>; riskYears: number; can: Caps } & K>(`${R}/advances${qs(p)}`),
  advanceHistory: (key: string) => call<{ contractKey: string; history: AdvanceHistory[] } & K>(`${R}/advances/${enc(key)}`),
  setAdvance: (key: string, b: { amount?: number | null; currency?: string; asOf?: string; reason: string; remove?: boolean; no?: string }) =>
    call<{ contractKey: string; history: AdvanceHistory[] }>(`${R}/advances/${enc(key)}`, { method: 'PUT', body: b }),
  renewals: (p: { days?: number; overdue?: boolean; q?: string; decision?: string; kind?: string }) =>
    call<{ items: Renewal[]; total: number; counts: Record<string, number>; days: number; overdue: boolean; today: string; can: Caps } & K>(`${R}/renewals${qs(p)}`),
  decideRenewal: (key: string, b: { decision: string; reason?: string; end?: string | null; no?: string | null }) =>
    call<{ decision: string }>(`${R}/renewals/${enc(key)}`, { method: 'PATCH', body: b }),
  suggestRenewal: (key: string) =>
    call<{ decision: string | null; probability: number | null; text: string | null; inputs: Record<string, unknown>; dropped: number } & K>(`${R}/renewals/${enc(key)}/suggest`, { method: 'POST', body: {}, timeout: 300_000 }),
  coverEmail: (id: string, party: string) =>
    call<CoverEmail>(`${R}/runs/${enc(id)}/parties/${enc(party)}/cover-email`, { method: 'POST', body: {}, timeout: 300_000 }),
  summaryNote: (id: string, fresh = false) =>
    call<RunNote>(`${R}/runs/${enc(id)}/summary-note${fresh ? '?fresh=true' : ''}`, { method: 'POST', body: {}, timeout: 300_000 }),
  contractLines: (key: string) =>
    call<{ items: Array<{ lineId: number; runId: string; runNo: string; label: string; runStatusLabel: string; status: LineStatus; statusLabel: string; exception: string | null; net: number | null; currency: string; statementId: string | null }> } & K>(`${R}/contracts/${enc(key)}/lines`),
};

export const rightsApi = {
  meta: () => call<RightsMeta>('/rights/meta'),
  search: (q: string, page = 0) =>
    call<{ items: Array<{ id: string; title: string; stockCode: string | null; isbn: string | null }>; total: number; shown: number; page: number } & K>(`/rights/search${qs({ q, page: page || undefined })}`),
  book: (id: string) => call<BookCard>(`/rights/books/${enc(id)}`),
  grantCreate: (b: Partial<Grant> & { bookId: string }) => call<Grant>('/rights/grants', { method: 'POST', body: b }),
  grantUpdate: (id: number, b: Partial<Grant>) => call<Grant>(`/rights/grants/${id}`, { method: 'PATCH', body: b }),
  grantDelete: (id: number) => call<Grant>(`/rights/grants/${id}`, { method: 'DELETE' }),
  licenses: (p: { q?: string; status?: string; book?: string }) => call<{ items: License[]; total: number; can: Caps } & K>(`/rights/licenses-out${qs(p)}`),
  licenseCreate: (b: Partial<License>) => call<License>('/rights/licenses-out', { method: 'POST', body: b }),
  licenseUpdate: (id: number, b: Partial<License>) => call<License>(`/rights/licenses-out/${id}`, { method: 'PATCH', body: b }),
  notes: (p: { status?: string; cls?: string; q?: string; page?: number }) =>
    call<Page<Note> & { counts: Record<string, number>; job: NotesJob; mapJob?: NotesJob; mapCounts?: Record<string, number>; can: Caps }>(`/rights/notes${qs(p)}`),
  classify: () => call<NotesJob>('/rights/notes/classify', { method: 'POST', body: {} }),
  approveNote: (id: number, cls?: string) => call<Note>(`/rights/notes/${id}/approve`, { method: 'POST', body: { class: cls } }),
  extractMap: () => call<NotesJob>('/rights/map/extract', { method: 'POST', body: {} }),
  decideMap: (id: number, b: { action: 'onayla' | 'reddet'; fields?: MapFields }) =>
    call<RightsMap>(`/rights/map/${id}/decide`, { method: 'POST', body: b }),
};

export const metaOptions = () => ({ queryKey: ['royalty', 'meta'], queryFn: royaltyApi.meta, staleTime: 10 * 60_000 });
export const rightsMetaOptions = () => ({ queryKey: ['rights', 'meta'], queryFn: rightsApi.meta, staleTime: 10 * 60_000 });

/** Dosya indirir (Word, CSV, zip); sunucunun verdiği dosya adıyla. */
export async function download(path: string): Promise<void> {
  const res = await fetch(`${ENGINE_BASE}/api/v1${path}`, { credentials: 'include', signal: AbortSignal.timeout(300_000) });
  if (res.status === 401) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } } | null;
    if (res.status === 403) throw new EngineForbiddenError(j?.detail?.message);
    throw new Error(j?.detail?.message || httpErrorText(res.status));
  }
  const blob = await res.blob();
  const m = (res.headers.get('Content-Disposition') || '').match(/filename\*=UTF-8''([^;]+)/);
  const name = m ? decodeURIComponent(m[1]) : 'dosya';
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export const runPath = (id: string) => `/royalty/runs/${enc(id)}`;

export const runTone = (s: RunStatus): 'ok' | 'warn' | 'err' | 'muted' | 'violet' =>
  s === 'onayli' ? 'ok' : s === 'onayda' || s === 'onaylaniyor' ? 'violet' : s === 'iptal' ? 'muted' : s === 'hesaplaniyor' ? 'violet' : 'warn';
export const lineTone = (s: LineStatus): 'ok' | 'warn' | 'err' | 'muted' => (s === 'hesaplandi' ? 'ok' : s === 'istisna' ? 'err' : 'muted');
