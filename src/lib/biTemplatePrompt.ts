import type { BiQueryTemplate } from '@/api/types';
import type { Locale } from '@/i18n';
import { t } from '@/i18n';
import { biFieldLabel } from '@/utils/biFieldLabel';

export type BiTemplateCategory = 'query' | 'widget' | 'schedule';

export function biTemplateCategory(template: BiQueryTemplate | string): BiTemplateCategory {
  if (typeof template === 'string') {
    if (template.startsWith('widget_')) return 'widget';
    if (template.startsWith('schedule_')) return 'schedule';
    return 'query';
  }
  const cat = (template.category || '').toLowerCase();
  if (cat === 'widget' || cat === 'schedule' || cat === 'query') return cat;
  return biTemplateCategory(template.id);
}

/** Prefer kind + identifiers so locale labels stay natural (ş/ğ/ü), else stored prompt. */
export function biTemplatePrompt(template: BiQueryTemplate, locale: Locale): string {
  const kind = (template.kind || '').toLowerCase();
  const tableRaw = template.table_name?.trim();
  if (kind && tableRaw) {
    const table = biFieldLabel(tableRaw);
    const measure = template.measure ? biFieldLabel(template.measure) : '';
    const category = template.category_col
      ? biFieldLabel(template.category_col)
      : '';
    switch (kind) {
      case 'count':
      case 'row_count':
        return t('bi.templates.prompt.count', { table });
      case 'sum':
      case 'sum_measure':
        return t('bi.templates.prompt.sum', { table, measure: measure || t('bi.field.tutar') });
      case 'breakdown':
      case 'by_category':
        return t('bi.templates.prompt.breakdown', {
          table,
          category: category || t('bi.field.durum'),
        });
      case 'trend':
        return t('bi.templates.prompt.trend', { table });
      default:
        break;
    }
  }

  const key = `prompt_${locale}` as keyof BiQueryTemplate;
  const localized = template[key];
  if (typeof localized === 'string' && localized.trim()) return localized;
  return template.prompt_tr || template.prompt_en || template.id;
}
