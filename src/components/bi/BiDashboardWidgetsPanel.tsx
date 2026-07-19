import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, Loader2, RefreshCw, Trash2, X } from 'lucide-react';
import { api, type ApiConfig } from '@/api/client';
import { BiCardWidget, BiVisualChart } from '@/components/bi/BiCharts';
import BiWidgetDetailSheet from '@/components/bi/BiWidgetDetailSheet';
import type { BiWidget } from '@/api/types';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

type Props = {
  config: ApiConfig;
  dashboardId: number;
  onClose: () => void;
  onChanged?: () => void;
};

function SourceWidgetCard({
  widget,
  index,
  onOpen,
}: {
  widget: BiWidget;
  index: number;
  onOpen: (w: BiWidget) => void;
}) {
  const isKpi = widget.type === 'kpi' || widget.type === 'metric' || widget.type === 'card';
  const accent = index % 8;
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(widget)}
        className="bi-pbi-tile bi-pbi-tile--3d bi-pbi-tile--vivid w-full overflow-hidden p-0 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
        data-accent={accent}
        aria-label={t('bi.analytics.openWidgetDetail', { title: widget.title || widget.id })}
      >
        <div className="bi-pbi-tile-glow" aria-hidden />
        <div className="bi-pbi-tile-shine" aria-hidden />
        <div className="bi-pbi-tile-accent" data-visual={widget.type || 'card'} aria-hidden />
        <div className="relative z-[1] border-b border-white/40 px-2.5 py-1.5">
          <p className="truncate text-xs font-semibold text-slate-800">{widget.title}</p>
        </div>
        <div className="pointer-events-none relative z-[1] p-2">
          {isKpi ? (
            <BiCardWidget widget={widget} kpi variant="preview" />
          ) : (
            <div className="h-40">
              <BiVisualChart widget={widget} variant="preview" height={160} />
            </div>
          )}
        </div>
      </button>
    </li>
  );
}

