import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** H2 Okuyucu veri tabanı ekranlarının köprü uçları: /api/v1/readers/*. Portal CRM'e yazmaz, ileti göndermez. */

export type Channel = 'email' | 'sms' | 'call';
export type ConsentStatus = 'izinli' | 'ret' | 'bilinmiyor';
export type SegmentStatus = 'taslak' | 'onay-bekliyor' | 'onayli' | 'arsiv';
export type FieldKind = 'set' | 'range' | 'number' | 'days' | 'bool';

export type Me = {
  username: string;
  display: string;
  canPersonal: boolean;
  canMerge: boolean;
  canSegment: boolean;
  canApprove: boolean;
  canList: boolean;
  canImport: boolean;
  canExport: boolean;
};

export type Job = { running: boolean; step: string | null; startedAt: string | null; finishedAt: string | null; error: string | null; result: Record<string, number> | null };

export type Meta = {
  me: Me;
  channels: Record<Channel | 'kvkk', string>;
  statuses: Record<ConsentStatus, string>;
  sources: Record<string, string>;
  origins: Record<string, string>;
  segmentStatuses: Record<SegmentStatus, string>;
  excludeLabels: Record<string, string>;
  importRoles: Record<string, string>;
  importRowStatuses: Record<string, string>;
  opLabels: Record<string, string>;
  settings: {
    requireKvkk: boolean; minorAge: number; minorExport: boolean; exportEnabled: boolean; importRetentionDays: number;
    okSources: string[]; fileMaxMb: number; staleHours: number;
  };
  job: Job;
  modelVar: boolean;
};

export type SourceState = { source: string; label: string; at: string | null; rows: number | null; error: string | null; stale: boolean; failing: boolean };

export type Campaign = { ad: string | null; gonderim: number | null; okunma: number | null; tiklama: number | null; karaListe: number | null; baslangic: string | null };

export type Overview = {
  readers: number;
  records: number;
  multiSource: number;
  duplicateRate: number | null;
  bySource: Array<{ source: string; label: string; readers: number; records: number }>;
  consent: Record<Channel | 'kvkk', Record<ConsentStatus, number>>;
  reach: Record<Channel, number>;
  notReachable: Record<Channel, Record<string, number>>;
  minors: number;
  sharedContact: number;
  pendingCandidates: number;
  distinctEmails: number;
  distinctPhones: number;
  run: {
    at: string | null;
    stats: {
      readers?: number; merged?: number; candidates?: number; candidateGroupsSkipped?: number;
      excluded?: { kurum: number; katki: number }; distinctEmailsContactLead?: number; iysRows?: number; iysUnmapped?: number;
      iysUnknownCustomer?: number; campaigns?: Campaign[]; errors?: Record<string, string>;
      formTypes?: Record<string, number>; formTypeLabels?: Record<string, string>; eventContacts?: number;
      read?: Record<string, number>;
      iysLast?: string | null;
    };
  };
  sources: SourceState[];
  rules: { requireKvkk: boolean; minorAge: number; minorExport: boolean; okSources: string[]; exportEnabled: boolean };
  kaynaklar?: Kaynaklar;
};

export type ReaderSummary = {
  id: string; sources: string[]; city: string | null; age: number | null; minor: boolean;
  consent: Record<Channel | 'kvkk', ConsentStatus>; lastTouch: string | null;
};

export type Evidence = { status: 'izinli' | 'ret'; source: string; sourceLabel: string; at: string | null; record: string; detail: string | null };

export type ReaderCard = {
  id: string; status: string; birthYear: number | null; age: number | null; city: string | null; gender: string | null; minor: boolean;
  firstSeen: string | null; lastTouch: string | null; interests: Array<{ ad: string; kaynak: string }>; attrs: Record<string, string[]>;
  events: number;
  sources: Array<{ source: string; label: string; rule: string; decidedBy: string | null; created: string | null }>;
  consents: Record<Channel | 'kvkk', { status: ConsentStatus; label: string; source: string | null; sourceLabel: string | null; at: string | null; evidence: Evidence[] }>;
  timeline: Array<{ at: string | null; kind: string; text: string }>;
  segments: Array<{ id: string; name: string }>;
  pendingCandidates: number;
  exportable: Partial<Record<Channel, boolean>>;
  personal: Array<{ source: string; sourceId: string; name: string | null; email: string | null; email2: string | null; phone: string | null; active: boolean }> | null;
  redirect?: string;
  kaynaklar?: Kaynaklar;
};

export type Candidate = {
  id: string; a: ReaderSummary; b: ReaderSummary; features: Record<string, string>; score: number; status: string;
  decidedBy: string | null; decidedAt: string | null; note: string | null; reasons: string[];
};

export type Rule = { field: string; op: string; value: unknown };
export type Definition = { match: 'all' | 'any'; rules: Rule[] };

