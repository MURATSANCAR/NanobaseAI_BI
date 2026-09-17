/**
 * Semantic bridge istemcisi (:8795). Kokpitin kullandığı servis budur; Logo
 * veritabanına bağlı olan da odur. Portal API'si (:8790) iş verisi taşımıyor.
 *
 * Tarayıcıdan erişim nginx üzerinden `/timas/api/...` yoluna gider ve oturum
 * ister (auth_request). Oturum yoksa 401 döner; kartlar bunu "oturum gerekli"
 * diye gösterir, sahte sayı üretmez.
 */
import type { DbTiming } from './DbTiming';

const RAW_BASE = (import.meta.env.VITE_ENGINE_BASE as string | undefined) ?? '';
export const ENGINE_BASE = RAW_BASE.replace(/\/$/, '');
export const ENGINE_ENABLED = ENGINE_BASE.length > 0;

/** Motor 401 dedikten sonra tekrar tekrar denemek konsolu kirletiyor ve
 *  sunucuyu boşuna yoruyor. Giriş yapılana kadar yoklama durur. */
let authBlocked = false;
export const isAuthBlocked = (): boolean => authBlocked;
export const clearAuthBlock = (): void => {
  authBlocked = false;
};

export class EngineAuthError extends Error {
  constructor() {
    super('Zeki AI oturumu gerekli');
    this.name = 'EngineAuthError';
  }
}

export type SqlResult<T> = DbTiming & {
  columns: Array<{ name: string; type: string }>;
  records: T[];
  totalRows?: number;
  truncated?: boolean;
};

async function post<T>(path: string, body: unknown, timeoutMs = 45_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) throw new Error(`Zeki AI ${res.status}`);
  return (await res.json()) as T;
}

/** Kataloğa doğrulatılmış SQL çalıştırır. Motor katalog dışı tabloyu reddeder. */
/** limit 0: motorun kendi üst sınırı. İstemci ayrıca kesmez; kesilirse `truncated` gelir. */
export function runSql<T>(sql: string, limit = 0): Promise<SqlResult<T>> {
  return post<SqlResult<T>>('/api/v1/run_sql', { sql, limit });
}

export type EngineInfo = {
  dataSource?: string;
  models?: number;
  relationships?: number;
  certified?: number;
  catalogVersion?: number;
  project?: string;
  deployed?: boolean;
};

export async function engineInfo(): Promise<EngineInfo> {
  const res = await fetch(`${ENGINE_BASE}/api/v1/engine`, {
    credentials: 'include',
    signal: AbortSignal.timeout(15_000),
  });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) throw new Error(`Zeki AI ${res.status}`);
  return (await res.json()) as EngineInfo;
}

export type AskAnswer = DbTiming & {
  id?: string;
  type?: string;
  sql?: string;
  summary?: string;
  explanation?: string;
  columns?: Array<{ name: string; type: string }>;
  records?: Array<Record<string, unknown>>;
  rowCount?: number;
  latency_ms?: number;
};

/** Doğal dil sorusu. Motor SQL üretir, çalıştırır ve özetler. */
export function ask(question: string): Promise<AskAnswer> {
  return post<AskAnswer>('/api/v1/ask', { question, language: 'TR', execute: true, sampleSize: 50 }, 180_000);
}

/** Tablonun ait olduğu iş sistemi: Logo ERP ya da CRM. Motor şemadan belirler. */
export type DataSource = 'logo' | 'crm';

export type ConceptMapping = {
  id?: string;
  source?: DataSource | null;
  entity?: string;
  table_pattern?: string;
  column?: string | null;
  operator?: string | null;
  values?: string[];
  /** Metriğin hesabı: SUM(STLINE.AMOUNT) gibi. */
  formula?: string | null;
  time_primitive?: string | null;
  extra?: { func?: string; aliases?: string[]; conditions?: string[] };
};

export type Concept = {
  id: string;
  term: string;
  normalized_term?: string;
  semantic_type: string;
  status: string;
  domain?: string;
  confidence?: number;
  version?: number;
  synonyms?: string[];
  created_at?: string;
  updated_at?: string;
  explain?: {
    score?: number;
    human_reason?: string;
    schema_drift?: string;
    support?: { doc?: number; llm?: number; human?: number; validated_queries?: number };
    breakdown?: Record<string, number>;
    gate?: { passed?: boolean; reasons?: string[]; mode?: string; min_support?: number };
    human_certified_by?: string;
  };
};

