/**
 * Semantik motor istemcisi — NanobaseAI Semantic Bridge (backend/semantic_bridge, :8795).
 * Tüm çağrılar aynı origin'deki /api altına gider; geliştirmede vite proxy, üretimde reverse proxy
 * bunları köprüye iletir. Sözleşme: /api/v1/ask, /api/v1/run_sql, /api/v1/generate_summary,
 * /api/v1/engine, /api/v1/feedback. Bu dosya yalnız istemci sarmalayıcıdır.
 */

const BASE = ((import.meta.env.VITE_ENGINE_BASE as string | undefined) ?? '');

export type SqlColumn = { name: string; type: string };

/** Köprünün sonuç setinden çıkardığı görselleştirme spec'i (BiWidget sözleşmesi).
 *  Karar deterministik ve backend'de: backend/nanobase_api/chat_widgets.py — ana uygulamayla ortak.
 *  `data` yalnız multi_card'da dolu gelir; diğer tiplerde satırlar `records`tedir. */
export type WidgetSpec = {
  id: string;
  type: 'kpi' | 'multi_card' | 'line' | 'bar' | 'pie' | 'table' | (string & {});
  title: string;
  x_key?: string;
  y_key?: string;
  label_key?: string;
  value_key?: string;
  format?: 'number' | 'percent' | 'currency';
  data?: { columns: string[]; rows: Record<string, unknown>[]; row_count?: number };
};

export type SqlResult = {
  id: string;
  columns: SqlColumn[];
  records: Record<string, unknown>[];
  totalRows: number;
  threadId?: string;
  widget?: WidgetSpec;
};

export class EngineError extends Error {
  constructor(message: string, public code?: string, public status?: number) {
    super(message);
  }
}

async function post<T>(path: string, body: unknown, timeoutMs = 120_000): Promise<T> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctl.signal,
    });
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok || data.code === 'INVALID_SQL_ERROR' || (typeof data.error === 'string' && data.error)) {
      throw new EngineError(String(data.error ?? data.message ?? `HTTP ${res.status}`), data.code as string | undefined, res.status);
    }
    return data as T;
  } finally {
    clearTimeout(t);
  }
}

/** Deterministik SQL çalıştırır (model adlarıyla: dbo_LG_411_01_INVOICE ...).
 *  `question` verilirse köprü sonuç setine göre bir `widget` spec'i de döndürür (grafik başlığı = soru). */
export function runSql(sql: string, limit = 500, question?: string): Promise<SqlResult> {
  return post<SqlResult>('/api/v1/run_sql', { sql, limit, ...(question ? { question } : {}) });
}

/** Köprünün her cevaba iliştirdiği anlam izi: hangi terim neye çözümlendi, hangi derleyici üretti. */
export type SemanticTrace = {
  compiler?: 'deterministic' | 'existing_llm' | 'supersonic' | (string & {});
  certified?: boolean;
  catalogVersion?: number;
  explain?: string[];
  query?: {
    slots?: Array<{ term: string; semanticType: string; status: string; mapping?: Record<string, unknown> | null; confidence?: number }>;
    unresolved?: string[];
    conflicts?: string[];
    temporal?: Array<{ text: string; primitive: string; start?: string | null; end?: string | null; ambiguous?: boolean }>;
    explanation?: string[];
  };
};

export type AskResult = {
  id: string;
  sql?: string;
  summary?: string;
  threadId?: string;
  explanation?: string;
  queryId?: string;
  semantic?: SemanticTrace;
  [k: string]: unknown;
};

/** Kullanıcının "doğru/yanlış" işareti: doğrulanmış çift havuzuna yazılır, gece madenciliğine girer. */
export function sendFeedback(queryId: string, validated: boolean): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>('/api/v1/feedback', { queryId, validated }, 30_000);
}

/** Doğal dil soru → SQL (+ özet). threadId verilirse takip sorusu olarak işlenir. */
export function ask(question: string, threadId?: string): Promise<AskResult> {
  return post<AskResult>('/api/v1/ask', { question, language: 'TR', sampleSize: 50, ...(threadId ? { threadId } : {}) }, 240_000);
}

/** Sonuç için Türkçe özet (motorun kendi özetleyicisi). */
export function generateSummary(question: string, sql: string, sampleSize = 50): Promise<{ summary?: string }> {
  return post<{ summary?: string }>('/api/v1/generate_summary', { question, sql, language: 'TR', sampleSize }, 180_000);
}


