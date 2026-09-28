import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** M27 Fuar, etkinlik ve ödül: köprü uçları /api/v1/events/*. */

export type ClassKey = 'fuar' | 'imza' | 'soylesi' | 'okul' | 'satis' | 'diger';
export type FairStatus = 'aday' | 'onayli' | 'iptal';
export type Phase = 'hazirlik' | 'suruyor' | 'bitti';

export type Meta = {
  classes: Record<ClassKey, string>;
  kinds: Record<string, string>;
  statuses: Record<FairStatus, string>;
  phases: Record<Phase, string>;
  costKinds: Record<string, string>;
  entryStatuses: Record<string, string>;
  orderTypes: Record<string, string>;
  settings: {
    channel: string;
    orderTypes: number[];
    remindDays: number[];
    awardRemindDays: number[];
    agendaDays: number;
    newBookMonths: number;
    newBookFactor: number;
    suggestFactor: number;
    resultTailDays: number;
    defaultClasses: ClassKey[];
    receiptMaxMb: number;
  };
  today: string;
  job: Job;
  me: { username: string; display: string; admin: boolean; canEdit: boolean; canApprove: boolean; canAwards: boolean; canExport: boolean };
};

export type Job = { state: 'bos' | 'calisiyor' | 'bitti' | 'hata'; done?: number; total?: number | null; error?: string; result?: { asked: number; unsure: number; total: number } };

export type Fair = {
  id: string;
  name: string;
  kind: string;
  kindLabel: string;
  startsOn: string;
  endsOn: string;
  city: string | null;
  venue: string | null;
  standInfo: string | null;
  note: string | null;
  budgetPlanned: number | null;
  status: FairStatus;
  statusLabel: string;
  phase: Phase;
  phaseLabel: string;
  daysLeft: number;
  owner: string | null;
  crmEventIds: string[];
  logoClientCodes: string[];
  prevFairId: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  decisionNote: string | null;
  createdBy: string;
  tasksTotal: number;
  tasksDone: number;
  tasksLate: number;
  prep: number | null;
  costTotal: number;
  books: number;
  resultAt: string | null;
  resultSummary: { netCiro: number; netAdet: number; toplamGider: number; roi: number | null } | null;
};

export type Task = { id: string; title: string; dueOn: string | null; owner: string | null; done: boolean; doneAt: string | null; doneBy: string | null; daysLeft: number | null; late: boolean };
export type Cost = { id: string; kind: string; kindLabel: string; amount: number; note: string | null; hasReceipt: boolean; by: string; at: string | null };
export type BookLine = {
  stokKodu: string;
  crmBookId: string | null;
  ad: string | null;
  qtySuggested: number | null;
  qtyPlanned: number | null;
  qtySold: number | null;
  stock: number | null;
  basisQty: number | null;
  featured: boolean;
  reason: string | null;
  source: 'zeki' | 'elle';
  stockShort: boolean;
  sellThrough: number | null;
};
export type AuthorSlot = { id: string; contactId: string | null; name: string; slotStart: string | null; slotEnd: string | null; note: string | null; conflicts: Array<{ fair: string; fairId: string; slotStart: string; slotEnd: string | null }> };

export type FairDetail = Fair & {
  tasks: Task[];
  costs: Cost[];
  costByKind: Record<string, number>;
  bookList: BookLine[];
  authors: AuthorSlot[];
  prev: { id: string; name: string; startsOn: string; endsOn: string } | null;
  result: Result | null;
  reopened?: boolean;
  newConflicts?: AuthorSlot['conflicts'];
  kaynaklar?: Kaynaklar;
};

export type CrmEvent = {
  id: string;
  ad: string | null;
  tipId: string | null;
  tip: string | null;
  baslangic: string | null;
  bitis: string | null;
  saat: string | null;
  yer: string | null;
  il: string | null;
  durum: number | null;
  durumAdi: string;
  iptal: boolean;
  katilimci: number | null;
  satilan: number | null;
  gelir: number | null;
  gider: number | null;
  oduller: string | null;
  url: string | null;
  sorumlu: string | null;
  sorumluAd: string | null;
  sinif: ClassKey | null;
  sinifOneri: ClassKey | null;
};

