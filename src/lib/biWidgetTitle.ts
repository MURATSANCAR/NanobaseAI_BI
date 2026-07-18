import type { BiQueryTemplate, BiWidget } from '@/api/types';
import type { Locale } from '@/i18n';
import { biTemplatePrompt } from '@/lib/biTemplatePrompt';

/** Resolve widget card title for the active portal locale (tr/en/ru/uz). */
export function biWidgetTitle(
  widget: BiWidget,
  locale: Locale,
  templates: BiQueryTemplate[] = [],
): string {
  const loc = (locale || 'en').slice(0, 2) as Locale;
  const fromMap = widget.titles?.[loc] || widget.titles?.en || widget.titles?.tr;
  if (fromMap?.trim()) return fromMap.trim();

  if (widget.template_id && templates.length) {
    const tpl = templates.find((t) => t.id === widget.template_id);
    if (tpl) return biTemplatePrompt(tpl, loc);
  }

  const current = (widget.title || '').trim();
  if (current && templates.length) {
    for (const tpl of templates) {
      const prompts = [tpl.prompt_en, tpl.prompt_tr, tpl.prompt_ru, tpl.prompt_uz]
        .filter((p): p is string => typeof p === 'string' && p.trim().length > 0)
        .map((p) => p.trim());
      if (prompts.includes(current)) return biTemplatePrompt(tpl, loc);
    }
  }

  return current || widget.id;
}