export type ConceptRow = { concept: Concept; mappings?: ConceptMapping[] };

export type TableRow = {
  tableName: string;
  tablePattern?: string;
  entity?: string;
  schema?: string;
  description?: string;
  rowCount?: number;
  columnCount?: number;
  certifiedColumns?: number;
  primaryKey?: string[];
  scannedAt?: string;
  columns?: Array<{ name: string; type?: string; nullable?: boolean; isPrimaryKey?: boolean; sensitive?: boolean }>;
};

export type ReviewItem = {
  id: string;
  term: string;
  /** Kök terimin okunur hâli: "malzem" → "malzeme". Motor dağıtımın kendi kelimelerinden üretir. */
  label?: string;
  type: string;
  confidence?: number;
  source?: DataSource | null;
  mapping?: {
    entity?: string;
    column?: string | null;
    table_pattern?: string;
    operator?: string | null;
    values?: string[];
    formula?: string | null;
    extra?: { conditions?: string[]; ref_entity?: string; ref_column?: string; func?: string };
  };
  /** Motorun düz Türkçe cümlesi: bu terim neye karşılık geliyor. */
  plain?: string;
  /** Kolonun iş anlamı (varsa değer kodlarıyla birlikte). */
  columnMeaning?: string | null;
  /** Kolonda gerçekten görülen değerler ve satır sayıları. */
  observed?: Array<{ value: string; rows: number; label?: string }>;
  /** Gözlenen değerlerin okunduğu şema taraması. */
  scannedAt?: string | null;
  evidence?: Record<string, number>;
  counterEvidence?: number;
};

async function get<T>(path: string, timeoutMs = 20_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, { credentials: 'include', signal: AbortSignal.timeout(timeoutMs) });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) throw new Error(`Zeki AI ${res.status}`);
  return (await res.json()) as T;
}

/** Veri sözlüğü: sertifikalı kavramlar. */
export function concepts(status = 'CERTIFIED', limit = 200) {
  return get<{ items: ConceptRow[] }>(`/api/v1/semantic/concepts?status=${status}&limit=${limit}`);
}

/** Şema envanteri: tablolar, açıklamaları, satır sayıları ve kolonları. */
export function inventory() {
  return get<{ tables: TableRow[]; tableCount?: number; columnCount?: number }>('/api/v1/schema/inventory', 60_000);
}

export type GapItem = {
  tablePattern: string;
  example: string;
  source?: DataSource;
  copies: number;
  description: string | null;
  tableMissing: boolean;
  rows: number;
  columns: number;
  missing: number;
  suggestions: number;
};

export type GapSuggestion = { id: string; text: string; confidence: number; model?: string };

export type GapColumn = {
  name: string;
  type?: string;
  status: 'UNDEFINED' | 'DESCRIBED' | 'CANDIDATE' | 'CERTIFIED';
  isPrimaryKey?: boolean;
  ref?: string | null;
  sensitive?: boolean;
  distinct?: number | null;
  topValues: Array<[string, number]>;
  unit?: string | null;
  derived: string[];
  description: string | null;
  annotationId: string | null;
  suggestion: GapSuggestion | null;
};

export type GapDetail = {
  tablePattern: string;
  example: string;
  source?: DataSource;
  tables: Array<{ name: string; rows: number }>;
  description: string | null;
  tableAnnotationId: string | null;
  rows: number;
  /** Satır sayısı ve örnek değerler şema taramasında okundu (canlı sorgu değil). */
  scannedAt?: string | null;
  primaryKey?: string[];
  missing: GapColumn[];
  described: GapColumn[];
};

export type GapSummary = {
  patterns: number;
  patternsWithGaps: number;
  tablesWithoutDescription: number;
  columns: number;
  missingColumns: number;
  suggestions: number;
  bySource?: Record<DataSource, number>;
};

/** Veri sözlüğü: tablo kalıpları (yıl/firma kopyaları tek satır), eksik açıklamalar ve yazma uçları. */
export const gapsApi = {
  list: () => get<{ summary: GapSummary; items: GapItem[] }>('/api/v1/schema/gaps', 120_000),
  detail: (tablePattern: string) =>
    get<GapDetail>(`/api/v1/schema/gaps/detail?tablePattern=${encodeURIComponent(tablePattern)}`, 60_000),
  describe: (tablePattern: string, column: string | null, text: string) =>
    send<unknown>('POST', '/api/v1/schema/gaps/describe', { tablePattern, column, text }, 60_000),
  accept: (id: string) => send<unknown>('POST', `/api/v1/schema/gaps/suggestions/${encodeURIComponent(id)}/accept`, {}, 60_000),
  dismiss: (id: string) => send<unknown>('POST', `/api/v1/schema/gaps/suggestions/${encodeURIComponent(id)}/dismiss`, {}, 30_000),
};

