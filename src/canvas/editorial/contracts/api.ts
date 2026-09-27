import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../../engine';
import { httpErrorText } from '../../httpError';

/** M6 Sözleşmeler: köprü uçları /api/v1/editorial/contracts/* (taslak, düzenleme, zeyilname, ödeme, hakediş, şablon). */

export type Status = 'taslak' | 'imzada' | 'yururlukte' | 'sona-erdi' | 'feshedildi' | 'iptal';
export type Party = { name: string; role: string; share: number | null; contactId?: string | null; accountId?: string | null; viaAgent?: boolean };
export type Book = { id?: string | null; title: string; stockCode?: string | null; isbn?: string | null; format?: string; listPrice?: number | null };
export type Tier = { from: number; rate: number };
export type Terms = {
  title: string;
  kind: string;
  company: string;
  parties: Party[];
  books: Book[];
  paymentType: string;
  basis: string;
  rates: Record<string, number>;
  tiers: Tier[];
  discountPct: number | null;
  currency: string;
  advance: number | null;
  advanceRecoupable: boolean;
  flatFee: number | null;
  withholdingPct: number | null;
  start: string | null;
  end: string | null;
  openEnded: boolean;
  years: number | null;
  periodMonths: number;
  paymentDays: number | null;
  printRun: number | null;
  territory: string;
  language: string;
  rights: Record<string, boolean>;
  notes: string;
};
export type Change = { field: string; label: string; old: unknown; new: unknown };
export type Record_ = {
  id: string;
  crmId: string | null;
  no: string;
  status: Status;
  statusLabel: string;
  expired: boolean;
  terms: Terms;
  crmTerms: Terms | null;
  templateId: string | null;
  body: string | null;
  bodyEdited: boolean;
  version: number;
  createdBy: string;
  createdAt: string;
  updatedBy: string;
  updatedAt: string;
  signedAt: string | null;
  payments?: { planned: number; overdue: number; next: string | null } | null;
};
export type Addendum = {
  id: string;
  contractId: string;
  seq: number;
  no: string;
  title: string;
  effectiveOn: string | null;
  reason: string | null;
  changes: Change[];
  status: 'taslak' | 'imzalandi' | 'iptal';
  statusLabel: string;
  templateId: string | null;
  createdBy: string;
  createdAt: string;
  updatedBy: string;
  signedBy: string | null;
  signedOn: string | null;
};
export type Payment = {
  id: string;
  contractId: string;
  kind: 'avans' | 'tek-odeme' | 'hakedis' | 'diger';
  kindLabel: string;
  party: string | null;
  dueOn: string | null;
  amount: number | null;
  currency: string;
  status: 'planlandi' | 'odendi' | 'iptal';
  statusLabel: string;
  overdue: boolean;
  periodStart: string | null;
  periodEnd: string | null;
  statementId: string | null;
  paidOn: string | null;
  paidAmount: number | null;
  paidRef: string | null;
  note: string | null;
  updatedBy: string;
  updatedAt: string;
  contractNo?: string;
  contractTitle?: string;
  contractKey?: string;
};
export type StatementLine = {
  book: string;
  stockCode: string;
  format: string;
  source: 'satış' | 'baskı';
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
  paymentType: string;
  basis: string;
  currency: string;
  contractCurrency: string;
  fx: { currency: string; rate: number; on: string } | null;
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
  lines: StatementLine[];
  warnings: string[];
  dataEnd: string | null;
  source?: string;
};
export type Statement = {
  id: string;
  contractId: string;
  periodStart: string;
  periodEnd: string;
  status: 'taslak' | 'onaylandi' | 'iptal';
  statusLabel: string;
  gross: number;
  advanceOffset: number;
  carryOut: number;
  net: number;
  currency: string;
  paymentId: string | null;
  note: string | null;
  calc: Calc;
  createdBy: string;
  createdAt: string;
  approvedBy: string | null;
  approvedAt: string | null;
  cancelledBy: string | null;
};
export type ContractEvent = { at: string; actor: string; action: string; summary: string; changes: Change[] | null };
export type Period = { periodStart: string; periodEnd: string; dueOn: string };
export type Caps = { edit: boolean; finance: boolean; templates: boolean };
export type Detail = {
  record: Record_ | null;
  key: string;
  no: string;
  status: Status;
  statusLabel: string;
  terms: Terms;
  crm: { no: string | null; status: Status; terms: Terms } | null;
  diff: Change[];
  crmChangedSinceAdopt?: boolean;
  crmError?: string | null;
  warnings: string[];
  addenda: Addendum[];
  payments: Payment[];
  statements: Statement[];
  events: ContractEvent[];
  periods: Period[];
  can: Caps;
};
export type Template = {
  id: string;
  name: string;
  target: 'sozlesme' | 'zeyilname' | 'hakedis';
  targetLabel: string;
  kind: string | null;
  description: string | null;
  body: string;
  hasDocx: boolean;
  docxName: string | null;
  version: number;
  active: boolean;
  fields: string[];
  unknownFields: string[];
  updatedBy: string;
  updatedAt: string;
};
export type Meta = {
  can: Caps;
  kinds: Record<string, string>;
  paymentTypes: Record<string, string>;
  bases: Record<string, string>;
  currencies: Record<string, string>;
  statuses: Record<Status, string>;
  transitions: Record<Status, Status[]>;
  freeEdit: Status[];
  rates: Record<string, string>;
  rights: Record<string, string>;
  partyRoles: Record<string, string>;
  labels: Record<string, string>;
  salesBased: string[];
  printBased: string[];
  tiered: string[];
  paymentKinds: Record<string, string>;
  paymentStatuses: Record<string, string>;
  templateFields: Record<string, string>;
  templateTargets: Record<string, string>;
};

