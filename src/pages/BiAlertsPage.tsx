import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Loader2, Pause, Play, Sparkles, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import ResponsiveTable from '@/components/ResponsiveTable';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useBiChatDock } from '@/context/BiChatDockContext';
import type { BiAlertRule } from '@/api/types';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';
import StatusBadge from '@/components/StatusBadge';
import { sortByIsoDateDesc } from '@/utils/sort';

const emptyForm = (): Partial<BiAlertRule> => ({
  title: '',
  sql: '',
  column: '',
  threshold: 0,
  condition: 'lt',
  status: 'active',
  recipient: '',
});

const FALLBACK_ALERT_CHIP_KEYS = [
  'bi.alertChip.salesBelow',
  'bi.alertChip.stockLow',
  'bi.alertChip.overdueInvoices',
] as const;

function conditionLabel(condition: string | undefined): string {
  if (condition === 'lt') return t('bi.alertCondLt');
  if (condition === 'eq') return t('bi.alertCondEq');
  if (condition === 'gte') return t('bi.alertCondGte');
  if (condition === 'lte') return t('bi.alertCondLte');
  if (condition === 'neq') return t('bi.alertCondNeq');
  return t('bi.alertCondGt');
}

function recipientSummary(r: BiAlertRule): string {
  const fromChannels = (r.channels || [])
    .filter((c) => c.type === 'email' && c.to)
    .map((c) => String(c.to));
  if (fromChannels.length) return fromChannels.join(', ');
  return r.recipient?.trim() || '—';
}