export type Calendar = {
  year: number;
  months: Array<{ month: number; counts: Record<string, number>; fairs: string[]; events: string[] }>;
  fairs: Fair[];
  events: CrmEvent[];
  totals: Record<string, number>;
  classes: ClassKey[];
  unmappedTypes: number;
  warnings: string[];
  crmMs: number;
  kaynaklar?: Kaynaklar;
};

export type Upcoming = {
  today: string;
  fairs: Fair[];
  awards: Array<{ id: string; name: string; category: string | null; deadline: string; daysLeft: number; entries: number }>;
  lateTasks: Array<{ id: string; fairId: string; fair: string; title: string; dueOn: string; owner: string | null; daysLate: number }>;
  reminders: Array<{ id: string; kind: string; message: string; link: string | null; target: string | null; at: string | null }>;
  kaynaklar?: Kaynaklar;
};

export type Result = {
  window: { from: string; to: string; tailDays: number };
  dataEnd: string | null;
  channel: string | null;
  clientCodes: string[];
  netCiro: number;
  netAdet: number;
  kitapSayisi: number;
  books: Array<{ stokKodu: string; ad: string | null; adet: number; ciro: number; gecenYilAdet: number | null; planlanan: number | null }>;
  clients: Array<{ kod: string; ad: string | null; adet: number; ciro: number }>;
  unsoldPlanned: Array<{ stokKodu: string; ad: string | null; planlanan: number }>;
  plannedTotal: number | null;
  sellThrough: number | null;
  prev: null | { label: string; from: string; to: string; netCiro: number | null; netAdet: number | null; degisim: number | null };
  orders: Array<{ tip: number; ad: string | null; adet: number; tutar: number }>;
  orderCount: number;
  orderTotal: number;
  crmEvents: Array<{ id: string; ad: string | null; baslangic: string | null; katilimci: number | null; satilan: number | null; gider: number | null; durum: string | null }>;
  katilimci: number | null;
  crmSatilan: number | null;
  costs: { portal: number; crm: number; byKind: Record<string, number> };
  toplamGider: number;
  butce: number | null;
  butceFarki: number | null;
  roi: number | null;
  warnings: string[];
  sql: string[];
  summary: string[];
  computedAt: string;
  complete?: boolean;
  cached?: boolean;
};

export type TypeRow = {
  id: string;
  name: string;
  active: boolean;
  count: number;
  last: string | null;
  class: ClassKey | null;
  decidedBy: string | null;
  decidedAt: string | null;
  suggested: ClassKey | null;
  suggestedProb: number | null;
  suggestedMargin: number | null;
  suggestedMethod: string | null;
};

export type AwardEntry = { id: string; awardId: string; stokKodu: string | null; crmBookId: string | null; bookName: string; status: string; statusLabel: string; text: string | null; submittedAt: string | null; resultAt: string | null; note: string | null; by: string; updatedAt: string | null };
export type Award = { id: string; name: string; category: string | null; organizer: string | null; deadline: string | null; daysLeft: number | null; conditions: string | null; url: string | null; recurring: boolean; note: string | null; by: string; entries: AwardEntry[] };

export type AgendaItem = {
  kind: 'fuar' | 'gorev' | 'crm';
  id: string;
  title: string;
  day: string;
  startsOn?: string;
  endsOn?: string;
  time?: string | null;
  where: string | null;
  type?: string | null;
  daysLeft: number | null;
  late?: boolean;
  link: string | null;
  status?: string;
};

export type BookHit = { id: string | null; stokKodu: string | null; ad: string | null; yazar: string | null; ilkYayin: string | null };

const B = '/api/v1/events';

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
  const j = (await res.json().catch(() => null)) as ({ detail?: { message?: string } | string } & T) | null;
  if (res.status === 403) {
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  }
  if (!res.ok) {
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || httpErrorText(res.status));
  }
  return j as T;
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

export type FairInput = Partial<{
  name: string;
  kind: string;
  startsOn: string;
  endsOn: string;
  city: string | null;
  venue: string | null;
  standInfo: string | null;
  note: string | null;
  budgetPlanned: number | string | null;
  ownerUser: string | null;
  crmEventIds: string[];
  logoClientCodes: string[];
  prevFairId: string | null;
  status: 'iptal' | 'aday';
}>;