export type Decision = 'APPROVE' | 'REJECT' | 'CORRECT';

/** Bir terim hakkında insanın kararı. CORRECT için açıklama zorunlu. */
export function decide(
  conceptId: string,
  body: { decision: Decision; note?: string; column?: string; entity?: string; term?: string; by?: string },
) {
  return post<{ ok?: boolean; status?: string; concept_id?: string }>(
    `/api/v1/semantic/concepts/${encodeURIComponent(conceptId)}/review`,
    body,
    60_000,
  );
}

/** Onay kuyruğu: insana sorulmayı bekleyen terimler. */
export function review(limit = 50) {
  return get<{ waiting: number; used: number; total: number; items: ReviewItem[] }>(
    `/api/v1/semantic/review?limit=${limit}`,
  );
}

/* ------------------------------------------------------------------ */
/* Eş anlamlılar — alan açıklamasından üretilir, insan onayıyla sözlüğe girer */
/* ------------------------------------------------------------------ */

export type VocabItem = {
  id: string;
  entity: string;
  column: string | null;
  term: string;
  role: 'COLUMN' | 'ENTITY' | 'METRIC';
  examples: string[];
  source: 'generated' | 'human';
  status: 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'DROPPED';
  reason?: string | null;
  conceptId?: string | null;
  decidedBy?: string | null;
  decidedAt?: string | null;
  createdAt?: string | null;
};
export type VocabGroup = { entity: string; column: string | null; source?: DataSource | null; items: VocabItem[] };
export type VocabCounts = Record<VocabItem['status'], number>;

export function vocabulary(status: 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'DROPPED' | 'ALL' = 'PROPOSED') {
  return get<{ groups: VocabGroup[]; counts: VocabCounts }>(`/api/v1/semantic/vocabulary?status=${status}&limit=5000`, 60_000);
}
export function vocabularyGaps() {
  return get<{ items: Array<{ entity: string; tablePattern: string; column: string; type: string; source?: DataSource | null }> }>('/api/v1/semantic/vocabulary/gaps', 60_000);
}
export function vocabularyDecide(id: string, decision: 'APPROVE' | 'REJECT', note?: string) {
  return post<{ id: string; status: string; conceptId?: string | null }>(`/api/v1/semantic/vocabulary/${encodeURIComponent(id)}/decide`, { decision, note }, 60_000);
}
export function vocabularyAdd(entity: string, column: string | null, term: string) {
  return post<{ id: string; status: string; conceptId?: string | null }>('/api/v1/semantic/vocabulary', { entity, column, term }, 60_000);
}
export function vocabularyGenerate(entity: string, column?: string | null) {
  return post<{ started: boolean }>('/api/v1/semantic/vocabulary/generate', { entity, column }, 60_000);
}
/** Bir alan için kullanıcının cümlesi; motor ondan hem kavram adayı hem eş anlamlı üretir. */
export function annotate(tablePattern: string, column: string | null, text: string) {
  return post<{ annotation: { id: string } }>('/api/v1/schema/annotations', { tablePattern, column, text }, 60_000);
}

/* ------------------------------------------------------------------ */
/* Uyarılar — kural bir sorudur, kontrolü sunucu yapar                  */
/* ------------------------------------------------------------------ */

export type AlertCondition = 'gt' | 'gte' | 'lt' | 'lte';

export type AlertRule = {
  id: string;
  title: string;
  question: string;
  sql: string;
  column: string | null;
  condition: AlertCondition;
  threshold: number;
  recipients: string[];
  status: 'active' | 'paused';
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_value: number | null;
  last_checked_at: string | null;
  last_triggered_at: string | null;
  state: 'unknown' | 'ok' | 'triggered' | 'error';
  last_error: string | null;
  last_notified_at: string | null;
  last_notify: 'sent' | 'failed' | 'no_smtp' | 'no_recipient' | null;
  /** Son ölçümde değerin veritabanından gelme süresi. */
  last_db?: DbTiming | null;
};

