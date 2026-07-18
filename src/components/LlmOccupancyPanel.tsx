import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Square } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api, isRunnerConfigured, type ApiConfig } from '@/api/client';
import { formatApiMessage, localizeUserMessage } from '@/utils/backendLabels';
import { t } from '@/i18n';

export type LlmLease = {
  lease_id: string;
  app?: string;
  purpose?: string;
  job_ref?: string | null;
  started_at?: string;
  status?: string;
};

export type LlmStatus = {
  llm_configured?: boolean;
  busy?: boolean;
  stopping?: boolean;
  slot?: {
    id?: number;
    id_task?: number;
    n_prompt_tokens?: number;
    n_prompt_tokens_processed?: number;
    is_processing?: boolean;
  } | null;
  slot_reachable?: boolean;
  leases?: LlmLease[];
  primary_lease_id?: string | null;
};

type Props = {
  config: ApiConfig;
};

function appLabel(app: string | undefined): string {
  const key = `settings.llm.app.${app || 'qa'}`;
  const translated = t(key);
  return translated === key ? app || 'qa' : translated;
}

function purposeLabel(purpose: string | undefined): string {
  if (!purpose) return t('settings.llm.purposeUnknown');
  const key = `settings.llm.purpose.${purpose}`;
  const translated = t(key);
  return translated === key ? purpose : translated;
}

function formatElapsed(sec: number): string {
  if (sec < 60) return t('settings.llm.elapsedSec', { n: String(sec) });
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  if (min < 60) {
    return rem > 0
      ? t('settings.llm.elapsedMinSec', { m: String(min), s: String(rem) })
      : t('settings.llm.elapsedMin', { n: String(min) });
  }
  const hr = Math.floor(min / 60);
  return t('settings.llm.elapsedHourMin', { h: String(hr), m: String(min % 60) });
}

function elapsedSeconds(iso: string | undefined, nowMs: number): number {
  if (!iso) return 0;
  const started = Date.parse(iso);
  if (!Number.isFinite(started)) return 0;
  return Math.max(0, Math.floor((nowMs - started) / 1000));
}

