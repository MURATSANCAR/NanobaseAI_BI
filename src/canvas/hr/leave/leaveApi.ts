import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError } from '../../engine';
import { httpErrorText } from '../../httpError';
import { hrDownload, hrSend, qs, type WithK } from '../hrApi';

/** M60 İzin yönetimi uçları (köprü `hr_leave_api.py`): `/api/v1/hr/leave/*`, İK `…/leave/admin/*`. */

const B = '/leave';
const AD = '/leave/admin';
const enc = encodeURIComponent;

export type LeaveType = {
  key: string; label: string; paid: boolean; fromBalance: boolean; payroll: boolean; sensitive: boolean; needsDoc: boolean;
  halfDay: boolean; countMode: 'is_gunu' | 'takvim_gunu'; maxRequest: number | null; maxYear: number | null; legal: string | null;
  approved: boolean; approvedBy: string | null; approvedAt: string | null; active: boolean; sort: number; builtin: boolean;
};

export type LeaveSummary = {
  balance: number; pending: number; available: number; usedYear: number; accruedYear: number;
  nextAccrual: { date: string; days: number; years: number } | null; startDate: string | null; hasOpening: boolean;
};

export type LeaveRequest = {
  id: string; personId: string; adSoyad: string; departman: string | null; typeKey: string | null; typeLabel: string;
  start: string; end: string; half: string; days: number; deputy: string | null; deputyId: string | null; contact: string | null;
  note: string | null; status: string; statusLabel: string; needsHr: boolean; managerDecidedBy: string | null; decidedBy: string | null;
  decidedAt: string | null; rejectReason: string | null; createdAt: string;
  files?: { id: string; filename: string; size: number }[]; needsDoc?: boolean;
};

export type Holiday = { day: string; name: string; half: boolean };

export type MyLeave = {
  linked: boolean; types: LeaveType[]; pendingTypes: string[]; halfOptions: Record<string, string>; status: Record<string, string>;
  holidays: Holiday[]; summary?: LeaveSummary; requests?: LeaveRequest[]; manager?: string | null;
  deputies?: { id: string; adSoyad: string; departman: string | null }[]; calendar?: string;
  rights: { admin: boolean; settings: boolean; sensitive: boolean };
};

export type Calc = { days: number; calendar: string; holidays: { day: string; half: boolean }[]; available: number | null; warnings: string[]; errors: string[] };

export type Team = {
  linked: boolean; month: string; conflictPct?: number;
  members: { id: string; adSoyad: string; unvan: string | null; balance: number }[];
  queue: LeaveRequest[]; requests: LeaveRequest[];
  days: { day: string; weekday: number; holiday: boolean; off: string[] }[];
  conflicts: { day: string; off: number; team: number }[];
};

export type OnLeave = { id: string; adSoyad: string; departman: string | null; back: string };

export type BalanceRow = LeaveSummary & { id: string; idNo: string; adSoyad: string; departman: string | null };

export type LeaveStats = {
  onLeaveToday: number; waiting: number;
  highBalance: { id: string; adSoyad: string; balance: number }[];
  accrualSoon: { id: string; adSoyad: string; date: string; days: number }[];
};

export type LedgerRow = { id: number; typeKey: string; days: number; reason: string; reasonLabel: string; requestId: string | null; onDate: string; note: string | null; actor: string | null; at: string };

export type WorkCalendar = { id: string; name: string; days: string; matchField: string | null; matchValues: string[]; isDefault: boolean };

export type LeaveSettings = {
  settings: {
    flow: 'yonetici' | 'yonetici_ik'; advance: boolean; tiers: { minYears: number; days: number }[];
    ageRule: { maxYoungAge: number; minOldAge: number; days: number }; startField: string; conflictPct: number; reminderWorkdays: number;
    accrualFrom: string | null;
  };
  types: LeaveType[]; holidays: Holiday[]; calendars: WorkCalendar[]; countModes: Record<string, string>; weekdays: string[];
};

export type OpeningResult = {
  rows: { row: number; idNo: string; adSoyad: string | null; days: number; onDate: string; note: string | null; errors: string[] }[];
  counts: { ok: number; error: number }; applied: number;
};

async function fail(res: Response): Promise<never> {
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  throw new Error(msg || httpErrorText(res.status));
}