export type FieldSpec = {
  field: string; label: string; kind: FieldKind; ops: string[]; options: string[] | null;
  optionLabels: Record<string, string> | null; help: string | null;
};

export type ChannelCounts = { izinli: number; ret: number; bilinmiyor: number; exportable: number; excluded: Record<string, number> };
export type Counts = {
  total: number; minors: number; email: ChannelCounts; sms: ChannelCounts; call: ChannelCounts; kvkk: Record<string, number>;
  explanation?: string; definition?: Definition; of?: number; kaynaklar?: Kaynaklar;
};

export type Segment = {
  id: string; name: string; definition: Definition; explanation: string | null; status: SegmentStatus; statusLabel: string;
  owner: string; submittedAt: string | null; approvedBy: string | null; approvedAt: string | null; decisionNote: string | null;
  version: number; domain: string; origin: string | null; createdAt: string | null; updatedBy: string | null; updatedAt: string | null;
  lastSnapshot?: { at: string | null; total: number; email: number; sms: number; call: number } | null;
  counts?: Counts;
  history?: Array<{ at: string | null; version: number | null; total: number; email: number; sms: number; call: number }>;
  kaynaklar?: Kaynaklar;
};

export type Draft = { name: string; definition: Definition; explanation: string; notes: string[]; counts: Counts };

export type ImportRow = {
  row: number; status: string; statusLabel: string; readerId: string | null; missingConsent: boolean | null;
  name: string | null; email: string | null; phone: string | null; city: string | null;
};

export type ImportInfo = {
  id: string; fileName: string; uploadedBy: string; at: string | null; status: 'yuklendi' | 'eslesti' | 'silindi';
  eventName: string | null; eventDate: string | null; headers: string[]; mapping: Record<string, number | null>; rows: number;
  matched: number; new: number; rejected: number; duplicates: number; missingConsent: number; confirmedBy: string | null;
  confirmedAt: string | null; purgeAfter: string | null; purgedAt: string | null;
};

export type ImportDetail = ImportInfo & {
  items: ImportRow[]; total: number; page: number; pageSize: number; byStatus: Record<string, number>; roles: Record<string, string>;
  kaynaklar?: Kaynaklar;
};

export type ExportRow = {
  id: string; segmentId: string; segment: string; version: number | null; user: string; at: string | null; purpose: string;
  channel: Channel; channelLabel: string; count: number; excludedTotal: number;
  excluded: Array<{ reason: string; label: string; count: number }>;
};

export type Paged<T> = { items: T[]; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar };

const B = '/api/v1/readers';

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

/** Dosya indirir (CSV). Sunucunun verdiği adı kullanır; sayılar başlıkta döner. */
async function download(method: 'GET' | 'POST', path: string, body?: unknown): Promise<{ count: number | null; excluded: number | null }> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(600_000),
  });
  if (!res.ok) return fail(res);
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? 'okur-listesi.csv';
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Nesne URL'si indirme başladıktan sonra bırakılır; hemen bırakılırsa Safari indirmeyi iptal eder.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  const n = (h: string) => (res.headers.get(h) != null ? Number(res.headers.get(h)) : null);
  return { count: n('X-Readers-Count'), excluded: n('X-Readers-Excluded') };
}

