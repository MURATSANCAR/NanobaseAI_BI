import type { BiSchemaColumn, BiSchemaTable } from '@/api/types';

export const ALERT_VALUE_COLUMN = 'alert_value';

export type BiAlertAggregate = 'count' | 'count_distinct' | 'sum' | 'avg' | 'min' | 'max';

export type BiAlertFilterOp =
  | 'eq'
  | 'neq'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'contains'
  | 'is_null'
  | 'is_not_null';

export type BiAlertFilter = {
  id: string;
  column: string;
  op: BiAlertFilterOp;
  value: string;
};

/** Visual rule that compiles to threshold-alert SQL. */
export type BiAlertStructuredRule = {
  table: string;
  schema?: string;
  tableName?: string;
  aggregate: BiAlertAggregate;
  /** Required for sum/avg/min/max/count_distinct; ignored for row count. */
  measureColumn?: string;
  filters: BiAlertFilter[];
};

export type CompileAlertRuleResult = {
  sql: string;
  column: string;
  summary: string;
};

const AGGREGATES_NEEDING_COLUMN: BiAlertAggregate[] = [
  'sum',
  'avg',
  'min',
  'max',
  'count_distinct',
];

export function emptyAlertRule(): BiAlertStructuredRule {
  return {
    table: '',
    aggregate: 'count',
    measureColumn: '',
    filters: [],
  };
}

export function newAlertFilter(partial?: Partial<BiAlertFilter>): BiAlertFilter {
  return {
    id: `f-${Math.random().toString(36).slice(2, 9)}`,
    column: '',
    op: 'eq',
    value: '',
    ...partial,
  };
}

export function quoteIdent(name: string): string {
  return `"${String(name).replace(/"/g, '""')}"`;
}

export function quoteLiteral(value: string): string {
  return `'${String(value).replace(/'/g, "''")}'`;
}

export function isNumericColumnType(type: string | undefined | null): boolean {
  const t = (type || '').toLowerCase();
  if (!t) return false;
  return (
    t.includes('int') ||
    t.includes('numeric') ||
    t.includes('decimal') ||
    t.includes('number') ||
    t.includes('float') ||
    t.includes('double') ||
    t.includes('real') ||
    t.includes('money') ||
    t === 'bigint' ||
    t === 'smallint'
  );
}

export function numericColumns(table: BiSchemaTable | undefined): BiSchemaColumn[] {
  if (!table) return [];
  return table.columns.filter((c) => isNumericColumnType(c.type_display || c.type));
}

export function aggregateNeedsColumn(aggregate: BiAlertAggregate): boolean {
  return AGGREGATES_NEEDING_COLUMN.includes(aggregate);
}

export function resolveAlertTable(
  tables: BiSchemaTable[],
  rule: BiAlertStructuredRule | null | undefined,
): BiSchemaTable | undefined {
  if (!rule?.table) return undefined;
  return (
    tables.find((t) => t.full_name === rule.table) ||
    tables.find((t) => t.name === rule.table) ||
    tables.find((t) => `${t.schema || 'public'}.${t.name}` === rule.table)
  );
}

function tableRef(rule: BiAlertStructuredRule, table?: BiSchemaTable): string {
  if (table?.schema && table.name) {
    return `${quoteIdent(table.schema)}.${quoteIdent(table.name)}`;
  }
  if (rule.schema && rule.tableName) {
    return `${quoteIdent(rule.schema)}.${quoteIdent(rule.tableName)}`;
  }
  const raw = rule.table.trim();
  if (raw.includes('.') && !raw.includes('"')) {
    const [schema, ...rest] = raw.split('.');
    const name = rest.join('.');
    if (schema && name) return `${quoteIdent(schema)}.${quoteIdent(name)}`;
  }
  return quoteIdent(raw);
}

function columnTypeMap(table?: BiSchemaTable): Map<string, string> {
  const map = new Map<string, string>();
  for (const col of table?.columns ?? []) {
    map.set(col.name, col.type_display || col.type || '');
  }
  return map;
}