export default function BiAlertsPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const { openChat } = useBiChatDock();
  const [params, setParams] = useSearchParams();
  const [form, setForm] = useState<Partial<BiAlertRule> | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [afterSave, setAfterSave] = useState<{ title: string; recipients: string } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const a = useQuery({
    queryKey: ['bi-alerts', config],
    queryFn: () => api.bi.alerts.list(config),
    enabled: isRunnerConfigured(config),
  });

  const sourcesQ = useQuery({
    queryKey: ['bi-sources', config],
    queryFn: () => api.bi.sources.list(config),
    enabled: isRunnerConfigured(config),
    staleTime: 60_000,
  });
  const activeDbName = sourcesQ.data?.active_id || undefined;

  const alertSuggestionsQ = useQuery({
    queryKey: ['bi-alert-suggestions', config, activeDbName],
    queryFn: () =>
      api.bi.alertSuggestions(config, {
        datasourceId: activeDbName,
        limit: 3,
      }),
    enabled: isRunnerConfigured(config) && Boolean(activeDbName),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (params.get('new') === '1') {
      const next = emptyForm();
      const title = params.get('title');
      const sql = params.get('sql');
      const column = params.get('column');
      const threshold = params.get('threshold');
      const condition = params.get('condition');
      const recipient = params.get('recipient');
      if (title) next.title = title;
      if (sql) next.sql = sql;
      if (column) next.column = column;
      if (threshold != null && threshold !== '') next.threshold = Number(threshold);
      if (condition) next.condition = condition as BiAlertRule['condition'];
      if (recipient) next.recipient = recipient;
      setForm(next);
      setShowAdvanced(Boolean(sql || column));
      setParams({}, { replace: true });
    }
  }, [params, setParams]);

  const saveMut = useMutation({
    mutationFn: (body: Partial<BiAlertRule> & { title: string; sql: string; column: string; threshold: number }) =>
      api.bi.alerts.save(config, body),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['bi-alerts'] });
      setForm(null);
      setShowAdvanced(false);
      setAfterSave({
        title: vars.title,
        recipients: vars.recipient?.trim() || recipientSummary(vars as BiAlertRule),
      });
      setFlash(t('bi.alertSavedSuccess'));
      window.setTimeout(() => setFlash(null), 5000);
    },
    onError: (err) => setFlash(localizeUserMessage((err as Error).message)),
  });

  const runDueMut = useMutation({
    mutationFn: () => api.bi.alerts.runDue(config),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-alerts'] });
      setFlash(t('bi.alertsRunDone'));
      window.setTimeout(() => setFlash(null), 4000);
    },
    onError: (err) => setFlash(localizeUserMessage((err as Error).message)),
  });

  const delMut = useMutation({
    mutationFn: (id: string) => api.bi.alerts.delete(config, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-alerts'] }),
  });

  const toggleMut = useMutation({
    mutationFn: (alert: BiAlertRule) =>
      api.bi.alerts.save(config, {
        ...alert,
        status: alert.status === 'active' ? 'paused' : 'active',
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-alerts'] }),
  });

  const items = sortByIsoDateDesc(a.data?.alerts ?? [], (r) => r.updated_at ?? r.created_at);
  const alertChips = (alertSuggestionsQ.data?.suggestions ?? [])
    .map((s) => (s.text || '').trim())
    .filter(Boolean);
  const askPrompt =
    alertSuggestionsQ.data?.ask_prompt?.trim() ||
    alertChips[0] ||
    t('bi.alertsAskPrompt');
  const canSaveManual =
    Boolean(form?.title?.trim()) &&
    Boolean(form?.recipient?.trim()) &&
    Boolean(form?.sql?.trim()) &&
    Boolean(form?.column?.trim()) &&
    !saveMut.isPending;

  return (
    <PageShell pageId="biAlerts" titleKey="bi.alertsTitle" subtitleKey="bi.alertsSubtitle" maxWidth="max-w-7xl">
      <p className="mb-3 text-sm text-slate-600">{t('bi.alertCreateGuide')}</p>

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <button
          type="button"
          onClick={() => openChat({ prompt: askPrompt })}
          className="btn-primary inline-flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
        >
          <Sparkles className="h-4 w-4" />
          {t('bi.alertsAskAi')}
        </button>
        <button type="button" className="btn-secondary min-h-11 w-full sm:w-auto" onClick={() => { setForm(emptyForm()); setShowAdvanced(false); }}>
          {t('bi.createAlert')}
        </button>
        <button
          type="button"
          className="btn-secondary min-h-11 w-full sm:w-auto"
          disabled={runDueMut.isPending || !isRunnerConfigured(config)}
          onClick={() => runDueMut.mutate()}
        >
          {runDueMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {t('bi.alertsCheckNow')}
        </button>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {alertChips.length > 0
          ? alertChips.map((text) => (
              <button
                key={text}
                type="button"
                className="ai-pill max-w-full justify-start px-3 py-2 text-left text-sm normal-case tracking-normal"
                onClick={() => openChat({ prompt: text })}
              >
                <Sparkles className="h-3.5 w-3.5 shrink-0 text-violet-500" />
                <span className="line-clamp-2">{text}</span>
              </button>
            ))
          : FALLBACK_ALERT_CHIP_KEYS.map((key) => (
              <button
                key={key}
                type="button"
                className="ai-pill max-w-full justify-start px-3 py-2 text-left text-sm normal-case tracking-normal"
                onClick={() => openChat({ prompt: t(key) })}
              >
                <Sparkles className="h-3.5 w-3.5 shrink-0 text-violet-500" />
                <span className="line-clamp-2">{t(key)}</span>
              </button>
            ))}
      </div>

      {flash && <p className="mb-3 text-sm text-status-ok">{flash}</p>}

      {afterSave && (
        <div className="card mb-4 space-y-2 border-emerald-200/80 bg-emerald-50/50 p-4 text-sm text-slate-700">
          <p className="font-semibold text-emerald-900">{t('bi.alertAfterSave.title')}</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>{t('bi.alertAfterSave.what', { title: afterSave.title })}</li>
            <li>{t('bi.alertAfterSave.when')}</li>
            <li>{t('bi.alertAfterSave.who', { recipients: afterSave.recipients || '—' })}</li>
            <li>{t('bi.alertAfterSave.how')}</li>
          </ul>
          <button type="button" className="btn-secondary mt-2 text-xs" onClick={() => setAfterSave(null)}>
            {t('common.close')}
          </button>
        </div>
      )}

      {form && (
        <div className="card mb-4 grid gap-3 p-4 sm:grid-cols-2">
          <input
            className="input-field sm:col-span-2"
            placeholder={t('bi.alertTitle')}
            value={form.title ?? ''}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            className="input-field"
            type="number"
            placeholder={t('bi.alertThreshold')}
            value={form.threshold ?? 0}
            onChange={(e) => setForm({ ...form, threshold: Number(e.target.value) })}
          />
          <select
            className="input-field"
            value={form.condition ?? 'lt'}
            onChange={(e) => setForm({ ...form, condition: e.target.value })}
          >
            <option value="lt">{t('bi.alertCondLt')}</option>
            <option value="lte">{t('bi.alertCondLte')}</option>
            <option value="gt">{t('bi.alertCondGt')}</option>
            <option value="gte">{t('bi.alertCondGte')}</option>
            <option value="eq">{t('bi.alertCondEq')}</option>
            <option value="neq">{t('bi.alertCondNeq')}</option>
          </select>
          <input
            className="input-field sm:col-span-2"
            placeholder={t('bi.alertRecipientHint')}
            value={form.recipient ?? ''}
            onChange={(e) => setForm({ ...form, recipient: e.target.value })}
          />
          {!form.recipient?.trim() && (
            <p className="text-xs text-amber-700 sm:col-span-2">{t('bi.alertRecipientRequired')}</p>
          )}

          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 sm:col-span-2"
            onClick={() => setShowAdvanced((v) => !v)}
          >
            <ChevronDown className={`h-4 w-4 transition ${showAdvanced ? 'rotate-180' : ''}`} />
            {t('bi.alertAdvancedSql')}
          </button>

          {showAdvanced && (
            <>
              <input
                className="input-field"
                placeholder={t('bi.alertColumn')}
                value={form.column ?? ''}
                onChange={(e) => setForm({ ...form, column: e.target.value })}
              />
              <input
                className="input-field sm:col-span-2 font-mono text-sm"
                placeholder={t('bi.alertSql')}
                value={form.sql ?? ''}
                onChange={(e) => setForm({ ...form, sql: e.target.value })}
              />
              <p className="text-xs text-slate-500 sm:col-span-2">{t('bi.alertAdvancedHint')}</p>
            </>
          )}

          {(!form.sql?.trim() || !form.column?.trim()) && (
            <div className="rounded-xl border border-violet-200 bg-violet-50/80 p-3 text-sm text-violet-900 sm:col-span-2">
              <p>{t('bi.alertPreferAi')}</p>
              <button
                type="button"
                className="btn-primary mt-2 inline-flex items-center gap-2 text-xs"
                onClick={() => openChat({ prompt: askPrompt })}
              >
                <Sparkles className="h-3.5 w-3.5" />
                {t('bi.alertsAskAi')}
              </button>
            </div>
          )}

          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <button
              type="button"
              className="btn-primary"
              disabled={!canSaveManual}
              onClick={() => {
                const channels = form.channels?.length
                  ? form.channels
                  : form.recipient
                    ? form.recipient
                        .split(',')
                        .map((e) => e.trim())
                        .filter(Boolean)
                        .map((to) => ({ type: 'email' as const, to }))
                    : undefined;
                saveMut.mutate({
                  ...(form as BiAlertRule & { title: string; sql: string; column: string; threshold: number }),
                  channels,
                });
              }}
            >
              {saveMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t('bi.saveAlert')}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setForm(null)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      <div className="card overflow-hidden">
        {a.isLoading ? (
          <div className="flex items-center gap-2 justify-center p-10 text-sm text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin text-accent" />
            {t('common.loading')}
          </div>
        ) : a.isError ? (
          <div className="p-8 text-center">
            <p className="text-sm text-status-fail">{localizeUserMessage((a.error as Error).message)}</p>
            <button type="button" className="btn-secondary mt-4 text-sm" onClick={() => a.refetch()}>
              {t('common.retry')}
            </button>
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            emoji="🔔"
            titleKey="empty.bi.alerts.title"
            descriptionKey="empty.bi.alerts.description"
            ctaLabelKey="empty.bi.alerts.ctaAi"
            onCtaClick={() => openChat({ prompt: askPrompt })}
          >
            <button type="button" className="btn-secondary mt-3 inline-flex items-center gap-2" onClick={() => setForm(emptyForm())}>
              {t('bi.createAlert')}
            </button>
          </EmptyState>
        ) : (
          <ResponsiveTable<BiAlertRule>
            columns={[
              { id: 'title', header: t('bi.alertTitle'), mobilePrimary: true, cell: (r) => r.title },
              {
                id: 'cond',
                header: t('bi.alertCondition'),
                mobileLabel: t('bi.alertCondition'),
                cell: (r) => t('bi.alertConditionPlain', { cond: conditionLabel(r.condition), threshold: String(r.threshold) }),
              },
              {
                id: 'recipient',
                header: t('bi.recipient'),
                mobileLabel: t('bi.recipient'),
                cell: (r) => recipientSummary(r),
              },
              { id: 'last', header: t('bi.lastValue'), mobileLabel: t('bi.lastValue'), cell: (r) => String(r.last_value ?? '—') },
              { id: 'status', header: t('bi.scheduleStatus'), mobileLabel: t('bi.scheduleStatus'), cell: (r) => <StatusBadge status={r.status} /> },
              {
                id: 'actions',
                header: t('common.actions'),
                mobileLabel: t('common.actions'),
                cell: (r) => (
                  <div className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-accent"
                      title={r.status === 'active' ? t('bi.pauseAlert') : t('bi.resumeAlert')}
                      onClick={() => toggleMut.mutate(r)}
                    >
                      {r.status === 'active' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                    </button>
                    <button
                      type="button"
                      className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-status-fail"
                      onClick={() => {
                        if (window.confirm(t('bi.deleteAlertConfirm'))) delMut.mutate(r.id);
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
        )}
      </div>
    </PageShell>
  );
}
