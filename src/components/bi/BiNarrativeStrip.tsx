import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, ChevronDown, Loader2, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { api, isRunnerConfigured, type ApiConfig } from '@/api/client';
import { getLocale, t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

type Props = {
  config: ApiConfig;
  dashboardId?: string;
  /** When false (default), only the title row shows until the user expands. */
  defaultOpen?: boolean;
  onDriverAsk?: (prompt: string, anomalyKey?: string) => void;
};

export default function BiNarrativeStrip({
  config,
  dashboardId = 'default',
  defaultOpen = false,
  onDriverAsk,
}: Props) {
  const enabled = isRunnerConfigured(config);
  const locale = getLocale();
  const [open, setOpen] = useState(defaultOpen);

  const q = useQuery({
    queryKey: ['bi-narrative', dashboardId, locale],
    queryFn: () => api.bi.narrative(config, dashboardId, locale),
    enabled: enabled && open,
    staleTime: 60_000,
    retry: 1,
  });

  if (!enabled) return null;

  return (
    <section className="rounded-xl border border-violet-200/70 bg-gradient-to-r from-violet-50/90 via-white to-sky-50/70 shadow-sm">
      <div className="flex items-center gap-1 px-2 py-1.5 sm:px-3">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-white/70"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          <BookOpen className="h-3.5 w-3.5 shrink-0 text-violet-600" aria-hidden />
          <span className="min-w-0 flex-1 truncate text-xs font-semibold uppercase tracking-wide text-violet-700/90">
            {t('bi.narrative.title')}
          </span>
          <ChevronDown
            className={clsx('h-4 w-4 shrink-0 text-violet-500 transition', open && 'rotate-180')}
            aria-hidden
          />
          <span className="sr-only">{open ? t('bi.narrative.collapse') : t('bi.narrative.expand')}</span>
        </button>
        {open ? (
          <button
            type="button"
            className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] font-medium text-slate-500 hover:bg-white/80 hover:text-slate-800"
            onClick={() => void q.refetch()}
            title={t('bi.narrative.refresh')}
            disabled={!q.isFetched && q.isLoading}
          >
            <RefreshCw className={clsx('h-3.5 w-3.5', q.isFetching && 'animate-spin')} />
            <span className="hidden sm:inline">{t('bi.wow.briefingRefreshCta')}</span>
          </button>
        ) : null}
      </div>

      {open ? (
        <div className="border-t border-violet-100/80 px-4 py-3">
          {q.isLoading ? (
            <p className="flex items-center gap-2 text-sm text-slate-600">
              <Loader2 className="h-4 w-4 animate-spin text-violet-500" />
              {t('bi.narrative.loading')}
            </p>
          ) : null}

          {q.isError ? (
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-rose-900">
              <p>{localizeUserMessage((q.error as Error)?.message) || t('bi.narrative.error')}</p>
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-2 py-1 text-xs font-medium"
                onClick={() => void q.refetch()}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                {t('bi.wow.briefingRefreshCta')}
              </button>
            </div>
          ) : null}

          {!q.isLoading && !q.isError && !q.data?.headline ? (
            <p className="text-sm text-slate-600">{t('bi.narrative.empty')}</p>
          ) : null}

          {!q.isLoading && !q.isError && q.data?.headline ? (
            <>
              <h2 className="text-sm font-semibold text-slate-900 sm:text-base">{q.data.headline}</h2>
              <ul className="mt-2 space-y-1 text-xs text-slate-700 sm:text-sm">
                {(q.data.bullets || []).slice(0, 3).map((b) => (
                  <li key={b}>• {b}</li>
                ))}
              </ul>
              {(q.data.drivers || []).length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {(q.data.drivers || []).map((d) => (
                    <button
                      key={String(d.anomaly_key || d.label)}
                      type="button"
                      onClick={() =>
                        onDriverAsk?.(
                          locale.startsWith('tr')
                            ? `${d.label || 'Metrik'} değişimini araştır (${d.delta_pct ?? ''}%)`
                            : `Investigate ${d.label || 'metric'} (${d.delta_pct ?? ''}%)`,
                          d.anomaly_key,
                        )
                      }
                      className={clsx(
                        'rounded-full border px-2.5 py-1 text-xs font-medium transition hover:-translate-y-0.5',
                        d.tone === 'bad' || d.tone === 'negative'
                          ? 'border-rose-200 bg-rose-50 text-rose-800'
                          : 'border-violet-200 bg-white text-violet-900',
                      )}
                    >
                      {d.label}
                      {d.delta_pct != null ? ` ${d.delta_pct > 0 ? '+' : ''}${d.delta_pct}%` : ''}
                    </button>
                  ))}
                </div>
              ) : onDriverAsk ? (
                <button
                  type="button"
                  className="mt-2 text-xs font-semibold text-violet-700 hover:underline"
                  onClick={() =>
                    onDriverAsk(
                      locale.startsWith('tr')
                        ? 'Bu haftanın hikayesini özetle ve dikkat edilmesi gerekenleri söyle'
                        : 'Summarize this week’s story and what needs attention',
                    )
                  }
                >
                  {t('bi.narrative.askCta')}
                </button>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