function formatFilterValue(op: BiAlertFilterOp, value: string, colType: string): string {
  if (op === 'contains') {
    const escaped = value.replace(/[%_\\]/g, (ch) => `\\${ch}`).replace(/'/g, "''");
    return `'%${escaped}%'`;
  }
  const trimmed = value.trim();
  if (isNumericColumnType(colType) && /^-?\d+(\.\d+)?$/.test(trimmed)) {
    return trimmed;
  }
  if (!isNumericColumnType(colType) && /^-?\d+(\.\d+)?$/.test(trimmed) && (op === 'gt' || op === 'gte' || op === 'lt' || op === 'lte')) {
    return trimmed;
  }
  return quoteLiteral(trimmed);
}

function compileFilter(
  filter: BiAlertFilter,
  types: Map<string, string>,
): string | null {
  const col = filter.column?.trim();
  if (!col) return null;
  const ident = quoteIdent(col);
  const colType = types.get(col) || '';
  switch (filter.op) {
    case 'is_null':
      return `${ident} IS NULL`;
    case 'is_not_null':
      return `${ident} IS NOT NULL`;
    case 'contains':
      if (!filter.value.trim()) return null;
      return `${ident} ILIKE ${formatFilterValue('contains', filter.value, colType)}`;
    case 'eq':
      if (!filter.value.trim()) return null;
      return `${ident} = ${formatFilterValue('eq', filter.value, colType)}`;
    case 'neq':
      if (!filter.value.trim()) return null;
      return `${ident} <> ${formatFilterValue('neq', filter.value, colType)}`;
    case 'gt':
      if (!filter.value.trim()) return null;
      return `${ident} > ${formatFilterValue('gt', filter.value, colType)}`;
    case 'gte':
      if (!filter.value.trim()) return null;
      return `${ident} >= ${formatFilterValue('gte', filter.value, colType)}`;
    case 'lt':
      if (!filter.value.trim()) return null;
      return `${ident} < ${formatFilterValue('lt', filter.value, colType)}`;
    case 'lte':
      if (!filter.value.trim()) return null;
      return `${ident} <= ${formatFilterValue('lte', filter.value, colType)}`;
    default:
      return null;
  }
}

function selectExpr(rule: BiAlertStructuredRule): string | null {
  const agg = rule.aggregate;
  if (agg === 'count') {
    return `COUNT(*) AS ${quoteIdent(ALERT_VALUE_COLUMN)}`;
  }
  const measure = rule.measureColumn?.trim();
  if (!measure) return null;
  const m = quoteIdent(measure);
  if (agg === 'count_distinct') return `COUNT(DISTINCT ${m}) AS ${quoteIdent(ALERT_VALUE_COLUMN)}`;
  if (agg === 'sum') return `SUM(${m}) AS ${quoteIdent(ALERT_VALUE_COLUMN)}`;
  if (agg === 'avg') return `AVG(${m}) AS ${quoteIdent(ALERT_VALUE_COLUMN)}`;
  if (agg === 'min') return `MIN(${m}) AS ${quoteIdent(ALERT_VALUE_COLUMN)}`;
  if (agg === 'max') return `MAX(${m}) AS ${quoteIdent(ALERT_VALUE_COLUMN)}`;
  return null;
}

export function validateAlertRule(
  rule: BiAlertStructuredRule | null | undefined,
): string | null {
  if (!rule?.table?.trim()) return 'table';
  if (aggregateNeedsColumn(rule.aggregate) && !rule.measureColumn?.trim()) return 'measure';
  for (const f of rule.filters) {
    if (!f.column?.trim()) return 'filter_column';
    if (f.op !== 'is_null' && f.op !== 'is_not_null' && !String(f.value ?? '').trim()) {
      return 'filter_value';
    }
  }
  return null;
}

export function compileAlertRule(
  rule: BiAlertStructuredRule,
  tables: BiSchemaTable[] = [],
): CompileAlertRuleResult | null {
  if (validateAlertRule(rule)) return null;
  const table = resolveAlertTable(tables, rule);
  const select = selectExpr(rule);
  if (!select) return null;
  const types = columnTypeMap(table);
  const whereParts = rule.filters
    .map((f) => compileFilter(f, types))
    .filter((p): p is string => Boolean(p));
  const from = tableRef(rule, table);
  const where = whereParts.length ? ` WHERE ${whereParts.join(' AND ')}` : '';
  const sql = `SELECT ${select}\nFROM ${from}${where}`;
  const measure =
    rule.aggregate === 'count'
      ? 'COUNT(*)'
      : rule.aggregate === 'count_distinct'
        ? `COUNT(DISTINCT ${rule.measureColumn})`
        : `${rule.aggregate.toUpperCase()}(${rule.measureColumn})`;
  const filterHint = whereParts.length ? ` · ${whereParts.length} filter(s)` : '';
  return {
    sql,
    column: ALERT_VALUE_COLUMN,
    summary: `${measure} · ${rule.table}${filterHint}`,
  };
}

export function isStructuredAlertRule(value: unknown): value is BiAlertStructuredRule {
  if (!value || typeof value !== 'object') return false;
  const r = value as BiAlertStructuredRule;
  return typeof r.table === 'string' && typeof r.aggregate === 'string' && Array.isArray(r.filters);
}
