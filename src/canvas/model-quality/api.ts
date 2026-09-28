import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';

/** M50 Zeki AI kalitesi ekranının köprü uçları: /api/v1/model-quality/*. */

export type Verdict = 'dogru' | 'kismen' | 'yanlis';
export type CaseStatus = 'saglam' | 'bozuk' | 'kararsiz' | 'veri' | 'ret' | 'hata' | 'yeni';
export type RunStatus = 'sirada' | 'calisiyor' | 'bitti' | 'hata';
export type TriageState = 'yeni' | 'siniflandi' | 'kapandi';

export type QualityClass = {
  klass: string;
  label: string;
  help: string | null;
  sort: number;
  countsAsError: boolean;
  active: boolean;
  rule: { any?: Array<Record<string, unknown>> };
  updatedBy: string | null;
  updatedAt: string | null;
};

export type Meta = {
  suites: Record<string, string>;
  startable: string[];
  caseStatuses: Record<CaseStatus, string>;
  runStatuses: Record<RunStatus, string>;
  verdicts: Record<Verdict, string>;
  triage: Record<TriageState, string>;
  kindLabels: Record<string, string>;
  classes: QualityClass[];
  unclassified: string;
  windowDays: number;
  me: { username: string; display: string; canRun: boolean; canDecide: boolean };
};

export type Version = {
  id: number;
  at: string | null;
  source: string;
  sourceLabel: string;
  kinds: string[];
  kindLabels: string[];
  env: string | null;
  codeSha: string | null;
  catalogVersion: number | null;
  catalogCertified: number | null;
  knowledgeDigest: string | null;
  rulesDigest: string | null;
  languageDigest: string | null;
  promptDigest: string | null;
  model: string;
  modelDigest: string | null;
  digest: string;
  note: string | null;
  by: string | null;
};

export type Install = { kind?: string; source?: string; at?: string | null; label?: string; kinds?: string[]; codeSha?: string | null; sourceLabel?: string };

export type Run = {
  id: string;
  suite: string;
  suiteLabel: string;
  label: string;
  status: RunStatus;
  statusLabel: string;
  requestedBy: string | null;
  requestedAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  durationSec: number | null;
  startedBy: string | null;
  versionId: number | null;
  codeSha: string | null;
  catalogVersion: number | null;
  env: string | null;
  metrics: Record<string, unknown>;
  tally: Partial<Record<CaseStatus, number>>;
  baselineRunId: string | null;
  total: number;
  broken: number;
  fixed: number;
  installsInWindow: Install[];
  polluted: boolean;
  note: string | null;
  error: string | null;
};

export type RunDetail = Run & { version: Version | null; baseline: Run | null; baselineVersion: Version | null };

export type Case = {
  id: string;
  n: number | null;
  question: string;
  status: CaseStatus;
  statusLabel: string;
  klass: string | null;
  sql: string | null;
  resultDigest: string | null;
  expectedDigest: string | null;
  detail: string[];
  note: string | null;
};
export type CaseRow = Case & { before: Case | null; change: 'bozulan' | 'duzelen' | null };

export type Metric = { key: string; label: string; value: number | null; kind?: 'ratio' | 'ms' | 'score'; help?: string };
export type ScoreRow = {
  id: string;
  label: string;
  page: string | null;
  measured: boolean;
  primary?: { label: string; value: number | null; kind?: string; detail?: string; at?: string | null; runId?: string; broken?: number; fixed?: number } | null;
  reading?: { label: string; value: number; total: number; at: string | null; runId: string } | null;
  metrics: Metric[];
  trend: Array<{ from: string; to: string; questions?: number; answeredRate?: number | null; wrong?: number }>;
  byType?: Record<string, number>;
  lastMeasured?: string | null;
  note: string | null;
};
export type Scorecard = {
  days: number;
  rows: ScoreRow[];
  hidden: number;
  runs: Record<string, Run | null>;
  version: Version | null;
  generatedAt: string;
};

export type ClassRow = {
  klass: string;
  label: string;
  help: string | null;
  countsAsError: boolean;
  questions: number;
  fromFeedback: number;
  gateCases: number;
  trend: number[];
};
export type ClassBoardData = {
  items: ClassRow[];
  errorQuestions: number;
  total: number;
  days: number;
  weeks: Array<{ from: string; to: string }>;
  classes: QualityClass[];
};
export type ClassItem = {
  queryId: string;
  question: string | null;
  klass: string;
  source: 'kayit' | 'geri-bildirim';
  at: string | null;
  answerType: string | null;
  verdict: Verdict | null;
  username: string | null;
};
export type GateCase = { runId: string; suite: string; caseId: string; question: string; status: CaseStatus; klass: string | null };

export type QueryBrief = {
  id: string;
  question: string | null;
  username: string | null;
  answerType: string | null;
  answerSummary: string | null;
  sql: string | null;
  rowCount: number | null;
  error: string | null;
  catalogVersion: number | null;
  latencyMs: number | null;
  createdAt: string | null;
};
export type FeedbackItem = {
  id: string;
  queryId: string;
  username: string;
  verdict: Verdict;
  verdictLabel: string;
  comment: string | null;
  at: string | null;
  triageState: TriageState;
  triageLabel: string;
  klass: string | null;
  klassSource: 'insan' | 'kural' | null;
  effectiveKlass: string | null;
  handledBy: string | null;
  handledAt: string | null;
  handleNote: string | null;
  query?: QueryBrief | null;
};

