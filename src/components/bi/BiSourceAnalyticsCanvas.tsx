import { useQuery } from '@tanstack/react-query';
import { Loader2, RefreshCw } from 'lucide-react';
import { api, type ApiConfig } from '@/api/client';
import { BiCardWidget, BiVisualChart } from '@/components/bi/BiCharts';
import type { BiWidget } from '@/api/types';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

type Props = {
  config: ApiConfig;
  datasourceId?: string;
  sourceLabel?: string;
  className?: string;
};

function WidgetTile({ widget, index }: { widget: BiWidget; index: number }) {
  const isKpi = widget.type === 'kpi' || widget.type === 'metric' || widget.type === 'card';
  return (
    <article
      className={
        isKpi
          ? 'bi-pbi-tile bi-pbi-tile--3d flex min-h-[8.5rem] flex-col p-4'
          : 'bi-pbi-tile bi-pbi-tile--3d flex min-h-[16rem] flex-col p-3 sm:col-span-2 lg:col-span-2'
      }
      data-accent={index % 6}
    >
      <div className="bi-pbi-tile-glow" aria-hidden />
      <div className="relative z-[1] flex min-h-0 flex-1 flex-col">
        <h3 className="mb-2 truncate text-xs font-semibold uppercase tracking-wide text-slate-600">
          {widget.title}
        </h3>
        <div className="min-h-0 flex-1">
          {isKpi ? (
            <BiCardWidget widget={widget} kpi variant="tile" />
          ) : (
            <BiVisualChart widget={widget} variant="tile" height={220} />
          )}
        </div>
      </div>
    </article>
  );
}

/** Main analytics surface: live, non-empty widgets for the active BI datasource. */
export default function BiSourceAnalyticsCanvas({
  config,
  datasourceId,
  sourceLabel,
  className,
}: Props) {
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
    <div className={`flex min-h-0 flex-1 flex-col overflow-hidden bg-[#F5F5F5] ${className || ''}`}>
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[#E1DFDD] bg-white/90 px-3 py-2 sm:px-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">
            {sourceLabel || datasourceId || t('bi.analytics.title')}
          </p>
          <p className="truncate text-[11px] text-slate-500">{t('bi.analytics.sourceCanvasHint')}</p>
        </div>
        <button
          type="button"
          className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
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
          <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
            {localizeUserMessage((widgetsQ.error as Error).message)}
          </p>
        ) : !widgets.length ? (
          <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            {t('bi.analytics.sourceWidgetsEmpty')}
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {widgets.map((w, i) => (
              <WidgetTile key={w.id} widget={w} index={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
