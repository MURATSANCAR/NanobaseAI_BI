/** Client helpers for budget actuals templates (schema templates come from API). */

export type BiBudgetActualsTemplateId = string;

export type BiBudgetActualsTemplate = {
  id: string;
  kind?: string;
  labelKey?: string;
  label_key?: string;
  table?: string | null;
  table_name?: string | null;
  measure?: string | null;
  sql: string;
  demo?: boolean;
};

export const BI_BUDGET_NONE_TEMPLATE: BiBudgetActualsTemplate = {
  id: 'none',
  kind: 'none',
  labelKey: 'bi.budget.template.none',
  sql: '',
  demo: false,
};

export function resolveActualsTemplateId(
  sql: string | null | undefined,
  templates: BiBudgetActualsTemplate[],
): BiBudgetActualsTemplateId {
  const trimmed = (sql || '').trim();
  if (!trimmed) return 'none';
  const hit = templates.find((t) => t.sql && t.sql === trimmed);
  return hit ? hit.id : 'custom';
}

export function sqlForActualsTemplate(
  id: BiBudgetActualsTemplateId,
  templates: BiBudgetActualsTemplate[],
): string {
  if (id === 'custom') return '';
  return templates.find((t) => t.id === id)?.sql ?? '';
}

export function templateOptionLabel(
  tpl: BiBudgetActualsTemplate,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  if (tpl.kind === 'schema' && (tpl.table_name || tpl.measure)) {
    const table = tpl.table_name || tpl.table || '';
    const measure = tpl.measure || '';
    return t('bi.budget.template.fromSchema', { table: String(table), measure: String(measure) });
  }
  const key = tpl.labelKey || tpl.label_key || 'bi.budget.template.none';
  return t(key);
}
