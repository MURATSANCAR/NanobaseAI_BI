/**
 * Semantic bridge istemcisi (:8795). Kokpitin kullandığı servis budur; Logo
 * veritabanına bağlı olan da odur. Portal API'si (:8790) iş verisi taşımıyor.
 *
 * Tarayıcıdan erişim nginx üzerinden `/timas/api/...` yoluna gider ve oturum
 * ister (auth_request). Oturum yoksa 401 döner; kartlar bunu "oturum gerekli"
 * diye gösterir, sahte sayı üretmez.
 */
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
    super('Motor oturumu gerekli');
    this.name = 'EngineAuthError';
  }
}

export type SqlResult<T> = {
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
  if (!res.ok) throw new Error(`Motor ${res.status}`);
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
  if (!res.ok) throw new Error(`Motor ${res.status}`);
  return (await res.json()) as EngineInfo;
}

export type AskAnswer = {
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

export type ConceptMapping = {
  id?: string;
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
  evidence?: Record<string, number>;
  counterEvidence?: number;
};

async function get<T>(path: string, timeoutMs = 20_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, { credentials: 'include', signal: AbortSignal.timeout(timeoutMs) });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) throw new Error(`Motor ${res.status}`);
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
    throw new Error(msg || `Motor ${res.status}`);
  }
  return (await res.json()) as T;
}

export const alertsApi = {
  list: () => send<{ alerts: AlertRule[]; email: AlertEmail }>('GET', '/api/v1/alerts'),
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