export const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export const readersApi = {
  meta: () => send<Meta>('GET', '/meta'),
  overview: () => send<Overview>('GET', '/overview'),
  mine: () => send<{ segmentsAwaiting: number; sourceProblems: string[] }>('GET', '/mine'),
  status: () => send<Job>('GET', '/status'),
  refresh: () => send<Job & { started: boolean }>('POST', '/refresh', {}),
  search: (q: string) => send<{ items: ReaderSummary[]; how: string; total?: number; note?: string; kaynaklar?: Kaynaklar }>('GET', `/search${qs({ q })}`),
  item: (id: string, personal = false) => send<ReaderCard>('GET', `/item/${enc(id)}${qs({ kisisel: personal })}`, undefined, 300_000),
  subject: (p: { email?: string; phone?: string }) => send<{ readers: ReaderCard[]; uploads: Array<{ import: string; row: number; status: string }>; kaynaklar?: Kaynaklar }>('GET', `/subject${qs(p)}`),
  candidates: (durum: string, page = 0) => send<Paged<Candidate>>('GET', `/merge-candidates${qs({ durum, page })}`),
  decide: (id: string, karar: 'ayni' | 'farkli', not?: string) => send<{ id: string; status: string }>('POST', `/merge-candidates/${enc(id)}/decision`, { karar, not }),
  fields: () => send<{ fields: FieldSpec[]; ops: Record<string, string> }>('GET', '/fields'),
  preview: (definition: Definition) => send<Counts>('POST', '/preview', { definition }),
  segments: (durum = '') => send<{ items: Segment[]; kaynaklar?: Kaynaklar }>('GET', `/segments${qs({ durum })}`),
  segment: (id: string) => send<Segment>('GET', `/segments/${enc(id)}`),
  createSegment: (b: { name: string; definition: Definition; origin?: string }) => send<Segment>('POST', '/segments', b),
  updateSegment: (id: string, b: { name?: string; definition?: Definition }) => send<Segment>('PATCH', `/segments/${enc(id)}`, b),
  submit: (id: string) => send<Segment>('POST', `/segments/${enc(id)}/submit`, {}),
  approve: (id: string, note?: string) => send<Segment>('POST', `/segments/${enc(id)}/approve`, { note }),
  reject: (id: string, note: string) => send<Segment>('POST', `/segments/${enc(id)}/reject`, { note }),
  archive: (id: string) => send<Segment>('POST', `/segments/${enc(id)}/archive`, {}),
  draft: (text: string) => send<Draft>('POST', '/segments/draft-from-text', { text }, 180_000),
  exportList: (id: string, channel: Channel, purpose: string) => download('POST', `/segments/${enc(id)}/export`, { channel, purpose }),
  imports: () => send<{ items: ImportInfo[]; kaynaklar?: Kaynaklar }>('GET', '/imports'),
  importDetail: (id: string, durum = '', page = 0) => send<ImportDetail>('GET', `/imports/${enc(id)}${qs({ durum, page })}`),
  upload: async (file: File) => {
    if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
    const res = await fetch(`${ENGINE_BASE}${B}/imports${qs({ filename: file.name })}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
      signal: AbortSignal.timeout(600_000),
    });
    if (!res.ok) return fail(res);
    return (await res.json()) as ImportDetail;
  },
  confirm: (id: string, b: { mapping: Record<string, number | null>; eventName: string; eventDate: string }) =>
    send<ImportDetail>('POST', `/imports/${enc(id)}/confirm`, b, 600_000),
  crmCsv: (id: string) => download('GET', `/imports/${enc(id)}/crm.csv`),
  purgeImport: (id: string) => send<{ purged: number }>('DELETE', `/imports/${enc(id)}`),
  exports: (page = 0) => send<Paged<ExportRow>>('GET', `/exports${qs({ page })}`),
};

// ------------------------------------------------------------------ biçimler

const dayFmt = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: '2-digit', month: 'short', year: 'numeric' });
export const fmtDay = (iso: string | null | undefined) => (iso ? dayFmt.format(new Date(iso)) : '—');
export const fmtInt = (n: number | null | undefined) => (n == null ? '—' : new Intl.NumberFormat('tr-TR').format(n));
export const fmtPct = (part: number, whole: number) => (whole ? `%${Math.round((part / whole) * 100)}` : '—');

export const CONSENT_TONE: Record<ConsentStatus, 'ok' | 'err' | 'muted'> = { izinli: 'ok', ret: 'err', bilinmiyor: 'muted' };
export const SEGMENT_TONE: Record<SegmentStatus, 'ok' | 'warn' | 'muted' | 'violet'> = {
  taslak: 'muted',
  'onay-bekliyor': 'warn',
  onayli: 'ok',
  arsiv: 'muted',
};
export const CHANNELS: Channel[] = ['email', 'sms', 'call'];

/** Kural değerini kısa metne çevirir (liste kutusu ve özet için). */
export function ruleText(r: Rule, f: FieldSpec | undefined, opLabels: Record<string, string>): string {
  const label = f?.label ?? r.field;
  const show = (v: unknown) => (f?.optionLabels && typeof v === 'string' ? f.optionLabels[v] ?? v : String(v));
  if (r.op === 'in' || r.op === 'not_in') {
    const vals = (Array.isArray(r.value) ? r.value : [r.value]).map(show).join(', ');
    return `${label} ${r.op === 'in' ? '∈' : '∉'} ${vals}`;
  }
  if (r.op === 'between') {
    const [lo, hi] = (r.value as Array<number | null>) ?? [null, null];
    return `${label}: ${lo ?? '…'}–${hi ?? '…'}`;
  }
  if (r.op === 'gte') return `${label} ≥ ${r.value}`;
  if (r.op === 'lte') return `${label} ≤ ${r.value}`;
  if (r.op === 'within') return `${label}: son ${r.value} gün`;
  if (r.op === 'older') return `${label}: ${r.value} günden eski`;
  if (r.op === 'is') return `${label}: ${r.value ? 'evet' : 'hayır'}`;
  return `${label} ${opLabels[r.op] ?? r.op}`;
}

/** Yeni kural için alan türüne göre başlangıç değeri. */
export function emptyRule(f: FieldSpec): Rule {
  const op = f.ops[0];
  if (f.kind === 'set') return { field: f.field, op, value: [] };
  if (f.kind === 'range') return { field: f.field, op, value: [null, null] };
  if (f.kind === 'bool') return { field: f.field, op, value: true };
  return { field: f.field, op, value: f.kind === 'days' ? 365 : 1 };
}
