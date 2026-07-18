import { useQuery } from '@tanstack/react-query';
import { GitBranch } from 'lucide-react';
import { api, type ApiConfig } from '@/api/client';
import { t } from '@/i18n';
import BiFreshnessBadge from '@/components/bi/BiFreshnessBadge';

type Props = {
  config: ApiConfig;
  metricId: string;
  onClose?: () => void;
};

export default function BiLineageDrawer({ config, metricId, onClose }: Props) {
  const q = useQuery({
    queryKey: ['bi-lineage', metricId],
    queryFn: () => api.bi.lineage.metric(config, metricId),
    enabled: Boolean(metricId),
  });

  const data = q.data || {};
  const metric = (data.metric || {}) as Record<string, unknown>;
  const freshness = (data.freshness || {}) as { snapshot_at?: string; stale?: boolean };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-lg">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <GitBranch className="h-4 w-4" />
          {t('bi.lineage.title')}
        </div>
        {onClose ? (
          <button type="button" className="text-xs text-slate-500" onClick={onClose}>
            ✕
          </button>
        ) : null}
      </div>
      <p className="text-sm text-slate-800">
        {String(metric.label || metricId)}
        {metric.version != null ? ` · v${String(metric.version)}` : ''}
        {metric.status === 'certified' ? ` · ${t('bi.semantic.certified')}` : ''}
      </p>
      {freshness.snapshot_at ? (
        <div className="mt-1">
          <BiFreshnessBadge refreshedAt={freshness.snapshot_at} />
        </div>
      ) : null}
      <pre className="mt-3 max-h-40 overflow-auto rounded bg-slate-50 p-2 text-[11px] text-slate-700">
        {String(metric.expression || data.expression || '')}
      </pre>
      {data.certified_by ? (
        <p className="mt-2 text-xs text-slate-500">
          {t('bi.lineage.certifiedBy')}: {String(data.certified_by)}
        </p>
      ) : null}
    </div>
  );
}
