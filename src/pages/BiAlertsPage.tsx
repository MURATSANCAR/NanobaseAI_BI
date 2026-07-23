import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, ChevronDown, Loader2, Pause, Pencil, Play, Plus, Sparkles, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import ResponsiveTable from '@/components/ResponsiveTable';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useBiChatDock } from '@/context/BiChatDockContext';
import type { BiAlertRule, BiSchemaTable } from '@/api/types';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';
import StatusBadge from '@/components/StatusBadge';
import { sortByIsoDateDesc } from '@/utils/sort';
import { ALERT_CREATE_INTENT } from '@/lib/alertChatIntent';
import { ensureNotifyPermission, showWebNotification } from '@/lib/webNotifications';
import {
  aggregateNeedsColumn,
  compileAlertRule,
  emptyAlertRule,
  isStructuredAlertRule,
  newAlertFilter,
  numericColumns,
  resolveAlertTable,
  validateAlertRule,
  type BiAlertAggregate,
  type BiAlertFilterOp,
  type BiAlertStructuredRule,
} from '@/lib/biAlertRuleBuilder';
import { formatSchemaColumnType } from '@/utils/biSchemaColumnType';

type AlertFormState = {
  id?: string;
  title: string;
  threshold: number;
  condition: string;
  status: string;
  recipient: string;
  rule: BiAlertStructuredRule;
  sql: string;
  column: string;
  channels?: BiAlertRule['channels'];
  mode: 'builder' | 'advanced';
};

const emptyForm = (): AlertFormState => ({
  title: '',
  threshold: 0,
  condition: 'lt',
  status: 'active',
  recipient: '',
  rule: emptyAlertRule(),
  sql: '',
  column: '',
  mode: 'builder',
});

const FALLBACK_ALERT_CHIP_KEYS = [
  'bi.alertChip.salesBelow',
  'bi.alertChip.stockLow',
  'bi.alertChip.overdueInvoices',
] as const;

const AGG_OPTIONS: BiAlertAggregate[] = ['count', 'sum', 'avg', 'min', 'max', 'count_distinct'];

const FILTER_OPS: BiAlertFilterOp[] = [
  'eq',
  'neq',
  'gt',
  'gte',
  'lt',
  'lte',
  'contains',
  'is_null',
  'is_not_null',
];

function conditionLabel(condition: string | undefined): string {
  if (condition === 'lt') return t('bi.alertCondLt');
  if (condition === 'eq') return t('bi.alertCondEq');
  if (condition === 'gte') return t('bi.alertCondGte');
  if (condition === 'lte') return t('bi.alertCondLte');
  if (condition === 'neq') return t('bi.alertCondNeq');
  return t('bi.alertCondGt');
}

function alertChannels(
  channels: BiAlertRule['channels'] | unknown,
): Array<{ type: string; to?: string; secret_ref?: string; url?: string }> {
  return Array.isArray(channels) ? channels : [];
}

function recipientSummary(r: BiAlertRule): string {
  const fromChannels = alertChannels(r.channels)
    .filter((c) => c.type === 'email' && c.to)
    .map((c) => String(c.to));
  if (fromChannels.length) return fromChannels.join(', ');
  return r.recipient?.trim() || t('bi.alertNotifyWebOnly');
}

function filterOpLabel(op: BiAlertFilterOp): string {
  if (op === 'contains') return t('bi.alertFilterContains');
  if (op === 'is_null') return t('bi.alertFilterIsNull');
  if (op === 'is_not_null') return t('bi.alertFilterIsNotNull');
  if (op === 'eq') return t('bi.alertCondEq');
  if (op === 'neq') return t('bi.alertCondNeq');
  if (op === 'gt') return t('bi.alertCondGt');
  if (op === 'gte') return t('bi.alertCondGte');
  if (op === 'lt') return t('bi.alertCondLt');
  return t('bi.alertCondLte');
}

function aggLabel(agg: BiAlertAggregate): string {
  if (agg === 'count') return t('bi.alertAggCount');
  if (agg === 'count_distinct') return t('bi.alertAggCountDistinct');
  if (agg === 'sum') return t('bi.alertAggSum');
  if (agg === 'avg') return t('bi.alertAggAvg');
  if (agg === 'min') return t('bi.alertAggMin');
  return t('bi.alertAggMax');
}

