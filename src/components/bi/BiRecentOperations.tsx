import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { Activity, ArrowRight, ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import type { BiAuditEntry } from '@/api/types';
import { t } from '@/i18n';
import { sortByIsoDateDesc } from '@/utils/sort';

type Props = {
  limit?: number;
  showViewAll?: boolean;
  /** When false (default), section starts collapsed. */
  defaultOpen?: boolean;
};

export default function BiRecentOperations({
  limit = 10,
  showViewAll = true,
  defaultOpen = false,
}: Props) {
  const { config } = useApiConfig();
  const [open, setOpen] = useState(defaultOpen);
  const audit = useQuery({
    queryKey: ['bi-audit-recent', config, limit],
    queryFn: () => api.bi.audit(config, limit),
    enabled: isRunnerConfigured(config) && open,
    staleTime: 30_000,
  });

  const entries = sortByIsoDateDesc((audit.data?.entries ?? []) as BiAuditEntry[], (r) => r.at).slice(0, limit);

  return (
    <section className="bi-schema-panel">
      <div className="bi-schema-panel-header flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-start gap-3 rounded-lg text-left transition hover:bg-slate-50/80"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          <div className="bi-schema-table-icon !h-9 !w-9">
            <Activity className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              {t('bi.recentOperations')}
              <ChevronDown
                className={clsx('h-4 w-4 shrink-0 text-slate-400 transition', open && 'rotate-180')}
                aria-hidden
              />
            </h2>
            <p className="text-xs text-slate-500">{t('bi.recentOperationsSubtitle', { count: limit })}</p>
          </div>
        </button>
        {showViewAll ? (
          <Link
            to="/bi/audit"
            className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium text-violet-700 transition-colors hover:bg-violet-50"
            onClick={(e) => e.stopPropagation()}
          >
            {t('bi.viewFullAudit')}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        ) : null}
      </div>

      {open ? (
        !entries.length && !audit.isLoading ? (
          <p className="p-5 text-sm text-slate-500">{t('empty.bi.audit.description')}</p>
        ) : (
          <div className="bi-schema-ops-list">
            {entries.map((entry) => {
              const actionKey = `bi.auditAction.${entry.action}`;
              const actionLabel = t(actionKey) !== actionKey ? t(actionKey) : entry.action;
              return (
                <div key={`${entry.at}-${entry.action}-${entry.sql ?? ''}`} className="bi-schema-op-row">
                  <span className={clsx('bi-schema-op-accent', !entry.ok && 'is-fail')} aria-hidden />
                  <div className="min-w-[8.5rem] shrink-0 font-mono text-xs text-slate-500">
                    {entry.at?.slice(0, 19) ?? '—'}
                  </div>
                  <span className="bi-schema-op-action">{actionLabel}</span>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                    {entry.duration_ms != null ? (
                      <span>{t('bi.auditDurationMs', { ms: entry.duration_ms })}</span>
                    ) : null}
                    {entry.row_count != null ? (
                      <span>
                        {t('bi.auditRows')}: {entry.row_count}
                      </span>
                    ) : null}
                    <span className={entry.ok ? 'text-emerald-600' : 'text-red-600'}>{entry.ok ? '✓' : '✗'}</span>
                  </div>
                  {entry.sql ? (
                    <code className="min-w-0 flex-1 basis-full truncate rounded-lg bg-slate-50/80 px-2 py-1 font-mono text-[11px] text-slate-600 sm:basis-auto">
                      {entry.sql.slice(0, 100)}
                    </code>
                  ) : null}
                </div>
              );
            })}
          </div>
        )
      ) : null}
    </section>
  );
}
