import { useEffect, useId, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, X } from 'lucide-react';
import { api, type ApiConfig } from '@/api/client';
import { BiCardWidget, BiTableWidget, BiVisualChart } from '@/components/bi/BiCharts';
import { BI_PIN_VIZ_OPTIONS, normalizeVisualType } from '@/components/bi/biVisualTypes';
import type { BiWidget } from '@/api/types';
import { t } from '@/i18n';
import { biVisualTypeLabel, biWidgetTitle } from '@/utils/biFieldLabel';
import { localizeUserMessage } from '@/utils/backendLabels';

const TYPE_OPTIONS = BI_PIN_VIZ_OPTIONS;

function isKpiWidget(type: string | undefined) {
  const n = normalizeVisualType(type);
  return n === 'kpi' || n === 'metric' || n === 'card';
}

/** Instant detail view — change type + persist; rows already on the widget. */
export default function BiWidgetDetailSheet({
  widget,
  config,
  datasourceId,
  onClose,
  onUpdated,
}: {
  widget: BiWidget;
  config: ApiConfig;
  datasourceId?: string;
  onClose: () => void;
  onUpdated?: (w: BiWidget) => void;
}) {
  const titleId = useId();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<BiWidget>(widget);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  useEffect(() => {
    setDraft(widget);
    setSaveMsg(null);
  }, [widget]);

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

  const saveType = useMutation({
    mutationFn: (nextType: string) =>
      api.bi.analytics.updateSourceWidgetType(config, widget.id, {
        type: nextType,
        datasource_id: datasourceId,
      }),
    onSuccess: (_res, nextType) => {
      const next = { ...draft, type: nextType };
      setDraft(next);
      onUpdated?.(next);
      void qc.invalidateQueries({ queryKey: ['bi-analytics-source-widgets'] });
      setSaveMsg(t('bi.analytics.widgetTypeSaved'));
    },
    onError: (err) => {
      setSaveMsg(localizeUserMessage((err as Error).message));
    },
  });

  const kpi = isKpiWidget(draft.type);
  const rowCount = draft.data?.row_count ?? draft.data?.rows?.length ?? 0;
  const currentType = normalizeVisualType(draft.type);

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
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="truncate text-base font-semibold text-slate-900">
              {biWidgetTitle(draft)}
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {t('bi.analytics.widgetDetailMeta', {
                rows: String(rowCount),
                type: biVisualTypeLabel(draft.type),
              })}
            </p>
            <label className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-600">
              <span className="font-semibold uppercase tracking-wide text-slate-500">
                {t('bi.analytics.widgetType')}
              </span>
              <select
                className="min-h-10 min-w-[10rem] rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-200"
                value={TYPE_OPTIONS.includes(currentType as (typeof TYPE_OPTIONS)[number]) ? currentType : 'table'}
                disabled={saveType.isPending}
                onChange={(e) => {
                  const nextType = e.target.value;
                  setDraft((prev) => ({ ...prev, type: nextType }));
                  setSaveMsg(null);
                  saveType.mutate(nextType);
                }}
                aria-label={t('bi.analytics.widgetType')}
              >
                {TYPE_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {biVisualTypeLabel(opt)}
                  </option>
                ))}
              </select>
              {saveType.isPending ? <Loader2 className="h-4 w-4 animate-spin text-sky-600" /> : null}
              {saveMsg ? (
                <span
                  className={
                    saveType.isError ? 'text-rose-600' : 'text-emerald-700'
                  }
                  role="status"
                >
                  {saveMsg}
                </span>
              ) : null}
            </label>
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
          <div className="bi-pbi-tile bi-pbi-tile--3d bi-pbi-tile--vivid overflow-visible p-3" data-accent={0}>
            <div className="bi-pbi-tile-depth" aria-hidden />
            <div className="bi-pbi-tile-shine" aria-hidden />
            <div className="relative z-[1] overflow-hidden rounded-xl">
              {kpi ? (
                <BiCardWidget widget={draft} kpi variant="preview" />
              ) : (
                <BiVisualChart widget={draft} variant="preview" height={280} />
              )}
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {t('bi.analytics.widgetDataTable')}
            </h3>
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
              <BiTableWidget widget={draft} maxRows={200} maxHeight={420} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