/** Motor durumu: bağlı veri kaynağı, profillenmiş model sayısı ve katalog sürümü (GET /api/v1/engine). */
export async function engineStatus(): Promise<{ dataSource: string; models: number; deployed: boolean }> {
  const res = await fetch(`${BASE}/api/v1/engine`);
  const d = (await res.json().catch(() => ({}))) as { dataSource?: string; models?: number; deployed?: boolean; error?: string };
  if (!res.ok) throw new EngineError(String(d.error ?? `HTTP ${res.status}`), undefined, res.status);
  return { dataSource: d.dataSource ?? 'mssql', models: Number(d.models ?? 0), deployed: Boolean(d.deployed) };
}

// ---------------------------------------------------------------- veri sözlüğü

/** Bir kolon hakkında bilinenler. Üç ayrı okuma yan yana durur ve hiçbiri diğerini ezmez:
 *  kaynağın kendi yorumu, bu sistemin veriden çıkardığı, ve bir kişinin buraya yazdığı. */
export type CatalogColumn = {
  name: string;
  type: string;
  nullable?: boolean;
  isPrimaryKey?: boolean;
  ref?: string | null;
  sensitive?: boolean;
  sensitivityReason?: string | null;
  sentinelValues?: string[];
  distinct?: number | null;
  topValues?: Array<[string, number]>;
  description?: string | null;
  derived?: Array<{ source: string; text: string }>;
  unit?: string | null;
  annotations: Array<{ id: string; text: string; author: string; createdAt: string }>;
  concepts: Array<{ id: string; term: string; type: string; status: string; values?: string[]; formula?: string }>;
  status: 'CERTIFIED' | 'CANDIDATE' | 'DESCRIBED' | 'UNDEFINED' | (string & {});
};

export type CatalogTable = {
  entity: string;
  tableName: string;
  tablePattern: string;
  schema: string;
  description?: string | null;
  rowCount?: number | null;
  primaryKey: string[];
  relationships: Array<{ column: string; ref_entity: string; ref_column: string }>;
  annotations: Array<{ id: string; text: string; author: string; createdAt: string }>;
  columns: CatalogColumn[];
  columnCount: number;
  certifiedColumns?: number;
  undefinedColumns: number;
};

export type CatalogPage = {
  tables: CatalogTable[];
  tableCount: number;
  total: number;
  /** Katalog okunamadığında dolu gelir — boş liste "veri yok" demek değildir. */
  warning?: string;
};

async function get<T>(path: string, timeoutMs = 60_000): Promise<T> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}`, { signal: ctl.signal });
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok) throw new EngineError(String(data.error ?? data.message ?? `HTTP ${res.status}`), data.code as string | undefined, res.status);
    return data as T;
  } finally {
    clearTimeout(t);
  }
}

/** Tablo listesi. Kolon ayrıntısı istenmez — tüm envanter sekiz megabayt, liste birkaç kilobayt. */
export function catalogTables(search: string, limit = 60, offset = 0): Promise<CatalogPage> {
  const qs = new URLSearchParams({ columns: 'false', limit: String(limit), offset: String(offset) });
  if (search.trim()) qs.set('q', search.trim());
  return get<CatalogPage>(`/api/v1/schema/inventory?${qs.toString()}`);
}

/** Tek bir tablonun kolonları — açıldığında istenir. */
export function catalogTable(entity: string): Promise<CatalogPage> {
  return get<CatalogPage>(`/api/v1/schema/inventory?entity=${encodeURIComponent(entity)}`);
}

export function writeLabel(tablePattern: string, column: string | null, text: string, author = 'kokpit'): Promise<{ annotation: { id: string } }> {
  return post('/api/v1/schema/annotations', { tablePattern, column, text, author });
}

/** Düzeltme yeni bir cümledir: eskisi geri çekilir, kayıtta kalır, modele yalnız yenisi gider. */
export async function rewriteLabel(id: string, tablePattern: string, column: string | null, text: string, author = 'kokpit'): Promise<{ annotation: { id: string } }> {
  const res = await fetch(`${BASE}/api/v1/schema/annotations/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tablePattern, column, text, author }),
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) throw new EngineError(String(data.error ?? data.message ?? `HTTP ${res.status}`), data.code as string | undefined, res.status);
  return data as { annotation: { id: string } };
}
