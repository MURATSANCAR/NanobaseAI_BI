import { t } from '@/i18n';
import { biFieldLabel } from '@/utils/biFieldLabel';

export type BiKpiSuggestionItem = {
  id: string;
  kind: string;
  table?: string;
  table_name?: string;
  measure?: string | null;
  category?: string | null;
  date_column?: string | null;
  title?: string;
  prompt?: string;
  reason?: string;
  sql_hint?: string;
};

function tableLabel(item: BiKpiSuggestionItem): string {
  const raw = (item.table_name || item.table || '').split('.').pop() || '';
  return biFieldLabel(raw);
}

/** Operator-facing chip text for a schema KPI suggestion. */
export function kpiSuggestionTitle(item: BiKpiSuggestionItem): string {
  const table = tableLabel(item);
  const measure = item.measure ? biFieldLabel(item.measure) : '';
  const category = item.category ? biFieldLabel(item.category) : '';
  switch (item.kind) {
    case 'count':
      return t('bi.kpiSuggest.chip.count', { table });
    case 'sum':
      return t('bi.kpiSuggest.chip.sum', { table, measure });
    case 'breakdown':
      return t('bi.kpiSuggest.chip.breakdown', { table, measure, category });
    case 'trend':
      return t('bi.kpiSuggest.chip.trend', { table });
    default:
      return item.title?.trim() || table;
  }
}

/** Prompt sent to chat — localized, still actionable for the BI assistant. */
export function kpiSuggestionPrompt(item: BiKpiSuggestionItem): string {
  const table = tableLabel(item);
  const measure = item.measure ? biFieldLabel(item.measure) : '';
  const category = item.category ? biFieldLabel(item.category) : '';
  switch (item.kind) {
    case 'count':
      return t('bi.kpiSuggest.prompt.count', { table });
    case 'sum':
      return t('bi.kpiSuggest.prompt.sum', { table, measure });
    case 'breakdown':
      return t('bi.kpiSuggest.prompt.breakdown', { table, measure, category });
    case 'trend':
      return t('bi.kpiSuggest.prompt.trend', { table });
    default:
      return item.prompt?.trim() || kpiSuggestionTitle(item);
  }
}
