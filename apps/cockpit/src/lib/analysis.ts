import type { AskResult, SqlResult } from './engine';
import type { ChartKind } from '../components/ResultChart';

export type Analysis = {
  question: string;
  answer: AskResult;
  result: SqlResult;
  chart?: ChartKind;
  overview?: boolean;
};

export function resultOf(a: AskResult): SqlResult | undefined {
  if (a.type !== 'TEXT_TO_SQL' || !Array.isArray(a.records) || !Array.isArray(a.columns)) return undefined;
  return { id: String(a.resultId ?? a.id ?? ''), columns: a.columns, records: a.records,
    totalRows: Number(a.totalRows ?? a.rowCount ?? a.records.length), truncated: a.truncated,
    computedAt: a.computedAt as number | undefined, cached: a.cached as boolean | undefined,
    ageSec: a.ageSec as number | undefined, widget: a.widget,
    dataCoverage: a.dataCoverage as SqlResult['dataCoverage'], presentation: a.presentation as SqlResult['presentation'] };
}

export const label = (s: string) => s.replace(/_/g, ' ');
export const numberText = (v: unknown) => v == null ? 'Veri yok' : typeof v === 'number' ? new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(v) : String(v);
export const complete = (r: SqlResult) => !r.truncated && r.records.length === r.totalRows;

/** No null-to-zero coercion, no totals of averages, no totals of a preview. */
export function metricValue(r: SqlResult, key: string, additive: boolean): number | null {
  if (!complete(r)) return null;
  if (r.records.length > 1 && !additive) return null;
  const values = r.records.map(row => row[key]).filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  return values.length ? values.reduce((sum, v) => sum + v, 0) : null;
}

export function change(current: unknown, reference: unknown) {
  if (typeof current !== 'number' || typeof reference !== 'number' || !Number.isFinite(current) || !Number.isFinite(reference)) return null;
  return { absolute: current - reference, percent: reference === 0 ? null : (current - reference) / Math.abs(reference) * 100 };
}

/** Only an entire explicit presentation command edits locally; unknown words go to the engine. */
export function chartCommand(text: string): ChartKind | undefined {
  const q = text.toLocaleLowerCase('tr-TR').trim().replace(/[.!?]+$/, '');
  const commands: Record<string, ChartKind> = {
    'bunu sütun grafik yap': 'column', 'sütun grafik yap': 'column',
    'bunu çizgi grafik yap': 'line', 'çizgi grafik yap': 'line',
    'bunu çubuk grafik yap': 'bar', 'bunu pasta grafik yap': 'pie', 'tablo olarak göster': 'table',
  };
  return commands[q];
}

export function rollup(r: SqlResult, dimension: string, metric: string): Record<string, unknown>[] {
  if (!complete(r) || !r.presentation?.metrics.some(m => m.key === metric && m.additive)) return [];
  const groups = new Map<string, { category: unknown; value: number | null }>();
  for (const row of r.records) {
    const category = row[dimension];
    const id = JSON.stringify(category ?? null);
    const group = groups.get(id) ?? { category, value: null };
    const v = row[metric];
    if (typeof v === 'number' && Number.isFinite(v)) group.value = (group.value ?? 0) + v;
    groups.set(id, group);
  }
  return [...groups.values()].map(g => ({ category: g.category ?? 'Belirtilmemiş', value: g.value }));
}