export type AlertEmail = { configured: boolean; sender: string | null };

export type AlertInput = {
  title: string;
  question: string;
  condition: AlertCondition;
  threshold: number;
  recipients: string[];
  column?: string | null;
};

/** GET dışı istekler; motorun düz Türkçe hata mesajını olduğu gibi taşır. */
async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 180_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || `Zeki AI ${res.status}`);
  }
  return (await res.json()) as T;
}

export const alertsApi = {
  list: () => send<{ user: string; alerts: AlertRule[]; email: AlertEmail }>('GET', '/api/v1/alerts'),
  create: (b: AlertInput) => send<AlertRule>('POST', '/api/v1/alerts', b),
  update: (id: string, b: Partial<AlertInput> & { status?: 'active' | 'paused' }) =>
    send<AlertRule>('PATCH', `/api/v1/alerts/${encodeURIComponent(id)}`, b),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/alerts/${encodeURIComponent(id)}`),
  check: (id?: string) =>
    send<{ checked: number; triggered: number; notified: number; errors: Array<{ id: string; error: string }> }>(
      'POST',
      `/api/v1/alerts/check${id ? `?id=${encodeURIComponent(id)}` : ''}`,
      {},
    ),
};

/* ------------------------------------------------------------------ pano */

export type BoardRefresh = 'manual' | 'hourly' | 'daily';

export type BoardCardResult = SqlResult<Record<string, unknown>> & { at: number };

/** Sunucudaki kart: kişiye özel, son sonucuyla birlikte gelir. */
export type BoardCardDto = {
  id: string;
  title: string;
  note: string;
  question: string;
  sql: string;
  chart: string;
  depth: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
  sqlOpen: boolean;
  refresh: BoardRefresh;
  refreshAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  lastAutoAt: string | null;
  lastError: string | null;
  result: BoardCardResult | null;
};

export const boardApi = {
  load: () => send<{ user: string; cards: BoardCardDto[] }>('GET', '/api/v1/board', undefined, 30_000),
  save: (cards: unknown[]) => send<{ user: string; cards: BoardCardDto[] }>('PUT', '/api/v1/board', { cards }, 30_000),
  run: (id: string) => send<BoardCardResult>('POST', `/api/v1/board/cards/${encodeURIComponent(id)}/run`, {}),
  /** Sunucuda üretilen Excel kitabı: özet + kart başına sayfa, tam veri, Excel grafiği. Boş liste = bütün kartlar. */
  exportXlsx: async (ids: string[] = []): Promise<{ blob: Blob; name: string }> => {
    const q = ids.length ? `?ids=${encodeURIComponent(ids.join(','))}` : '';
    const res = await fetch(`${ENGINE_BASE}/api/v1/board/export.xlsx${q}`, {
      credentials: 'include',
      signal: AbortSignal.timeout(600_000),
    });
    if (res.status === 401 || res.status === 403) {
      authBlocked = true;
      throw new EngineAuthError();
    }
    if (!res.ok) {
      const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
      const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
      throw new Error(msg || `Excel üretilemedi (${res.status})`);
    }
    const m = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '');
    return { blob: await res.blob(), name: m?.[1] ?? 'pano.xlsx' };
  },
};

/* ------------------------------------------------------------------ planlı raporlar */

export type ReportRecurrence = 'daily' | 'weekly' | 'monthly' | 'once';
export type ReportFormat = 'xlsx' | 'csv';
export type ReportStatus = 'active' | 'paused' | 'done';
export type ReportLastStatus = 'sent' | 'no_smtp' | 'no_recipient' | 'failed' | null;
export type ColumnFormat = 'auto' | 'text' | 'number' | 'money' | 'percent' | 'date';
/** Kişinin ekranda kurduğu kolon düzeni; `key` motorun verdiği kaynak kolon adıdır. Sıra dizinin sırasıdır. */
export type ReportColumn = { key: string; label: string; hidden: boolean; format: ColumnFormat };

export type ReportDto = {
  id: string;
  title: string;
  prompt: string;
  question: string;
  sql: string;
  fmt: ReportFormat;
  recurrence: ReportRecurrence;
  at: string;
  weekday: number | null;
  monthday: number | null;
  onceAt: string | null;
  recipients: string[];
  status: ReportStatus;
  createdAt: string | null;
  updatedAt: string | null;
  nextRunAt: string | null;
  lastRunAt: string | null;
  lastStatus: ReportLastStatus;
  lastError: string | null;
  lastRows: number | null;
  /** Son çalışmada verinin veritabanından gelme süresi; hiç çalışmadıysa null. */
  lastDb: DbTiming | null;
  hasFile: boolean;
  columns: ReportColumn[];
  /** "Her gün 08:00" gibi okunur plan. */
  when: string;
};

export type ReportDraft = DbTiming & {
  question: string;
  title: string;
  recurrence: ReportRecurrence;
  at: string;
  weekday: number | null;
  monthday: number | null;
  /** Tek seferlikte ayrıştırıcının bulduğu an ("bugün/yarın"), İstanbul saatli ISO. */
  onceAt?: string | null;
  recipients: string[];
  fmt: ReportFormat;
  sql: string;
  columns: Array<{ name: string; type: string }>;
  records: Array<Record<string, unknown>>;
  rowCount?: number | null;
  summary?: string;
  layout: ReportColumn[];
};

/** Önizlemede düzeltme sonucu. `requery` ise veri yeniden çekildi ve sql/columns/records geldi. */
export type ReportRefinement = DbTiming & {
  question: string;
  requery: boolean;
  via: 'rules' | 'model';
  changes: string[];
  layout: ReportColumn[];
  added: string[];
  dropped: string[];
  sql?: string;
  columns?: Array<{ name: string; type: string }>;
  records?: Array<Record<string, unknown>>;
  rowCount?: number | null;
  summary?: string;
};

export type ReportInput = {
  title: string;
  prompt?: string;
  question: string;
  sql?: string;
  fmt: ReportFormat;
  recurrence: ReportRecurrence;
  at: string;
  weekday?: number | null;
  monthday?: number | null;
  onceAt?: string | null;
  recipients: string[];
  status?: ReportStatus;
  columns?: ReportColumn[];
};

export const reportsApi = {
  list: () => send<{ user: string; reports: ReportDto[]; email: AlertEmail }>('GET', '/api/v1/reports', undefined, 30_000),
  parse: (text: string) => send<ReportDraft>('POST', '/api/v1/reports/parse', { text }, 600_000),
  refine: (b: { question: string; instruction: string; columns: ReportColumn[] }) =>
    send<ReportRefinement>('POST', '/api/v1/reports/refine', b, 600_000),
  preview: (b: { question: string; columns: ReportColumn[] }) =>
    send<Omit<ReportRefinement, 'requery' | 'via' | 'changes'>>('POST', '/api/v1/reports/preview', b, 600_000),
  create: (b: ReportInput) => send<ReportDto>('POST', '/api/v1/reports', b, 30_000),
  update: (id: string, b: Partial<ReportInput>) => send<ReportDto>('PATCH', `/api/v1/reports/${encodeURIComponent(id)}`, b, 30_000),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/reports/${encodeURIComponent(id)}`, undefined, 30_000),
  run: (id: string) => send<ReportDto>('POST', `/api/v1/reports/${encodeURIComponent(id)}/run`, {}, 600_000),
  fileUrl: (id: string) => `${ENGINE_BASE}/api/v1/reports/${encodeURIComponent(id)}/file`,
};

