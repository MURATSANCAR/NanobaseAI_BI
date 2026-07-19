import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Loader2, RefreshCw, Table2 } from 'lucide-react';
import { api, type ApiConfig } from '@/api/client';
import { BiCardWidget, BiVisualChart } from '@/components/bi/BiCharts';
import BiWidgetDetailSheet from '@/components/bi/BiWidgetDetailSheet';
import type { BiWidget } from '@/api/types';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';
import { biVisualTypeLabel, biWidgetTitle } from '@/utils/biFieldLabel';

type Props = {
  config: ApiConfig;
  datasourceId?: string;
  sourceLabel?: string;
  className?: string;
};

function isKpiWidget(widget: BiWidget) {
  return widget.type === 'kpi' || widget.type === 'metric' || widget.type === 'card';
}

function WidgetTile({
  widget,
  index,
  onOpen,
}: {
  widget: BiWidget;
  index: number;
  onOpen: (w: BiWidget) => void;
}) {
  const kpi = isKpiWidget(widget);
  const accent = index % 8;
  return (
    <button
      type="button"
      onClick={() => onOpen(widget)}
      className={
        kpi
          ? 'bi-pbi-tile bi-pbi-tile--3d bi-pbi-tile--vivid bi-pbi-tile--kpi flex min-h-[9.5rem] w-full flex-col overflow-hidden p-0 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400'
          : 'bi-pbi-tile bi-pbi-tile--3d bi-pbi-tile--vivid flex min-h-[17rem] w-full flex-col overflow-hidden p-0 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 sm:col-span-2 lg:col-span-2'
      }
      data-accent={accent}
      aria-label={t('bi.analytics.openWidgetDetail', { title: biWidgetTitle(widget) })}
    >
      <div className="bi-pbi-tile-glow" aria-hidden />
      <div className="bi-pbi-tile-shine" aria-hidden />
      <div className="bi-pbi-tile-accent" data-visual={widget.type || 'card'} aria-hidden />
      <div className="relative z-[1] flex min-h-0 flex-1 flex-col px-3.5 pb-3 pt-3.5 sm:px-4">
        <div className="mb-2 flex items-start justify-between gap-2">
          <h3 className="bi-pbi-tile-title min-w-0 flex-1 truncate text-[11px] font-bold uppercase tracking-wide text-slate-700 sm:text-xs">
            {biWidgetTitle(widget)}
          </h3>
          <span className="bi-pbi-type-chip bi-pbi-type-chip--compact shrink-0" data-accent={accent}>
            {biVisualTypeLabel(widget.type)}
          </span>
        </div>
        <div className="pointer-events-none min-h-0 flex-1">
          {kpi ? (
            <BiCardWidget widget={widget} kpi variant="tile" />
          ) : (
            <BiVisualChart widget={widget} variant="tile" height={232} />
          )}
        </div>
        <p className="mt-2 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500/90">
          <Table2 className="h-3 w-3" aria-hidden />
          {t('bi.analytics.viewData')}
        </p>
      </div>
    </button>
  );
}

/** Main analytics surface: live, non-empty widgets for the active BI datasource. */
export default function BiSourceAnalyticsCanvas({
  config,
  datasourceId,
  sourceLabel,
  className,
}: Props) {
  const [selected, setSelected] = useState<BiWidget | null>(null);

  const widgetsQ = useQuery({
    queryKey: ['bi-analytics-source-widgets', config, datasourceId],
    queryFn: () => api.bi.analytics.sourceWidgets(config, datasourceId),
    enabled: Boolean(datasourceId),
    staleTime: 45_000,
    refetchInterval: 90_000,
  });

  const widgets = (widgetsQ.data?.widgets ?? []).filter((w) => {
    const rows = w.data?.rows ?? [];
    return rows.length > 0;
  });

  return (
    <div className={`bi-analytics-canvas--vivid flex min-h-0 flex-1 flex-col overflow-hidden ${className || ''}`}>
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/50 bg-white/70 px-3 py-2 backdrop-blur-md sm:px-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">
            {sourceLabel || datasourceId || t('bi.analytics.title')}
          </p>
          <p className="truncate text-[11px] text-slate-500">{t('bi.analytics.sourceCanvasHint')}</p>
        </div>
        <button
          type="button"
          className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-white/70 bg-white/90 px-3 py-2 text-xs font-medium text-slate-700 shadow-sm hover:bg-white"
          onClick={() => void widgetsQ.refetch()}
          disabled={widgetsQ.isFetching}
        >
          {widgetsQ.isFetching ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          {t('common.refresh')}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-4">
        {widgetsQ.isLoading ? (
          <div className="flex h-full min-h-[12rem] items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            {t('bi.analytics.loading')}
          </div>
        ) : widgetsQ.isError ? (
          <p className="rounded-xl border border-rose-200 bg-rose-50/90 px-4 py-3 text-sm text-rose-800 shadow-sm">
            {localizeUserMessage((widgetsQ.error as Error).message)}
          </p>
        ) : !widgets.length ? (
          <p className="rounded-xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-900 shadow-sm">
            {t('bi.analytics.sourceWidgetsEmpty')}
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4">
            {widgets.map((w, i) => (
              <WidgetTile key={w.id} widget={w} index={i} onOpen={setSelected} />
            ))}
          </div>
        )}
      </div>

      {selected ? <BiWidgetDetailSheet widget={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}