export default function BiDashboardWidgetsPanel({
  config,
  dashboardId,
  onClose,
  onChanged,
}: Props) {
  const qc = useQueryClient();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedSourceWidget, setSelectedSourceWidget] = useState<BiWidget | null>(null);

  const sourcesQ = useQuery({
    queryKey: ['bi-sources', config],
    queryFn: () => api.bi.sources.list(config),
    staleTime: 30_000,
  });
  const activeSourceId = sourcesQ.data?.active_id || undefined;
  const activeLabel =
    sourcesQ.data?.sources?.find((s) => s.id === activeSourceId)?.label || activeSourceId || '—';

  const sourceWidgetsQ = useQuery({
    queryKey: ['bi-analytics-source-widgets', config, activeSourceId],
    queryFn: () => api.bi.analytics.sourceWidgets(config, activeSourceId),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const chartsQ = useQuery({
    queryKey: ['bi-analytics-dashboard-charts', dashboardId],
    queryFn: () => api.bi.analytics.dashboardCharts(config, dashboardId),
    enabled: dashboardId > 0,
  });

  const charts = chartsQ.data?.charts ?? [];
  const sourceWidgets = sourceWidgetsQ.data?.widgets ?? [];

  const refresh = useCallback(async () => {
    await qc.invalidateQueries({ queryKey: ['bi-analytics-dashboard-charts', dashboardId] });
    await qc.invalidateQueries({ queryKey: ['bi-analytics-charts'] });
    await qc.invalidateQueries({ queryKey: ['bi-analytics-source-widgets'] });
    onChanged?.();
  }, [dashboardId, onChanged, qc]);

  const removeMut = useMutation({
    mutationFn: (chartId: number) => api.bi.analytics.removeChart(config, dashboardId, chartId),
    onSuccess: () => void refresh(),
  });

  const reorderMut = useMutation({
    mutationFn: (chartIds: number[]) => api.bi.analytics.reorderLayout(config, dashboardId, chartIds),
    onSuccess: () => void refresh(),
  });

  const move = async (index: number, delta: number) => {
    const next = [...charts];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    const tmp = next[index]!;
    next[index] = next[target]!;
    next[target] = tmp;
    setError(null);
    setBusyId(tmp.id);
    try {
      await reorderMut.mutateAsync(next.map((c) => c.id));
    } catch (err) {
      setError(localizeUserMessage((err as Error).message));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (chartId: number) => {
    if (!window.confirm(t('bi.analytics.removeWidgetConfirm'))) return;
    setError(null);
    setBusyId(chartId);
    try {
      await removeMut.mutateAsync(chartId);
    } catch (err) {
      setError(localizeUserMessage((err as Error).message));
    } finally {
      setBusyId(null);
    }
  };

  const mutating = removeMut.isPending || reorderMut.isPending;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-[#E1DFDD] px-3 py-2.5">
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-800">
          {t('bi.analytics.manageWidgets')}
        </p>
        <button
          type="button"
          className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
          onClick={() => void refresh()}
          aria-label={t('common.refresh')}
          title={t('common.refresh')}
        >
          <RefreshCw className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
          onClick={onClose}
          aria-label={t('common.close')}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {error && (
        <div className="shrink-0 border-b border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
          {error}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        <section className="mb-3">
          <div className="mb-1.5 flex items-center justify-between gap-2 px-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {t('bi.analytics.sourceWidgetsTitle')}
            </p>
            <span className="truncate text-[10px] font-medium text-violet-700">{activeLabel}</span>
          </div>
          {sourceWidgetsQ.isLoading ? (
            <div className="flex items-center justify-center gap-2 py-6 text-xs text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('bi.analytics.loading')}
            </div>
          ) : sourceWidgetsQ.isError ? (
            <p className="px-1 py-3 text-xs text-rose-700">
              {localizeUserMessage((sourceWidgetsQ.error as Error).message)}
            </p>
          ) : !sourceWidgets.length ? (
            <p className="px-1 py-3 text-xs text-slate-500">{t('bi.analytics.sourceWidgetsEmpty')}</p>
          ) : (
            <ul className="space-y-2.5">
              {sourceWidgets.map((w, i) => (
                <SourceWidgetCard
                  key={w.id}
                  widget={w}
                  index={i}
                  onOpen={setSelectedSourceWidget}
                />
              ))}
            </ul>
          )}
        </section>

        {dashboardId > 0 ? (
          <section>
            <p className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {t('bi.analytics.supersetWidgetsTitle')}
            </p>
            {chartsQ.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-6 text-xs text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('bi.analytics.loading')}
              </div>
            ) : !charts.length ? (
              <div className="px-1 py-4 text-center text-xs text-slate-500">
                <p>{t('bi.analytics.emptyWidgets')}</p>
                <p className="mt-2 text-slate-400">{t('bi.analytics.emptyWidgetsHint')}</p>
              </div>
            ) : (
              <ul className="space-y-1.5">
                {charts.map((chart, index) => {
                  const busy = busyId === chart.id && mutating;
                  return (
                    <li
                      key={chart.id}
                      className="flex items-start gap-1 rounded-xl border border-[#E1DFDD]/90 bg-white px-2 py-2 shadow-sm"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="line-clamp-2 text-xs font-medium text-slate-800">
                          {chart.title || `#${chart.id}`}
                        </p>
                        <p className="mt-0.5 text-[10px] text-slate-400">#{chart.id}</p>
                      </div>
                      <div className="flex shrink-0 flex-col gap-0.5">
                        <button
                          type="button"
                          className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
                          disabled={index === 0 || mutating}
                          onClick={() => void move(index, -1)}
                          aria-label={t('bi.analytics.moveWidgetUp')}
                          title={t('bi.analytics.moveWidgetUp')}
                        >
                          <ArrowUp className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
                          disabled={index >= charts.length - 1 || mutating}
                          onClick={() => void move(index, 1)}
                          aria-label={t('bi.analytics.moveWidgetDown')}
                          title={t('bi.analytics.moveWidgetDown')}
                        >
                          <ArrowDown className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      <button
                        type="button"
                        className="rounded p-1 text-rose-600 hover:bg-rose-50 disabled:opacity-40"
                        disabled={mutating}
                        onClick={() => void remove(chart.id)}
                        aria-label={t('bi.removeWidget')}
                        title={t('bi.removeWidget')}
                      >
                        {busy ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        ) : null}
      </div>

      {selectedSourceWidget ? (
        <BiWidgetDetailSheet
          widget={selectedSourceWidget}
          onClose={() => setSelectedSourceWidget(null)}
        />
      ) : null}
    </div>
  );
}