/* ------------------------------------------------------------------ yönetim */

export type AdminSettingType = 'text' | 'int' | 'bool' | 'secret' | 'email' | 'users' | 'time';

export type AdminSetting = {
  key: string;
  group: string;
  label: string;
  type: AdminSettingType;
  help: string;
  /** Gizli alanlarda her zaman null; yalnız `hasValue` söylenir. */
  value: string | null;
  hasValue: boolean;
  /** screen: yönetim ekranında kaydedildi · env: servis ortam dosyası · file: giriş servisi dosyası · default: varsayılan */
  source: 'screen' | 'env' | 'file' | 'default';
  updatedBy: string | null;
  updatedAt: string | null;
};

export type AdminSettings = { groups: Array<{ id: string; label: string; help: string }>; items: AdminSetting[] };

export type AdminUnit = {
  unit: string;
  label: string;
  every?: string;
  state: string;
  sub?: string | null;
  last?: string | null;
  next?: string | null;
  result?: string | null;
};

export type AuditItem = {
  id: number;
  at: string;
  actor: string;
  action: string;
  kind: string;
  kindLabel: string;
  objectId: string | null;
  title: string | null;
  detail: Record<string, unknown> | null;
};

export type AdminOverview = {
  counts: {
    reports: number;
    reportsActive: number;
    reportsFailed: number;
    alerts: number;
    alertsActive: number;
    alertsTriggered: number;
    cards: number;
    cardsFailed: number;
    users: number;
    admins: number;
  };
  email: AlertEmail;
  engine: { model: string; llm: boolean; db: boolean; catalog: Record<string, number>; profiles: number };
  services: AdminUnit[];
  timers: AdminUnit[];
  recent: AuditItem[];
};