const BASE = '/api/v1/editorial/contracts';

async function call<T>(path: string, init: { method?: string; body?: unknown; raw?: BodyInit; timeout?: number } = {}): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const method = init.method ?? 'GET';
  const res = await fetch(`${ENGINE_BASE}${BASE}${path}`, {
    method,
    credentials: 'include',
    headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : method === 'GET' ? freshHeaders() : undefined,
    body: init.raw ?? (init.body !== undefined ? JSON.stringify(init.body) : undefined),
    signal: AbortSignal.timeout(init.timeout ?? 60_000),
  });
  if (res.status === 401) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } | string } | null;
    const detail = j?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message;
    if (res.status === 403 && typeof detail === 'object' && detail?.code === 'FORBIDDEN') throw new EngineForbiddenError(msg);
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

export const contractApi = {
  meta: () => call<Meta>('/meta'),
  records: (p: { q?: string; status?: string; source?: string }) => call<{ items: Record_[] }>(`/records${qs(p)}`),
  detail: (key: string) => call<Detail>(`/item/${enc(key)}`),
  create: (terms: Partial<Terms>, templateId?: string) => call<Record_>('/drafts', { method: 'POST', body: { terms, templateId } }),
  update: (key: string, terms: Partial<Terms>, version?: number, reason?: string) =>
    call<Record_>(`/item/${enc(key)}`, { method: 'PATCH', body: { terms, version, reason } }),
  status: (key: string, status: Status, version?: number, note?: string, signedOn?: string) =>
    call<Record_>(`/item/${enc(key)}/status`, { method: 'POST', body: { status, version, note, signedOn } }),
  body: (key: string, body: string, version: number) => call<Record_>(`/item/${enc(key)}/body`, { method: 'PUT', body: { body, version } }),
  render: (key: string, templateId: string) => call<Record_>(`/item/${enc(key)}/render`, { method: 'POST', body: { templateId } }),
  addendum: (key: string, b: { title: string; effectiveOn?: string | null; reason?: string; changes: Record<string, unknown>; templateId?: string }) =>
    call<Addendum>(`/item/${enc(key)}/addenda`, { method: 'POST', body: b }),
  addendumUpdate: (id: string, b: { title?: string; effectiveOn?: string | null; reason?: string; changes?: Record<string, unknown> }) =>
    call<Addendum>(`/addenda/${enc(id)}`, { method: 'PATCH', body: b }),
  addendumStatus: (id: string, status: 'imzalandi' | 'iptal', signedOn?: string) =>
    call<Addendum>(`/addenda/${enc(id)}/status`, { method: 'POST', body: { status, signedOn } }),
  paymentAdd: (key: string, b: { kind: string; party?: string; dueOn?: string | null; amount: number | null; currency?: string; note?: string }) =>
    call<Payment>(`/item/${enc(key)}/payments`, { method: 'POST', body: b }),
  paymentPlan: (key: string) => call<{ added: string[]; periods: Period[] }>(`/item/${enc(key)}/payments/plan`, { method: 'POST', body: {} }),
  paymentUpdate: (id: string, b: Partial<{ kind: string; party: string; dueOn: string | null; amount: number | null; currency: string; note: string }>) =>
    call<Payment>(`/payments/${enc(id)}`, { method: 'PATCH', body: b }),
  paymentPaid: (id: string, b: { paidOn?: string; paidAmount?: number | null; paidRef?: string }) =>
    call<Payment>(`/payments/${enc(id)}/paid`, { method: 'POST', body: b }),
  paymentCancel: (id: string, note?: string) => call<Payment>(`/payments/${enc(id)}/cancel`, { method: 'POST', body: { note } }),
  due: (p: { status?: string; within?: number; kind?: string }) =>
    call<{ items: Payment[]; totals: Record<string, { amount: number; overdue: number }>; today: string; can: Caps }>(`/payments${qs(p)}`),
  preview: (key: string, b: StatementInput) => call<Calc>(`/item/${enc(key)}/statements/preview`, { method: 'POST', body: b, timeout: 620_000 }),
  statementSave: (key: string, b: StatementInput & { note?: string }) =>
    call<Statement>(`/item/${enc(key)}/statements`, { method: 'POST', body: b, timeout: 620_000 }),
  statementApprove: (id: string) => call<Statement>(`/statements/${enc(id)}/approve`, { method: 'POST', body: {} }),
  statementCancel: (id: string, note?: string) => call<Statement>(`/statements/${enc(id)}/cancel`, { method: 'POST', body: { note } }),
  templates: (p: { target?: string; archived?: boolean } = {}) =>
    call<{ items: Template[]; fields: Record<string, string>; targets: Record<string, string>; can: Caps }>(`/templates${qs(p)}`),
  templateSave: (b: Partial<Template> & { version?: number }, id?: string) =>
    call<Template>(id ? `/templates/${enc(id)}` : '/templates', { method: id ? 'PATCH' : 'POST', body: b }),
  templatePreview: (id: string, contract?: string) =>
    call<{ text: string; missing: string[]; sample: boolean; fromDocx: boolean }>(`/templates/${enc(id)}/preview${qs({ contract })}`),
  templateDocx: (id: string, file: File) =>
    call<Template>(`/templates/${enc(id)}/docx${qs({ filename: file.name })}`, { method: 'PUT', raw: file, timeout: 120_000 }),
  templateDocxRemove: (id: string) => call<Template>(`/templates/${enc(id)}/docx`, { method: 'DELETE' }),
  lookupBooks: (q: string) => call<{ items: Array<{ id: string; title: string; stockCode: string | null; isbn: string | null }> }>(`/lookup/books${qs({ q })}`),
  lookupParties: (q: string) => call<{ items: Array<{ type: 'kisi' | 'firma'; id: string; name: string }> }>(`/lookup/parties${qs({ q })}`),
};

