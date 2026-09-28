import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';

/** M49 Veri güvenliği ekranının köprü uçları: /api/v1/data-security/*. */

export type Severity = 'kritik' | 'uyari' | 'bilgi';

export type SecurityMeta = {
  me: { username: string; isAdmin: boolean; canClose: boolean; canRevoke: boolean; canRetention: boolean };
  loginService: { configured: boolean };
  rules: {
    failThreshold: number; failWindowMin: number; workHours: string; workDays: number[]; offhoursExportMin: number;
    idleDays: number; recipients: number; dailyAt: string;
  };
  kinds: Record<string, string>;
  reasons: Record<string, string>;
  ruleLabels: Record<string, string>;
  hygieneKinds: Record<string, { label: string; severity: Severity }>;
  retention: Array<{ id: string; label: string; what: string; default: number }>;
};

export type Summary = {
  openAlerts: { kritik: number; uyari: number };
  last24h: { loginOk: number; loginFailed: number; forbidden: number; export: number };
  retention: { apply: boolean; lastOk: string | null; lastApply: string | null; lastPreview: string | null };
  loginPull: { at: string; ok: boolean; imported?: number; error?: string } | null;
  everyone: { all: boolean; pages: number; pagesTotal: number };
  unassignedEntities: number | null;
  sensitiveColumns: number | null;
  loginService: { configured: boolean };
  at: string;
};

export type Alert = {
  id: number; at: string; rule: string; ruleLabel: string; username: string | null; severity: Severity; summary: string;
  evidence: unknown; state: 'open' | 'closed'; closedBy: string | null; closedAt: string | null;
  verdict: 'gercek' | 'gercek-degil' | null; note: string | null; mailed: string | null;
};

export type LoginRow = { id: number; at: string; username: string; ok: boolean; reason: string; reasonLabel: string; addr: string | null };
export type SessionRow = {
  id: string; username: string; display: string | null; created: number | null; expires: number; addr: string | null;
  adEnabled: boolean | null;
};
export type AccessRow = {
  id: string; at: string; username: string; kind: 'forbidden' | 'export' | 'not_permitted'; kindLabel: string;
  method: string | null; path: string | null; permKey: string | null; detail: Record<string, unknown> | null; offHours: boolean;
};
export type HygieneItem = {
  kind: string; kindLabel: string; severity: Severity; username: string; display: string; detail: string;
  lastLogin: string | null; sources: string[];
};
export type Hygiene = {
  items: HygieneItem[]; counts: Record<string, number>; kinds: Record<string, { label: string; severity: Severity }>;
  notes: string[]; sources: { ad: boolean; crm: boolean; sessions: boolean; adPeople: number; crmUsers: number };
  loginsSince: string | null; at: string;
};
export type EveryonePreview = {
  people: number; admins: number; affected: number; note: string | null;
  items: Array<{ username: string; display: string; roles: string[]; lostPages: string[]; lost: Array<{ key: string; label: string }>; gained: Array<{ key: string; label: string }> }>;
  byKey: Array<{ key: string; label: string; lose: number }>;
  gainByKey: Array<{ key: string; label: string; gain: number }>;
  current: { all: boolean; perms: string[] };
  proposed: { all: boolean; perms: string[] };
};
export type Inventory = {
  source: Array<{ entity: string; table: string; source: string; column: string; reason: string; masked: boolean; tables: number }>;
  sourceCounts: Record<string, { masked: number; names: number }>;
  sensitiveCount: number;
  nameCount: number;
  portal: Array<{
    object: string; kind: 'tablo' | 'klasör'; columns?: string[]; data: string; subjects: string; purpose: string;
    retention?: string | null; retentionNote?: string; retentionDays?: number | null; retentionLabel?: string | null; module: string;
    rows?: number | null; files?: number | null; bytes?: number | null; path?: string; error: string | null;
  }>;
};
export type RetentionObject = {
  id: string; label: string; what: string; key: string; days: number; defaultDays: number; cutoff: string | null;
  rows: number | null; from: string | null; to: string | null; error: string | null;
};
export type Retention = { apply: boolean; applyOn: string | null; lastOk: string | null; dailyAt: string; objects: RetentionObject[] };
export type RetentionRun = {
  id: number; at: string; object: string; objectLabel: string; mode: 'onizleme' | 'uygulama'; days: number | null;
  cutoff: string | null; rows: number | null; from: string | null; to: string | null; ok: boolean; error: string | null; actor: string | null;
};
export type Paged<T> = { items: T[]; next: number | string | null };