function formFromAlert(alert: BiAlertRule): AlertFormState {
  const hasRule = isStructuredAlertRule(alert.rule);
  return {
    id: alert.id,
    title: alert.title || '',
    threshold: alert.threshold ?? 0,
    condition: alert.condition || 'lt',
    status: alert.status || 'active',
    recipient: recipientEmails(alert),
    rule: hasRule
      ? {
          table: alert.rule!.table,
          schema: alert.rule!.schema,
          tableName: alert.rule!.tableName,
          aggregate: (alert.rule!.aggregate || 'count') as BiAlertAggregate,
          measureColumn: alert.rule!.measureColumn || '',
          filters: (alert.rule!.filters || []).map((f) =>
            newAlertFilter({
              id: f.id,
              column: f.column || '',
              op: (f.op || 'eq') as BiAlertFilterOp,
              value: f.value || '',
            }),
          ),
        }
      : emptyAlertRule(),
    sql: alert.sql || '',
    column: alert.column || '',
    channels: alert.channels,
    mode: hasRule ? 'builder' : 'advanced',
  };
}

function recipientEmails(r: BiAlertRule): string {
  const fromChannels = alertChannels(r.channels)
    .filter((c) => c.type === 'email' && c.to)
    .map((c) => String(c.to));
  if (fromChannels.length) return fromChannels.join(', ');
  return r.recipient?.trim() || '';
}

function ruleSourceSummary(r: BiAlertRule): string {
  if (isStructuredAlertRule(r.rule) && r.rule.table) {
    const agg = String(r.rule.aggregate || 'count');
    const measure =
      agg === 'count' ? 'COUNT(*)' : `${agg.toUpperCase()}(${r.rule.measureColumn || '…'})`;
    const filters = r.rule.filters?.length ? ` · ${r.rule.filters.length}` : '';
    return `${r.rule.table} · ${measure}${filters}`;
  }
  return r.sql?.trim() ? t('bi.alertSourceSql') : '—';
}

