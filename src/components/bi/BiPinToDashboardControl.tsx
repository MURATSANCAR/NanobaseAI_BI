import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LayoutDashboard, Loader2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import {
  BI_PIN_VIZ_OPTIONS,
  isPinVizType,
  type BiPinVizType,
} from '@/components/bi/biVisualTypes';
import { t } from '@/i18n';

export type BiPinSelection = {
  dashboardId: number;
  vizType: BiPinVizType;
};

type Props = {
  pinning?: boolean;
  pinned?: boolean;
  pinnedDashboardId?: number | null;
  /** Preferred board (active analytics canvas). */
  preferredDashboardId?: string | number | null;
  /** Suggested viz from chat preview / query shape. */
  preferredVizType?: string | null;
  onPin: (selection: BiPinSelection) => void | Promise<void>;
  compact?: boolean;
};

export default function BiPinToDashboardControl({
  pinning,
  pinned,
  pinnedDashboardId,
  preferredDashboardId,
  preferredVizType,
  onPin,
  compact,
}: Props) {
  const { config } = useApiConfig();
  const boardsQ = useQuery({
    queryKey: ['bi-analytics-dashboards', config],
    queryFn: () => api.bi.analytics.dashboards(config),
    enabled: isRunnerConfigured(config),
    staleTime: 60_000,
  });

  const boards = boardsQ.data?.dashboards ?? [];
  const preferred = Number(preferredDashboardId || 0);
  const initialId = useMemo(() => {
    if (Number.isFinite(preferred) && preferred > 0 && boards.some((b) => Number(b.id) === preferred)) {
      return preferred;
    }
    return Number(boards[0]?.id || 0);
  }, [boards, preferred]);

  const initialViz = useMemo<BiPinVizType>(() => {
    if (isPinVizType(preferredVizType || undefined)) return preferredVizType as BiPinVizType;
    const normalized = (preferredVizType || '').toLowerCase().trim();
    if (normalized === 'metric' || normalized === 'gauge' || normalized === 'multi_card') return 'kpi';
    if (normalized === 'matrix') return 'table';
    if (normalized === 'stacked_bar' || normalized === 'stacked_column') return 'bar';
    return 'table';
  }, [preferredVizType]);

  const [selectedId, setSelectedId] = useState<number>(0);
  const [selectedViz, setSelectedViz] = useState<BiPinVizType>(initialViz);

  useEffect(() => {
    if (selectedId <= 0 && initialId > 0) setSelectedId(initialId);
  }, [initialId, selectedId]);

  useEffect(() => {
    setSelectedViz(initialViz);
  }, [initialViz]);

  const selectedTitle =
    boards.find((b) => Number(b.id) === Number(pinnedDashboardId || selectedId))?.title ||
    t('bi.pinBoardFallback');

  if (pinned) {
    return (
      <div className="flex flex-wrap items-center justify-end gap-2">
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-[10px] font-semibold text-emerald-800">
          <LayoutDashboard className="h-3 w-3" />
          {t('bi.pinSuccessNamed', { name: selectedTitle })}
        </span>
        {pinnedDashboardId ? (
          <Link
            to={`/bi?dashboard=${pinnedDashboardId}`}
            className="text-[11px] font-semibold text-violet-700 hover:underline"
          >
            {t('bi.pinOpenBoard')}
          </Link>
        ) : null}
      </div>
    );
  }

  if (boardsQ.isLoading) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {t('common.loading')}
      </span>
    );
  }

  if (!boards.length) {
    return (
      <p className="text-[11px] text-amber-800">{t('bi.pinNoBoards')}</p>
    );
  }

  return (
    <div
      className={
        compact
          ? 'flex flex-wrap items-center justify-end gap-1.5'
          : 'flex w-full max-w-md flex-col gap-2 sm:ml-auto sm:items-end'
      }
    >
      <label className="flex min-w-0 flex-1 flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-2">
        <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          {t('bi.pinSelectBoard')}
        </span>
        <select
          className="input-field min-w-[10rem] flex-1 py-1.5 text-xs"
          value={selectedId || ''}
          disabled={pinning}
          onChange={(e) => setSelectedId(Number(e.target.value))}
        >
          {boards.map((b) => (
            <option key={b.id} value={b.id}>
              {b.title || `#${b.id}`}
            </option>
          ))}
        </select>
      </label>
      <label className="flex min-w-0 flex-1 flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-2">
        <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          {t('bi.pinSelectWidget')}
        </span>
        <select
          className="input-field min-w-[10rem] flex-1 py-1.5 text-xs"
          value={selectedViz}
          disabled={pinning}
          onChange={(e) => setSelectedViz(e.target.value as BiPinVizType)}
        >
          {BI_PIN_VIZ_OPTIONS.map((viz) => (
            <option key={viz} value={viz}>
              {t(`bi.visual.${viz}`)}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="inline-flex items-center justify-center gap-1.5 rounded-full bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-violet-700 disabled:opacity-60"
        disabled={pinning || !selectedId}
        onClick={() => {
          if (selectedId > 0) void onPin({ dashboardId: selectedId, vizType: selectedViz });
        }}
      >
        {pinning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LayoutDashboard className="h-3.5 w-3.5" />}
        {t('bi.chatPinWidgets')}
      </button>
    </div>
  );
}
