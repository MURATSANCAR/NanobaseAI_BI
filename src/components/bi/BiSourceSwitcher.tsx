import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { api, isRunnerConfigured, type ApiConfig } from '@/api/client';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

type Props = {
  config: ApiConfig;
  className?: string;
  compact?: boolean;
};

/** Switch active BI database source (erp / sigorta / …). */
export default function BiSourceSwitcher({ config, className, compact }: Props) {
  const enabled = isRunnerConfigured(config);
  const qc = useQueryClient();

  const sourcesQ = useQuery({
    queryKey: ['bi-sources', config],
    queryFn: () => api.bi.sources.list(config),
    enabled,
    staleTime: 30_000,
  });

  const activateMut = useMutation({
    mutationFn: (id: string) => api.bi.sources.activate(config, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-sources'] });
      void qc.invalidateQueries({ queryKey: ['bi-connection'] });
      void qc.invalidateQueries({ queryKey: ['bi-status'] });
      void qc.invalidateQueries({ queryKey: ['bi-schema'] });
      void qc.invalidateQueries({ queryKey: ['bi-briefing'] });
      void qc.invalidateQueries({ queryKey: ['bi-ops-health'] });
      void qc.invalidateQueries({ queryKey: ['bi-templates'] });
      void qc.invalidateQueries({ queryKey: ['bi-kpi-suggestions'] });
    },
  });

  const sources = sourcesQ.data?.sources ?? [];
  if (!enabled || sources.length === 0) return null;

  const activeId = sourcesQ.data?.active_id ?? '';

  return (
    <div className={clsx('flex flex-wrap items-center gap-2', className)}>
      {!compact && (
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {t('bi.sources.activeLabel')}
        </span>
      )}
      <div className="inline-flex max-w-full flex-wrap gap-1 overflow-x-auto rounded-lg border border-slate-200 bg-white p-1">
        {sources.map((s) => {
          const id = s.id || '';
          const isActive = id === activeId;
          return (
            <button
              key={id}
              type="button"
              disabled={activateMut.isPending || isActive}
              onClick={() => activateMut.mutate(id)}
              className={clsx(
                'min-h-10 rounded-md px-3 py-2 text-xs font-medium transition',
                isActive
                  ? 'bg-violet-600 text-white shadow-sm'
                  : 'text-slate-700 hover:bg-slate-50',
              )}
              title={s.supabase_url || s.host || id}
            >
              {s.label || id}
            </button>
          );
        })}
      </div>
      {activateMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />}
      {activateMut.isError && (
        <span className="text-xs text-status-fail">
          {localizeUserMessage((activateMut.error as Error).message)}
        </span>
      )}
    </div>
  );
}
