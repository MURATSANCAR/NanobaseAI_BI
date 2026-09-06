/**
 * Semantik motor istemcisi (wren-ui REST + GraphQL).
 * Tüm çağrılar aynı origin'deki /api altına gider; geliştirmede vite proxy, üretimde reverse proxy
 * bunları wren-ui:3000'e iletir. Motor yetenekleri (modelleme, deploy, thread'ler) olduğu gibi korunur;
 * bu dosya yalnız istemci sarmalayıcıdır.
 */

const BASE = (import.meta.env.VITE_WREN_BASE as string | undefined) ?? '';

export type SqlColumn = { name: string; type: string };
export type SqlResult = { id: string; columns: SqlColumn[]; records: Record<string, unknown>[]; totalRows: number; threadId?: string };

export class WrenError extends Error {
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
      throw new WrenError(String(data.error ?? data.message ?? `HTTP ${res.status}`), data.code as string | undefined, res.status);
    }
    return data as T;
  } finally {
    clearTimeout(t);
  }
}

/** Deterministik SQL çalıştırır (model adlarıyla: dbo_LG_411_01_INVOICE ...). */
export function runSql(sql: string, limit = 500): Promise<SqlResult> {
  return post<SqlResult>('/api/v1/run_sql', { sql, limit });
}

export type AskResult = {
  id: string;
  sql?: string;
  summary?: string;
  threadId?: string;
  explanation?: string;
  [k: string]: unknown;
};

/** Doğal dil soru → SQL (+ özet). threadId verilirse takip sorusu olarak işlenir. */
export function ask(question: string, threadId?: string): Promise<AskResult> {
  return post<AskResult>('/api/v1/ask', { question, language: 'TR', sampleSize: 50, ...(threadId ? { threadId } : {}) }, 240_000);
}

/** Sonuç için Türkçe özet (motorun kendi özetleyicisi). */
export function generateSummary(question: string, sql: string, sampleSize = 50): Promise<{ summary?: string }> {
  return post<{ summary?: string }>('/api/v1/generate_summary', { question, sql, language: 'TR', sampleSize }, 180_000);
}

export async function graphql<T>(query: string, variables?: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${BASE}/api/graphql`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, variables }),
  });
  const data = (await res.json()) as { data?: T; errors?: { message: string }[] };
  if (data.errors?.length) throw new WrenError(data.errors.map((e) => e.message).join('; '));
  return data.data as T;
}

/** Motor durumu: bağlı veri kaynağı ve deploy edilmiş modeller. */
export async function engineStatus(): Promise<{ dataSource: string; models: number; deployed: boolean }> {
  const d = await graphql<{
    settings: { dataSource: { type: string; properties: { displayName?: string } } };
    listModels: { id: number }[];
  }>('query { settings { dataSource { type properties } } listModels { id } }');
  // SELECT 1 model olmadan da geçer; gerçek deploy kontrolü modele dokunmalı.
  let deployed = true;
  try {
    await runSql('SELECT "LOGICALREF" FROM dbo_LG_411_01_INVOICE LIMIT 1', 1);
  } catch {
    deployed = false;
  }
  return {
    dataSource: d.settings.dataSource.properties?.displayName ?? d.settings.dataSource.type,
    models: d.listModels.length,
    deployed,
  };
}