/** Bağlantı denemesinin sonucu: ne denendi, ne zaman, ne kadar sürdü. */
export type AdminCheck = {
  id: string;
  group: string | null;
  label: string;
  ok: boolean;
  message: string;
  ms: number;
  at: string;
};

export type AdminSystem = {
  items: Array<{ label: string; value: string }>;
  checks: Array<{ id: string; group: string | null; label: string }>;
};

export type AdminReport = ReportDto & { owner: string };

export type AdminCard = {
  id: string;
  owner: string;
  title: string;
  question: string;
  chart: string;
  refresh: string;
  refreshAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  resultAt: string | null;
  lastAutoAt: string | null;
  lastError: string | null;
};

export type AdminUser = { username: string; cards: number; reports: number; actions: number; lastSeen: string | null; admin: boolean };

export type AuditQuery = { kind?: string; action?: string; actor?: string; q?: string; before?: number };

/* --------------------------------------------------------------- promt izleyici */

/** Promt izleyicide liste satırı (hafif: tam sonuç/çözümleme yok). */
export type PromptRow = {
  id: string;
  question: string;
  username: string | null;
  threadId: string | null;
  sql: string | null;
  compiler: string | null;
  answerType: string | null;
  answerSummary: string | null;
  executed: boolean;
  rowCount: number | null;
  latencyMs: number | null;
  error: string | null;
  validated: boolean | null;
  catalogVersion: number | null;
  reviewFlag: 'todo' | 'fixed' | 'ignored' | null;
  reviewNote: string | null;
  reviewedBy: string | null;
  reviewedAt: string | null;
  createdAt: string | null;
};

/** Tek promtun her şeyi: SQL, tam sonuç satırları, semantik çözümleme, kapı kararları. */
export type PromptDetail = PromptRow & {
  resolved: Record<string, unknown>;
  result: { columns: Array<{ name: string }>; records: Array<Record<string, unknown>>; totalRows?: number; truncated?: boolean; _truncated_store?: boolean } | null;
  gate: Record<string, unknown> | null;
};

export type PromptOverview = {
  sinceDays: number;
  total: number;
  answered: number;
  failed: number;
  todo: number;
  byType: Record<string, number>;
  byCompiler: Record<string, number>;
  unresolvedTerms: Array<[string, number]>;
  topFailing: Array<{ question: string; count: number }>;
};

export type PromptQuery = { limit?: number; offset?: number; only?: string; q?: string; user?: string; days?: number };

