import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';

/** M48 Sistem durumu ekranının köprü uçları: /api/v1/it-ops/*. */

export type RingId = 'logo' | 'crm' | 'giris' | 'model' | 'eposta' | 'vpn' | 'vm';
export type RingState = 'ok' | 'fail' | 'down' | 'stale' | 'unknown';

export type Incident = {
  id: string;
  ring: RingId;
  ringLabel: string;
  kind: 'kopma' | 'tazelik';
  kindLabel: string;
  openedAt: string;
  closedAt: string | null;
  open: boolean;
  minutes: number | null;
  firstError: string | null;
  lastError: string | null;
  notifiedAt: string | null;
  notifyStatus: string | null;
  remindedAt: string | null;
  closedNotify: string | null;
  rootCause: string | null;
  rootCauseBy: string | null;
  rootCauseAt: string | null;
  falseAlarm: boolean;
  postmortemDraft: string | null;
  postmortemStatus: 'yok' | 'taslak' | 'yayında';
  postmortemBy: string | null;
  postmortemAt: string | null;
  recipe: string;
};

export type Check = {
  id: number;
  ring: RingId;
  at: string;
  ok: boolean | null;
  latencyMs: number | null;
  dataEnd: string | null;
  detail: string | null;
  source: 'timer' | 'manual' | 'watchdog';
};

export type Ring = {
  id: RingId;
  label: string;
  hint: string;
  recipe: string;
  state: RingState;
  ok: boolean | null;
  at: string | null;
  latencyMs: number | null;
  detail: string | null;
  lastOkAt: string | null;
  dataEnd: string | null;
  dataEndAge: string;
  staleLimitHours: number | null;
  incident: Incident | null;
  stale: Incident | null;
};

export type Release = {
  id: number;
  env: 'test' | 'vm' | 'gpu';
  at: string;
  codeSha: string | null;
  image: string | null;
  appledoubleCount: number | null;
  reportedBy: string | null;
  note: string | null;
};

export type Status = {
  at: string;
  summary: { tone: 'ok' | 'warn' | 'err' | 'unknown'; text: string };
  rings: Ring[];
  open: Incident[];
  me: { username: string; canCheck: boolean; canClose: boolean; canSettings: boolean };
  email: { configured: boolean; sender: string | null; recipients: string[]; rejected: string[] };
  env: 'test' | 'vm';
  jobs: { total: number; failed: number };
  releases: { latest: Partial<Record<Release['env'], Release>>; parity: boolean | null };
};

export type Job = {
  job: string;
  label: string;
  every: string | null;
  lastAt: string | null;
  nextAt: string | null;
  lastOk: boolean | null;
  lastError: string | null;
  failedCount: number | null;
  totalCount: number | null;
  source: 'systemd' | 'jobs-container' | 'table' | 'watchdog';
  updatedAt: string | null;
};

export type Capacity = {
  since: string;
  days: number;
  disks: Array<{ path: string; total?: number; used?: number; free?: number; ratio?: number | null; error?: string }>;
  modules: Array<{ module: string; jobs: number; waitP50Ms: number | null; modelP50Ms: number | null }>;
  questions: { count: number; errors: number; latencyP50Ms: number | null };
};

export type SettingItem = {
  key: string;
  group: string;
  label: string;
  type: 'text' | 'int' | 'bool' | 'email' | 'secret' | 'time' | 'users';
  help: string;
  value: string | null;
  hasValue: boolean;
  source: string;
  updatedBy: string | null;
  updatedAt: string | null;
};

export type IncidentDetail = Incident & {
  timeline: Check[];
  /** Yalnız taslak ucunun cevabında: «zeki» model metni, «kural» (model metni olgu dışı sayı taşıdı ya da boştu). */
  draftSource?: 'zeki' | 'kural';
  draftForeignNumbers?: string[];
};
export type Page<T, C = string> = { items: T[]; next: C | null };