const B = '/api/v1/data-security';

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
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const securityApi = {
  meta: () => send<SecurityMeta>('GET', '/meta'),
  summary: () => send<Summary>('GET', '/summary'),
  alerts: (p: { state?: string; before?: number | null }) => send<Paged<Alert> & { counts: { open: number; closed: number } }>('GET', `/alerts${qs(p)}`),
  closeAlert: (id: number, body: { state?: 'open' | 'closed'; verdict?: string; note?: string }) => send<Alert>('PATCH', `/alerts/${id}`, body),
  logins: (p: { user?: string; ok?: string; since?: string; before?: number | null }) =>
    send<Paged<LoginRow> & { configured: boolean; pull: Summary['loginPull'] }>('GET', `/logins${qs(p)}`),
  sessions: () => send<{ configured: boolean; items: SessionRow[]; note?: string | null }>('GET', '/sessions'),
  revoke: (body: { username?: string; session?: string }) => send<{ revoked: number }>('POST', '/sessions/revoke', body),
  access: (p: { kind?: string; user?: string; since?: string; before?: string | null }) => send<Paged<AccessRow>>('GET', `/access${qs(p)}`),
  hygiene: () => send<Hygiene>('GET', '/hygiene', undefined, 180_000),
  /** `perms` verilirse «Herkes»in yeni yetkisi odur (boş liste = yalnız Kampüs); verilmezse bugünkünden `remove` çıkarılır. */
  previewEveryone: (o: { remove?: string[]; perms?: string[] }) =>
    send<EveryonePreview>(
      'GET',
      `/preview-everyone${o.perms ? `?perms=${encodeURIComponent(o.perms.join(','))}` : qs({ remove: (o.remove ?? []).join(',') })}`,
      undefined,
      180_000,
    ),
  inventory: () => send<Inventory>('GET', '/inventory', undefined, 180_000),
  retention: () => send<Retention>('GET', '/retention'),
  retentionPreview: (days: Record<string, number>) => send<{ objects: RetentionObject[] }>('POST', '/retention/preview', { days }),
  saveRetention: (body: { apply?: boolean; days?: Record<string, number>; onizlemeGoruldu?: boolean }) =>
    send<{ changed: string[]; objects: RetentionObject[]; apply: boolean }>('PUT', '/retention', body),
  runs: (before?: number | null) => send<Paged<RetentionRun>>('GET', `/retention/runs${qs({ before })}`),
};

const nf = new Intl.NumberFormat('tr-TR');
export const fmtN = (v: number | null | undefined) => (v === null || v === undefined ? '—' : nf.format(v));
const dtf = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const df = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: '2-digit', month: 'short', year: 'numeric' });
export const fmtAt = (iso: string | null | undefined) => (iso ? dtf.format(new Date(iso)) : '—');
export const fmtDay = (iso: string | null | undefined) => (iso ? df.format(new Date(iso)) : '—');
export const fmtEpoch = (s: number | null | undefined) => (s ? dtf.format(new Date(s * 1000)) : '—');
export const fmtBytes = (b: number | null | undefined) => {
  if (b === null || b === undefined) return '—';
  if (b < 1024 * 1024) return `${nf.format(Math.round(b / 1024))} KB`;
  if (b < 1024 * 1024 * 1024) return `${nf.format(Math.round(b / 1024 / 1024))} MB`;
  return `${(b / 1024 / 1024 / 1024).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} GB`;
};
export const SEVERITY: Record<Severity, { label: string; tone: 'err' | 'warn' | 'muted' }> = {
  kritik: { label: 'Kritik', tone: 'err' },
  uyari: { label: 'Uyarı', tone: 'warn' },
  bilgi: { label: 'Bilgi', tone: 'muted' },
};
