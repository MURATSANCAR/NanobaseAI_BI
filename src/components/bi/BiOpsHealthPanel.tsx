import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, Database, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

export default function BiOpsHealthPanel() {
  const { config } = useApiConfig();
  const runnerOk = isRunnerConfigured(config);
  const qc = useQueryClient();

  const statusQ = useQuery({
    queryKey: ['bi-status', config],
    queryFn: () => api.bi.status(config),
    enabled: runnerOk,
    refetchInterval: 30_000,
  });

  const opsQ = useQuery({
    queryKey: ['bi-ops-health', config],
    queryFn: () => api.bi.opsHealth(config),
    enabled: runnerOk,
    refetchInterval: 30_000,
  });

  const llmQ = useQuery({
    queryKey: ['llm-status', config],
    queryFn: () => api.llm.status(config),
    enabled: runnerOk,
    refetchInterval: 30_000,
  });

  const refreshMut = useMutation({
    mutationFn: () => api.bi.refreshSchema(config),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-status'] });
      void qc.invalidateQueries({ queryKey: ['bi-ops-health'] });
      void qc.invalidateQueries({ queryKey: ['bi-schema'] });
    },
  });

  if (!runnerOk) return null;

  const status = statusQ.data;
  const ops = opsQ.data;
  const schemaReady = Boolean(status?.schema_ready ?? status?.schema_cached);
  const dbOk = Boolean(status?.connection?.ok ?? ops?.db_ready);
  const llmOk = Boolean(llmQ.data?.llm_configured);
  const sourceLabel = ops?.data_pulse?.source_label;
  const tableCount = status?.table_count ?? ops?.data_pulse?.table_count;

  const refreshStatus = () => {
    void statusQ.refetch();
    void opsQ.refetch();
    void llmQ.refetch();
  };

  return (
    <section className="card space-y-4 p-4" data-testid="bi-ops-health-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{t('bi.settings.opsTitle')}</h3>
          <p className="mt-0.5 text-xs text-slate-500">{t('bi.settings.opsHint')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-secondary inline-flex items-center gap-1.5 text-xs"
            disabled={statusQ.isFetching || opsQ.isFetching}
            onClick={refreshStatus}
          >
            {statusQ.isFetching || opsQ.isFetching ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            {t('bi.settings.refreshStatus')}
          </button>
          <button
            type="button"
            className="btn-primary inline-flex items-center gap-1.5 text-xs"
            disabled={refreshMut.isPending}
            onClick={() => refreshMut.mutate()}
          >
            {refreshMut.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Database className="h-3.5 w-3.5" />
            )}
            {t('bi.settings.refreshSchema')}
          </button>
        </div>
      </div>

      {(statusQ.isError || opsQ.isError || refreshMut.isError) && (
        <p className="text-xs text-rose-700">
          {localizeUserMessage(
            String(statusQ.error || opsQ.error || refreshMut.error || ''),
          )}
        </p>
      )}
      {refreshMut.isSuccess ? (
        <p className="text-xs text-emerald-700">{t('bi.settings.schemaReady')}</p>
      ) : null}

      <ul className="grid gap-2 sm:grid-cols-2">
        <li className="flex items-center gap-2 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-xs">
          <Database className={`h-3.5 w-3.5 ${dbOk ? 'text-emerald-600' : 'text-amber-600'}`} />
          <span className="font-medium text-slate-800">
            {dbOk ? t('bi.settings.sourceActive') : t('bi.settings.noSource')}
          </span>
          {sourceLabel ? <span className="truncate text-slate-500">· {sourceLabel}</span> : null}
        </li>
        <li className="flex items-center gap-2 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-xs">
          <Activity className={`h-3.5 w-3.5 ${schemaReady ? 'text-emerald-600' : 'text-amber-600'}`} />
          <span className="font-medium text-slate-800">
            {schemaReady ? t('bi.settings.schemaReady') : t('bi.settings.schemaNotReady')}
          </span>
          {tableCount != null ? <span className="text-slate-500">· {tableCount}</span> : null}
        </li>
        <li className="flex items-center gap-2 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-xs">
          <Sparkles className={`h-3.5 w-3.5 ${llmOk ? 'text-emerald-600' : 'text-slate-400'}`} />
          <span className="font-medium text-slate-800">
            {llmOk ? t('bi.settings.llmReady') : t('bi.settings.llmNotReady')}
          </span>
        </li>
        {ops ? (
          <li className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-xs text-slate-600">
            {ops.anomaly_count} anomalies · {ops.alert_count} alerts · {ops.action_count} actions
          </li>
        ) : null}
      </ul>
    </section>
  );
}