const B = '/api/v1/it-ops';

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
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const itOpsApi = {
  status: () => send<Status>('GET', '/status'),
  checks: (p: { ring?: string; before?: number | null } = {}) => send<Page<Check, number>>('GET', `/checks${qs({ ring: p.ring, before: p.before })}`),
  incidents: (state: 'open' | 'closed' | 'all', before?: string | null) =>
    send<Page<Incident> & { downtime30?: Record<string, { count: number; minutes: number }> }>('GET', `/incidents${qs({ state, before })}`),
  incident: (id: string) => send<IncidentDetail>('GET', `/incidents/${encodeURIComponent(id)}`),
  updateIncident: (id: string, b: { rootCause?: string; falseAlarm?: boolean; postmortem?: string; publish?: boolean }) =>
    send<IncidentDetail>('PATCH', `/incidents/${encodeURIComponent(id)}`, b),
  draft: (id: string) => send<IncidentDetail>('POST', `/incidents/${encodeURIComponent(id)}/draft`, {}, 300_000),
  jobs: () => send<{ items: Job[] }>('GET', '/jobs'),
  releases: (before?: number | null) =>
    send<Page<Release, number> & { latest: Status['releases']['latest']; parity: boolean | null }>('GET', `/releases${qs({ before })}`),
  capacity: () => send<Capacity>('GET', '/capacity'),
  settings: () => send<{ items: SettingItem[]; canEdit: boolean }>('GET', '/settings'),
  saveSettings: (values: Record<string, string>) =>
    send<{ items: SettingItem[]; canEdit: boolean }>('PUT', '/settings', { values }),
  checkNow: (ring?: RingId) => send<Status & { failed: string[]; opened: number; closed: number }>('POST', '/check-now', { ring }, 330_000),
  banner: () => send<{ items: Array<{ ring: RingId; label: string; since: string }> }>('GET', '/banner', undefined, 20_000),
};

/* ------------------------------------------------------------------ biçim */

const dtf = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const dayf = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: 'numeric', month: 'long', year: 'numeric' });
export const fmtAt = (iso: string | null | undefined) => (iso ? dtf.format(new Date(iso)) : '—');
export const fmtDay = (iso: string | null | undefined) => (iso ? dayf.format(new Date(iso)) : '—');

export function fmtMinutes(m: number | null | undefined): string {
  if (m === null || m === undefined) return '—';
  if (m < 60) return `${m} dk`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  if (h < 48) return mm ? `${h} sa ${mm} dk` : `${h} sa`;
  const d = Math.floor(h / 24);
  const hh = h % 24;
  return hh ? `${d} gün ${hh} sa` : `${d} gün`;
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} sn`;
}

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toLocaleString('tr-TR', { maximumFractionDigits: 1 })} ${u[i]}`;
}

export const STATE: Record<RingState, { label: string; tone: 'ok' | 'warn' | 'err' | 'muted'; dot: string }> = {
  ok: { label: 'Çalışıyor', tone: 'ok', dot: 'bg-emerald-500' },
  stale: { label: 'Veri eski', tone: 'warn', dot: 'bg-amber-400' },
  fail: { label: 'Son deneme başarısız', tone: 'warn', dot: 'bg-amber-500' },
  down: { label: 'Kopuk', tone: 'err', dot: 'bg-red-500' },
  unknown: { label: 'Ölçülmedi', tone: 'muted', dot: 'bg-slate-300' },
};

export const NOTIFY: Record<string, string> = {
  sent: 'e-posta gitti',
  no_smtp: 'e-posta ayarı yok',
  no_recipient: 'alıcı yok',
  failed: 'e-posta gönderilemedi',
  skip: 'bildirim yok',
};

export const SOURCE: Record<Job['source'], string> = {
  systemd: 'Sunucu zamanlayıcısı',
  'jobs-container': 'Uygulama sunucusu',
  table: 'Modül kaydı',
  watchdog: 'Sağlık denetimi',
};

export const ENV_LABEL: Record<Release['env'], string> = { test: 'Test sunucusu', vm: 'Şirket içi kurulum', gpu: 'Zeki AI sunucusu' };
