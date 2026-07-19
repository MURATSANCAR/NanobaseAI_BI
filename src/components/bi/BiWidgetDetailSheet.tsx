import { useEffect, useId } from 'react';
import { X } from 'lucide-react';
import { BiCardWidget, BiTableWidget, BiVisualChart } from '@/components/bi/BiCharts';
import type { BiWidget } from '@/api/types';
import { t } from '@/i18n';

function isKpiWidget(widget: BiWidget) {
  return widget.type === 'kpi' || widget.type === 'metric' || widget.type === 'card';
}

/** Instant detail view — uses rows already loaded on the widget (no extra API). */
export default function BiWidgetDetailSheet({
  widget,
  onClose,
}: {
  widget: BiWidget;
  onClose: () => void;
}) {
  const titleId = useId();
  const kpi = isKpiWidget(widget);
  const rowCount = widget.data?.row_count ?? widget.data?.rows?.length ?? 0;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[80] flex items-end justify-center bg-slate-900/45 p-0 backdrop-blur-[2px] sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 px-4 py-3 sm:px-5">
          <div className="min-w-0">
            <h2 id={titleId} className="truncate text-base font-semibold text-slate-900">
              {widget.title || widget.id}
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {t('bi.analytics.widgetDetailMeta', {
                rows: String(rowCount),
                type: widget.type || 'widget',
              })}
            </p>
          </div>
          <button
            type="button"
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50"
            onClick={onClose}
            aria-label={t('common.close')}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:px-5">
          <div className="rounded-xl border border-slate-200 bg-[#F8F8F8] p-3">
            {kpi ? (
              <BiCardWidget widget={widget} kpi variant="preview" />
            ) : (
              <BiVisualChart widget={widget} variant="preview" height={280} />
            )}
          </div>
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {t('bi.analytics.widgetDataTable')}
            </h3>
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
              <BiTableWidget widget={widget} maxRows={200} maxHeight={420} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
