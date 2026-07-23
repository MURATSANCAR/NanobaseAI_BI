import clsx from 'clsx';
import { useQuery } from '@tanstack/react-query';
import { BarChart3 } from 'lucide-react';
import { BiVisualChart } from '@/components/bi/BiCharts';
import BiPinToDashboardControl from '@/components/bi/BiPinToDashboardControl';
import { isCompactVisual, widgetVisualType } from '@/components/bi/biVisualTypes';
import { api } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import type { BiWidget } from '@/api/types';
import { getLocale, t } from '@/i18n';
import { biWidgetTitle } from '@/lib/biWidgetTitle';

type Props = {
  widgets: BiWidget[];
  dashboardId?: string;
  pinned?: boolean;
  pinning?: boolean;
  pinnedDashboardId?: number | null;
  onPin?: (selection: { dashboardId: number; vizType: string }) => void | Promise<void>;
};

/** Rich chat answer visuals (charts/tables) — not a dashboard staging preview. */
export default function BiChatWidgetPreview({
  widgets,
  dashboardId,
  pinned,
  pinning,
  pinnedDashboardId,
  onPin,
}: Props) {
  const { config } = useApiConfig();
  const locale = getLocale();
  const { data: templatesResp } = useQuery({
    queryKey: ['bi-templates', config],
    queryFn: () => api.bi.templates(config),
    staleTime: 5 * 60_000,
  });
  const templates = templatesResp?.templates ?? [];
  const preferredViz = widgets[0] ? widgetVisualType(widgets[0]) : 'table';

  if (!widgets.length) return null;

  return (
    <div className="bi-chat-answer-visual mt-3 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-sky-100 to-violet-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-700 ring-1 ring-sky-200/70">
          <BarChart3 className="h-3 w-3 text-sky-600" aria-hidden />
          {t('bi.result.answerBadge')}
        </span>
        {onPin ? (
          <BiPinToDashboardControl
            compact
            pinning={pinning}
            pinned={pinned}
            pinnedDashboardId={pinnedDashboardId}
            preferredDashboardId={dashboardId}
            preferredVizType={preferredViz}
            onPin={onPin}
          />
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-3">
        {widgets.slice(0, 3).map((widget, index) => {
          const visual = widgetVisualType(widget);
          const compact = isCompactVisual(visual);
          const displayTitle = biWidgetTitle(widget, locale, templates);
          const accents = [
            'from-sky-50 via-white to-cyan-50 border-sky-200/70',
            'from-violet-50 via-white to-fuchsia-50 border-violet-200/70',
            'from-emerald-50 via-white to-teal-50 border-emerald-200/70',
            'from-amber-50 via-white to-orange-50 border-amber-200/70',
          ] as const;
          const shell = accents[index % accents.length]!;
          return (
            <div
              key={widget.id}
              className={clsx(
                'overflow-hidden rounded-2xl border bg-gradient-to-br p-3 shadow-sm sm:p-4',
                shell,
              )}
            >
              <p className="mb-2 truncate text-xs font-bold uppercase tracking-wide text-slate-600">
                {displayTitle}
              </p>
              <div className={clsx('min-h-0', compact ? 'min-h-[5.5rem]' : 'min-h-[11rem]')}>
                <BiVisualChart
                  widget={widget}
                  variant="preview"
                  containerHeight={compact ? 96 : 180}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