async function sendFile<T>(path: string, file: File, extra: Record<string, string | number | undefined> = {}): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}/api/v1/hr${path}${qs({ filename: file.name, ...extra })}`, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/octet-stream' }, body: file, signal: AbortSignal.timeout(300_000),
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

export type NewLeave = { type: string; start: string; end: string; half?: string; deputyId?: string; contact?: string; note?: string };

export const leaveApi = {
  me: () => hrSend<MyLeave>('GET', `${B}/me`),
  calc: (b: Pick<NewLeave, 'type' | 'start' | 'end' | 'half'>) => hrSend<Calc>('POST', `${B}/calc`, b),
  create: (b: NewLeave) => hrSend<{ id: string; status: string; days: number }>('POST', `${B}/requests`, b),
  cancel: (id: string) => hrSend<{ ok: boolean; status: string }>('POST', `${B}/requests/${enc(id)}/cancel`),
  decide: (id: string, action: 'onayla' | 'reddet', reason?: string) => hrSend<{ ok: boolean; status: string }>('POST', `${B}/requests/${enc(id)}/decide`, { action, reason }),
  upload: (id: string, f: File) => sendFile<{ id: string; filename: string; size: number }>(`${B}/requests/${enc(id)}/files`, f),
  file: (id: string, f: { id: string; filename: string }) => hrDownload(`${B}/requests/${enc(id)}/files/${enc(f.id)}`, f.filename),
  team: (month?: string) => hrSend<Team>('GET', `${B}/team${qs({ month })}`),
  today: () => hrSend<{ items: OnLeave[] }>('GET', `${B}/today`),

  adminRequests: (p: { status?: string; type?: string; month?: string; q?: string }) =>
    hrSend<{ items: LeaveRequest[]; total: number; status: Record<string, string> }>('GET', `${AD}/requests${qs(p)}`),
  balances: () => hrSend<{ items: BalanceRow[]; total: number; stats: LeaveStats } & WithK>('GET', `${AD}/balances`),
  ledger: (pid: string) => hrSend<{ person: { id: string; idNo: string; adSoyad: string }; summary: LeaveSummary; items: LedgerRow[] }>('GET', `${AD}/ledger/${enc(pid)}`),
  adjust: (b: { personId: string; days: number; note: string; onDate?: string }) => hrSend<{ balance: number }>('POST', `${AD}/ledger`, b),
  opening: (f: File, apply: boolean) => sendFile<OpeningResult>(`${AD}/opening`, f, { apply: apply ? 1 : 0 }),
  openingTemplate: () => hrDownload(`${AD}/opening-template`, 'izin-acilis-sablon.xlsx'),
  payroll: (month: string) => hrDownload(`${AD}/payroll${qs({ month })}`, `bordro-izin-${month}.xlsx`),
  settings: () => hrSend<LeaveSettings>('GET', `${AD}/settings`),
  saveSettings: (b: Partial<LeaveSettings['settings']>) => hrSend<LeaveSettings['settings']>('PUT', `${AD}/settings`, b),
  createType: (b: Partial<LeaveType>) => hrSend<LeaveType>('POST', `${AD}/types`, b),
  updateType: (key: string, b: Partial<LeaveType>) => hrSend<LeaveType>('PATCH', `${AD}/types/${enc(key)}`, b),
  saveHolidays: (days: (Holiday & { delete?: boolean })[]) => hrSend<{ ok: boolean; days: number }>('PUT', `${AD}/holidays`, { days }),
  fixedHolidays: (year: number) => hrSend<{ ok: boolean; added: number }>('POST', `${AD}/holidays/fixed${qs({ year })}`),
  saveCalendars: (items: WorkCalendar[]) => hrSend<{ items: WorkCalendar[] }>('PUT', `${AD}/calendars`, { items }),
};

/* ------------------------------------------------------------------ biçim */

const dmy = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' });
const dmyY = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' });
const toDate = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
export const shortDay = (iso: string) => dmy.format(toDate(iso));
export const span = (a: string, b: string) => {
  if (a === b) return dmyY.format(toDate(a));
  const sameYear = a.slice(0, 4) === b.slice(0, 4);
  return `${sameYear ? dmy.format(toDate(a)) : dmyY.format(toDate(a))} – ${dmyY.format(toDate(b))}`;
};
export const gun = (n: number) => `${String(n).replace('.', ',')} gün`;
export const STATUS_TONE: Record<string, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  yonetici: 'warn', ik: 'violet', onaylandi: 'ok', reddedildi: 'err', geri_alindi: 'muted', iptal: 'muted',
};