export const evApi = {
  meta: () => send<Meta>('GET', '/meta'),
  calendar: (year: number, classes: string[], unmapped: boolean) =>
    send<Calendar>('GET', `/calendar${qs({ year, classes: classes.join(',') || 'yok', unmapped: unmapped ? 1 : 0 })}`, undefined, 180_000),
  upcoming: () => send<Upcoming>('GET', '/upcoming'),
  crmEvents: (p: { frm: string; to: string; cls?: string; q?: string; page?: number }) =>
    send<{ items: CrmEvent[]; total: number; page: number; pageSize: number; from: string; to: string; kaynaklar?: Kaynaklar }>('GET', `/crm-events${qs(p)}`, undefined, 180_000),
  agenda: () => send<{ today: string; until: string; items: AgendaItem[]; total: number; warnings: string[]; canOpen: boolean }>('GET', '/me/agenda'),
  typeMap: () => send<{ items: TypeRow[]; classes: Record<ClassKey, string>; job: Job; counts: { total: number; decided: number; suggested: number }; kaynaklar?: Kaynaklar }>('GET', '/type-map', undefined, 180_000),
  setTypes: (items: Array<{ id: string; class: ClassKey | null }>) => send<{ changed: number }>('PUT', '/type-map', { items }),
  suggestTypes: (all = false) => send<Job>('POST', `/type-map/suggest${qs({ hepsi: all ? 1 : 0 })}`),
  fairs: (year?: number) => send<{ items: Fair[]; kaynaklar?: Kaynaklar }>('GET', `/fairs${qs({ year })}`),
  create: (b: FairInput) => send<FairDetail>('POST', '/fairs', b),
  fair: (id: string) => send<FairDetail>('GET', `/fairs/${enc(id)}`),
  update: (id: string, b: FairInput) => send<FairDetail>('PATCH', `/fairs/${enc(id)}`, b),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/fairs/${enc(id)}`),
  approve: (id: string, note?: string) => send<FairDetail>('POST', `/fairs/${enc(id)}/approve`, { note }),
  suggest: (id: string) =>
    send<{ counts: { added: number; updated: number; removed: number }; basis: { label: string; from: string; to: string }; warnings: string[]; sql: string[]; detail: FairDetail; kaynaklar?: Kaynaklar }>(
      'POST', `/fairs/${enc(id)}/suggest-books`, undefined, 300_000),
  books: (id: string, items: Array<{ stokKodu: string; qtyPlanned: number | null; featured: boolean; new?: boolean }>) =>
    send<FairDetail>('PUT', `/fairs/${enc(id)}/books`, { items }, 180_000),
  addTask: (id: string, b: { title: string; dueOn?: string | null; owner?: string | null }) => send<FairDetail>('POST', `/fairs/${enc(id)}/tasks`, b),
  patchTask: (id: string, tid: string, b: Partial<{ title: string; dueOn: string | null; owner: string | null; done: boolean }>) =>
    send<FairDetail>('PATCH', `/fairs/${enc(id)}/tasks/${enc(tid)}`, b),
  removeTask: (id: string, tid: string) => send<FairDetail>('DELETE', `/fairs/${enc(id)}/tasks/${enc(tid)}`),
  addCost: (id: string, b: { kind: string; amount: string; note?: string; receipt?: { type: string; dataBase64: string } | null }) =>
    send<FairDetail>('POST', `/fairs/${enc(id)}/costs`, b, 180_000),
  removeCost: (id: string, cid: string) => send<FairDetail>('DELETE', `/fairs/${enc(id)}/costs/${enc(cid)}`),
  receiptUrl: (id: string, cid: string) => `${ENGINE_BASE}${B}/fairs/${enc(id)}/costs/${enc(cid)}/receipt`,
  addAuthor: (id: string, b: { name: string; contactId?: string | null; slotStart?: string | null; slotEnd?: string | null; note?: string | null }) =>
    send<FairDetail>('POST', `/fairs/${enc(id)}/authors`, b),
  removeAuthor: (id: string, aid: string) => send<FairDetail>('DELETE', `/fairs/${enc(id)}/authors/${enc(aid)}`),
  result: (id: string, refresh = false) => send<{ fair: FairDetail; result: Result; kaynaklar?: Kaynaklar }>('GET', `/fairs/${enc(id)}/result${qs({ yenile: refresh ? 1 : 0 })}`, undefined, 300_000),
  pdfUrl: (id: string) => `${ENGINE_BASE}${B}/fairs/${enc(id)}/result/export.pdf`,
  books_: (q: string) => send<{ items: BookHit[]; total: number; shown: number; kaynaklar?: Kaynaklar }>('GET', `/lookup/books${qs({ q })}`, undefined, 180_000),
  authors: (q: string) => send<{ items: Array<{ id: string; ad: string }>; total: number; shown: number }>('GET', `/lookup/authors${qs({ q })}`, undefined, 180_000),
  clients: () => send<{ items: Array<{ kod: string; ad: string | null; sehir: string | null; pasif: boolean }>; channel: string }>('GET', '/lookup/clients', undefined, 180_000),
  awards: () => send<{ items: Award[]; statuses: Record<string, string>; today: string; kaynaklar?: Kaynaklar }>('GET', '/awards'),
  createAward: (b: Partial<Award>) => send<{ items: Award[] }>('POST', '/awards', b),
  updateAward: (id: string, b: Partial<Award>) => send<{ items: Award[] }>('PATCH', `/awards/${enc(id)}`, b),
  removeAward: (id: string) => send<{ items: Award[] }>('DELETE', `/awards/${enc(id)}`),
  addEntry: (id: string, b: { stokKodu?: string | null; bookName?: string; status?: string; note?: string }) => send<{ items: Award[] }>('POST', `/awards/${enc(id)}/entries`, b),
  patchEntry: (eid: string, b: Partial<{ status: string; text: string; note: string; submittedAt: string | null; resultAt: string | null }>) =>
    send<{ items: Award[] }>('PATCH', `/award-entries/${enc(eid)}`, b),
  removeEntry: (eid: string) => send<{ items: Award[] }>('DELETE', `/award-entries/${enc(eid)}`),
};

/* ------------------------------------------------------------------ biçim */

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${int0.format(v)} ₺`);
export const fmtPct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: digits }).format(v);
export const fmtRatio = (v: number | null | undefined) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(v);