const qs = (o: Record<string, string | number | undefined>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const adminApi = {
  me: () => send<{ user: string; isAdmin: boolean }>('GET', '/api/v1/admin/me', undefined, 15_000),
  overview: () => send<AdminOverview>('GET', '/api/v1/admin/overview', undefined, 30_000),
  settings: () => send<AdminSettings>('GET', '/api/v1/admin/settings', undefined, 15_000),
  saveSettings: (values: Record<string, string>) =>
    send<AdminSettings & { changed: string[]; applied: string[]; applyError: string | null }>(
      'PUT',
      '/api/v1/admin/settings',
      { values },
      60_000,
    ),
  resetSetting: (key: string) => send<AdminSettings>('DELETE', `/api/v1/admin/settings/${encodeURIComponent(key)}`, undefined, 15_000),
  testEmail: (to: string) => send<{ ok: boolean; message: string }>('POST', '/api/v1/admin/email/test', { to }, 60_000),
  testDirectory: (username: string) =>
    send<{ ok: boolean; message: string }>('POST', '/api/v1/admin/directory/test', { username }, 30_000),
  /** Tek bağlantı denemesi: database · crm · llm · directory · email · store. */
  test: (id: string) => send<AdminCheck>('POST', `/api/v1/admin/tests/${encodeURIComponent(id)}`, undefined, 120_000),
  testAll: () => send<{ items: AdminCheck[]; ok: boolean; at: string }>('POST', '/api/v1/admin/tests', undefined, 180_000),
  system: () => send<AdminSystem>('GET', '/api/v1/admin/system', undefined, 15_000),
  reports: () => send<{ items: AdminReport[] }>('GET', '/api/v1/admin/reports', undefined, 30_000),
  updateReport: (id: string, b: Partial<ReportInput>) =>
    send<ReportDto>('PATCH', `/api/v1/admin/reports/${encodeURIComponent(id)}`, b, 30_000),
  deleteReport: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/admin/reports/${encodeURIComponent(id)}`, undefined, 30_000),
  alerts: () => send<{ items: AlertRule[] }>('GET', '/api/v1/admin/alerts', undefined, 30_000),
  updateAlert: (id: string, b: Partial<AlertInput> & { status?: 'active' | 'paused' }) =>
    send<AlertRule>('PATCH', `/api/v1/admin/alerts/${encodeURIComponent(id)}`, b, 30_000),
  deleteAlert: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/admin/alerts/${encodeURIComponent(id)}`, undefined, 30_000),
  cards: () => send<{ items: AdminCard[] }>('GET', '/api/v1/admin/cards', undefined, 30_000),
  deleteCard: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/admin/cards/${encodeURIComponent(id)}`, undefined, 30_000),
  users: () => send<{ items: AdminUser[] }>('GET', '/api/v1/admin/users', undefined, 30_000),
  audit: (q: AuditQuery) => send<{ items: AuditItem[]; next: number | null }>('GET', `/api/v1/admin/audit${qs(q)}`, undefined, 30_000),
  prompts: (q: PromptQuery) =>
    send<{ items: PromptRow[]; hasMore: boolean; nextOffset: number | null }>('GET', `/api/v1/admin/prompts${qs(q)}`, undefined, 30_000),
  promptsOverview: (days = 30) => send<PromptOverview>('GET', `/api/v1/admin/prompts/overview${qs({ days })}`, undefined, 30_000),
  prompt: (id: string) => send<PromptDetail>('GET', `/api/v1/admin/prompts/${encodeURIComponent(id)}`, undefined, 30_000),
  markPrompt: (id: string, b: { flag?: string; note?: string }) =>
    send<PromptDetail>('PATCH', `/api/v1/admin/prompts/${encodeURIComponent(id)}`, b, 30_000),
  /** CSV indirme adresi (aynı köken, oturum çerezi taşınır). */
  promptsExportUrl: (q: PromptQuery) => `${ENGINE_BASE}/api/v1/admin/prompts/export.csv${qs(q)}`,
};

/* ------------------------------------------------------------------ kişi tercihleri */

/** Kişinin kendi ekran alanları (AD hesabına bağlı, sunucuda). */
export const prefsApi = {
  get: <T,>(key: string) =>
    send<{ user: string; key: string; value: T | null; updatedAt: string | null }>('GET', `/api/v1/me/prefs/${encodeURIComponent(key)}`, undefined, 15_000),
  put: <T,>(key: string, value: T) =>
    send<{ user: string; key: string; value: T; updatedAt: string }>('PUT', `/api/v1/me/prefs/${encodeURIComponent(key)}`, { value }, 15_000),
  remove: (key: string) => send<{ ok: boolean }>('DELETE', `/api/v1/me/prefs/${encodeURIComponent(key)}`, undefined, 15_000),
};

/* ------------------------------------------------------------------ toplantı odaları */

export type Room = { id: string; name: string; location: string; capacity: number | null; active: boolean };
export type RoomBooking = {
  id: string;
  roomId: string;
  roomName?: string;
  start: string;
  end: string;
  /** İstanbul günü, YYYY-AA-GG. */
  date: string;
  startLocal: string;
  endLocal: string;
  username: string;
  displayName: string;
  title: string;
  mine: boolean;
  canCancel: boolean;
};
export type RoomGrid = { start: string; end: string; slotMinutes: number; startMin: number; endMin: number };
export type RoomsMe = { username: string; displayName: string; admin: boolean };
export type RoomsDay = { date: string; today: string; grid: RoomGrid; rooms: Room[]; bookings: RoomBooking[]; me: RoomsMe };
export type RoomNow = Room & { current: RoomBooking | null; next: RoomBooking | null };
export type RoomsNow = { now: string; today: string; rooms: RoomNow[]; me: RoomsMe };

/** Oda servisinin düz Türkçe hatası. 409'da saati kimin aldığı `booking` içinde gelir. */
export class RoomsError extends Error {
  constructor(message: string, readonly status: number, readonly booking?: RoomBooking) {
    super(message);
    this.name = 'RoomsError';
  }
}

/** `send` 403'ü oturum düşmesi sayar; burada 403 "bu işi yapamazsın" demektir, oturum yerinde kalır. */
async function roomsSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
  if (res.status === 401) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string; booking?: RoomBooking } | string } | null;
    const d = j?.detail;
    const msg = typeof d === 'string' ? d : d?.message;
    throw new RoomsError(msg || `Oda servisi ${res.status}`, res.status, typeof d === 'object' ? d?.booking : undefined);
  }
  return (await res.json()) as T;
}

export type Greeting = { id: string; from: string; to: string; occasion: string | null; at: string; seen: boolean };

/** Kampüs kutlamaları: `sent` bugün kutladıklarım, `inbox` bana gelen ve henüz görmediklerim,
 *  `received` son 30 günde bana gelenlerin hepsi (zil), `wall` herkesin son 30 günü (alkış duvarı). */
export const greetingsApi = {
  state: () => roomsSend<{ sent: string[]; inbox: Greeting[]; received: Greeting[]; wall: Greeting[] }>('GET', '/api/v1/greetings'),
  send: (to: string, occasion?: string) => roomsSend<Greeting & { created: boolean }>('POST', '/api/v1/greetings', { to, occasion }),
  seen: (ids: string[]) => roomsSend<{ marked: number }>('POST', '/api/v1/greetings/seen', { ids }),
};

/* ------------------------------------------------------------------ kişi rehberi ve profil */

/** CRM'deki gerçek, etkin kullanıcı. Boş alan "". dahili/kat CRM'de yoksa kişinin profilinden gelir. */
export type Person = {
  id: string;
  username: string;
  name: string;
  title: string;
  unit: string;
  email: string;
  mobile: string;
  phone: string;
  extension: string;
  floor: string;
  desk?: string;
  about?: string;
  photoVersion: number | null;
};
export type PeopleList = { items: Person[]; total: number; truncated: boolean; source: 'crm'; adChecked: boolean; at: string; db?: DbTiming | null };
export type ProfileFields = { extension: string; floor: string; desk: string; mobile: string; about: string };
export type MyProfile = {
  username: string;
  displayName: string;
  inCrm: boolean;
  crm: Person | null;
  fields: ProfileFields;
  photoVersion: number | null;
  updatedAt: string | null;
  /** CRM kaydının veritabanından gelme süresi; CRM okunamadıysa null. */
  db?: DbTiming | null;
};

export const photoUrl = (username: string, version: number | null) =>
  version ? `${ENGINE_BASE}/api/v1/people/${encodeURIComponent(username)}/photo?v=${version}` : null;

export const peopleApi = {
  list: () => roomsSend<PeopleList>('GET', '/api/v1/people'),
  me: () => roomsSend<MyProfile>('GET', '/api/v1/me/profile'),
  save: (fields: ProfileFields) => roomsSend<MyProfile>('PUT', '/api/v1/me/profile', { fields }),
  savePhoto: (dataUrl: string) => roomsSend<{ photoVersion: number }>('PUT', '/api/v1/me/profile/photo', { dataUrl }),
  deletePhoto: () => roomsSend<{ ok: boolean }>('DELETE', '/api/v1/me/profile/photo'),
};

export const roomsApi = {
  day: (date: string) => roomsSend<RoomsDay>('GET', `/api/v1/rooms?date=${encodeURIComponent(date)}`),
  now: () => roomsSend<RoomsNow>('GET', '/api/v1/rooms/now'),
  book: (roomId: string, b: { date: string; start: string; end: string; title: string }) =>
    roomsSend<RoomBooking>('POST', `/api/v1/rooms/${encodeURIComponent(roomId)}/bookings`, b),
  cancel: (id: string) => roomsSend<{ ok: boolean; booking: RoomBooking }>('DELETE', `/api/v1/rooms/bookings/${encodeURIComponent(id)}`),
  addRoom: (b: { name: string; location: string; capacity: number | null }) => roomsSend<Room>('POST', '/api/v1/admin/rooms', b),
  removeRoom: (id: string) =>
    roomsSend<Room & { cancelledBookings: number }>('DELETE', `/api/v1/admin/rooms/${encodeURIComponent(id)}`),
};
