import clsx from 'clsx';
import { CalendarClock, LayoutDashboard, Loader2, MessageSquare, Search, Sparkles, Trash2 } from 'lucide-react';
import EmptyState from '@/components/EmptyState';
import type { BiQueryTemplate } from '@/api/types';
import { getLocale, t } from '@/i18n';
import { biTemplateCategory, biTemplatePrompt, type BiTemplateCategory } from '@/lib/biTemplatePrompt';

type BiQueryTemplateGridProps = {
  templates: BiQueryTemplate[];
  loading?: boolean;
  compact?: boolean;
  limit?: number;
  selectedIds?: string[];
  warmReadyIds?: Set<string>;
  onToggleSelect?: (id: string) => void;
  onSelect: (prompt: string, template: BiQueryTemplate) => void;
  onSeed?: (template: BiQueryTemplate) => void;
  onDelete?: (template: BiQueryTemplate) => void;
  seedingId?: string | null;
  className?: string;
};

function categoryIcon(category: BiTemplateCategory) {
  switch (category) {
    case 'widget':
      return LayoutDashboard;
    case 'schedule':
      return CalendarClock;
    default:
      return Search;
  }
}

function categoryTone(category: BiTemplateCategory): string {
  switch (category) {
    case 'widget':
      return 'border-indigo-200/80 bg-indigo-50/80 text-indigo-800';
    case 'schedule':
      return 'border-violet-200/80 bg-violet-50/80 text-violet-800';
    default:
      return 'border-sky-200/80 bg-sky-50/80 text-sky-800';
  }
}

function isCustom(tpl: BiQueryTemplate): boolean {
  return tpl.source === 'custom' || tpl.id.startsWith('custom-');
}

export default function BiQueryTemplateGrid({
  templates,
  loading,
  compact,
  limit,
  selectedIds,
  warmReadyIds,
  onToggleSelect,
  onSelect,
  onSeed,
  onDelete,
  seedingId,
  className,
}: BiQueryTemplateGridProps) {
  const locale = getLocale();
  const items = limit ? templates.slice(0, limit) : templates;
  const selectable = Boolean(onToggleSelect) && !compact;

  if (loading) {
    return (
      <div className={clsx('flex items-center justify-center gap-2 py-8 text-sm text-slate-500', className)}>
        <Loader2 className="h-5 w-5 animate-spin text-accent" />
        {t('common.loading')}
      </div>
    );
  }

  if (!items.length) {
    return (
      <EmptyState
        emoji="📋"
        titleKey="empty.bi.templates.title"
        descriptionKey="empty.bi.templates.description"
        ctaLabelKey="empty.bi.templates.cta"
        ctaTo="/bi/sources"
        className={className}
      />
    );
  }

  if (compact) {
    return (
      <div className={clsx('flex w-full max-w-md flex-col gap-2', className)}>
        {items.map((tpl) => {
          const prompt = biTemplatePrompt(tpl, locale);
          const ready = Boolean(warmReadyIds?.has(tpl.id) || tpl.sql_hint);
          return (
            <button
              key={tpl.id}
              type="button"
              className="ai-pill w-full justify-start gap-2 px-3 py-2.5 text-left text-sm normal-case tracking-normal"
              onClick={() => onSelect(prompt, tpl)}
            >
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-violet-500" />
              <span className="min-w-0 flex-1 line-clamp-2">{prompt}</span>
              {ready ? (
                <span className="shrink-0 rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800">
                  {warmReadyIds?.has(tpl.id) ? t('bi.templatesInstant') : t('bi.templatesPrepared')}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className={clsx('grid gap-4 sm:grid-cols-2 xl:grid-cols-3', className)}>
      {items.map((tpl) => {
        const category = biTemplateCategory(tpl);
        const Icon = categoryIcon(category);
        const prompt = biTemplatePrompt(tpl, locale);
        const categoryKey = `bi.templatesCategory.${category}` as const;
        const canSeed = Boolean(onSeed && tpl.sql_hint);
        const selected = selectedIds?.includes(tpl.id) ?? false;

        return (
          <article
            key={tpl.id}
            className={clsx(
              'card ai-panel-glow flex flex-col gap-3 border-sky-200/50 bg-gradient-to-br from-white to-sky-50/30 p-4 transition hover:border-sky-300/70 hover:shadow-lg hover:shadow-sky-100/60',
              selected && 'ring-2 ring-violet-400',
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <span
                className={clsx(
                  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide',
                  categoryTone(category),
                )}
              >
                <Icon className="h-3 w-3" />
                {t(categoryKey)}
              </span>
              {selectable ? (
                <label className="inline-flex items-center gap-1.5 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => onToggleSelect?.(tpl.id)}
                    className="h-4 w-4 rounded border-slate-300"
                  />
                  {t('bi.templatesSelect')}
                </label>
              ) : null}
            </div>
            <p className="flex-1 text-sm leading-relaxed text-slate-800">{prompt}</p>
            <div className="flex flex-wrap gap-2 pt-1">
              <button type="button" className="btn-primary flex-1 text-xs sm:flex-none" onClick={() => onSelect(prompt, tpl)}>
                <MessageSquare className="h-3.5 w-3.5" />
                {t('bi.templatesAskChat')}
              </button>
              {canSeed && (
                <button
                  type="button"
                  className="btn-secondary flex-1 text-xs sm:flex-none"
                  disabled={seedingId === tpl.id}
                  onClick={() => onSeed?.(tpl)}
                >
                  {seedingId === tpl.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <LayoutDashboard className="h-3.5 w-3.5" />
                  )}
                  {t('bi.templatesSeedWidget')}
                </button>
              )}
              {onDelete && isCustom(tpl) ? (
                <button
                  type="button"
                  className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-status-fail hover:bg-red-50"
                  title={t('common.delete')}
                  onClick={() => onDelete(tpl)}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}
