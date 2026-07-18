import type { ApiConfig } from '@/api/client';
import { api } from '@/api/client';
import type { BiQueryTemplate, BiWidgetData } from '@/api/types';

export type BiWarmEntry = {
  template_id: string;
  sql: string;
  result: BiWidgetData;
  duration_ms?: number;
  ready: boolean;
  error?: string;
};

const cache = new Map<string, BiWarmEntry>();
let warming = false;

export function getTemplateWarm(templateId: string): BiWarmEntry | undefined {
  return cache.get(templateId);
}

export function clearTemplateWarmCache(): void {
  cache.clear();
}

/** Background-warm sql_hint for ready chips — click can skip Text2SQL. */
export async function warmTemplatesInBackground(
  config: ApiConfig,
  templates: BiQueryTemplate[],
  limit = 6,
): Promise<void> {
  if (warming) return;
  const withSql = templates.filter((t) => Boolean(t.sql_hint?.trim())).slice(0, limit);
  if (!withSql.length) return;
  warming = true;
  try {
    const out = await api.bi.warmTemplates(config, {
      template_ids: withSql.map((t) => t.id),
    });
    for (const row of out.results ?? []) {
      const tid = String(row.template_id || '');
      if (!tid) continue;
      if (row.ok && row.result) {
        cache.set(tid, {
          template_id: tid,
          sql: String(row.sql || ''),
          result: row.result as BiWidgetData,
          duration_ms: typeof row.duration_ms === 'number' ? row.duration_ms : undefined,
          ready: true,
        });
      } else if (row.error) {
        cache.set(tid, {
          template_id: tid,
          sql: String(row.sql || ''),
          result: { columns: [], rows: [], row_count: 0 },
          ready: false,
          error: String(row.error),
        });
      }
    }
  } catch {
    /* warm is best-effort — click still uses prepared_sql fast path */
  } finally {
    warming = false;
  }
}