const utc = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
const shortFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const weekday = new Intl.DateTimeFormat('tr-TR', { weekday: 'long', timeZone: 'UTC' });
export const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
export const fmtDay = (iso: string | null | undefined) => (iso ? dayFmt.format(utc(iso)) : '—');
export const fmtShort = (iso: string | null | undefined) => (iso ? shortFmt.format(utc(iso)) : '—');
export const fmtWeekday = (iso: string | null | undefined) => (iso ? weekday.format(utc(iso)) : '');
export const fmtRange = (a: string, b: string) => (a === b ? fmtDay(a) : `${fmtShort(a)} – ${fmtDay(b)}`);
export const fmtSlot = (s: string | null) => (s ? `${fmtShort(s)} ${s.slice(11, 16)}` : '—');

/** «1.234,5» ya da «1234.5» → sayı; boşsa null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, '').replace(/₺|TL/g, '');
  if (!t) return null;
  const norm = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : /^\d{1,3}(\.\d{3})+$/.test(t) ? t.replace(/\./g, '') : t;
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

export const CLASS_TONE: Record<ClassKey | 'yok', string> = {
  fuar: 'bg-rose-50 text-rose-700',
  imza: 'bg-violet-50 text-violet-700',
  soylesi: 'bg-sky-50 text-sky-700',
  okul: 'bg-emerald-50 text-emerald-700',
  satis: 'bg-slate-100 text-canvas-muted',
  diger: 'bg-amber-50 text-amber-800',
  yok: 'bg-slate-100 text-canvas-muted',
};

export const STATUS_TONE: Record<FairStatus, 'ok' | 'warn' | 'muted'> = { aday: 'warn', onayli: 'ok', iptal: 'muted' };

/** Dosyayı base64'e çevirir (fiş fotoğrafı). */
export function fileToBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const s = String(r.result || '');
      resolve(s.slice(s.indexOf(',') + 1));
    };
    r.onerror = () => reject(new Error('Dosya okunamadı.'));
    r.readAsDataURL(f);
  });
}