export default function LlmOccupancyPanel({ config }: Props) {
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const [msgTone, setMsgTone] = useState<'ok' | 'warn' | 'err'>('ok');
  const [awaitingStop, setAwaitingStop] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const status = useQuery({
    queryKey: ['llm-status', config],
    queryFn: () => api.llm.status(config) as Promise<LlmStatus>,
    enabled: isRunnerConfigured(config),
    refetchInterval: (q) => {
      const d = q.state.data;
      if (awaitingStop || d?.stopping || d?.busy) return 1500;
      return 8000;
    },
  });

  const data = status.data;
  const leases = data?.leases || [];
  const activeLeases = leases.filter((l) => (l.status || '').toLowerCase() !== 'cancelling');
  const cancellingLeases = leases.filter((l) => (l.status || '').toLowerCase() === 'cancelling');
  const primaryId = data?.primary_lease_id;
  const primary =
    leases.find((l) => l.lease_id === primaryId) ||
    activeLeases[activeLeases.length - 1] ||
    cancellingLeases[cancellingLeases.length - 1] ||
    leases[leases.length - 1];
  const busy = Boolean(data?.busy);
  const stopping = Boolean(data?.stopping) || awaitingStop || cancellingLeases.length > 0;
  const tokens = data?.slot?.n_prompt_tokens;

  useEffect(() => {
    if (!busy && !stopping) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [busy, stopping]);

  useEffect(() => {
    if (awaitingStop && data && !data.busy && !data.stopping) {
      setAwaitingStop(false);
      setMsgTone('ok');
      setMsg(t('settings.llm.cancelCleared'));
    }
  }, [awaitingStop, data]);

  const cancelMut = useMutation({
    mutationFn: () => api.llm.cancel(config, { cancel_all: true }),
    onSuccess: (res) => {
      const code = String(res?.code || 'llm_cancel_stopping');
      const still =
        Boolean((res as { stopping?: boolean; slot_still_busy?: boolean })?.stopping) ||
        Boolean((res as { slot_still_busy?: boolean })?.slot_still_busy);
      setAwaitingStop(still || code === 'llm_cancel_stopping' || code === 'llm_cancel_slot_only');
      if (still || code === 'llm_cancel_stopping') {
        setMsgTone('warn');
        setMsg(formatApiMessage(code) || t('settings.llm.cancelStopping'));
      } else {
        setMsgTone('ok');
        setMsg(formatApiMessage(code) || t('settings.llm.cancelCleared'));
      }
      void qc.invalidateQueries({ queryKey: ['llm-status', config] });
    },
    onError: (err: unknown) => {
      setAwaitingStop(false);
      setMsgTone('err');
      setMsg(localizeUserMessage(err instanceof Error ? err.message : String(err)));
    },
  });

  const phaseLabel = useMemo(() => {
    if (!data?.llm_configured) return t('settings.llm.notConfigured');
    if (stopping) return t('settings.llm.stopping');
    if (!busy) return t('settings.llm.idle');
    if (primary) return t('settings.llm.usingApp', { app: appLabel(primary.app) });
    return t('settings.llm.busyUnknown');
  }, [data?.llm_configured, busy, stopping, primary]);

  if (!isRunnerConfigured(config)) return null;

  const onCancel = () => {
    if (!window.confirm(t('settings.llm.cancelConfirm'))) return;
    setMsg(null);
    setAwaitingStop(true);
    cancelMut.mutate();
  };

  const badgeClass = stopping
    ? 'bg-amber-100 text-amber-900'
    : busy
      ? 'bg-rose-50 text-rose-800'
      : 'bg-emerald-50 text-emerald-800';
  const badgeText = stopping
    ? t('settings.llm.stopping')
    : busy
      ? t('settings.llm.busy')
      : t('settings.llm.idle');

  const extraActive = activeLeases.filter((l) => l.lease_id !== primary?.lease_id);

  return (
    <section className="card space-y-4 p-4" data-testid="llm-occupancy-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">{t('settings.llm.title')}</h3>
          <p className="mt-0.5 text-xs text-slate-500">{t('settings.llm.hint')}</p>
        </div>
        <span className={`shrink-0 rounded-md px-2.5 py-1 text-xs font-medium ${badgeClass}`}>
          {stopping ? <Loader2 className="mr-1 inline h-3 w-3 animate-spin" /> : null}
          {badgeText}
        </span>
      </div>

      {status.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('common.loading')}
        </p>
      ) : status.isError ? (
        <p className="text-sm text-rose-700">
          {localizeUserMessage(status.error instanceof Error ? status.error.message : String(status.error))}
        </p>
      ) : (
        <div className="space-y-3">
          <p className="text-sm font-medium text-slate-800">{phaseLabel}</p>

          {(busy || stopping) && primary ? (
            <div
              className={
                stopping
                  ? 'rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-3'
                  : 'rounded-lg border border-slate-200 bg-slate-50 px-3 py-3'
              }
            >
              <dl className="grid gap-2 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-slate-500">{t('settings.llm.usingAppLabel')}</dt>
                  <dd className="mt-0.5 font-medium text-slate-900">{appLabel(primary.app)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">{t('settings.llm.purpose')}</dt>
                  <dd className="mt-0.5 font-medium text-slate-900">{purposeLabel(primary.purpose)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">{t('settings.llm.elapsed')}</dt>
                  <dd className="mt-0.5 font-medium tabular-nums text-slate-900">
                    {formatElapsed(elapsedSeconds(primary.started_at, nowMs))}
                  </dd>
                </div>
                {typeof tokens === 'number' ? (
                  <div>
                    <dt className="text-slate-500">{t('settings.llm.tokens')}</dt>
                    <dd className="mt-0.5 font-medium tabular-nums text-slate-900">{tokens}</dd>
                  </div>
                ) : null}
              </dl>
              {stopping ? (
                <p className="mt-2 text-xs text-amber-900">{t('settings.llm.cancelStoppingHint')}</p>
              ) : null}
            </div>
          ) : null}

          {busy && !primary ? (
            <p className="text-xs text-slate-500">{t('settings.llm.noLease')}</p>
          ) : null}

          {extraActive.length > 0 ? (
            <div className="space-y-1">
              <p className="text-xs font-medium text-slate-500">{t('settings.llm.otherRuns')}</p>
              <ul className="space-y-1 text-xs text-slate-600">
                {extraActive.map((lease) => (
                  <li key={lease.lease_id} className="flex items-center justify-between gap-2">
                    <span>
                      {appLabel(lease.app)} · {purposeLabel(lease.purpose)} ·{' '}
                      {formatElapsed(elapsedSeconds(lease.started_at, nowMs))}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3">
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-md border border-rose-300 bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-800 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={(!busy && !stopping) || cancelMut.isPending}
          onClick={onCancel}
        >
          {cancelMut.isPending || stopping ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Square className="h-3.5 w-3.5" />
          )}
          {stopping ? t('settings.llm.cancelPending') : t('settings.llm.cancel')}
        </button>
        {msg ? (
          <span
            className={
              msgTone === 'err'
                ? 'text-xs text-rose-700'
                : msgTone === 'warn'
                  ? 'text-xs text-amber-800'
                  : 'text-xs text-emerald-700'
            }
          >
            {msg}
          </span>
        ) : null}
      </div>
    </section>
  );
}