export default function BiAlertsPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const { openChat } = useBiChatDock();
  const [params, setParams] = useSearchParams();
  const [form, setForm] = useState<AlertFormState | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [tableQuery, setTableQuery] = useState('');
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

  const schemaQ = useQuery({
    queryKey: ['bi-schema', config, activeDbName],
    queryFn: () => api.bi.schema(config, activeDbName),
    enabled: isRunnerConfigured(config) && Boolean(activeDbName),
    staleTime: 60_000,
  });

  const tables = schemaQ.data?.tables ?? [];

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
      if (sql) {
        next.sql = sql;
        next.mode = 'advanced';
        setShowAdvanced(true);
      }
      if (column) next.column = column;
      if (threshold != null && threshold !== '') next.threshold = Number(threshold);
      if (condition) next.condition = condition;
      if (recipient) next.recipient = recipient;
      setForm(next);
      setParams({}, { replace: true });
    }
  }, [params, setParams]);

  const selectedTable: BiSchemaTable | undefined = useMemo(
    () => (form ? resolveAlertTable(tables, form.rule) : undefined),
    [form, tables],
  );

  const measureCols = useMemo(() => numericColumns(selectedTable), [selectedTable]);
  const allCols = selectedTable?.columns ?? [];

  const compiled = useMemo(() => {
    if (!form || form.mode !== 'builder') return null;
    return compileAlertRule(form.rule, tables);
  }, [form, tables]);

  const filteredTables = useMemo(() => {
    const q = tableQuery.trim().toLowerCase();
    if (!q) return tables.slice(0, 80);
    return tables.filter((tb) => tb.full_name.toLowerCase().includes(q) || tb.name.toLowerCase().includes(q)).slice(0, 80);
  }, [tables, tableQuery]);

  const saveMut = useMutation({
    mutationFn: (body: Partial<BiAlertRule> & { title: string; sql: string; column: string; threshold: number }) =>
      api.bi.alerts.save(config, body),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['bi-alerts'] });
      setForm(null);
      setShowAdvanced(false);
      setTableQuery('');
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
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ['bi-alerts'] });
      const triggered = Number((res as { triggered?: number } | undefined)?.triggered || 0);
      setFlash(
        triggered > 0
          ? t('bi.alertsRunTriggered', {
              checked: String((res as { checked?: number }).checked ?? 0),
              triggered: String(triggered),
            })
          : t('bi.alertsRunDone'),
      );
      if (triggered > 0) {
        showWebNotification({
          title: t('bi.notify.alertFiredTitle'),
          body: t('bi.notify.alertFiredBody', { count: String(triggered) }),
          tag: 'bi-alert-check',
        });
      }
      window.setTimeout(() => setFlash(null), 4000);
    },
    onError: (err) => setFlash(localizeUserMessage((err as Error).message)),
  });

  const askWithAi = (prompt: string) => {
    openChat({ prompt, intent: ALERT_CREATE_INTENT });
  };

  const delMut = useMutation({
    mutationFn: (id: string) => api.bi.alerts.delete(config, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-alerts'] }),
  });

  const toggleMut = useMutation({
    mutationFn: (alert: BiAlertRule) => {
      const { rule, ...rest } = alert;
      return api.bi.alerts.save(config, {
        ...rest,
        ...(isStructuredAlertRule(rule) ? { rule } : {}),
        status: alert.status === 'active' ? 'paused' : 'active',
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-alerts'] }),
  });

  const items = sortByIsoDateDesc(a.data?.alerts ?? [], (r) => r.updated_at ?? r.created_at);
  const alertChips = (alertSuggestionsQ.data?.suggestions ?? [])
    .map((s) => (s.text || '').trim())
    .filter(Boolean);
  const askPrompt =
    alertSuggestionsQ.data?.ask_prompt?.trim() || alertChips[0] || t('bi.alertsAskPrompt');

  const builderValid = form?.mode === 'builder' && !validateAlertRule(form.rule) && Boolean(compiled);
  const advancedValid =
    form?.mode === 'advanced' && Boolean(form.sql?.trim()) && Boolean(form.column?.trim());
  const canSaveManual =
    Boolean(form?.title?.trim()) && (builderValid || advancedValid) && !saveMut.isPending;

  const updateRule = (patch: Partial<BiAlertStructuredRule>) => {
    if (!form) return;
    setForm({ ...form, rule: { ...form.rule, ...patch } });
  };

  const openCreate = () => {
    setForm(emptyForm());
    setShowAdvanced(false);
    setTableQuery('');
  };

  const persistForm = async () => {
    if (!form) return;
    void ensureNotifyPermission();
    const useBuilder = form.mode === 'builder';
    const compiledSql = useBuilder ? compileAlertRule(form.rule, tables) : null;
    if (useBuilder && !compiledSql) {
      setFlash(t('bi.alertBuilderIncomplete'));
      return;
    }
    const sql = useBuilder ? compiledSql!.sql : form.sql.trim();
    const column = useBuilder ? compiledSql!.column : form.column.trim();
    const emails = form.recipient
      .split(',')
      .map((e) => e.trim())
      .filter(Boolean);
    const existing = alertChannels(form.channels);
    const channels = emails.length
      ? emails.map((to) => ({ type: 'email' as const, to }))
      : existing.filter((c) => c.type !== 'email');
    const tableMeta = resolveAlertTable(tables, form.rule);
    const rulePayload =
      useBuilder && form.rule.table
        ? {
            ...form.rule,
            schema: tableMeta?.schema,
            tableName: tableMeta?.name,
            table: tableMeta?.full_name || form.rule.table,
          }
        : null;

    saveMut.mutate({
      id: form.id,
      title: form.title.trim(),
      sql,
      column,
      threshold: Number(form.threshold) || 0,
      condition: form.condition || 'lt',
      status: form.status || 'active',
      recipient: emails.join(', ') || undefined,
      channels: channels.length ? channels : undefined,
      ...(useBuilder ? { rule: rulePayload } : { rule: null }),
    });
  };

  return (
    <PageShell pageId="biAlerts" titleKey="bi.alertsTitle" subtitleKey="bi.alertsSubtitle" maxWidth="max-w-7xl">
      <p className="mb-3 text-sm text-slate-600">{t('bi.alertCreateGuide')}</p>

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <button
          type="button"
          onClick={() => askWithAi(askPrompt)}
          className="btn-primary inline-flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
        >
          <Sparkles className="h-4 w-4" />
          {t('bi.alertsAskAi')}
        </button>
        <button type="button" className="btn-secondary min-h-11 w-full sm:w-auto" onClick={openCreate}>
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
                onClick={() => askWithAi(text)}
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
                onClick={() => askWithAi(t(key))}
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
        <div className="card mb-4 space-y-4 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-slate-800">
              {form.id ? t('bi.alertEditTitle') : t('bi.alertBuilderTitle')}
            </p>
            <div className="flex rounded-lg border border-slate-200 p-0.5 text-xs font-semibold">
              <button
                type="button"
                className={`rounded-md px-3 py-1.5 ${form.mode === 'builder' ? 'bg-sky-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
                onClick={() => setForm({ ...form, mode: 'builder' })}
              >
                {t('bi.alertModeBuilder')}
              </button>
              <button
                type="button"
                className={`rounded-md px-3 py-1.5 ${form.mode === 'advanced' ? 'bg-sky-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
                onClick={() => {
                  setForm({
                    ...form,
                    mode: 'advanced',
                    sql: compiled?.sql || form.sql,
                    column: compiled?.column || form.column || 'alert_value',
                  });
                  setShowAdvanced(true);
                }}
              >
                {t('bi.alertModeAdvanced')}
              </button>
            </div>
          </div>

          <input
            className="input-field"
            placeholder={t('bi.alertTitle')}
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />

          {form.mode === 'builder' ? (
            <>
              <section className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {t('bi.alertPickTable')}
                </label>
                {schemaQ.isLoading ? (
                  <p className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('common.loading')}
                  </p>
                ) : tables.length === 0 ? (
                  <p className="text-sm text-amber-700">{t('bi.alertNoTables')}</p>
                ) : (
                  <>
                    <input
                      className="input-field"
                      placeholder={t('bi.alertTableSearch')}
                      value={tableQuery}
                      onChange={(e) => setTableQuery(e.target.value)}
                    />
                    <select
                      className="input-field"
                      value={form.rule.table}
                      onChange={(e) => {
                        const full = e.target.value;
                        const tb = tables.find((x) => x.full_name === full);
                        updateRule({
                          table: full,
                          schema: tb?.schema,
                          tableName: tb?.name,
                          measureColumn: '',
                          filters: [],
                        });
                      }}
                    >
                      <option value="">{t('bi.alertPickTablePlaceholder')}</option>
                      {filteredTables.map((tb) => (
                        <option key={tb.full_name} value={tb.full_name}>
                          {tb.full_name}
                        </option>
                      ))}
                    </select>
                  </>
                )}
              </section>

              <section className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {t('bi.alertPickMetric')}
                  </label>
                  <select
                    className="input-field"
                    value={form.rule.aggregate}
                    disabled={!form.rule.table}
                    onChange={(e) =>
                      updateRule({
                        aggregate: e.target.value as BiAlertAggregate,
                        measureColumn:
                          e.target.value === 'count' ? '' : form.rule.measureColumn,
                      })
                    }
                  >
                    {AGG_OPTIONS.map((agg) => (
                      <option key={agg} value={agg}>
                        {aggLabel(agg)}
                      </option>
                    ))}
                  </select>
                </div>
                {aggregateNeedsColumn(form.rule.aggregate) ? (
                  <div className="space-y-2">
                    <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {t('bi.alertPickField')}
                    </label>
                    <select
                      className="input-field"
                      value={form.rule.measureColumn || ''}
                      disabled={!form.rule.table}
                      onChange={(e) => updateRule({ measureColumn: e.target.value })}
                    >
                      <option value="">{t('bi.alertPickFieldPlaceholder')}</option>
                      {(measureCols.length ? measureCols : allCols).map((col) => (
                        <option key={col.name} value={col.name}>
                          {col.name} ({formatSchemaColumnType(col)})
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <p className="self-end text-xs text-slate-500 sm:pb-3">{t('bi.alertCountRowsHint')}</p>
                )}
              </section>

              <section className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {t('bi.alertFilters')}
                  </label>
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 text-xs font-semibold text-sky-700 disabled:opacity-40"
                    disabled={!form.rule.table}
                    onClick={() =>
                      updateRule({
                        filters: [...form.rule.filters, newAlertFilter({ column: allCols[0]?.name || '' })],
                      })
                    }
                  >
                    <Plus className="h-3.5 w-3.5" />
                    {t('bi.alertAddFilter')}
                  </button>
                </div>
                {form.rule.filters.length === 0 ? (
                  <p className="text-xs text-slate-500">{t('bi.alertFiltersHint')}</p>
                ) : (
                  <div className="space-y-2">
                    {form.rule.filters.map((filter, idx) => {
                      const needsValue = filter.op !== 'is_null' && filter.op !== 'is_not_null';
                      return (
                        <div key={filter.id} className="grid gap-2 rounded-xl border border-slate-200 bg-slate-50/70 p-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
                          <select
                            className="input-field"
                            value={filter.column}
                            onChange={(e) => {
                              const filters = form.rule.filters.slice();
                              filters[idx] = { ...filter, column: e.target.value };
                              updateRule({ filters });
                            }}
                          >
                            <option value="">{t('bi.alertPickFieldPlaceholder')}</option>
                            {allCols.map((col) => (
                              <option key={col.name} value={col.name}>
                                {col.name}
                              </option>
                            ))}
                          </select>
                          <select
                            className="input-field"
                            value={filter.op}
                            onChange={(e) => {
                              const filters = form.rule.filters.slice();
                              filters[idx] = { ...filter, op: e.target.value as BiAlertFilterOp };
                              updateRule({ filters });
                            }}
                          >
                            {FILTER_OPS.map((op) => (
                              <option key={op} value={op}>
                                {filterOpLabel(op)}
                              </option>
                            ))}
                          </select>
                          {needsValue ? (
                            <input
                              className="input-field"
                              placeholder={t('bi.alertFilterValue')}
                              value={filter.value}
                              onChange={(e) => {
                                const filters = form.rule.filters.slice();
                                filters[idx] = { ...filter, value: e.target.value };
                                updateRule({ filters });
                              }}
                            />
                          ) : (
                            <span className="self-center text-xs text-slate-400">—</span>
                          )}
                          <button
                            type="button"
                            className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-status-fail"
                            aria-label={t('common.delete')}
                            onClick={() =>
                              updateRule({
                                filters: form.rule.filters.filter((f) => f.id !== filter.id),
                              })
                            }
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>

              {compiled && (
                <div className="rounded-xl border border-sky-100 bg-sky-50/60 px-3 py-2 text-xs text-sky-900">
                  <p className="font-semibold">{t('bi.alertPreviewMetric')}</p>
                  <p className="mt-0.5">{compiled.summary}</p>
                </div>
              )}
            </>
          ) : null}

          <section className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t('bi.alertWhenResult')}
              </label>
              <select
                className="input-field"
                value={form.condition}
                onChange={(e) => setForm({ ...form, condition: e.target.value })}
              >
                <option value="lt">{t('bi.alertCondLt')}</option>
                <option value="lte">{t('bi.alertCondLte')}</option>
                <option value="gt">{t('bi.alertCondGt')}</option>
                <option value="gte">{t('bi.alertCondGte')}</option>
                <option value="eq">{t('bi.alertCondEq')}</option>
                <option value="neq">{t('bi.alertCondNeq')}</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t('bi.alertThreshold')}
              </label>
              <input
                className="input-field"
                type="number"
                value={form.threshold}
                onChange={(e) => setForm({ ...form, threshold: Number(e.target.value) })}
              />
            </div>
          </section>

          <section className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {t('bi.alertNotifySection')}
            </label>
            <div className="flex items-start gap-2 rounded-xl border border-violet-100 bg-violet-50/50 px-3 py-2 text-xs text-violet-900">
              <Bell className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{t('bi.alertNotifyWebHint')}</p>
            </div>
            <input
              className="input-field"
              placeholder={t('bi.alertRecipientOptional')}
              value={form.recipient}
              onChange={(e) => setForm({ ...form, recipient: e.target.value })}
            />
          </section>

          {(form.mode === 'advanced' || showAdvanced) && (
            <>
              {form.mode === 'builder' && (
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600"
                  onClick={() => setShowAdvanced((v) => !v)}
                >
                  <ChevronDown className={`h-4 w-4 transition ${showAdvanced ? 'rotate-180' : ''}`} />
                  {t('bi.alertAdvancedSql')}
                </button>
              )}
              {(form.mode === 'advanced' || showAdvanced) && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <input
                    className="input-field"
                    placeholder={t('bi.alertColumn')}
                    value={form.mode === 'builder' ? compiled?.column || form.column : form.column}
                    onChange={(e) => setForm({ ...form, column: e.target.value, mode: 'advanced' })}
                    readOnly={form.mode === 'builder'}
                  />
                  <textarea
                    className="input-field min-h-[5.5rem] font-mono text-sm sm:col-span-2"
                    placeholder={t('bi.alertSql')}
                    value={form.mode === 'builder' ? compiled?.sql || form.sql : form.sql}
                    onChange={(e) => setForm({ ...form, sql: e.target.value, mode: 'advanced' })}
                    readOnly={form.mode === 'builder'}
                  />
                  {form.mode === 'advanced' && (
                    <p className="text-xs text-slate-500 sm:col-span-2">{t('bi.alertAdvancedHint')}</p>
                  )}
                </div>
              )}
            </>
          )}

          {form.mode === 'builder' && !showAdvanced && (
            <button
              type="button"
              className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600"
              onClick={() => setShowAdvanced(true)}
            >
              <ChevronDown className="h-4 w-4" />
              {t('bi.alertShowGeneratedSql')}
            </button>
          )}

          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-primary" disabled={!canSaveManual} onClick={() => void persistForm()}>
              {saveMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t('bi.saveAlert')}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setForm(null);
                setShowAdvanced(false);
                setTableQuery('');
              }}
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              className="btn-secondary inline-flex items-center gap-1.5"
              onClick={() => askWithAi(askPrompt)}
            >
              <Sparkles className="h-3.5 w-3.5" />
              {t('bi.alertsAskAi')}
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
            onCtaClick={() => askWithAi(askPrompt)}
          >
            <button type="button" className="btn-secondary mt-3 inline-flex items-center gap-2" onClick={openCreate}>
              {t('bi.createAlert')}
            </button>
          </EmptyState>
        ) : (
          <ResponsiveTable<BiAlertRule>
            columns={[
              { id: 'title', header: t('bi.alertTitle'), mobilePrimary: true, cell: (r) => r.title },
              {
                id: 'source',
                header: t('bi.alertSource'),
                mobileLabel: t('bi.alertSource'),
                cell: (r) => <span className="line-clamp-2 text-xs text-slate-600">{ruleSourceSummary(r)}</span>,
              },
              {
                id: 'cond',
                header: t('bi.alertCondition'),
                mobileLabel: t('bi.alertCondition'),
                cell: (r) =>
                  t('bi.alertConditionPlain', {
                    cond: conditionLabel(r.condition),
                    threshold: String(r.threshold),
                  }),
              },
              {
                id: 'recipient',
                header: t('bi.recipient'),
                mobileLabel: t('bi.recipient'),
                cell: (r) => recipientSummary(r),
              },
              {
                id: 'last',
                header: t('bi.lastValue'),
                mobileLabel: t('bi.lastValue'),
                cell: (r) => String(r.last_value ?? '—'),
              },
              {
                id: 'status',
                header: t('bi.scheduleStatus'),
                mobileLabel: t('bi.scheduleStatus'),
                cell: (r) => <StatusBadge status={r.status} />,
              },
              {
                id: 'actions',
                header: t('common.actions'),
                mobileLabel: t('common.actions'),
                cell: (r) => (
                  <div className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-accent"
                      title={t('bi.alertEditTitle')}
                      onClick={() => {
                        setForm(formFromAlert(r));
                        setShowAdvanced(!isStructuredAlertRule(r.rule));
                        setTableQuery('');
                      }}
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
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
