import type { BiWidget, BiWidgetData, BiChatResponse } from '@/api/types';
import { normalizeResultColumns } from '@/utils/biChatSanitize';

const TIME_HINT = /(date|time|tarih|gun|gün|ay|yil|yıl|week|hafta|month|year|period|donem|dönem)/i;

function isNumber(value: unknown): boolean {
  if (typeof value === 'boolean') return false;
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value === 'string') {
    const s = value.trim().replace(/,/g, '');
    if (!s) return false;
    return Number.isFinite(Number(s));
  }
  return false;
}

function looksLikeTime(col: string, rows: Array<Record<string, unknown>>): boolean {
  if (TIME_HINT.test(col || '')) return true;
  let hits = 0;
  let checked = 0;
  for (const row of rows.slice(0, 12)) {
    const val = row[col];
    if (val == null || val === '') continue;
    checked += 1;
    if (val instanceof Date) {
      hits += 1;
      continue;
    }
    const s = String(val).trim();
    if (/^\d{4}([-/.]\d{1,2}){1,2}/.test(s) || /^\d{4}-\d{2}/.test(s)) hits += 1;
  }
  return checked > 0 && hits / checked >= 0.5;
}

function numericCols(cols: string[], rows: Array<Record<string, unknown>>): string[] {
  return cols.filter((col) => {
    const sample = rows.slice(0, 30).map((r) => r[col]);
    const nonempty = sample.filter((v) => v != null && v !== '');
    if (!nonempty.length) return false;
    return nonempty.filter(isNumber).length / nonempty.length >= 0.7;
  });
}

function widgetId(sql: string, title: string, wtype: string): string {
  let hash = 0;
  const s = `${sql}|${title}|${wtype}`;
  for (let i = 0; i < s.length; i += 1) hash = (hash * 31 + s.charCodeAt(i)) >>> 0;
  return `chat_${hash.toString(16).padStart(8, '0')}`;
}

/** Infer a chart/KPI/table widget from an executed chat query_result. */
export function widgetsFromQueryResult(opts: {
  data?: BiWidgetData | null;
  sql?: string | null;
  title?: string | null;
}): BiWidget[] {
  const cols = normalizeResultColumns(opts.data?.columns);
  const rows = (opts.data?.rows ?? []).filter(
    (r): r is Record<string, unknown> => !!r && typeof r === 'object' && !Array.isArray(r),
  );
  const resolvedCols = cols.length ? cols : rows[0] ? Object.keys(rows[0]) : [];
  if (!resolvedCols.length || !rows.length) return [];

  const sql = (opts.sql || '').trim() || undefined;
  const title = (opts.title || '').replace(/\s+/g, ' ').trim().slice(0, 80) || 'Chat sonucu';
  const data: BiWidgetData = {
    columns: resolvedCols,
    rows,
    row_count: opts.data?.row_count ?? rows.length,
  };
  const nums = numericCols(resolvedCols, rows);
  const cats = resolvedCols.filter((c) => !nums.includes(c));

  const base = (type: string, extra: Partial<BiWidget> = {}): BiWidget => ({
    id: widgetId(sql || title, title, type),
    type,
    title,
    sql,
    data,
    ...extra,
  });

  if (rows.length === 1 && nums.length === 1 && resolvedCols.length <= 2) {
    return [base('kpi', { value_key: nums[0], format: 'number' })];
  }

  if (rows.length === 1 && nums.length >= 2 && nums.length <= 4) {
    const row0 = rows[0]!;
    const mcRows = nums.map((c) => ({ label: c, value: row0[c] }));
    return [
      {
        id: widgetId(sql || title, title, 'multi_card'),
        type: 'multi_card',
        title,
        sql,
        label_key: 'label',
        value_key: 'value',
        data: { columns: ['label', 'value'], rows: mcRows, row_count: mcRows.length },
      },
    ];
  }

  if (cats.length && nums.length && rows.length >= 2) {
    const xk = cats[0]!;
    const yk = nums[0]!;
    let type: string = 'bar';
    if (looksLikeTime(xk, rows)) type = 'line';
    else if (rows.length <= 8 && cats.length === 1) type = 'pie';
    return [base(type, { x_key: xk, y_key: yk, label_key: xk, value_key: yk })];
  }

  return [base('table')];
}

/** Ensure chat responses carry widgets for chart preview / pin. */
export function ensureChatWidgets(result: BiChatResponse): BiChatResponse {
  if ((result.widgets?.length ?? 0) > 0) return result;
  if (!result.query_result?.rows?.length) return result;
  const title =
    (result.reply || '').replace(/\s+/g, ' ').trim().slice(0, 80) ||
    undefined;
  return {
    ...result,
    widgets: widgetsFromQueryResult({
      data: result.query_result,
      sql: result.sql,
      title,
    }),
  };
}