export type Page<T> = { items: T[]; total: number; page: number; size: number };

const B = '/api/v1/model-quality';
const enc = encodeURIComponent;

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

const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

/** Başarısız soru kümesi (öneri 20): anlamca yakın başarısız sorular; Zeki AI sınıf önerir, onay insanda. */
export type Cluster = {
  id: string; size: number; distinctTexts: number; samples: string[];
  ruleClasses: Array<{ klass: string; label: string; count: number }>;
  suggested: string | null; suggestedLabel: string | null; probability: number | null; margin: number | null;
  method: string; confident: boolean; status: 'oneri' | 'onaylandi' | 'reddedildi'; statusLabel: string;
  decidedKlass: string | null; decidedLabel: string | null; decidedBy: string | null; decidedAt: string | null;
  builtAt: string | null; windowDays: number; note: string | null;
};
export type ClusterJob = { running: boolean; startedAt: string | null; finishedAt: string | null; error: string | null;
  result: { clusters: number; questions: number; singletons: number; asked: number; stopped: string | null; note?: string } | null };
export type ClusterList = { items: Cluster[]; builtAt: string | null; method: string; job: ClusterJob; canDecide: boolean;
  classes: Array<{ klass: string; label: string }> };

export const mqApi = {
  meta: () => send<Meta>('GET', '/meta'),
  scorecard: (days?: number) => send<Scorecard>('GET', `/scorecard${qs({ days })}`, undefined, 300_000),
  runs: (p: { suite?: string; page?: number }) => send<Page<Run>>('GET', `/runs${qs(p)}`),
  run: (id: string) => send<RunDetail>('GET', `/runs/${enc(id)}`),
  cases: (id: string, p: { status?: string; change?: string; page?: number }) =>
    send<Page<CaseRow> & { counts: Record<string, number>; baselineRunId: string | null }>('GET', `/runs/${enc(id)}/cases${qs(p)}`),
  start: (suite: string) => send<Run>('POST', '/runs/start', { suite }),
  classes: (days?: number) => send<ClassBoardData>('GET', `/classes${qs({ days })}`, undefined, 300_000),
  classQuestions: (klass: string, p: { days?: number; page?: number }) =>
    send<Page<ClassItem> & { gateCases: GateCase[] }>('GET', `/classes/${enc(klass)}/questions${qs(p)}`, undefined, 300_000),
  queue: (p: { verdict?: string; state?: string; page?: number }) =>
    send<Page<FeedbackItem> & { counts: Record<string, number> }>('GET', `/queue${qs({ type: 'feedback', ...p })}`),
  decide: (id: string, b: { klass?: string; triageState?: TriageState; note?: string }) =>
    send<FeedbackItem>('PATCH', `/queue/feedback/${enc(id)}`, b),
  versions: (page = 0) =>
    send<Page<Version> & { installs: Array<{ at: string | null; env: string | null; codeSha: string | null; note: string | null }> }>(
      'GET',
      `/versions${qs({ page })}`,
    ),
  feedback: (b: { queryId: string; verdict: Verdict; comment?: string }) =>
    send<{ ok: boolean; verdict: Verdict; verdictLabel: string; message: string; comment: string | null }>('POST', '/feedback', b),
  clusters: (status = 'oneri') => send<ClusterList>('GET', `/clusters${qs({ status })}`),
  buildClusters: (days?: number) => send<{ started: boolean; job: ClusterJob }>('POST', `/clusters/build${qs({ days })}`),
  decideCluster: (id: string, b: { action: 'onayla' | 'reddet'; klass?: string; note?: string }) =>
    send<{ id: string; status: string; klass?: string; written: number }>('POST', `/clusters/${enc(id)}/decide`, b),
  mine: (queryId: string) =>
    send<{ feedback: { verdict: Verdict; comment: string | null; triageLabel: string } | null }>('GET', `/feedback/mine${qs({ queryId })}`),
};

/* ------------------------------------------------------------------ biçim */

const pct = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1 });
const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const num1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const dt = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
const day = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: '2-digit', month: 'short' });

export function fmtValue(v: number | null | undefined, kind?: string): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  if (kind === 'ratio') return pct.format(v);
  if (kind === 'ms') return v >= 1000 ? `${num1.format(v / 1000)} sn` : `${int0.format(v)} ms`;
  if (kind === 'score') return num1.format(v);
  return int0.format(v);
}
export const fmtAt = (v: string | null | undefined) => (v ? dt.format(new Date(v)) : '—');
export const fmtDay = (v: string | null | undefined) => (v ? day.format(new Date(v)) : '—');
export const fmtDuration = (sec: number | null | undefined) =>
  sec === null || sec === undefined ? '—' : sec < 90 ? `${sec} sn` : `${Math.round(sec / 60)} dk`;
export const shortSha = (v: string | null | undefined) => (v ? v.slice(0, 8) : '—');

export const STATUS_TONE: Record<CaseStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  saglam: 'ok',
  bozuk: 'err',
  kararsiz: 'warn',
  veri: 'muted',
  ret: 'muted',
  hata: 'err',
  yeni: 'violet',
};
export const RUN_TONE: Record<RunStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  sirada: 'violet',
  calisiyor: 'warn',
  bitti: 'ok',
  hata: 'err',
};
export const VERDICT_TONE: Record<Verdict, 'ok' | 'warn' | 'err'> = { dogru: 'ok', kismen: 'warn', yanlis: 'err' };
