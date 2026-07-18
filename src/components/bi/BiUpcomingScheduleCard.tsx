import { CalendarClock, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, isRunnerConfigured } from '@/api/client';
import type { ApiConfig } from '@/api/http';
import { t } from '@/i18n';

type Props = {
  config: ApiConfig;
};

export default function BiUpcomingScheduleCard({ config }: Props) {
  const enabled = isRunnerConfigured(config);
  const schedules = useQuery({
    queryKey: ['bi-schedules', config],
    queryFn: () => api.bi.schedules(config),
    enabled,
    refetchInterval: 60_000,
  });

  const pending = (schedules.data?.schedules ?? [])
    .filter((s) => s.status === 'pending')
    .sort((a, b) => (a.run_at || '').localeCompare(b.run_at || ''));
  const next = pending[0];

  const recurrenceLabel = (rec?: string) => {
    if (rec === 'daily') return t('bi.scheduleRecurrenceDaily');
    if (rec === 'weekly') return t('bi.scheduleRecurrenceWeekly');
    return t('bi.scheduleRecurrenceOnce');
  };

  return (
    <div className="rounded-xl border border-violet-200/70 bg-white/80 px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-100 text-violet-700">
            <CalendarClock className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900">{t('bi.wow.nextScheduleTitle')}</p>
            {next ? (
              <>
                <p className="mt-0.5 truncate text-sm text-slate-700">{next.subject}</p>
                <p className="mt-1 font-mono text-xs text-slate-500">
                  {next.run_at?.slice(0, 16)?.replace('T', ' ')}
                  {' · '}
                  {recurrenceLabel(next.recurrence)}
                  {next.local_time ? ` · ${next.local_time}` : ''}
                </p>
                {next.recipient && (
                  <p className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                    <Mail className="h-3 w-3" />
                    {next.recipient}
                  </p>
                )}
              </>
            ) : (
              <p className="mt-0.5 text-sm text-slate-500">{t('bi.wow.nextScheduleEmpty')}</p>
            )}
          </div>
        </div>
        <Link to="/bi/schedules" className="shrink-0 text-sm font-medium text-violet-700 hover:underline">
          {t('bi.wow.manageSchedules')}
        </Link>
      </div>
    </div>
  );
}
