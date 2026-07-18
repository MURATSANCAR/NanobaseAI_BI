import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Activity, ArrowRight } from 'lucide-react';
import { api, isRunnerConfigured, type ApiConfig } from '@/api/client';
import { isBuildModuleEnabled } from '@/lib/portalBuildProfile';
import { t } from '@/i18n';

type Props = {
  config: ApiConfig;
  className?: string;
};

/** Read-only BI ops signal on QA gate screens when BI module is built in. */
export default function QaBiOpsStrip({ config, className }: Props) {
  const biEnabled = isBuildModuleEnabled('bi') && isRunnerConfigured(config);
  const health = useQuery({
    queryKey: ['bi-ops-health', config],
    queryFn: () => api.bi.opsHealth(config),
    enabled: biEnabled,
    staleTime: 45_000,
    retry: false,
  });

  if (!biEnabled || health.isError || !health.data) return null;

  const { anomaly_count, alert_count, db_ready, delta_summary } = health.data;
  const moved = (delta_summary || []).filter(
    (d) =>
      (d.delta_day_pct != null && Math.abs(d.delta_day_pct) >= 5) ||
      (d.delta_week_pct != null && Math.abs(d.delta_week_pct) >= 5),
  ).length;

  return (
    <section
      data-testid="qa-bi-ops-strip"
      className={`rounded-xl border border-violet-200/80 bg-violet-50/50 px-3 py-2.5 text-sm text-slate-700 ${className || ''}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 font-medium text-violet-900">
          <Activity className="h-4 w-4" />
          {t('bi.qaOps.title')}
        </p>
        <Link to="/bi" className="inline-flex items-center gap-1 text-xs font-medium text-violet-800 hover:underline">
          {t('bi.qaOps.openReports')}
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
      <p className="mt-1 text-xs text-slate-600">
        {!db_ready
          ? t('bi.qaOps.dbOff')
          : t('bi.qaOps.summary', {
              anomalies: String(anomaly_count ?? 0),
              alerts: String(alert_count ?? 0),
              moved: String(moved),
            })}
      </p>
    </section>
  );
}
