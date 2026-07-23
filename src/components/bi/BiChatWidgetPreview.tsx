import clsx from 'clsx';
import { useQuery } from '@tanstack/react-query';
import { BiVisualChart } from '@/components/bi/BiCharts';
import BiPbiTile from '@/components/bi/BiPbiTile';
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

/** Preview tiles; pin CTA adds the result to a chosen NanobaseAI dashboard. */
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
    <div className="bi-chat-widget-preview bi-fluent-canvas mt-3 rounded-xl border border-[#E1DFDD]/80 p-3 sm:p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <span className="bi-pbi-type-chip">
          {t('bi.chatWidgetsPreview', { count: String(widgets.length) })}
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
      <div className="bi-analytics-canvas-stage grid grid-cols-1 gap-4 min-[480px]:grid-cols-2">
        {widgets.slice(0, 3).map((widget, index) => {
          const visual = widgetVisualType(widget);
          const compact = isCompactVisual(visual);
          const wide = visual === 'table' || visual === 'matrix';
          const displayTitle = biWidgetTitle(widget, locale, templates);
          return (
            <BiPbiTile
              key={widget.id}
              visualType={visual}
              accentIndex={index}
              title={displayTitle}
              compact
              kpi={compact}
              className={clsx('bi-chat-preview-tile', wide && 'min-[480px]:col-span-2')}
              bodyClassName={compact ? 'p-2' : 'p-2 pt-1'}
            >
              <BiVisualChart
                widget={widget}
                variant="preview"
                containerHeight={compact ? 72 : 140}
              />
            </BiPbiTile>
          );
        })}
      </div>
    </div>
  );
}
