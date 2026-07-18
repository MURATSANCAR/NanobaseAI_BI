import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, MessageSquare } from 'lucide-react';
import { api, isRunnerConfigured } from '@/api/client';
import type { ApiConfig } from '@/api/http';
import { t } from '@/i18n';

type Props = {
  config: ApiConfig;
  onAskInChat?: (prompt: string) => void;
};

export default function BiAlertActionStrip({ config, onAskInChat }: Props) {
  const enabled = isRunnerConfigured(config);
  const alerts = useQuery({
    queryKey: ['bi-alerts', config],
    queryFn: () => api.bi.alerts.list(config),
    enabled,
    refetchInterval: 60_000,
  });

  const triggered = (alerts.data?.alerts ?? []).filter(
    (a) => a.status === 'active' && Boolean(a.last_triggered_at),
  );

  if (!triggered.length) return null;

  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50/90 px-4 py-3 shadow-sm">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-semibold text-rose-900">
          <AlertTriangle className="h-4 w-4" />
          {t('bi.wow.alertStripTitle', { count: String(triggered.length) })}
        </p>
        <div className="flex flex-wrap gap-3 text-sm font-medium text-rose-800">
          <Link to="/bi/alerts" className="hover:underline">
            {t('bi.wow.alertStripManage')}
          </Link>
          <Link to="/bi/schedules" className="hover:underline">
            {t('bi.alertIncludeInMorningMail')}
          </Link>
        </div>
      </div>
      <ul className="space-y-2">
        {triggered.slice(0, 4).map((a) => (
          <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 text-sm text-rose-950">
            <span>
              <span className="font-medium">{a.title}</span>
              {a.last_value != null && (
                <span className="ml-2 text-xs opacity-80">
                  {t('bi.wow.alertStripValue', {
                    value: String(a.last_value),
                    threshold: String(a.threshold),
                  })}
                </span>
              )}
            </span>
            {onAskInChat && (
              <button
                type="button"
                className="inline-flex items-center gap-1 text-xs font-medium text-rose-800 hover:underline"
                onClick={() =>
                  onAskInChat(
                    t('bi.wow.alertAskWhy', { title: a.title, value: String(a.last_value ?? '') }),
                  )
                }
              >
                <MessageSquare className="h-3.5 w-3.5" />
                {t('bi.wow.alertStripWhy')}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
