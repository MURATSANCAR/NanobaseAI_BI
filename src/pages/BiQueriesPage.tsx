import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, MessageSquare, Play, Trash2 } from 'lucide-react';
import { useState } from 'react';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import ResponsiveTable from '@/components/ResponsiveTable';
import DynamicResultTable from '@/components/DynamicResultTable';
import BiExportMenu from '@/components/bi/BiExportMenu';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useBiChatDock } from '@/context/BiChatDockContext';
import type { BiSavedQuery, BiWidgetData } from '@/api/types';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';
import { sortByIsoDateDesc } from '@/utils/sort';

function sqlPreview(sql: string | undefined): string {
  const text = (sql || '').trim();
  if (!text) return '—';
  return text.length > 80 ? `${text.slice(0, 80)}…` : text;
}

export default function BiQueriesPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const { openChat } = useBiChatDock();
  const [result, setResult] = useState<{ query: BiSavedQuery; data: BiWidgetData } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ['bi-queries', config],
    queryFn: () => api.bi.queries.list(config),
    enabled: isRunnerConfigured(config),
  });

  const runMut = useMutation({
    mutationFn: async (query: BiSavedQuery) => {
      const data = (await api.bi.queries.run(config, query.id)) as BiWidgetData;
      return { query, data };
    },
    onSuccess: (res) => setResult(res),
    onError: (err) => setFlash(localizeUserMessage((err as Error).message)),
  });

  const delMut = useMutation({
    mutationFn: (id: string) => api.bi.queries.delete(config, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bi-queries'] });
      setResult(null);
    },
  });

  const pinToChat = (query: BiSavedQuery) => {
    const prompt = t('bi.pinQueryChatPrompt', {
      title: query.title,
      sql: (query.sql || '').slice(0, 500),
    });
    openChat({ prompt });
  };

  const items = sortByIsoDateDesc(q.data?.queries ?? [], (r) => r.updated_at ?? r.created_at ?? r.last_run_at);
  const cols = result?.data?.columns ?? [];
  const rows = result?.data?.rows ?? [];

  return (
    <PageShell pageId="biQueries" titleKey="bi.queriesTitle" subtitleKey="bi.queriesSubtitle" maxWidth="max-w-7xl">
      {flash && <p className="mb-3 text-sm text-status-fail">{flash}</p>}

      {q.isLoading ? (
        <div className="card flex items-center justify-center gap-2 p-10 text-sm text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin text-accent" />
          {t('common.loading')}
        </div>
      ) : q.isError ? (
        <div className="card p-8 text-center">
          <p className="text-sm text-status-fail">{localizeUserMessage((q.error as Error).message)}</p>
          <button type="button" className="btn-secondary mt-4 text-sm" onClick={() => q.refetch()}>
            {t('common.retry')}
          </button>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          emoji="📌"
          titleKey="empty.bi.queries.title"
          descriptionKey="empty.bi.queries.description"
          ctaLabelKey="empty.bi.queries.cta"
          onCtaClick={() => openChat()}
        />
      ) : (
        <div className="card overflow-hidden">
          <ResponsiveTable<BiSavedQuery>
            columns={[
              { id: 'title', header: t('bi.reportTitle'), mobilePrimary: true, cell: (r) => r.title },
              { id: 'sql', header: t('bi.sqlColumn'), mobileLabel: t('bi.sqlColumn'), cell: (r) => <code className="text-xs break-all">{sqlPreview(r.sql)}</code> },
              {
                id: 'actions',
                header: t('common.actions'),
                mobileLabel: t('common.actions'),
                cell: (r) => (
                  <div className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-accent"
                      title={t('bi.runQueryResult')}
                      disabled={runMut.isPending}
                      onClick={() => runMut.mutate(r)}
                    >
                      <Play className="h-4 w-4" />
                    </button>
                    <BiExportMenu sql={r.sql} />
                    <button
                      type="button"
                      className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-accent"
                      title={t('bi.pinQueryToDashboard')}
                      onClick={() => pinToChat(r)}
                    >
                      <MessageSquare className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-status-fail"
                      title={t('common.delete')}
                      onClick={() => {
                        if (window.confirm(t('bi.deleteQueryConfirm'))) delMut.mutate(r.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ),
              },
            ]}
            rows={items}
            rowKey={(r) => r.id}
          />
        </div>
      )}

      {result && (
        <div className="card mt-4 overflow-hidden">
          <div className="border-b border-surface-border px-4 py-3 font-semibold">
            {t('bi.runQueryResult')}: {result.query.title}
          </div>
          {rows.length === 0 ? (
            <p className="p-4 text-sm text-slate-500">{t('bi.queryRunEmpty')}</p>
          ) : (
            <DynamicResultTable className="p-1" columns={cols} rows={rows} maxRows={50} />
          )}
        </div>
      )}
    </PageShell>
  );
}