export const metaOptions = () => ({ queryKey: ['contracts', 'meta'], queryFn: contractApi.meta, staleTime: 10 * 60_000 });
export const detailKey = (key: string) => ['contracts', 'detail', key.toLowerCase()];

export type StatementInput = {
  periodStart: string;
  periodEnd: string;
  prints?: Record<string, number | null>;
  listPrices?: Record<string, number | null>;
};

/** Word belgesini indirir. Doldurulamayan alanları döndürür (ekranda uyarı). */
export async function downloadDocx(path: string): Promise<string[]> {
  const res = await fetch(`${ENGINE_BASE}${BASE}${path}`, { credentials: 'include', signal: AbortSignal.timeout(120_000) });
  if (res.status === 401) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } } | null;
    if (res.status === 403 && j?.detail?.code === 'FORBIDDEN') throw new EngineForbiddenError(j.detail.message);
    throw new Error(j?.detail?.message || httpErrorText(res.status));
  }
  const blob = await res.blob();
  const cd = res.headers.get('Content-Disposition') || '';
  const m = cd.match(/filename\*=UTF-8''([^;]+)/);
  const name = m ? decodeURIComponent(m[1]) : 'sozlesme.docx';
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  const missing = res.headers.get('X-Missing-Fields');
  return missing ? missing.split(',').filter(Boolean) : [];
}
